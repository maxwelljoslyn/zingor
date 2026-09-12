"""The building materials catalogue: what a building design is made of (#197).

A catalogue material never carries a price of its own. It names the trade
good that supplies it and how much of the design's bill of materials one of
that good covers: the Budapest sheet sells a limestone wall as a 6 ft by 8 ft
section, so one good covers 48 ft² of wall face, while a cut limestone block
is one cubic foot of stone. Prices then come from whatever price list is
current, and re-importing a trade table never has to touch the catalogue.

``CATALOGUE`` is the seed, and ``seed_catalogue`` writes it to the database,
refusing to write anything while any row's trade good cannot be found.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from .models import BuildingMaterial, TradeGood


@dataclass(frozen=True)
class MaterialSeed:
    """One catalogue row, naming its trade good by vendor and item name.

    `description` is a prefix of the good's description, needed only where
    the sheet sells two goods under one vendor and name (the two window
    frames). Nominal sizes are in feet and are editor defaults only.
    """

    key: str
    name: str
    usage: str
    unit: str
    vendor: str
    good: str
    per_good: str
    basis: str
    description: str = ""
    thickness: str | None = None
    width: str | None = None
    height: str | None = None


WALL = BuildingMaterial.WALL
FLOOR = BuildingMaterial.FLOOR
ROOF = BuildingMaterial.ROOF
SOLID = BuildingMaterial.SOLID
OPENING = BuildingMaterial.OPENING
STAIR = BuildingMaterial.STAIR
CUFT = BuildingMaterial.CUBIC_FEET
SQFT = BuildingMaterial.SQUARE_FEET
EACH = BuildingMaterial.EACH

CATALOGUE: list[MaterialSeed] = [
    # Walls sold as finished sections are priced by the face they cover; the
    # sheet includes the mason's or carpenter's labour in the price.
    MaterialSeed(
        "limestone-wall",
        "Limestone wall (rubble)",
        WALL,
        SQFT,
        "mason",
        "limestone wall",
        "48",
        "a 6 ft × 8 ft section, mason's labour included; the sheet states no thickness",
    ),
    MaterialSeed(
        "brick-wall",
        "Brick wall",
        WALL,
        SQFT,
        "mason",
        "brick wall",
        "48",
        "a 6 ft × 8 ft section of single-wythe brick, mason's labour included",
        thickness="0.375",
    ),
    MaterialSeed(
        "exterior-wall",
        "Half-timbered exterior wall",
        WALL,
        SQFT,
        "carpenter",
        "exterior wall",
        "40",
        "a section 8 ft high × 5 ft wide, 5 in thick",
        thickness="0.4167",
    ),
    MaterialSeed(
        "interior-wall",
        "Half-timbered interior wall",
        WALL,
        SQFT,
        "carpenter",
        "interior wall",
        "43.333333",
        "a section 8 ft 8 in high × 5 ft wide, 3.5 in thick",
        thickness="0.2917",
    ),
    # Cut stone is sold by the block, one cubic foot each, with no labour.
    MaterialSeed(
        "cut-limestone",
        "Cut limestone",
        WALL,
        CUFT,
        "mason",
        "cut limestone block",
        "1",
        "one block is a cubic foot of stone; no labour",
    ),
    MaterialSeed(
        "cut-granite",
        "Cut granite",
        WALL,
        CUFT,
        "mason",
        "cut granite block",
        "1",
        "one block is a cubic foot of stone; no labour",
    ),
    MaterialSeed(
        "cut-sandstone",
        "Cut sandstone",
        WALL,
        CUFT,
        "mason",
        "cut sandstone block",
        "1",
        "one block is a cubic foot of stone; no labour",
    ),
    MaterialSeed(
        "cut-grey-marble",
        "Cut grey marble",
        WALL,
        CUFT,
        "mason",
        "cut grey marble block",
        "1",
        "one block is a cubic foot of stone; no labour",
    ),
    MaterialSeed(
        "cut-slate",
        "Cut slate",
        WALL,
        CUFT,
        "mason",
        "cut slate slab",
        "1",
        "one slab is a cubic foot of stone; no labour",
    ),
    MaterialSeed(
        "wattle-and-daub",
        "Wattle & daub",
        WALL,
        CUFT,
        "carpenter",
        "wattle & daub",
        "1",
        "sold per cubic foot",
    ),
    MaterialSeed(
        "patchworking",
        "Mortar and fill",
        SOLID,
        CUFT,
        "mason",
        "patchworking",
        "1",
        "sold per cubic foot, as repair work",
    ),
    # Floors, ceilings and finishes, by the area they cover.
    MaterialSeed(
        "subfloor",
        "Subfloor (fir)",
        FLOOR,
        SQFT,
        "carpenter",
        "subfloor",
        "25",
        "per 25 ft², without joists",
    ),
    MaterialSeed(
        "upper-flooring",
        "Upper flooring (fir on joists)",
        FLOOR,
        SQFT,
        "carpenter",
        "upper flooring",
        "25",
        "per 25 ft², on spruce joists",
    ),
    MaterialSeed(
        "ceiling-panel",
        "Ceiling panel",
        FLOOR,
        SQFT,
        "carpenter",
        "ceiling panel",
        "25",
        "per 25 ft², plastered pine",
    ),
    MaterialSeed(
        "plaster-surfacing",
        "Plaster surfacing",
        FLOOR,
        SQFT,
        "mason",
        "plaster surfacing",
        "25",
        "per 25 ft² of interior wall",
    ),
    MaterialSeed(
        "concrete-foundation",
        "Concrete foundation",
        FLOOR,
        SQFT,
        "mason",
        "concrete foundation",
        "100",
        "6 in thick, the base for a 10 ft square; excavation not included",
    ),
    MaterialSeed(
        "alabaster-tile",
        "Alabaster tile",
        FLOOR,
        SQFT,
        "mason",
        "alabaster tile",
        "1",
        "per ft²",
    ),
    MaterialSeed(
        "granite-tile",
        "Granite tile",
        FLOOR,
        SQFT,
        "mason",
        "granite tile",
        "1",
        "per ft²",
    ),
    MaterialSeed(
        "obsidian-tile",
        "Obsidian tile",
        FLOOR,
        SQFT,
        "mason",
        "obsidian tile",
        "1",
        "per ft²",
    ),
    MaterialSeed(
        "slate-tile", "Slate tile", FLOOR, SQFT, "mason", "slate tile", "1", "per ft²"
    ),
    MaterialSeed(
        "white-marble-tile",
        "White marble tile",
        FLOOR,
        SQFT,
        "mason",
        "white marble tile",
        "1",
        "per ft²",
    ),
    # Roofs, by surface area (plan area over the cosine of the pitch).
    MaterialSeed(
        "spruce-roof",
        "Spruce roof with joists",
        ROOF,
        SQFT,
        "carpenter",
        "roof",
        "25",
        "per 25 ft², 1.5 in thick, joists included",
    ),
    MaterialSeed(
        "lattice-work",
        "Lattice work",
        ROOF,
        SQFT,
        "carpenter",
        "lattice work",
        "25",
        "per 25 ft² of roof, to carry thatch",
    ),
    MaterialSeed(
        "thatching",
        "Thatching",
        ROOF,
        SQFT,
        "carpenter",
        "thatching",
        "25",
        "per 25 ft², 6 in thick",
    ),
    MaterialSeed(
        "shingles",
        "Shingles",
        ROOF,
        SQFT,
        "carpenter",
        "shingles",
        "25",
        "cover 25 ft²",
    ),
    MaterialSeed(
        "terra-cotta",
        "Terra cotta tiles",
        ROOF,
        SQFT,
        "mason",
        "terra cotta",
        "25",
        "per 25 ft² of covering",
    ),
    # Doors, windows and gates, one each.
    MaterialSeed(
        "casement-window",
        "Casement window",
        OPENING,
        EACH,
        "glazier",
        "casement window",
        "1",
        "2.5 ft wide, 4 ft high",
        width="2.5",
        height="4",
    ),
    MaterialSeed(
        "closed-window",
        "Closed window",
        OPENING,
        EACH,
        "glazier",
        "closed window",
        "1",
        "12 in square",
        width="1",
        height="1",
    ),
    MaterialSeed(
        "half-glazed-window",
        "Half-glazed window",
        OPENING,
        EACH,
        "glazier",
        "half-glazed window",
        "1",
        "1 ft wide, 4 ft tall",
        width="1",
        height="4",
    ),
    MaterialSeed(
        "lunette",
        "Lunette",
        OPENING,
        EACH,
        "glazier",
        "lunette",
        "1",
        "3 ft wide, 1.5 ft tall",
        width="3",
        height="1.5",
    ),
    MaterialSeed(
        "window-frame",
        "Window frame",
        OPENING,
        EACH,
        "carpenter",
        "window frame",
        "1",
        "3 ft by 18 in",
        description="3 ft.",
        width="1.5",
        height="3",
    ),
    MaterialSeed(
        "window-frame-half",
        "Window frame, half-sized",
        OPENING,
        EACH,
        "carpenter",
        "window frame",
        "1",
        "18 in square",
        description="half-sized",
        width="1.5",
        height="1.5",
    ),
    MaterialSeed(
        "shutter",
        "Shutter",
        OPENING,
        EACH,
        "carpenter",
        "shutter",
        "1",
        "for a window 3 ft tall, 18 in wide",
        width="1.5",
        height="3",
    ),
    MaterialSeed(
        "board-and-batten-door",
        "Board-and-batten door",
        OPENING,
        EACH,
        "carpenter",
        "board-and-batten door",
        "1",
        "the sheet states no size",
    ),
    MaterialSeed(
        "sentry-door",
        "Sentry door",
        OPENING,
        EACH,
        "carpenter",
        "sentry door",
        "1",
        "4 ft by 2.5 ft",
        width="2.5",
        height="4",
    ),
    MaterialSeed(
        "reinforced-door",
        "Reinforced door",
        OPENING,
        EACH,
        "engineer",
        "reinforced door",
        "1",
        "spruce; the sheet states no size",
    ),
    MaterialSeed(
        "siege-door",
        "Siege door",
        OPENING,
        EACH,
        "blacksmith",
        "siege door",
        "1",
        "iron plate, 4.5 ft high by 2.5 ft wide",
        width="2.5",
        height="4.5",
    ),
    MaterialSeed(
        "bastion-gate",
        "Bastion gate",
        OPENING,
        EACH,
        "carpenter",
        "bastion gate",
        "1",
        "two doors, each 6 ft wide and 14 ft high",
        width="12",
        height="14",
    ),
    MaterialSeed(
        "stairwell",
        "Stairwell",
        STAIR,
        EACH,
        "carpenter",
        "stairwell",
        "1",
        "climbs 9 ft, 3 ft wide, 14 steps",
        width="3",
        height="9",
    ),
]


class CatalogueError(Exception):
    """The seed names trade goods that cannot be found, or found unambiguously."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class SeedReport:
    """What one seeding run did, by material key."""

    created: list[str] = field(default_factory=list)
    refreshed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


