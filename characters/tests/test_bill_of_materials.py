"""Tests for a building design's bill of materials and its cost (#197).

Every expected quantity is worked by hand in the test's docstring or comment.
"""

import math
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from characters.bill_of_materials import BomLine, bill_of_materials, cost_bill
from characters.design_document import MaterialSpec
from characters.models import (
    BuildingMaterial,
    Market,
    Price,
    PriceList,
    TradeGood,
    Vendor,
)
from characters.units import D, u

MATERIALS = {
    "limestone-wall": MaterialSpec("wall", "sqft"),
    "cut-limestone": MaterialSpec("wall", "cuft"),
    "subfloor": MaterialSpec("floor", "sqft"),
    "patchworking": MaterialSpec("solid", "cuft"),
    "spruce-roof": MaterialSpec("roof", "sqft"),
    "thatching": MaterialSpec("roof", "sqft"),
    "door": MaterialSpec("opening", "each"),
}


def bom(document) -> dict[str, Decimal]:
    return {
        line.material: line.quantity for line in bill_of_materials(document, MATERIALS)
    }


class BillOfMaterialsTests(SimpleTestCase):
    def test_block_wall_is_volume(self):
        """20 ft long × 2 ft thick × 10 ft high = 400 ft³."""
        document = {
            "walls": [
                {
                    "id": "w1",
                    "points": [[0, 0], [20, 0]],
                    "thickness": 2,
                    "z": [0, 10],
                    "material": "cut-limestone",
                }
            ]
        }
        self.assertEqual(
            bill_of_materials(document, MATERIALS),
            [BomLine("cut-limestone", D("400.0000"), "cuft")],
        )

    def test_a_diagonal_wall_costs_its_true_length(self):
        """(0,0)→(30,40) is 50 ft: 50 × 1 × 10 = 500 ft³."""
        document = {
            "walls": [
                {
                    "id": "w1",
                    "points": [[0, 0], [30, 40]],
                    "thickness": 1,
                    "z": [0, 10],
                    "material": "cut-limestone",
                }
            ]
        }
        self.assertEqual(bom(document), {"cut-limestone": D(500)})

    def test_section_wall_is_face_area_whatever_its_thickness(self):
        """A closed 10 ft square, 8 ft high: 40 × 8 = 320 ft² of face."""
        document = {
            "walls": [
                {
                    "id": "w1",
                    "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                    "closed": True,
                    "thickness": 3,
                    "z": [0, 8],
                    "material": "limestone-wall",
                }
            ]
        }
        self.assertEqual(bom(document), {"limestone-wall": D(320)})

    def test_openings_subtract_from_the_wall_and_add_a_product(self):
        """A 3 × 7 door in a 2 ft block wall removes 42 ft³ from 400; a 2 × 4
        window in a section wall removes 8 ft² of face from 320."""
        document = {
            "walls": [
                {
                    "id": "w1",
                    "points": [[0, 0], [20, 0]],
                    "thickness": 2,
                    "z": [0, 10],
                    "material": "cut-limestone",
                },
                {
                    "id": "w2",
                    "points": [[0, 20], [10, 20], [10, 30], [0, 30]],
                    "closed": True,
                    "thickness": 1,
                    "z": [0, 8],
                    "material": "limestone-wall",
                },
            ],
            "openings": [
                {
                    "id": "o1",
                    "wall": "w1",
                    "offset": 2,
                    "width": 3,
                    "height": 7,
                    "sill": 0,
                    "product": "door",
                },
                {
                    "id": "o2",
                    "wall": "w2",
                    "offset": 2,
                    "width": 2,
                    "height": 4,
                    "sill": 2,
                    "product": "door",
                },
            ],
        }
        self.assertEqual(
            bom(document),
            {"cut-limestone": D(358), "limestone-wall": D(312), "door": D(2)},
        )

    def test_floor_is_area_and_solid_is_volume(self):
        """A 10 × 10 floor is 100 ft²; a 4 × 5 plinth 5 ft deep is 100 ft³."""
        document = {
            "floors": [
                {
                    "id": "f1",
                    "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                    "z": 0,
                    "material": "subfloor",
                }
            ],
            "solids": [
                {
                    "id": "s1",
                    "points": [[0, 0], [4, 0], [4, 5], [0, 5]],
                    "z": [-5, 0],
                    "material": "patchworking",
                }
            ],
        }
        self.assertEqual(bom(document), {"subfloor": D(100), "patchworking": D(100)})

    def test_roof_is_plan_area_over_cosine_of_pitch_for_both_layers(self):
        """100 ft² of plan at 60° is 100 / cos 60° = 200 ft² of roof."""
        document = {
            "roofs": [
                {
                    "id": "r1",
                    "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                    "z": 10,
                    "pitch": 60,
                    "material": "spruce-roof",
                    "covering": "thatching",
                }
            ]
        }
        self.assertEqual(bom(document), {"spruce-roof": D(200), "thatching": D(200)})

    def test_a_30_degree_roof_is_about_15_percent_more_than_its_footprint(self):
        document = {
            "roofs": [
                {
                    "id": "r1",
                    "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                    "z": 10,
                    "pitch": 30,
                    "material": "spruce-roof",
                }
            ]
        }
        expected = Decimal(repr(100 / math.cos(math.radians(30)))).quantize(D("0.0001"))
        self.assertEqual(bom(document), {"spruce-roof": expected})

    def test_shapes_of_one_material_sum_into_one_line(self):
        floor = {"points": [[0, 0], [10, 0], [10, 10], [0, 10]], "material": "subfloor"}
        document = {"floors": [dict(floor, id="f1", z=0), dict(floor, id="f2", z=10)]}
        self.assertEqual(
            bill_of_materials(document, MATERIALS),
            [BomLine("subfloor", D(200), "sqft")],
        )


