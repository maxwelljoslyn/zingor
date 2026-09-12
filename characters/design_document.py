"""The design document: a building design's shapes, as stored JSON (#197).

A document is a JSON object of shape lists, all lengths in feet:

- ``walls``: ``{id, points: [[x, y], ...], closed, thickness, z: [bottom, top], material}``
- ``floors``: ``{id, points, z, material}``, a floor or ceiling polygon at height z
- ``solids``: ``{id, points, z: [bottom, top], material}``
- ``roofs``: ``{id, points, z, pitch, material, covering}``, the plan outline at the
  eaves, pitch in degrees, and an optional second material laid over the first
- ``openings``: ``{id, wall, offset, width, height, sill, product}``, offset along
  the wall's centreline from its first point, sill above the wall's bottom
- ``rooms``: ``{id, name, points, z: [bottom, top]}``

Every list may be absent. Shape ids are strings the editor chooses, except
a room's, which is the pk of its Room row: a room's identity has to outlive
any one version, because items are left in it (see Room). Layers (5 ft
z-slices, negative below ground) are how the editor slices the plan; they
are not stored.

Documents are frozen into DesignVersion rows and will be read by editor code
not yet written, so each is stored beside its schema version and brought up
to date on read by ``upgrade``. Frozen history is never rewritten.

``problems`` is the server's whole check of a document, run on every commit:
structure, material and room references, buildable geometry, and that no
two bodies overlap. The bill of materials sums volumes on the assumption
that nothing is counted twice, so this cannot be left to the editor.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from .geometry import (
    OVERLAP_TOLERANCE,
    GeometryError,
    Point,
    convex_overlap_area,
    is_simple,
    overlap_area,
    polygon_area,
    segment_spans,
    triangulate,
    wall_pieces,
)
from .models import BuildingMaterial

SCHEMA_VERSION = 1
SHAPE_KINDS = ("walls", "floors", "solids", "roofs", "openings", "rooms")
SINGULAR = {
    "walls": "wall",
    "floors": "floor",
    "solids": "solid",
    "roofs": "roof",
    "openings": "opening",
    "rooms": "room",
}
LAYER_HEIGHT = 5
MAX_COORDINATE = 10_000.0
MAX_POINTS = 500
MAX_PITCH = 75.0
MAX_ID_LENGTH = 64
MAX_ROOM_NAME = 200
# Smallest polygon worth keeping, in ft²: anything less is a mis-click.
MIN_AREA = 0.01
# Heights closer than this (ft) are the same height.
SAME_HEIGHT = 1e-6


class MaterialSpec(NamedTuple):
    """What the checks and the bill of materials need to know about a material."""

    usage: str
    unit: str


def material_specs() -> dict[str, MaterialSpec]:
    """The catalogue, keyed as documents refer to it."""
    return {
        key: MaterialSpec(usage, unit)
        for key, usage, unit in BuildingMaterial.objects.values_list(
            "key", "usage", "unit"
        )
    }


def upgrade(document: dict[str, Any], schema_version: int) -> dict[str, Any]:
    """Bring a stored document up to the current schema, without saving it.

    Upgrade-on-read: stored versions keep the schema they were written in,
    and each change to the format adds a step here. There is one schema so far.
    """
    if schema_version == SCHEMA_VERSION:
        return document
    raise ValueError(f"unknown design schema version {schema_version}")


def empty_document() -> dict[str, list]:
    """A design with nothing drawn yet."""
    return {kind: [] for kind in SHAPE_KINDS}


def shapes(document: Mapping[str, Any], kind: str) -> list[dict[str, Any]]:
    """One kind's shapes, an absent list read as empty."""
    return document.get(kind) or []


def points_of(shape: Mapping[str, Any]) -> list[Point]:
    """A shape's points as tuples."""
    return [(float(x), float(y)) for x, y in shape["points"]]


