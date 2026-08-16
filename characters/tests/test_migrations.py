"""Tests for data-migration logic that must survive real inventories."""

import importlib

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from characters.models import (
    Character,
    Item,
    SageAbilityPoints,
    SageChosenField,
    SageStudyPoints,
)
from characters.units import D

consolidation = importlib.import_module(
    "characters.migrations.0015_consolidate_duplicate_items"
)
coins_to_items = importlib.import_module("characters.migrations.0017_coins_to_items")
canonical_names = importlib.import_module(
    "characters.migrations.0030_canonical_sage_names"
)


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


class MultipleChosenSageFieldsTests(TransactionTestCase):
    """0029 carries the old single chosen field/study into the new rows.

    Unlike the migrations above, this one reads columns that no longer exist on
    the live models, so it has to run against historical model states — hence
    the executor, and TransactionTestCase to let it change the schema.
    """

    migrate_from = ("characters", "0028_character_picture")
    migrate_to = ("characters", "0029_multiple_chosen_sage_fields")

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        self.old_apps = executor.loader.project_state([self.migrate_from]).apps

    def tearDown(self):
        """Leave the database at the latest migration for whatever runs next."""
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _character(self, **kwargs):
        OldUser = self.old_apps.get_model("auth", "User")
        OldCharacter = self.old_apps.get_model("characters", "Character")
        user = OldUser.objects.create(username=f"u{OldUser.objects.count()}")
        return OldCharacter.objects.create(user=user, name="Thorn", **kwargs)

    def _migrate_forward(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])
        return executor.loader.project_state([self.migrate_to]).apps

    def test_chosen_field_becomes_a_row(self):
        character = self._character(chosen_field="Animal Training")
        new_apps = self._migrate_forward()
        SageChosenField = new_apps.get_model("characters", "SageChosenField")
        self.assertEqual(
            list(
                SageChosenField.objects.filter(character_id=character.pk).values_list(
                    "field", flat=True
                )
            ),
            ["Animal Training"],
        )

    def test_chosen_study_becomes_a_flag_on_its_existing_row(self):
        character = self._character(chosen_study="Horseback Riding")
        OldStudy = self.old_apps.get_model("characters", "SageStudyPoints")
        OldStudy.objects.create(
            character_id=character.pk, study="Horseback Riding", points=42
        )
        new_apps = self._migrate_forward()
        SageStudyPoints = new_apps.get_model("characters", "SageStudyPoints")
        row = SageStudyPoints.objects.get(
            character_id=character.pk, study="Horseback Riding"
        )
        self.assertTrue(row.chosen)
        self.assertEqual(row.points, 42)

    def test_chosen_study_without_a_points_row_gets_one(self):
        character = self._character(chosen_study="Horseback Riding")
        new_apps = self._migrate_forward()
        SageStudyPoints = new_apps.get_model("characters", "SageStudyPoints")
        row = SageStudyPoints.objects.get(
            character_id=character.pk, study="Horseback Riding"
        )
        self.assertTrue(row.chosen)
        self.assertEqual(row.points, 0)

    def test_character_with_no_choices_gains_nothing(self):
        character = self._character()
        new_apps = self._migrate_forward()
        SageChosenField = new_apps.get_model("characters", "SageChosenField")
        SageStudyPoints = new_apps.get_model("characters", "SageStudyPoints")
        self.assertFalse(
            SageChosenField.objects.filter(character_id=character.pk).exists()
        )
        self.assertFalse(
            SageStudyPoints.objects.filter(character_id=character.pk).exists()
        )


