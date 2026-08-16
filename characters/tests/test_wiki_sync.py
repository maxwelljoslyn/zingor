"""Tests for wiki_sync: applying parsed ZMF to a Character row.

``fetch_page`` is monkeypatched to return the local ``lexent.html`` fixture, so
no network is touched.
"""

from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from characters import wiki_sync
from characters.limits import MAX_SYNC_WARNINGS
from characters.models import (
    Character,
    Item,
    SageAbilityPoints,
    SageChosenField,
    SageStudyPoints,
    Spell,
)

LEXENT_HTML = (Path(__file__).parent / "data" / "lexent.html").read_text()
# Lexent's real page has no zingor-spell-level, so its spells are skipped (level
# is required). Inject one so the spell-write path can be exercised.
LEXENT_HTML_WITH_SPELL_LEVELS = LEXENT_HTML.replace(
    '<td class="zingor-spell-memorized">X</td>',
    '<td class="zingor-spell-memorized">X</td>'
    + '<td class="zingor-spell-level">1</td>',
)
SAGE_ABILITY_MARKUP = "".join(
    [
        '<tr class="zingor-sage-ability">',
        '<td class="zingor-sage-ability-name">Read Weather</td>',
        '<td class="zingor-sage-ability-points">12</td>',
        '<td class="zingor-sage-ability-source">Old sailor</td>',
        "</tr>",
    ]
)
LEXENT_HTML_WITH_SAGE_ABILITY = LEXENT_HTML.replace(
    "</body>", SAGE_ABILITY_MARKUP + "</body>"
)
CHOSEN_FIELD_MARKUP = "".join(
    [
        '<li class="zingor-chosen-field">',
        '<span class="zingor-chosen-field-name">Animal Training</span>',
        "</li>",
        '<li class="zingor-chosen-field">',
        '<span class="zingor-chosen-field-name">Leadership</span>',
        "</li>",
    ]
)
LEXENT_HTML_WITH_CHOSEN_FIELDS = LEXENT_HTML.replace(
    "</body>", CHOSEN_FIELD_MARKUP + "</body>"
)
WIKI_URL = "https://adventure.alexissmolensk.com/index.php/Lexent"


def _with_study(name: str, points: int = 3) -> str:
    """Lexent's page with one extra sage study, named as the caller wants.

    The fixture's own sage table is plain wiki markup with no zingor-* classes,
    so the parser never sees it; a study has to be injected to be parsed.
    """
    row = "".join(
        [
            '<tr class="zingor-sage-study">',
            f'<td class="zingor-sage-study-name">{name}</td>',
            f'<td class="zingor-sage-study-points">{points}</td>',
            "</tr>",
        ]
    )
    return LEXENT_HTML.replace("</body>", row + "</body>")


class SyncCharacterFromWikiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="joey", password="pw")
        self.character = Character.objects.create(
            user=self.user, name="Lexent", wiki_url=WIKI_URL
        )
        patcher = mock.patch.object(wiki_sync, "fetch_page", return_value=LEXENT_HTML)
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)

    def test_scalar_fields_are_written(self):
        wiki_sync.sync_character_from_wiki(self.character)
        self.character.refresh_from_db()
        self.assertEqual(self.character.name, "Lexent Povarov")
        self.assertEqual(self.character.level, 5)
        self.assertEqual(self.character.xp, 13414)
        self.assertEqual(self.character.strength, 14)
        self.assertEqual(self.character.current_hp, 12)

    def test_fetch_uses_the_characters_wiki_url(self):
        wiki_sync.sync_character_from_wiki(self.character)
        self.fetch.assert_called_once_with(WIKI_URL)

    def test_sage_studies_are_written(self):
        wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.sage_studies.count(), 5)

    def test_sage_abilities_are_written(self):
        with mock.patch.object(
            wiki_sync, "fetch_page", return_value=LEXENT_HTML_WITH_SAGE_ABILITY
        ):
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.sage_abilities.count(), 1)
        ability = self.character.sage_abilities.first()
        self.assertEqual(ability.ability, "Read Weather")
        self.assertEqual(ability.points, 12)
        self.assertEqual(ability.source, "Old sailor")

    def test_spells_are_written(self):
        with mock.patch.object(
            wiki_sync, "fetch_page", return_value=LEXENT_HTML_WITH_SPELL_LEVELS
        ):
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.spells.count(), 4)

    def test_pk_is_preserved(self):
        original_pk = self.character.pk
        wiki_sync.sync_character_from_wiki(self.character)
        self.character.refresh_from_db()
        self.assertEqual(self.character.pk, original_pk)

    def test_inventory_is_untouched(self):
        Item.objects.create(owner=self.character, name="Torch")
        wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.inventory.count(), 1)
        self.assertEqual(self.character.inventory.first().name, "Torch")

    def test_sync_is_idempotent(self):
        """Replace-all collections don't accumulate duplicates across runs."""
        with mock.patch.object(
            wiki_sync, "fetch_page", return_value=LEXENT_HTML_WITH_SPELL_LEVELS
        ):
            wiki_sync.sync_character_from_wiki(self.character)
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.spells.count(), 4)
        self.assertEqual(self.character.sage_studies.count(), 5)

    def test_absent_scalar_does_not_nuke_existing_value(self):
        """A field missing from the wiki keeps its current DB value."""
        html_without_hp = LEXENT_HTML.replace("zingor-current-hp", "zingor-absent-hp")
        self.character.current_hp = 7
        self.character.save()
        with mock.patch.object(wiki_sync, "fetch_page", return_value=html_without_hp):
            wiki_sync.sync_character_from_wiki(self.character)
        self.character.refresh_from_db()
        self.assertEqual(self.character.current_hp, 7)

    def test_absent_sage_section_does_not_wipe_existing_studies(self):
        """A page with no sage-study markup leaves the DB's studies alone."""
        SageStudyPoints.objects.create(
            character=self.character, study="Faith", points=27
        )
        html_without_sage = LEXENT_HTML.replace(
            "zingor-sage-study", "zingor-absent-sage-study"
        )
        with mock.patch.object(wiki_sync, "fetch_page", return_value=html_without_sage):
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.sage_studies.count(), 1)
        self.assertEqual(self.character.sage_studies.first().study, "Faith")

    def test_chosen_fields_are_written(self):
        with mock.patch.object(
            wiki_sync, "fetch_page", return_value=LEXENT_HTML_WITH_CHOSEN_FIELDS
        ):
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(
            list(self.character.chosen_fields.values_list("field", flat=True)),
            ["Animal Training", "Leadership"],
        )

    def test_absent_chosen_field_section_does_not_wipe_existing_choices(self):
        """A page with no chosen-field markup leaves the DB's choices alone."""
        SageChosenField.objects.create(character=self.character, field="Wilderland")
        wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.chosen_fields.count(), 1)
        self.assertEqual(self.character.chosen_fields.first().field, "Wilderland")

    def test_study_listed_under_two_fields_becomes_one_row(self):
        """A hand-written page may repeat a study under each field heading it
        belongs to; the per-character unique key means the first listing wins."""
        repeated = "".join(
            [
                '<tr class="zingor-sage-study">',
                '<td class="zingor-sage-study-name">Beasts</td>',
                '<td class="zingor-sage-study-points">7</td>',
                "</tr>",
            ]
        )
        html = LEXENT_HTML.replace("</body>", repeated + repeated + "</body>")
        with mock.patch.object(wiki_sync, "fetch_page", return_value=html):
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.sage_studies.filter(study="Beasts").count(), 1)

    def test_wiki_spelling_is_stored_under_the_catalogue_name(self):
        """A page written before the name corrections says "Heraldry, Signs,
        and Sigils"; the row must land on the catalogue's spelling so it groups
        under The Church rather than "Other"."""
        with mock.patch.object(
            wiki_sync,
            "fetch_page",
            return_value=_with_study("Heraldry, Signs, and Sigils"),
        ):
            wiki_sync.sync_character_from_wiki(self.character)
        stored = set(self.character.sage_studies.values_list("study", flat=True))
        self.assertIn("Heraldry, Signs & Sigils", stored)
        self.assertNotIn("Heraldry, Signs, and Sigils", stored)

    def test_rewritten_name_is_reported_as_a_warning(self):
        with mock.patch.object(
            wiki_sync,
            "fetch_page",
            return_value=_with_study("Heraldry, Signs, and Sigils"),
        ):
            warnings = wiki_sync.sync_character_from_wiki(self.character)
        self.assertTrue(
            any("Heraldry, Signs, and Sigils" in w for w in warnings),
            f"no warning naming the page's spelling: {warnings}",
        )

    def test_unknown_study_keeps_the_pages_spelling(self):
        """Studies are freetext; one that matches no catalogue entry is stored
        as written rather than dropped."""
        with mock.patch.object(
            wiki_sync, "fetch_page", return_value=_with_study("Nonexistent Study")
        ):
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertTrue(
            self.character.sage_studies.filter(study="Nonexistent Study").exists()
        )

    def test_hidden_row_in_the_old_spelling_still_blocks_the_wiki(self):
        """The suppression matches on name, so a hidden row saved before the
        corrections must not let the page's new spelling resurrect it."""
        SageStudyPoints.objects.create(
            character=self.character,
            study="Heraldry, Signs, and Sigils",
            points=99,
            hidden=True,
        )
        with mock.patch.object(
            wiki_sync,
            "fetch_page",
            return_value=_with_study("Heraldry, Signs & Sigils"),
        ):
            wiki_sync.sync_character_from_wiki(self.character)
        rows = self.character.sage_studies.filter(
            study__in=["Heraldry, Signs & Sigils", "Heraldry, Signs, and Sigils"]
        )
        self.assertEqual(rows.count(), 1)
        self.assertTrue(rows.first().hidden)
        self.assertEqual(rows.first().points, 99)

    def test_chosen_field_is_stored_under_the_catalogue_name(self):
        markup = "".join(
            [
                '<li class="zingor-chosen-field">',
                '<span class="zingor-chosen-field-name">Legends and Folklore</span>',
                "</li>",
            ]
        )
        html = LEXENT_HTML.replace("</body>", markup + "</body>")
        with mock.patch.object(wiki_sync, "fetch_page", return_value=html):
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(
            list(self.character.chosen_fields.values_list("field", flat=True)),
            ["Legends & Folklore"],
        )

    def test_absent_sage_ability_section_does_not_wipe_existing_abilities(self):
        """A page with no sage-ability markup leaves the DB's abilities alone."""
        SageAbilityPoints.objects.create(
            character=self.character, ability="Read Weather", points=12
        )
        wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.sage_abilities.count(), 1)
        self.assertEqual(self.character.sage_abilities.first().ability, "Read Weather")

    def test_hidden_sage_ability_is_preserved_across_sync(self):
        """A soft-deleted (hidden) ability keeps its row and points, and the wiki
        can't resurrect it."""
        SageAbilityPoints.objects.create(
            character=self.character,
            ability="Read Weather",
            points=99,
            hidden=True,
        )
        with mock.patch.object(
            wiki_sync, "fetch_page", return_value=LEXENT_HTML_WITH_SAGE_ABILITY
        ):
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.sage_abilities.count(), 1)
        preserved = self.character.sage_abilities.first()
        self.assertEqual(preserved.ability, "Read Weather")
        self.assertEqual(preserved.points, 99)
        self.assertTrue(preserved.hidden)

    def test_absent_spell_section_does_not_wipe_existing_spells(self):
        """A page with no spell markup leaves the DB's spells alone."""
        Spell.objects.create(character=self.character, name="Light", level=1)
        html_without_spells = LEXENT_HTML.replace("zingor-spell", "zingor-absent-spell")
        with mock.patch.object(
            wiki_sync, "fetch_page", return_value=html_without_spells
        ):
            wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.spells.count(), 1)
        self.assertEqual(self.character.spells.first().name, "Light")

    def test_present_but_unparseable_section_still_wipes(self):
        """A present section whose rows all fail to parse is an authoritative wipe.

        Lexent's spells lack zingor-spell-level, so every row is skipped, but the
        section is present — the existing spell should be deleted.
        """
        Spell.objects.create(character=self.character, name="Light", level=1)
        wiki_sync.sync_character_from_wiki(self.character)
        self.assertEqual(self.character.spells.count(), 0)


