"""Bill of materials and cost for a building design (#197).

``bill_of_materials`` is a pure function of a design document (one that
``design_document.problems`` has passed) and the catalogue's material units.
Every shape reduces to one of three units:

- a wall is its centreline length × height of face (ft²) when its material is
  sold by the section, or that face × thickness (ft³) when sold by the block;
- an opening subtracts its face, or its face × the wall's thickness, from
  its wall's material and adds one of its product;
- a floor is its area (ft²), a solid its area × height (ft³);
- a roof is its plan area / cos(pitch) (ft²), for its material and again for
  its covering, if any.

Walls meeting at a butt joint leave a corner notch counted by neither (see
#197 §5); a closed wall has no such notch, since its corners are mitred.

``cost_bill`` prices a bill against a market's latest price list through
each material's trade good. Costs are summed in copper so that a total
mixing gold, silver and copper prices converts exactly, and use the listed
(quarter-coin) price times the fractional number of goods, unrounded: the
purchase rounding of characters.trade belongs to the point of sale.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .design_document import MaterialSpec, points_of, shapes, wall_height
from .geometry import polygon_area, polyline_length
from .models import BuildingMaterial, Market, Price
from .trade import listed_price
from .units import Quantity, u

# The market a design is priced in until buildings know their town.
DEFAULT_MARKET = "Budapest"
QUANTITY_PLACES = Decimal("0.0001")


@dataclass(frozen=True)
class BomLine:
    """So much of one material, in that material's unit."""

    material: str
    quantity: Decimal
    unit: str


def bill_of_materials(
    document: Mapping[str, Any], materials: Mapping[str, MaterialSpec]
) -> list[BomLine]:
    """The materials a document's shapes need, one line per material, by key."""
    totals: dict[str, float] = defaultdict(float)
    walls = {}
    for wall in shapes(document, "walls"):
        walls[wall["id"]] = wall
        length = polyline_length(points_of(wall), wall.get("closed", False))
        face = length * wall_height(wall)
        if materials[wall["material"]].unit == BuildingMaterial.CUBIC_FEET:
            totals[wall["material"]] += face * wall["thickness"]
        else:
            totals[wall["material"]] += face
    for opening in shapes(document, "openings"):
        wall = walls[opening["wall"]]
        face = opening["width"] * opening["height"]
        if materials[wall["material"]].unit == BuildingMaterial.CUBIC_FEET:
            totals[wall["material"]] -= face * wall["thickness"]
        else:
            totals[wall["material"]] -= face
        totals[opening["product"]] += 1
    for floor in shapes(document, "floors"):
        totals[floor["material"]] += polygon_area(points_of(floor))
    for solid in shapes(document, "solids"):
        bottom, top = solid["z"]
        totals[solid["material"]] += polygon_area(points_of(solid)) * (top - bottom)
    for roof in shapes(document, "roofs"):
        surface = polygon_area(points_of(roof)) / math.cos(math.radians(roof["pitch"]))
        totals[roof["material"]] += surface
        if roof.get("covering"):
            totals[roof["covering"]] += surface
    return [
        BomLine(
            key, Decimal(repr(total)).quantize(QUANTITY_PLACES), materials[key].unit
        )
        for key, total in sorted(totals.items())
        if total > 0
    ]


@dataclass
class CostedLine:
    """A bill line with its trade good's price, when the market lists one."""

    material: BuildingMaterial
    quantity: Decimal
    # How many of the trade good the quantity comes to, fractions included.
    goods: Decimal
    price: Price | None
    cost: Quantity | None


@dataclass
class Costing:
    """A priced bill of materials."""

    market: Market | None
    lines: list[CostedLine]

    @property
    def total(self) -> Quantity:
        """The priced lines' cost, in copper."""
        return sum(
            (line.cost for line in self.lines if line.cost is not None),
            Decimal(0) * u.cp,
        )

    @property
    def unpriced(self) -> list[CostedLine]:
        """Lines whose good the market does not list, left out of the total."""
        return [line for line in self.lines if line.price is None]


def default_market() -> Market | None:
    """The market designs are priced in, or None before its table is imported."""
    return Market.objects.filter(name=DEFAULT_MARKET).first()


def cost_bill(bill: list[BomLine], market: Market | None) -> Costing:
    """Price each line from `market`'s latest price list."""
    catalogue = {
        material.key: material
        for material in BuildingMaterial.objects.filter(
            key__in=[line.material for line in bill]
        ).select_related("good")
    }
    price_list = market.latest_price_list() if market is not None else None
    prices = {}
    if price_list is not None:
        prices = {
            price.good_id: price
            for price in Price.objects.filter(
                price_list=price_list,
                good__in=[material.good_id for material in catalogue.values()],
            )
        }
    lines = []
    for line in bill:
        material = catalogue[line.material]
        goods = line.quantity / material.units_per_good
        price = prices.get(material.good_id)
        cost = None
        if price is not None:
            cost = (listed_price(price.amount) * goods * price.unit).to(u.cp)
        lines.append(CostedLine(material, line.quantity, goods, price, cost))
    return Costing(market, lines)
