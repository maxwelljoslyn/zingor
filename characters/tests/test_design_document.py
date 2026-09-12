"""Tests for the design document's checks: structure, references and overlap (#197)."""

from django.test import SimpleTestCase

from characters.design_document import (
    SCHEMA_VERSION,
    MaterialSpec,
    check_structure,
    empty_document,
    problems,
    upgrade,
)

MATERIALS = {
    "limestone-wall": MaterialSpec("wall", "sqft"),
    "cut-limestone": MaterialSpec("wall", "cuft"),
    "subfloor": MaterialSpec("floor", "sqft"),
    "patchworking": MaterialSpec("solid", "cuft"),
    "spruce-roof": MaterialSpec("roof", "sqft"),
    "thatching": MaterialSpec("roof", "sqft"),
    "door": MaterialSpec("opening", "each"),
}


def wall(wall_id="w1", points=((0, 0), (20, 0)), **overrides) -> dict:
    shape = {
        "id": wall_id,
        "points": [list(p) for p in points],
        "closed": False,
        "thickness": 2,
        "z": [0, 10],
        "material": "cut-limestone",
    }
    shape.update(overrides)
    return shape


def square(x=0, y=0, size=10) -> list[list[float]]:
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size]]


def door(door_id="d1", wall_id="w1", offset=4, **overrides) -> dict:
    shape = {
        "id": door_id,
        "wall": wall_id,
        "offset": offset,
        "width": 3,
        "height": 7,
        "sill": 0,
        "product": "door",
    }
    shape.update(overrides)
    return shape


def check(document, room_ids=None) -> list[str]:
    return problems(document, MATERIALS, room_ids)


class UpgradeTests(SimpleTestCase):
    def test_current_schema_reads_as_is(self):
        document = empty_document()
        self.assertIs(upgrade(document, SCHEMA_VERSION), document)

    def test_unknown_schema_is_refused(self):
        with self.assertRaises(ValueError):
            upgrade({}, SCHEMA_VERSION + 1)


class StructureTests(SimpleTestCase):
    def test_empty_design_is_fine(self):
        self.assertEqual(check({}), [])
        self.assertEqual(check(empty_document()), [])

    def test_a_sound_design_passes(self):
        document = {
            "walls": [wall(closed=True, points=[(0, 0), (20, 0), (20, 20), (0, 20)])],
            "openings": [door()],
            "floors": [
                {"id": "f1", "points": square(), "z": 0, "material": "subfloor"}
            ],
            "roofs": [
                {
                    "id": "r1",
                    "points": square(size=20),
                    "z": 10,
                    "pitch": 30,
                    "material": "spruce-roof",
                    "covering": "thatching",
                }
            ],
            "rooms": [{"id": 7, "name": "Hall", "points": square(), "z": [0, 10]}],
        }
        self.assertEqual(check(document, room_ids={7}), [])

    def test_not_an_object(self):
        self.assertEqual(check([]), ["the design is not a JSON object"])

    def test_unknown_shape_list(self):
        self.assertEqual(check({"towers": []}), ["unknown shape list 'towers'"])

    def test_unknown_material(self):
        found = check({"walls": [wall(material="adamant")]})
        self.assertEqual(
            found, ["wall w1: material 'adamant' is not in the materials catalogue"]
        )

    def test_material_must_suit_the_shape(self):
        found = check({"walls": [wall(material="subfloor")]})
        self.assertEqual(found, ["wall w1: subfloor cannot be used for this"])

    def test_a_solid_may_be_any_stone_sold_by_volume(self):
        solid = {"id": "s1", "points": square(), "z": [0, 5]}
        self.assertEqual(check({"solids": [dict(solid, material="cut-limestone")]}), [])
        self.assertEqual(
            check({"solids": [dict(solid, material="limestone-wall")]}),
            ["solid s1: limestone-wall cannot be used for this"],
        )

    def test_ids_must_be_unique(self):
        found = check({"walls": [wall(), wall(points=[(0, 30), (20, 30)])]})
        self.assertEqual(found, ["wall w1: id is used twice"])

    def test_top_must_be_above_bottom(self):
        self.assertEqual(
            check({"walls": [wall(z=[10, 10])]}),
            ["wall w1: its top must be above its bottom"],
        )

    def test_numbers_must_be_numbers(self):
        found = check({"walls": [wall(thickness="thick")]})
        self.assertEqual(found, ["wall w1: thickness must be a number"])

    def test_a_crossed_outline_is_refused(self):
        bowtie = [[0, 0], [10, 10], [10, 0], [0, 10]]
        found = check(
            {"floors": [{"id": "f1", "points": bowtie, "z": 0, "material": "subfloor"}]}
        )
        self.assertEqual(found, ["floor f1: its outline crosses itself"])

    def test_a_hairpin_wall_is_refused(self):
        found = check({"walls": [wall(points=[(0, 0), (20, 0), (0, 1)])]})
        self.assertEqual(found, ["wall w1: a wall turns too sharp a corner"])

    def test_roof_pitch_is_bounded(self):
        roof = {
            "id": "r1",
            "points": square(),
            "z": 10,
            "pitch": 80,
            "material": "spruce-roof",
        }
        self.assertEqual(
            check({"roofs": [roof]}), ["roof r1: pitch must be at most 75"]
        )

    def test_room_must_belong_to_the_building(self):
        room = {"id": 3, "name": "Cellar", "points": square(), "z": [-10, 0]}
        self.assertEqual(
            check({"rooms": [room]}, room_ids={4}),
            ["room 3: is not a room of this building"],
        )

    def test_room_needs_a_name(self):
        room = {"id": 3, "name": " ", "points": square(), "z": [-10, 0]}
        self.assertEqual(
            check({"rooms": [room]}),
            ["room 3: needs a name of at most 200 characters"],
        )

    def test_opening_must_name_a_wall(self):
        found = check({"walls": [wall()], "openings": [door(wall_id="w9")]})
        self.assertEqual(found, ["opening d1: is not in any wall of this design"])

    def test_opening_must_fit_one_straight_run(self):
        bent = wall(points=[(0, 0), (10, 0), (10, 10)])
        found = check({"walls": [bent], "openings": [door(offset=9)]})
        self.assertEqual(
            found, ["opening d1: does not fit along one straight run of its wall"]
        )

    def test_opening_may_sit_on_the_second_run(self):
        bent = wall(points=[(0, 0), (10, 0), (10, 10)])
        self.assertEqual(check({"walls": [bent], "openings": [door(offset=12)]}), [])

    def test_opening_must_fit_under_the_wall_top(self):
        found = check({"walls": [wall()], "openings": [door(sill=4)]})
        self.assertEqual(found, ["opening d1: is taller than its wall"])