class CostBillTests(TestCase):
    def setUp(self):
        mason = Vendor.objects.create(name="mason")
        carpenter = Vendor.objects.create(name="carpenter")
        wall_good = TradeGood.objects.create(vendor=mason, name="limestone wall")
        floor_good = TradeGood.objects.create(vendor=carpenter, name="subfloor")
        door_good = TradeGood.objects.create(vendor=carpenter, name="door")
        self.market = Market.objects.create(name="Budapest")
        price_list = PriceList.objects.create(market=self.market)
        # 4.43 gp is listed as 4 2/4 gp, and the listed price is what counts.
        Price.objects.create(
            price_list=price_list, good=wall_good, amount=D("4.43"), coin="gp"
        )
        Price.objects.create(
            price_list=price_list, good=floor_good, amount=D("13.5"), coin="sp"
        )
        for key, good, unit, per_good in (
            ("limestone-wall", wall_good, "sqft", "48"),
            ("subfloor", floor_good, "sqft", "25"),
            ("door", door_good, "each", "1"),
        ):
            BuildingMaterial.objects.create(
                key=key,
                name=key,
                usage="wall",
                unit=unit,
                good=good,
                units_per_good=D(per_good),
            )

    def test_prices_lines_in_copper_through_the_trade_good(self):
        """96 ft² of wall is 2 sections × 4.5 gp = 9 gp = 1728 cp; 50 ft² of
        subfloor is 2 lots × 13.5 sp = 27 sp = 324 cp."""
        bill = [
            BomLine("limestone-wall", D(96), "sqft"),
            BomLine("subfloor", D(50), "sqft"),
        ]
        costing = cost_bill(bill, self.market)
        wall, floor = costing.lines
        self.assertEqual(wall.goods, D(2))
        self.assertEqual(wall.cost, D(1728) * u.cp)
        self.assertEqual(floor.cost, D(324) * u.cp)
        self.assertEqual(costing.total, D(2052) * u.cp)
        self.assertEqual(costing.total.to(u.gp).magnitude, D("10.6875"))

    def test_fractions_of_a_good_are_priced_unrounded(self):
        """24 ft² is half a section: 2.25 gp = 432 cp, not a whole section."""
        costing = cost_bill([BomLine("limestone-wall", D(24), "sqft")], self.market)
        self.assertEqual(costing.total, D(432) * u.cp)

    def test_unpriced_goods_are_reported_not_guessed(self):
        costing = cost_bill([BomLine("door", D(2), "each")], self.market)
        self.assertEqual([line.material.key for line in costing.unpriced], ["door"])
        self.assertEqual(costing.total, D(0) * u.cp)

    def test_no_market_prices_nothing(self):
        costing = cost_bill([BomLine("subfloor", D(25), "sqft")], None)
        self.assertEqual(len(costing.unpriced), 1)
