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
from characters.models import (
    Character,
    Item,
    SageAbilityPoints,
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
WIKI_URL = "https://adventure.alexissmolensk.com/index.php/Lexent"


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