def wall_height(wall: Mapping[str, Any]) -> float:
    """How tall a wall stands."""
    bottom, top = wall["z"]
    return float(top) - float(bottom)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class _Checker:
    """Collects a document's problems as sentences a player can act on."""

    def __init__(
        self, materials: Mapping[str, MaterialSpec], room_ids: Collection[int] | None
    ):
        self.materials = materials
        self.room_ids = room_ids
        self.found: list[str] = []
        self.ids: set[str] = set()
        self.room_seen: set[int] = set()
        self.walls: dict[str, Mapping] = {}
        self.wall_index: dict[str, int] = {}

    def add(self, problem: str) -> None:
        self.found.append(problem)

    def number(
        self,
        shape: Mapping[str, Any],
        key: str,
        label: str,
        *,
        minimum: float | None = None,
        above: float | None = None,
        maximum: float | None = None,
    ) -> float | None:
        value = shape.get(key)
        if not _is_number(value):
            self.add(f"{label}: {key} must be a number")
            return None
        if minimum is not None and value < minimum:
            self.add(f"{label}: {key} must be at least {minimum:g}")
            return None
        if above is not None and value <= above:
            self.add(f"{label}: {key} must be more than {above:g}")
            return None
        if maximum is not None and value > maximum:
            self.add(f"{label}: {key} must be at most {maximum:g}")
            return None
        return float(value)

    def z_range(self, shape: Mapping[str, Any], label: str) -> bool:
        z = shape.get("z")
        if not (
            isinstance(z, list)
            and len(z) == 2
            and all(_is_number(v) and abs(v) <= MAX_COORDINATE for v in z)
        ):
            self.add(f"{label}: z must be [bottom, top] in feet")
            return False
        if z[1] <= z[0]:
            self.add(f"{label}: its top must be above its bottom")
            return False
        return True

    def points(
        self, shape: Mapping[str, Any], label: str, minimum: int
    ) -> list[Point] | None:
        points = shape.get("points")
        if not isinstance(points, list) or not minimum <= len(points) <= MAX_POINTS:
            self.add(f"{label}: needs from {minimum} to {MAX_POINTS} points")
            return None
        for point in points:
            if not (
                isinstance(point, list)
                and len(point) == 2
                and all(_is_number(v) and abs(v) <= MAX_COORDINATE for v in point)
            ):
                self.add(f"{label}: every point must be [x, y] in feet")
                return None
        return points_of(shape)

    def polygon(self, shape: Mapping[str, Any], label: str) -> None:
        points = self.points(shape, label, 3)
        if points is None:
            return
        if not is_simple(points, closed=True):
            self.add(f"{label}: its outline crosses itself")
        elif polygon_area(points) < MIN_AREA:
            self.add(f"{label}: it encloses no area")

    def material(
        self,
        shape: Mapping[str, Any],
        key: str,
        label: str,
        usages: Collection[str],
        unit: str | None = None,
    ) -> None:
        value = shape.get(key)
        spec = self.materials.get(value) if isinstance(value, str) else None
        if spec is None:
            self.add(f"{label}: {key} {value!r} is not in the materials catalogue")
        elif spec.usage not in usages or (unit is not None and spec.unit != unit):
            self.add(f"{label}: {value} cannot be used for this")

    def wall(self, wall: Mapping[str, Any], label: str) -> None:
        closed = wall.get("closed", False)
        if not isinstance(closed, bool):
            self.add(f"{label}: closed must be true or false")
            return
        points = self.points(wall, label, 3 if closed else 2)
        thickness = self.number(wall, "thickness", label, above=0, maximum=100)
        self.z_range(wall, label)
        self.material(wall, "material", label, [BuildingMaterial.WALL])
        if points is None or thickness is None:
            return
        if not is_simple(points, closed):
            self.add(f"{label}: it crosses itself")
            return
        try:
            wall_pieces(points, thickness, closed)
        except GeometryError as exc:
            self.add(f"{label}: {exc}")

    def floor(self, floor: Mapping[str, Any], label: str) -> None:
        self.polygon(floor, label)
        self.number(floor, "z", label, minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE)
        self.material(floor, "material", label, [BuildingMaterial.FLOOR])

    def solid(self, solid: Mapping[str, Any], label: str) -> None:
        self.polygon(solid, label)
        self.z_range(solid, label)
        self.material(
            solid,
            "material",
            label,
            [BuildingMaterial.SOLID, BuildingMaterial.WALL],
            unit=BuildingMaterial.CUBIC_FEET,
        )

    def roof(self, roof: Mapping[str, Any], label: str) -> None:
        self.polygon(roof, label)
        self.number(roof, "z", label, minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE)
        self.number(roof, "pitch", label, minimum=0, maximum=MAX_PITCH)
        self.material(roof, "material", label, [BuildingMaterial.ROOF])
        if roof.get("covering") is not None:
            self.material(roof, "covering", label, [BuildingMaterial.ROOF])

    def room(self, room: Mapping[str, Any], label: str) -> None:
        name = room.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > MAX_ROOM_NAME:
            self.add(f"{label}: needs a name of at most {MAX_ROOM_NAME} characters")
        self.polygon(room, label)
        self.z_range(room, label)

    def shape(self, kind: str, index: int, shape: Any) -> None:
        """Check one shape of `kind`, the `index`th in its list."""
        if not isinstance(shape, dict):
            self.add(f"{kind}[{index}] must be an object")
            return
        shape_id = shape.get("id")
        label = f"{SINGULAR[kind]} {shape_id}"
        if kind == "rooms":
            if not isinstance(shape_id, int) or isinstance(shape_id, bool):
                self.add(f"rooms[{index}]: id must be a room number")
            elif shape_id in self.room_seen:
                self.add(f"{label}: appears twice")
            elif self.room_ids is not None and shape_id not in self.room_ids:
                self.add(f"{label}: is not a room of this building")
            self.room_seen.add(shape_id)
            self.room(shape, label)
            return
        if not isinstance(shape_id, str) or not 0 < len(shape_id) <= MAX_ID_LENGTH:
            self.add(f"{kind}[{index}]: id must be a short string")
            return
        if shape_id in self.ids:
            self.add(f"{label}: id is used twice")
            return
        self.ids.add(shape_id)
        if kind == "walls":
            self.walls[shape_id] = shape
            self.wall_index[shape_id] = index
            self.wall(shape, label)
        elif kind == "floors":
            self.floor(shape, label)
        elif kind == "solids":
            self.solid(shape, label)
        elif kind == "roofs":
            self.roof(shape, label)
        else:
            self.opening(shape, label, self.walls)

    def opening(
        self, opening: Mapping[str, Any], label: str, walls: Mapping[str, Mapping]
    ) -> None:
        self.material(opening, "product", label, [BuildingMaterial.OPENING])
        offset = self.number(opening, "offset", label, minimum=0)
        width = self.number(opening, "width", label, above=0)
        height = self.number(opening, "height", label, above=0)
        sill = self.number(opening, "sill", label, minimum=0)
        wall = walls.get(opening.get("wall"))
        if wall is None:
            self.add(f"{label}: is not in any wall of this design")
            return
        if None in (offset, width, height, sill):
            return
        try:
            spans = segment_spans(points_of(wall), wall.get("closed", False))
            fits_along = any(
                start - SAME_HEIGHT <= offset and offset + width <= end + SAME_HEIGHT
                for start, end in spans
            )
            fits_up = sill + height <= wall_height(wall) + SAME_HEIGHT
        except (KeyError, TypeError, ValueError):
            # The wall itself is malformed, which is already reported.
            return
        if not fits_along:
            self.add(f"{label}: does not fit along one straight run of its wall")
        if not fits_up:
            self.add(f"{label}: is taller than its wall")


