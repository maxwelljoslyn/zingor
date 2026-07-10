"""Tests for the models."""

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from characters.models import (
    BonusHitPoints,
    Character,
    Condition,
    HitDie,
    Item,
    Spell,
)
from characters.units import D, u


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

    def test_maximum_hp_includes_bonus_hp(self):
        HitDie.objects.create(
            character=self.character, level=1, die_type="d10", roll=8, con_bonus=1
        )
        BonusHitPoints.objects.create(
            character=self.character, amount=3, note="soldier at arms"
        )
        BonusHitPoints.objects.create(
            character=self.character, amount=2, note="blessing"
        )
        self.assertEqual(self.character.maximum_hp, 14)

    def test_maximum_hp_bonus_only(self):
        BonusHitPoints.objects.create(
            character=self.character, amount=5, note="soldier at arms"
        )
        self.assertEqual(self.character.maximum_hp, 5)


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

    def test_total_weight_oz_normalizes_mixed_units(self):
        """Sort key converts container + contents to a single unit (oz)."""
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", weight="1 lb"
        )
        Item.objects.create(
            owner=self.character, name="Flask", weight="8 oz", container=backpack
        )
        self.assertEqual(backpack.total_weight_oz, D(24))

    def test_total_weight_oz_plain_item(self):
        """For a non-container, total weight is just its own weight."""
        sword = Item.objects.create(owner=self.character, name="Sword", weight="3 lb")
        self.assertEqual(sword.total_weight_oz, D(48))

    def test_carried_weight_skips_uncarried_contents(self):
        """A not-carried item inside a container is excluded from carried_weight."""
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", weight="2 lb"
        )
        Item.objects.create(
            owner=self.character, name="Rope", weight="5 lb", container=backpack
        )
        Item.objects.create(
            owner=self.character,
            name="Anvil",
            weight="50 lb",
            container=backpack,
            is_carried=False,
        )
        self.assertEqual(backpack.total_weight.magnitude, D(57))
        self.assertEqual(backpack.carried_weight.magnitude, D(7))

    def test_encumbrance_excludes_uncarried_nested_items(self):
        """Encumbrance treats nested and top-level not-carried items alike."""
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", weight="2 lb"
        )
        Item.objects.create(
            owner=self.character,
            name="Anvil",
            weight="50 lb",
            container=backpack,
            is_carried=False,
        )
        self.assertEqual(
            self.character.weight_of_carried_items.to("lb").magnitude, D(2)
        )

    def test_percent_left(self):
        item = Item.objects.create(
            owner=self.character,
            name="Torch",
            weight="1 lb",
            props={"percent_left": 50},
        )
        self.assertEqual(item.adjusted_weight.magnitude, D("0.50"))

    def test_quantity_defaults_to_one(self):
        item = Item.objects.create(owner=self.character, name="Sword", weight="3 lb")
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.adjusted_weight.magnitude, D(3))

    def test_quantity_multiplies_weight(self):
        """A stack's weight is per-unit weight times quantity."""
        item = Item.objects.create(
            owner=self.character, name="Torch", weight="1.5 lb", quantity=4
        )
        self.assertEqual(item.adjusted_weight.magnitude, D(6))

    def test_quantity_with_percent_left(self):
        """percent_left scales the whole stack's weight."""
        item = Item.objects.create(
            owner=self.character,
            name="Lamp oil",
            weight="1 lb",
            quantity=4,
            props={"percent_left": 50},
        )
        self.assertEqual(item.adjusted_weight.magnitude, D(2))

    def test_stacked_contents_count_in_container_weight(self):
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", weight="2 lb"
        )
        Item.objects.create(
            owner=self.character,
            name="Rope",
            weight="5 lb",
            quantity=2,
            container=backpack,
        )
        self.assertEqual(backpack.total_weight.magnitude, D(12))
        self.assertEqual(backpack.carried_weight.magnitude, D(12))

    def test_quantity_must_be_at_least_one(self):
        with self.assertRaises(IntegrityError):
            Item.objects.create(
                owner=self.character, name="Ghost", weight="1 lb", quantity=0
            )

    def test_container_quantity_must_be_one(self):
        """Containers are individuals: contents point at one row, so no stacks."""
        with self.assertRaises(IntegrityError):
            Item.objects.create(
                owner=self.character,
                name="Sacks",
                weight="1 lb",
                quantity=6,
                is_container=True,
            )


class MoneyItemTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def _coins(self, currency, quantity, **overrides):
        defaults = {
            "owner": self.character,
            "name": f"{currency} coins",
            "weight": None,
            "currency": currency,
            "quantity": quantity,
        }
        defaults.update(overrides)
        return Item.objects.create(**defaults)

    def test_money_weight_is_derived_from_coin_exchange(self):
        """40 gold at 0.4 oz each weighs a pound, no stored weight involved."""
        coins = self._coins("gp", 40)
        self.assertEqual(coins.adjusted_weight.to(u.oz).magnitude, D(16))

    def test_each_currency_has_its_own_coin_weight(self):
        self.assertEqual(self._coins("sp", 10).adjusted_weight.to(u.oz).magnitude, D(6))
        self.assertEqual(self._coins("cp", 10).adjusted_weight.to(u.oz).magnitude, D(8))

    def test_money_cannot_store_a_weight(self):
        with self.assertRaises(IntegrityError):
            self._coins("gp", 40, weight="5 lb")

    def test_money_cannot_be_a_container(self):
        with self.assertRaises(IntegrityError):
            self._coins("gp", 40, is_container=True)

    def test_character_coin_totals_are_derived_from_items(self):
        self._coins("gp", 40)
        self._coins("gp", 10, name="stash", is_carried=False)
        self._coins("sp", 7)
        self.assertEqual(self.character.gp, D(50) * u.gp)
        self.assertEqual(self.character.sp, D(7) * u.sp)
        self.assertEqual(self.character.cp, D(0) * u.cp)

    def test_money_total_converts_currencies(self):
        self._coins("gp", 1)
        self._coins("sp", 2)
        self._coins("cp", 5)
        self.assertEqual(self.character.money.to(u.cp).magnitude, D(255))

    def test_carried_coins_count_toward_encumbrance(self):
        self._coins("gp", 40)
        self.assertEqual(self.character.current_encumbrance.to(u.oz).magnitude, D(16))

    def test_stashed_coins_do_not_count_toward_encumbrance(self):
        self._coins("gp", 40, is_carried=False)
        self.assertEqual(self.character.current_encumbrance.to(u.oz).magnitude, D(0))

    def test_coins_in_uncarried_container_do_not_count(self):
        chest = Item.objects.create(
            owner=self.character, name="Chest", weight="10 lb", is_carried=False
        )
        self._coins("gp", 40, container=chest)
        self.assertEqual(self.character.current_encumbrance.to(u.oz).magnitude, D(0))


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