class SyncWarningStorageTests(TestCase):
    """The last run's warnings are kept on the row for the sheet to show."""

    def setUp(self):
        self.user = User.objects.create_user(username="joey", password="pw")
        self.character = Character.objects.create(
            user=self.user, name="Lexent", wiki_url=WIKI_URL
        )

    def _sync(self, html):
        with mock.patch.object(wiki_sync, "fetch_page", return_value=html):
            return wiki_sync.sync_character_from_wiki(self.character)

    def test_warnings_are_stored_and_dated(self):
        """Lexent's spells have no level, so each one warns."""
        returned = self._sync(LEXENT_HTML)
        self.character.refresh_from_db()
        self.assertTrue(returned)
        self.assertEqual(self.character.sync_warnings, returned)
        self.assertIsNotNone(self.character.last_synced_at)

    def test_a_clean_page_stores_no_warnings(self):
        html = LEXENT_HTML.replace("zingor-spell", "zingor-absent-spell")
        self._sync(html)
        self.character.refresh_from_db()
        self.assertEqual(self.character.sync_warnings, [])
        self.assertIsNotNone(self.character.last_synced_at)

    def test_a_later_clean_sync_clears_earlier_warnings(self):
        """The stored list describes the page as it stands, not a history."""
        self._sync(LEXENT_HTML)
        self.character.refresh_from_db()
        self.assertTrue(self.character.sync_warnings)
        self._sync(LEXENT_HTML.replace("zingor-spell", "zingor-absent-spell"))
        self.character.refresh_from_db()
        self.assertEqual(self.character.sync_warnings, [])

    def test_long_warning_lists_are_capped_with_a_count(self):
        broken = '<tr class="zingor-sage-study"><td class="zingor-sage-study-name">X</td></tr>'
        html = LEXENT_HTML.replace(
            "</body>", broken * (MAX_SYNC_WARNINGS + 5) + "</body>"
        )
        self._sync(html)
        self.character.refresh_from_db()
        self.assertEqual(len(self.character.sync_warnings), MAX_SYNC_WARNINGS + 1)
        self.assertIn("more warnings not shown", self.character.sync_warnings[-1])