@dataclass
class StructureReport:
    """A document's structure problems, and which shapes they belong to."""

    problems: list[str] = field(default_factory=list)
    # (kind, index in its list) -> that shape's problems. The bill of
    # materials cannot trust a shape listed here, and can trust every other.
    broken: dict[tuple[str, int], list[str]] = field(default_factory=dict)
    # The document is not even an object, so nothing in it can be used.
    unusable: bool = False

    def sound_document(self, document: Any) -> dict[str, list]:
        """The document without its broken shapes."""
        sound = empty_document()
        if self.unusable:
            return sound
        for kind in SHAPE_KINDS:
            listed = document.get(kind)
            if isinstance(listed, list):
                sound[kind] = [
                    shape
                    for index, shape in enumerate(listed)
                    if (kind, index) not in self.broken
                ]
        return sound


def check_structure(
    document: Any,
    materials: Mapping[str, MaterialSpec],
    room_ids: Collection[int] | None = None,
) -> StructureReport:
    """Everything wrong with a document short of shapes overlapping, shape by shape.

    `room_ids` are the building's Room pks, which a room shape's id must be
    one of; pass None to skip that check. An opening in a broken wall is
    broken too, since it cannot be placed or priced without its wall.
    """
    report = StructureReport()
    if not isinstance(document, dict):
        report.problems.append("the design is not a JSON object")
        report.unusable = True
        return report
    check = _Checker(materials, room_ids)
    for key in document:
        if key not in SHAPE_KINDS:
            check.add(f"unknown shape list {key!r}")
    for kind in SHAPE_KINDS:
        listed = document.get(kind, [])
        if not isinstance(listed, list):
            check.add(f"{kind} must be a list")
            continue
        for index, shape in enumerate(listed):
            before = len(check.found)
            check.shape(kind, index, shape)
            if len(check.found) > before:
                report.broken[(kind, index)] = check.found[before:]
    openings = document.get("openings")
    if isinstance(openings, list):
        for index, opening in enumerate(openings):
            if ("openings", index) in report.broken:
                continue
            wall_index = check.wall_index.get(opening.get("wall"))
            if ("walls", wall_index) in report.broken:
                problem = f"opening {opening.get('id')}: its wall has a problem"
                check.add(problem)
                report.broken[("openings", index)] = [problem]
    report.problems = check.found
    return report


