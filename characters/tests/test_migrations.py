"""Tests for data-migration logic that must survive real inventories."""

import importlib

from django.apps import apps
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from characters.models import Character, Item
from characters.units import D

consolidation = importlib.import_module(
    "characters.migrations.0015_consolidate_duplicate_items"
)
coins_to_items = importlib.import_module("characters.migrations.0017_coins_to_items")


def run_consolidation() -> None:
    """Invoke the migration's forward function against the live app registry."""
    consolidation.consolidate_duplicates(apps, None)


class ConsolidateDuplicateItemsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def _torch(self, **overrides) -> Item:
        defaults = {"owner": self.character, "name": "Torch", "weight": "1.5 lb"}
        defaults.update(overrides)
        return Item.objects.create(**defaults)

    def test_exact_duplicates_merge_into_one_stack(self):
        for _ in range(3):
            self._torch()
        run_consolidation()
        torches = Item.objects.filter(name="Torch")
        self.assertEqual(torches.count(), 1)
        self.assertEqual(torches.get().quantity, 3)

    def test_merge_sums_existing_quantities(self):
        self._torch(quantity=2)
        self._torch(quantity=5)
        run_consolidation()
        self.assertEqual(Item.objects.get(name="Torch").quantity, 7)

    def test_different_weight_not_merged(self):
        self._torch()
        self._torch(weight="2 lb")
        run_consolidation()
        self.assertEqual(Item.objects.filter(name="Torch").count(), 2)

    def test_different_flags_not_merged(self):
        self._torch()
        self._torch(is_carried=False)
        self._torch(is_worn=True)
        run_consolidation()
        self.assertEqual(Item.objects.filter(name="Torch").count(), 3)

    def test_different_owner_not_merged(self):
        other = Character.objects.create(user=self.user, name="Blossom")
        self._torch()
        self._torch(owner=other)
        run_consolidation()
        self.assertEqual(Item.objects.filter(name="Torch").count(), 2)

    def test_different_container_not_merged(self):
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", is_container=True
        )
        self._torch()
        self._torch(container=backpack)
        run_consolidation()
        self.assertEqual(Item.objects.filter(name="Torch").count(), 2)

    def test_same_container_duplicates_merge(self):
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", is_container=True
        )
        self._torch(container=backpack)
        self._torch(container=backpack)
        run_consolidation()
        merged = Item.objects.get(name="Torch")
        self.assertEqual(merged.quantity, 2)
        self.assertEqual(merged.container, backpack)

    def test_containers_never_merge(self):
        for _ in range(2):
            Item.objects.create(
                owner=self.character, name="Sack", weight="0.08 lb", is_container=True
            )
        run_consolidation()
        self.assertEqual(Item.objects.filter(name="Sack").count(), 2)

    def test_row_with_contents_never_merges(self):
        """A row holding contents keeps its identity even if is_container is False."""
        holder = self._torch()
        Item.objects.create(owner=self.character, name="Tinder", container=holder)
        self._torch()
        run_consolidation()
        self.assertEqual(Item.objects.filter(name="Torch").count(), 2)

    def test_different_props_not_merged(self):
        self._torch(props={"percent_left": 50})
        self._torch()
        run_consolidation()
        self.assertEqual(Item.objects.filter(name="Torch").count(), 2)


class WholeCoinsTests(SimpleTestCase):
    """The coin migration's exact decomposition of fractional amounts.

    Campaign rates: 1 gp = 16 sp, 1 sp = 12 cp. Prod held 13.75 sp, which is
    exactly 13 sp + 9 cp — fractions cascade into smaller coins, and any
    remainder below one copper is simply discarded.
    """

    def _whole(self, gp, sp, cp):
        return coins_to_items.whole_coins(D(str(gp)), D(str(sp)), D(str(cp)))

    def test_whole_amounts_pass_through(self):
        counts = self._whole(670, 224, 227)
        self.assertEqual(counts, {"gp": 670, "sp": 224, "cp": 227})

    def test_fractional_sp_cascades_to_cp(self):
        counts = self._whole(0, "13.75", 0)
        self.assertEqual(counts, {"gp": 0, "sp": 13, "cp": 9})

    def test_fractional_gp_cascades_to_sp(self):
        counts = self._whole("2.5", 0, 0)
        self.assertEqual(counts, {"gp": 2, "sp": 8, "cp": 0})

    def test_cascade_through_both_denominations(self):
        counts = self._whole("1.5", "0.5", 3)
        self.assertEqual(counts, {"gp": 1, "sp": 8, "cp": 9})

    def test_sub_copper_remainder_discarded(self):
        self.assertEqual(self._whole(0, 0, "0.4"), {"gp": 0, "sp": 0, "cp": 0})
        self.assertEqual(self._whole(0, "0.03125", 0), {"gp": 0, "sp": 0, "cp": 0})
        self.assertEqual(self._whole(0, "13.8", 0), {"gp": 0, "sp": 13, "cp": 9})

    def test_large_amounts_do_not_lose_precision(self):
        """The app's global Decimal prec is 4; the helper must not inherit it."""
        counts = self._whole(0, "999.75", 999)
        self.assertEqual(counts, {"gp": 0, "sp": 999, "cp": 1008})

    def test_negative_amounts_abort(self):
        with self.assertRaises(ValueError):
            self._whole(0, "-1", 0)