class OverlapTests(SimpleTestCase):
    def test_crossing_walls_are_refused(self):
        document = {
            "walls": [wall(), wall("w2", points=[(10, -10), (10, 10)])],
        }
        self.assertEqual(check(document), ["wall w1 overlaps wall w2 by 4.00 ft²"])

    def test_a_wall_butted_against_a_face_is_fine(self):
        document = {"walls": [wall(), wall("w2", points=[(10, 1), (10, 10)])]}
        self.assertEqual(check(document), [])

    def test_walls_on_different_storeys_may_cross_in_plan(self):
        document = {
            "walls": [wall(), wall("w2", points=[(10, -10), (10, 10)], z=[10, 20])],
        }
        self.assertEqual(check(document), [])

    def test_a_solid_inside_a_wall_is_refused(self):
        solid = {
            "id": "s1",
            "points": [[5, -1], [8, -1], [8, 1], [5, 1]],
            "z": [0, 5],
            "material": "patchworking",
        }
        self.assertEqual(
            check({"walls": [wall()], "solids": [solid]}),
            ["wall w1 overlaps solid s1 by 6.00 ft²"],
        )

    def test_floors_overlap_only_at_the_same_height(self):
        floors = [
            {"id": "f1", "points": square(), "z": 0, "material": "subfloor"},
            {"id": "f2", "points": square(5, 5), "z": 0, "material": "subfloor"},
        ]
        self.assertEqual(
            check({"floors": floors}), ["floor f1 overlaps floor f2 by 25.00 ft²"]
        )
        floors[1]["z"] = 10
        self.assertEqual(check({"floors": floors}), [])

    def test_rooms_may_not_share_space(self):
        rooms = [
            {"id": 1, "name": "Hall", "points": square(), "z": [0, 10]},
            {"id": 2, "name": "Pantry", "points": square(8, 0), "z": [0, 10]},
        ]
        self.assertEqual(
            check({"rooms": rooms}),
            ["room 1 (Hall) overlaps room 2 (Pantry) by 20.00 ft²"],
        )

    def test_openings_may_not_overlap_in_a_wall(self):
        document = {"walls": [wall()], "openings": [door(), door("d2", offset=6)]}
        self.assertEqual(check(document), ["opening d1 overlaps opening d2"])

    def test_a_window_above_a_door_is_fine(self):
        window = door("d2", offset=4, height=1, sill=8)
        self.assertEqual(check({"walls": [wall()], "openings": [door(), window]}), [])

    def test_a_wall_hooking_back_into_itself_is_refused(self):
        """Its last run ends 0.5 ft from the first run's centreline, inside its face."""
        hook = wall(points=[(0, 0), (20, 0), (20, 5), (10, 5), (10, 0.5)])
        self.assertEqual(check({"walls": [hook]}), ["wall w1: runs back over itself"])


class StructureReportTests(SimpleTestCase):
    """Problems attributed to shapes, so the sound ones can still be priced."""

    def test_problems_belong_to_their_shape(self):
        bowtie = [[0, 0], [10, 10], [10, 0], [0, 10]]
        document = {
            "walls": [wall(), wall("w2", thickness="thick")],
            "floors": [{"id": "f1", "points": bowtie, "z": 0, "material": "subfloor"}],
        }
        report = check_structure(document, MATERIALS)
        self.assertEqual(set(report.broken), {("walls", 1), ("floors", 0)})
        self.assertEqual(
            report.broken[("walls", 1)], ["wall w2: thickness must be a number"]
        )
        sound = report.sound_document(document)
        self.assertEqual((sound["walls"], sound["floors"]), ([wall()], []))

    def test_an_opening_in_a_broken_wall_is_broken_too(self):
        document = {"walls": [wall(material="adamant")], "openings": [door()]}
        report = check_structure(document, MATERIALS)
        self.assertEqual(
            report.broken[("openings", 0)], ["opening d1: its wall has a problem"]
        )
        self.assertEqual(report.sound_document(document)["openings"], [])

    def test_a_document_that_is_not_an_object_is_unusable(self):
        report = check_structure("walls", MATERIALS)
        self.assertTrue(report.unusable)
        self.assertEqual(report.sound_document("walls"), empty_document())
