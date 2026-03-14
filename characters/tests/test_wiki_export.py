"""Tests for the MediaWiki export function."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from characters.models import Character, Item, Spell
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
