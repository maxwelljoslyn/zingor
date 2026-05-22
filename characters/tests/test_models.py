"""Tests for the models."""

from django.contrib.auth.models import User
from django.test import TestCase

from characters.models import Character, Condition, HitDie, Item, Spell
from characters.units import D


class CharacterModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_create_empty_character(self):
        """A character with just name should have all other fields None."""
        c = self.character
        self.assertEqual(c.name, "Thorn")
        self.assertIsNone(c.race)
        self.assertIsNone(c.sex)
        self.assertIsNone(c.char_class)
        self.assertIsNone(c.level)
        self.assertIsNone(c.strength)
        self.assertIsNone(c.dexterity)
        self.assertIsNone(c.constitution)
        self.assertIsNone(c.intelligence)
        self.assertIsNone(c.wisdom)
        self.assertIsNone(c.charisma)
        self.assertIsNone(c.current_hp)
        self.assertIsNone(c.height)
        self.assertIsNone(c.weight)

    def test_ability_score_with_no_conditions(self):
        self.character.strength = 15
        self.character.save()
        self.assertEqual(self.character.current_ability_score("strength"), 15)

    def test_ability_score_with_condition(self):
        self.character.strength = 15
        self.character.save()
        Condition.objects.create(
            character=self.character,
            modifier_type="ability",
            target="strength",
            value=2,
            source="Bull's Strength",
        )
        self.assertEqual(self.character.current_ability_score("strength"), 17)

    def test_ability_score_none_returns_none(self):
        self.assertIsNone(self.character.current_ability_score("strength"))

    def test_maximum_hp_with_hit_dice(self):
        HitDie.objects.create(
            character=self.character, level=1, die_type="d10", roll=8, con_bonus=1
        )
        HitDie.objects.create(
            character=self.character, level=2, die_type="d10", roll=6, con_bonus=1
        )
        self.assertEqual(self.character.maximum_hp, 16)

    def test_maximum_hp_no_dice(self):
        self.assertIsNone(self.character.maximum_hp)


class ItemModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_item_weight(self):
        item = Item.objects.create(owner=self.character, name="Sword", weight="3 lb")
        self.assertEqual(item.adjusted_weight.magnitude, D(3))

    def test_container_weight(self):
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", weight="2 lb"
        )
        Item.objects.create(
            owner=self.character,
            name="Rope",
            weight="5 lb",
            container=backpack,
        )
        total = backpack.total_weight
        self.assertEqual(total.magnitude, D(7))

    def test_percent_left(self):
        item = Item.objects.create(
            owner=self.character,
            name="Torch",
            weight="1 lb",
            props={"percent_left": 50},
        )
        self.assertEqual(item.adjusted_weight.magnitude, D("0.50"))


class SpellModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Wizard")

    def test_create_spell(self):
        spell = Spell.objects.create(
            character=self.character, name="Magic Missile", level=1
        )
        self.assertEqual(spell.name, "Magic Missile")
        self.assertEqual(spell.level, 1)

    def test_duplicate_spell_rejected(self):
        Spell.objects.create(character=self.character, name="Magic Missile", level=1)
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Spell.objects.create(
                character=self.character, name="Magic Missile", level=1
            )