def find_good(seed: MaterialSeed) -> TradeGood | str:
    """The trade good `seed` names, or a sentence saying why there is not exactly one."""
    goods = TradeGood.objects.filter(vendor__name=seed.vendor, name=seed.good)
    if seed.description:
        goods = goods.filter(description__startswith=seed.description)
    found = list(goods[:2])
    label = f"{seed.key}: {seed.vendor}: {seed.good}"
    if seed.description:
        label += f" ({seed.description}…)"
    if not found:
        return f"{label} is not in the trade table; import it first"
    if len(found) > 1:
        return f"{label} matches more than one trade good"
    return found[0]


def seed_catalogue(
    catalogue: list[MaterialSeed] = CATALOGUE, *, refresh: bool = False
) -> SeedReport:
    """Create the catalogue's materials from the imported trade goods.

    Materials already present are left as they are, so edits made in the
    admin survive a re-run; with `refresh` they are overwritten from the seed.
    Nothing is written unless every row's trade good is found.
    """
    goods = {seed.key: find_good(seed) for seed in catalogue}
    problems = [good for good in goods.values() if isinstance(good, str)]
    if problems:
        raise CatalogueError(problems)
    report = SeedReport()
    existing = set(BuildingMaterial.objects.values_list("key", flat=True))
    with transaction.atomic():
        for seed in catalogue:
            fields = {
                "name": seed.name,
                "usage": seed.usage,
                "unit": seed.unit,
                "good": goods[seed.key],
                "units_per_good": seed.per_good,
                "basis": seed.basis,
                "nominal_thickness": seed.thickness,
                "nominal_width": seed.width,
                "nominal_height": seed.height,
            }
            if seed.key not in existing:
                BuildingMaterial.objects.create(key=seed.key, **fields)
                report.created.append(seed.key)
            elif refresh:
                BuildingMaterial.objects.filter(key=seed.key).update(**fields)
                report.refreshed.append(seed.key)
            else:
                report.unchanged.append(seed.key)
    return report
