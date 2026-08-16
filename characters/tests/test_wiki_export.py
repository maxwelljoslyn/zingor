"""Tests for the MediaWiki export function."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from characters.microformats import parse_sheet
from characters.models import (
    Character,
    Item,
    SageAbilityPoints,
    SageChosenField,
    SageStudyPoints,
    Spell,
)
from characters.wiki_export import character_to_wiki

User = get_user_model()


class WikiExportTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="x")
        self.char = Character.objects.create(
            user=self.user,
            name="Aldric",
            race="human",
            sex="male",
            char_class="fighter",
            level=3,
            xp=6000,
            strength=17,
            dexterity=14,
            constitution=15,
            intelligence=10,
            wisdom=12,
            charisma=8,
            current_hp=22,
        )

    def test_identity_section_present(self):
        wiki = character_to_wiki(self.char)
        assert "== Identity ==" in wiki
        assert "Aldric" in wiki
        assert "fighter" in wiki

    def test_ability_scores_section(self):
        wiki = character_to_wiki(self.char)
        assert "== Ability Scores ==" in wiki
        assert "Strength" in wiki
        assert "17" in wiki

    def test_inventory_wikitable(self):
        Item.objects.create(owner=self.char, name="Longsword", weight="4 lb")
        wiki = character_to_wiki(self.char)
        assert "== Inventory ==" in wiki
        assert '{| class="wikitable"' in wiki
        assert "Longsword" in wiki

    def test_spells_section(self):
        Spell.objects.create(character=self.char, name="Magic Missile", level=1)
        wiki = character_to_wiki(self.char)
        assert "== Spells ==" in wiki
        assert "Magic Missile" in wiki

    def test_empty_inventory_no_table(self):
        wiki = character_to_wiki(self.char)
        assert "No items." in wiki
        assert '{| class="wikitable"' not in wiki

    def test_sage_abilities_section(self):
        SageAbilityPoints.objects.create(
            character=self.char,
            ability="Read Weather",
            source="Old sailor's mentorship",
            points=12,
        )
        wiki = character_to_wiki(self.char)
        assert "=== Standalone Abilities ===" in wiki
        assert "Read Weather" in wiki
        assert "Old sailor's mentorship" in wiki

    def test_no_sage_abilities(self):
        wiki = character_to_wiki(self.char)
        assert "No standalone sage abilities." in wiki
        assert "=== Standalone Abilities ===" not in wiki

    def test_hidden_sage_ability_omitted(self):
        SageAbilityPoints.objects.create(
            character=self.char, ability="Read Weather", points=12, hidden=True
        )
        wiki = character_to_wiki(self.char)
        assert "Read Weather" not in wiki

    def test_notes_section(self):
        self.char.background = "Born in a village."
        self.char.save()
        wiki = character_to_wiki(self.char)
        assert "== Notes ==" in wiki
        assert "Born in a village." in wiki


class WikiExportZMFTest(TestCase):
    """The export embeds Zingor microformats so an exported page round-trips
    back through microformats.parse_sheet (issue #91)."""

    def setUp(self):
        self.user = User.objects.create_user("tester", password="x")
        self.char = Character.objects.create(
            user=self.user,
            name="Aldric",
            race="human",
            sex="male",
            char_class="fighter",
            level=3,
            xp=6000,
            strength=17,
            dexterity=14,
            constitution=15,
            intelligence=10,
            wisdom=12,
            charisma=8,
            current_hp=22,
            background="Born in a village.",
        )

    def test_scalar_zmf_classes_present(self):
        wiki = character_to_wiki(self.char)
        assert 'class="zingor-name"' in wiki
        assert 'class="zingor-class"' in wiki
        assert 'class="zingor-strength"' in wiki
        assert 'class="zingor-current-hp"' in wiki

    def test_scalars_round_trip_through_parser(self):
        sheet = parse_sheet(character_to_wiki(self.char))
        assert sheet.character.name == "Aldric"
        assert sheet.character.char_class == "fighter"
        assert sheet.character.level == 3
        assert sheet.character.xp == 6000
        assert sheet.character.strength == 17
        assert sheet.character.wisdom == 12
        assert sheet.character.current_hp == 22
        assert sheet.character.background == "Born in a village."

    def test_percentile_strength_round_trips(self):
        self.char.strength = 18
        self.char.percentile_strength = 76
        self.char.save()
        sheet = parse_sheet(character_to_wiki(self.char))
        assert sheet.character.strength == 18
        assert sheet.character.percentile_strength == 76

    def test_spells_round_trip_with_level(self):
        Spell.objects.create(character=self.char, name="Magic Missile", level=1)
        Spell.objects.create(character=self.char, name="Fireball", level=3)
        sheet = parse_sheet(character_to_wiki(self.char))
        by_name = {s.name: s for s in sheet.spells}
        assert by_name["Magic Missile"].level == 1
        assert by_name["Fireball"].level == 3
        assert sheet.warnings == []

    def test_sage_study_table_carries_zmf_classes(self):
        """Sage studies use MediaWiki table-attribute syntax; MediaWiki turns
        these into <tr>/<td> classes (as on the real Lexent page), so the
        markup, not a raw-text parse, is what to assert here."""
        SageStudyPoints.objects.create(
            character=self.char, study="Divination", points=13
        )
        wiki = character_to_wiki(self.char)
        assert '|- class="zingor-sage-study"' in wiki
        assert 'class="zingor-sage-study-name" | Divination' in wiki
        assert 'class="zingor-sage-study-points" | 13' in wiki

    def test_chosen_fields_round_trip(self):
        SageChosenField.objects.create(character=self.char, field="Animal Training")
        SageChosenField.objects.create(character=self.char, field="Leadership")
        sheet = parse_sheet(character_to_wiki(self.char))
        assert [f.field for f in sheet.chosen_fields] == [
            "Animal Training",
            "Leadership",
        ]
        assert sheet.warnings == []

    def test_no_chosen_fields_emits_no_records(self):
        assert "zingor-chosen-field" not in character_to_wiki(self.char)

    def test_chosen_study_carries_a_mark_and_an_unchosen_one_does_not(self):
        """Like the other sage tables this is MediaWiki attribute syntax, only
        HTML once the page renders, so the assertion is on the markup."""
        SageStudyPoints.objects.create(
            character=self.char, study="Divination", points=13, chosen=True
        )
        SageStudyPoints.objects.create(character=self.char, study="Faith", points=4)
        rows = [
            line
            for line in character_to_wiki(self.char).splitlines()
            if 'class="zingor-sage-study-name"' in line
        ]
        divination = next(line for line in rows if "| Divination " in line)
        faith = next(line for line in rows if "| Faith " in line)
        assert divination.endswith('class="zingor-sage-study-chosen" | X')
        # The cell is always emitted so the column stays aligned; empty is an
        # absent optional subfield to the parser.
        assert faith.endswith('class="zingor-sage-study-chosen" | ')

    def test_study_in_two_of_the_characters_fields_is_exported_once(self):
        """The sheet lists such a study under both fields, but the wiki page is
        parsed back in, so a second listing would be a second record for the
        one row."""
        self.char.char_class = "paladin"
        self.char.save()
        SageChosenField.objects.create(
            character=self.char, field="Legends and Folklore"
        )
        SageStudyPoints.objects.create(character=self.char, study="Beasts", points=7)
        wiki = character_to_wiki(self.char)
        assert wiki.count('class="zingor-sage-study-name" | Beasts') == 1

    def test_area_of_concentration_rides_along_in_the_name_cell(self):
        SageStudyPoints.objects.create(
            character=self.char,
            study="History",
            concentration="Ancient European",
            points=31,
        )
        wiki = character_to_wiki(self.char)
        assert 'class="zingor-sage-study-name" | History (Ancient European)' in wiki

    def test_each_area_gets_its_own_row_under_the_one_field(self):
        """Two areas of History are two point totals, but one study, so they
        sit as two rows under a single The Church heading."""
        for area, points in [("Ancient European", 31), ("Ancient African", 6)]:
            SageStudyPoints.objects.create(
                character=self.char,
                study="History",
                concentration=area,
                points=points,
            )
        wiki = character_to_wiki(self.char)
        assert wiki.count("=== The Church ===") == 1
        assert wiki.count('|- class="zingor-sage-study"') == 2
        # Alphabetical within the study, as the rest of the table is.
        assert wiki.index("(Ancient African)") < wiki.index("(Ancient European)")

    def test_a_study_taken_whole_exports_under_its_bare_name(self):
        SageStudyPoints.objects.create(character=self.char, study="History", points=9)
        wiki = character_to_wiki(self.char)
        assert 'class="zingor-sage-study-name" | History |' in wiki

    def test_sage_ability_table_carries_zmf_classes(self):
        """Standalone abilities are exported as a table like sage studies, so
        (as there) the assertion is on the MediaWiki attribute syntax that
        becomes <tr>/<td> classes once the page renders."""
        SageAbilityPoints.objects.create(
            character=self.char,
            ability="Read Weather",
            source="Old sailor's mentorship",
            points=12,
        )
        wiki = character_to_wiki(self.char)
        assert '|- class="zingor-sage-ability"' in wiki
        assert 'class="zingor-sage-ability-name" | Read Weather' in wiki
        assert 'class="zingor-sage-ability-points" | 12' in wiki
        assert 'class="zingor-sage-ability-source" | Old sailor\'s mentorship' in wiki

    def test_sage_ability_without_source_still_carries_its_class(self):
        """The source cell is always emitted so the column stays aligned; an
        empty one is simply an absent optional subfield to the parser."""
        SageAbilityPoints.objects.create(
            character=self.char, ability="Read Weather", points=12
        )
        wiki = character_to_wiki(self.char)
        assert 'class="zingor-sage-ability-source"' in wiki
