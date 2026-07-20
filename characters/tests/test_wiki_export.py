"""Tests for the MediaWiki export function."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from characters.microformats import parse_sheet
from characters.models import Character, Item, SageStudyPoints, Spell
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