def structure_problems(
    document: Any,
    materials: Mapping[str, MaterialSpec],
    room_ids: Collection[int] | None = None,
) -> list[str]:
    """Everything wrong with a document short of shapes overlapping."""
    return check_structure(document, materials, room_ids).problems


def _z_overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    (a0, a1), (b0, b1) = a["z"], b["z"]
    return a0 < b1 - SAME_HEIGHT and b0 < a1 - SAME_HEIGHT


def _pairwise_overlaps(
    labelled: list[tuple[str, Mapping[str, Any], list]],
    same_level,
) -> list[str]:
    found = []
    for i, (label_a, shape_a, pieces_a) in enumerate(labelled):
        for label_b, shape_b, pieces_b in labelled[i + 1 :]:
            if not same_level(shape_a, shape_b):
                continue
            area = overlap_area(pieces_a, pieces_b)
            if area > OVERLAP_TOLERANCE:
                found.append(f"{label_a} overlaps {label_b} by {area:.2f} ft²")
    return found


def _same_height(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return abs(a["z"] - b["z"]) <= SAME_HEIGHT


def overlap_problems(document: Mapping[str, Any]) -> list[str]:
    """Shapes occupying the same space, for a document with no structure problems.

    Walls and solids may not share volume with each other; floors may not
    overlap at the same height, nor roofs at the same eaves height; rooms
    may not share space, since an item left in one must be in only one; and
    openings may not overlap within a wall.
    """
    found = []
    bodies = []
    for wall in shapes(document, "walls"):
        closed = wall.get("closed", False)
        pieces = wall_pieces(points_of(wall), float(wall["thickness"]), closed)
        label = f"wall {wall['id']}"
        count = len(pieces)
        for i in range(count):
            for j in range(i + 2, count):
                if closed and i == 0 and j == count - 1:
                    continue
                if convex_overlap_area(pieces[i], pieces[j]) > OVERLAP_TOLERANCE:
                    found.append(f"{label}: runs back over itself")
                    break
            else:
                continue
            break
        bodies.append((label, wall, pieces))
    for solid in shapes(document, "solids"):
        bodies.append((f"solid {solid['id']}", solid, triangulate(points_of(solid))))
    found += _pairwise_overlaps(bodies, _z_overlap)
    for kind, same_level in (("floors", _same_height), ("roofs", _same_height)):
        labelled = [
            (f"{SINGULAR[kind]} {shape['id']}", shape, triangulate(points_of(shape)))
            for shape in shapes(document, kind)
        ]
        found += _pairwise_overlaps(labelled, same_level)
    rooms = [
        (f"room {room['id']} ({room['name']})", room, triangulate(points_of(room)))
        for room in shapes(document, "rooms")
    ]
    found += _pairwise_overlaps(rooms, _z_overlap)
    by_wall: dict[str, list[Mapping[str, Any]]] = {}
    for opening in shapes(document, "openings"):
        by_wall.setdefault(opening["wall"], []).append(opening)
    for listed in by_wall.values():
        for i, a in enumerate(listed):
            for b in listed[i + 1 :]:
                along = (
                    a["offset"] < b["offset"] + b["width"]
                    and b["offset"] < a["offset"] + a["width"]
                )
                up = a["sill"] < b["sill"] + b["height"] and b["sill"] < (
                    a["sill"] + a["height"]
                )
                if along and up:
                    found.append(f"opening {a['id']} overlaps opening {b['id']}")
    return found


def problems(
    document: Any,
    materials: Mapping[str, MaterialSpec],
    room_ids: Collection[int] | None = None,
) -> list[str]:
    """Everything that stops a document being committed; empty when it may be."""
    found = structure_problems(document, materials, room_ids)
    if found:
        return found
    return overlap_problems(document)