class CapWarningsTests(TestCase):
    def test_a_short_list_passes_through_unchanged(self):
        warnings = ["one", "two"]
        self.assertEqual(wiki_sync.cap_warnings(warnings), warnings)

    def test_a_list_at_the_limit_is_not_annotated(self):
        warnings = [f"w{n}" for n in range(MAX_SYNC_WARNINGS)]
        self.assertEqual(wiki_sync.cap_warnings(warnings), warnings)

    def test_an_over_long_list_is_trimmed_and_counted(self):
        warnings = [f"w{n}" for n in range(MAX_SYNC_WARNINGS + 3)]
        capped = wiki_sync.cap_warnings(warnings)
        self.assertEqual(capped[:MAX_SYNC_WARNINGS], warnings[:MAX_SYNC_WARNINGS])
        self.assertEqual(capped[-1], "and 3 more warnings not shown")


class SyncWikiCommandTests(TestCase):
    """The sync_wiki command processes only wiki-synced characters."""

    def setUp(self):
        self.user = User.objects.create_user(username="joey", password="pw")

    def test_only_enabled_characters_with_url_are_synced(self):
        synced = Character.objects.create(
            user=self.user, name="On", wiki_url=WIKI_URL, sync_from_wiki=True
        )
        flag_off = Character.objects.create(
            user=self.user, name="FlagOff", wiki_url=WIKI_URL, sync_from_wiki=False
        )
        with mock.patch.object(
            wiki_sync, "fetch_page", return_value=LEXENT_HTML
        ) as fetch:
            call_command("sync_wiki", stdout=StringIO())
        fetch.assert_called_once_with(WIKI_URL)
        synced.refresh_from_db()
        self.assertEqual(synced.name, "Lexent Povarov")
        flag_off.refresh_from_db()
        self.assertEqual(flag_off.name, "FlagOff")

    def test_reports_when_no_characters_enabled(self):
        out = StringIO()
        call_command("sync_wiki", stdout=out)
        self.assertIn("No characters have wiki sync enabled", out.getvalue())