class CanonicalSageNamesTests(TestCase):
    """0030 rewrites stored sage names to the catalogue's spelling.

    It reads only columns the live models still have, so it can run against the
    real app registry rather than a historical state.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Lexent")
        self.other = Character.objects.create(user=self.user, name="Someone Else")

    def _run(self) -> None:
        canonical_names.forwards(apps, None)

    def _studies(self, character=None):
        return set(
            SageStudyPoints.objects.filter(
                character=character or self.character
            ).values_list("study", flat=True)
        )

    def test_old_spelling_is_rewritten(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Heraldry, Signs, and Sigils", points=4
        )
        self._run()
        self.assertEqual(self._studies(), {"Heraldry, Signs & Sigils"})
        self.assertEqual(SageStudyPoints.objects.get().points, 4)

    def test_american_spelling_is_rewritten(self):
        SageStudyPoints.objects.create(character=self.character, study="Leather Armor")
        self._run()
        self.assertEqual(self._studies(), {"Leather Armour"})

    def test_canonical_name_is_left_alone(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Bugs & Spiders", points=9
        )
        self._run()
        self.assertEqual(self._studies(), {"Bugs & Spiders"})
        self.assertEqual(SageStudyPoints.objects.get().points, 9)

    def test_uncatalogued_study_is_left_alone(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Nonexistent Study", points=2
        )
        self._run()
        self.assertEqual(self._studies(), {"Nonexistent Study"})

    def test_colliding_rows_merge_keeping_the_higher_points(self):
        """A hidden row from before the correction alongside the one the wiki
        resurrected: renaming outright would trip the per-character unique key."""
        SageStudyPoints.objects.create(
            character=self.character,
            study="Heraldry, Signs, and Sigils",
            points=99,
            hidden=True,
        )
        SageStudyPoints.objects.create(
            character=self.character, study="Heraldry, Signs & Sigils", points=4
        )
        self._run()
        rows = SageStudyPoints.objects.filter(character=self.character)
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertEqual(row.study, "Heraldry, Signs & Sigils")
        self.assertEqual(row.points, 99)

    def test_merged_study_stays_visible_if_either_row_was(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Bugs and Spiders", points=1, hidden=True
        )
        SageStudyPoints.objects.create(
            character=self.character, study="Bugs & Spiders", points=1, hidden=False
        )
        self._run()
        self.assertFalse(SageStudyPoints.objects.get(character=self.character).hidden)

    def test_merged_study_keeps_a_chosen_mark_from_either_row(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Bugs and Spiders", chosen=True
        )
        SageStudyPoints.objects.create(
            character=self.character, study="Bugs & Spiders", chosen=False
        )
        self._run()
        self.assertTrue(SageStudyPoints.objects.get(character=self.character).chosen)

    def test_two_stale_spellings_of_one_study_collapse(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Bugs and Spiders", points=3
        )
        SageStudyPoints.objects.create(
            character=self.character, study="bugs and spiders", points=8
        )
        self._run()
        self.assertEqual(self._studies(), {"Bugs & Spiders"})
        self.assertEqual(SageStudyPoints.objects.get().points, 8)

    def test_each_character_is_migrated_independently(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Bugs and Spiders", points=3
        )
        SageStudyPoints.objects.create(
            character=self.other, study="Bugs and Spiders", points=5
        )
        self._run()
        self.assertEqual(self._studies(), {"Bugs & Spiders"})
        self.assertEqual(self._studies(self.other), {"Bugs & Spiders"})
        self.assertEqual(SageStudyPoints.objects.count(), 2)

    def test_chosen_fields_are_rewritten(self):
        SageChosenField.objects.create(
            character=self.character, field="Legends and Folklore"
        )
        self._run()
        self.assertEqual(
            list(SageChosenField.objects.values_list("field", flat=True)),
            ["Legends & Folklore"],
        )

    def test_colliding_chosen_fields_collapse_to_one(self):
        SageChosenField.objects.create(
            character=self.character, field="Legends and Folklore"
        )
        SageChosenField.objects.create(
            character=self.character, field="Legends & Folklore"
        )
        self._run()
        self.assertEqual(
            list(SageChosenField.objects.values_list("field", flat=True)),
            ["Legends & Folklore"],
        )

    def test_standalone_abilities_are_untouched(self):
        """Abilities are freetext by design and share no namespace with the
        catalogue, so a name that happens to look like a study is left alone."""
        SageAbilityPoints.objects.create(
            character=self.character, ability="Bugs and Spiders", points=5
        )
        self._run()
        self.assertEqual(
            list(SageAbilityPoints.objects.values_list("ability", flat=True)),
            ["Bugs and Spiders"],
        )

    def test_running_twice_changes_nothing_further(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Bugs and Spiders", points=3
        )
        self._run()
        self._run()
        self.assertEqual(self._studies(), {"Bugs & Spiders"})
        self.assertEqual(SageStudyPoints.objects.get().points, 3)
