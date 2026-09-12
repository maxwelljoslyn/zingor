"""Tests for the building materials catalogue and its seed (#197)."""

from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from characters.building_materials import (
    CATALOGUE,
    CatalogueError,
    MaterialSeed,
    seed_catalogue,
)
from characters.models import BuildingMaterial, TradeGood, Vendor
from characters.trade import import_trade_table
from characters.units import D

BUDAPEST = (
    Path(__file__).resolve().parents[1] / "spreadsheets" / "price-table-budapest.xlsx"
)


def seed(key: str, good: str, **overrides) -> MaterialSeed:
    """A catalogue row for a mason's good, with only what a test cares about."""
    fields = {
        "key": key,
        "name": key,
        "usage": BuildingMaterial.WALL,
        "unit": BuildingMaterial.SQUARE_FEET,
        "vendor": "mason",
        "good": good,
        "per_good": "48",
        "basis": "",
    }
    fields.update(overrides)
    return MaterialSeed(**fields)


class SeedCatalogueTests(TestCase):
    def setUp(self):
        self.mason = Vendor.objects.create(name="mason")
        self.wall = TradeGood.objects.create(vendor=self.mason, name="limestone wall")

    def test_creates_a_material_pointing_at_its_good(self):
        report = seed_catalogue([seed("limestone-wall", "limestone wall")])
        self.assertEqual(report.created, ["limestone-wall"])
        material = BuildingMaterial.objects.get(key="limestone-wall")
        self.assertEqual(material.good, self.wall)
        self.assertEqual(material.units_per_good, D(48))

    def test_a_missing_good_writes_nothing_and_names_every_gap(self):
        rows = [
            seed("limestone-wall", "limestone wall"),
            seed("brick-wall", "brick wall"),
            seed("granite", "cut granite block"),
        ]
        with self.assertRaises(CatalogueError) as caught:
            seed_catalogue(rows)
        self.assertEqual(len(caught.exception.problems), 2)
        self.assertIn("brick wall", caught.exception.problems[0])
        self.assertFalse(BuildingMaterial.objects.exists())

    def test_goods_sharing_a_name_need_a_description(self):
        carpenter = Vendor.objects.create(name="carpenter")
        TradeGood.objects.create(
            vendor=carpenter, name="window frame", description="3 ft. by 18 in."
        )
        half = TradeGood.objects.create(
            vendor=carpenter, name="window frame", description="half-sized, 18 in."
        )
        with self.assertRaises(CatalogueError):
            seed_catalogue([seed("frame", "window frame", vendor="carpenter")])
        seed_catalogue(
            [
                seed(
                    "frame-half",
                    "window frame",
                    vendor="carpenter",
                    description="half-sized",
                )
            ]
        )
        self.assertEqual(BuildingMaterial.objects.get(key="frame-half").good, half)

    def test_rerun_keeps_admin_edits_unless_refreshed(self):
        rows = [seed("limestone-wall", "limestone wall")]
        seed_catalogue(rows)
        BuildingMaterial.objects.filter(key="limestone-wall").update(name="Edited")
        report = seed_catalogue(rows)
        self.assertEqual(report.unchanged, ["limestone-wall"])
        self.assertEqual(BuildingMaterial.objects.get().name, "Edited")
        report = seed_catalogue(rows, refresh=True)
        self.assertEqual(report.refreshed, ["limestone-wall"])
        self.assertEqual(BuildingMaterial.objects.get().name, "limestone-wall")


class BudapestCatalogueTests(TestCase):
    """The shipped seed against the real Budapest workbook."""

    @classmethod
    def setUpTestData(cls):
        import_trade_table(BUDAPEST, "Budapest")

    def test_every_seed_row_finds_its_good(self):
        report = seed_catalogue()
        self.assertEqual(len(report.created), len(CATALOGUE))

    def test_keys_are_unique(self):
        keys = [row.key for row in CATALOGUE]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_material_is_priced_in_budapest(self):
        from characters.models import Market

        seed_catalogue()
        market = Market.objects.get(name="Budapest")
        unpriced = [
            material.key
            for material in BuildingMaterial.objects.select_related("good")
            if material.good.current_price(market) is None
        ]
        self.assertEqual(unpriced, [])

    def test_command_reports_counts(self):
        out = StringIO()
        call_command("seed_building_materials", stdout=out)
        self.assertIn(f"{len(CATALOGUE)} materials created", out.getvalue())


class SeedCommandTests(TestCase):
    def test_fails_loudly_before_the_trade_table_is_imported(self):
        with self.assertRaises(CommandError) as caught:
            call_command("seed_building_materials", stdout=StringIO())
        self.assertIn("not in the trade table", str(caught.exception))
        self.assertFalse(BuildingMaterial.objects.exists())
