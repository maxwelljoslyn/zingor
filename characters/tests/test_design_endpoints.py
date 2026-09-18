"""Tests for the building design editor's JSON endpoints and their permissions (#197)."""

import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from characters.models import (
    Building,
    BuildingMaterial,
    Character,
    Design,
    DesignDraft,
    DesignVersion,
    Market,
    Price,
    PriceList,
    Room,
    TradeGood,
    Vendor,
)
from characters.units import D


def wall(wall_id="w1", points=((0, 0), (20, 0)), **overrides) -> dict:
    shape = {
        "id": wall_id,
        "points": [list(p) for p in points],
        "closed": False,
        "thickness": 2,
        "z": [0, 10],
        "material": "limestone-wall",
    }
    shape.update(overrides)
    return shape


def room(room_id, name="Hall") -> dict:
    return {
        "id": room_id,
        "name": name,
        "points": [[0, 2], [10, 2], [10, 10], [0, 10]],
        "z": [0, 10],
    }


@override_settings(BUILDING_DESIGNER_ENABLED=True)
class DesignEndpointBase(TestCase):
    """Alice owns the mill through Bela; Carol owns nothing."""

    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pass")
        self.carol = User.objects.create_user(username="carol", password="pass")
        bela = Character.objects.create(user=self.alice, name="Bela")
        self.mill = Building.objects.create(name="Mill")
        self.mill.owners.set([bela])
        self.design = Design.objects.create(building=self.mill, name="Main")
        mason = Vendor.objects.create(name="mason")
        good = TradeGood.objects.create(vendor=mason, name="limestone wall")
        market = Market.objects.create(name="Budapest")
        price_list = PriceList.objects.create(market=market)
        Price.objects.create(
            price_list=price_list, good=good, amount=D("4.5"), coin="gp"
        )
        BuildingMaterial.objects.create(
            key="limestone-wall",
            name="Limestone wall",
            usage="wall",
            unit="sqft",
            good=good,
            units_per_good=D(48),
        )
        self.base = f"/building/{self.mill.pk}/design/{self.design.pk}"
        self.client.login(username="alice", password="pass")

    def post(self, suffix: str, body) -> "HttpResponse":  # noqa: F821
        return self.client.post(
            self.base + suffix, json.dumps(body), content_type="application/json"
        )


class LoadTests(DesignEndpointBase):
    def test_empty_design_loads_with_the_catalogue(self):
        data = self.client.get(self.base + "/document/").json()
        self.assertTrue(data["can_edit"])
        self.assertIsNone(data["head"])
        self.assertIsNone(data["draft"])
        self.assertEqual([m["key"] for m in data["materials"]], ["limestone-wall"])

    def test_anyone_logged_in_may_look(self):
        self.client.login(username="carol", password="pass")
        response = self.client.get(self.base + "/document/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["can_edit"])

    def test_login_is_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.base + "/document/").status_code, 302)

    def test_a_design_of_another_building_is_not_found(self):
        other = Building.objects.create(name="Barn")
        response = self.client.get(
            f"/building/{other.pk}/design/{self.design.pk}/document/"
        )
        self.assertEqual(response.status_code, 404)


class DraftTests(DesignEndpointBase):
    def test_draft_saves_unchecked_and_loads_back(self):
        half_drawn = {"walls": [{"id": "w1", "points": [[0, 0]]}]}
        response = self.post("/draft/", {"document": half_drawn, "base_version": None})
        self.assertEqual(response.status_code, 200)
        data = self.client.get(self.base + "/document/").json()
        self.assertEqual(data["draft"]["document"], half_drawn)

    def test_saving_again_replaces_the_draft(self):
        self.post("/draft/", {"document": {"walls": []}})
        self.post("/draft/", {"document": {"rooms": []}})
        self.assertEqual(DesignDraft.objects.get().document, {"rooms": []})

    def test_discard(self):
        self.post("/draft/", {"document": {}})
        self.post("/draft/discard/", {})
        self.assertFalse(DesignDraft.objects.exists())

    def test_a_non_owner_cannot_save_a_draft(self):
        self.client.login(username="carol", password="pass")
        response = self.post("/draft/", {"document": {}})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DesignDraft.objects.exists())

    def test_a_draft_must_be_an_object(self):
        self.assertEqual(self.post("/draft/", {"document": []}).status_code, 400)

    def test_drafts_are_per_player(self):
        self.post("/draft/", {"document": {}})
        bob = User.objects.create_user(username="bob", password="pass")
        self.mill.owners.add(Character.objects.create(user=bob, name="Ferenc"))
        self.client.login(username="bob", password="pass")
        self.assertIsNone(self.client.get(self.base + "/document/").json()["draft"])


class CommitTests(DesignEndpointBase):
    def test_first_commit_is_a_root_and_becomes_the_head(self):
        response = self.post(
            "/commit/",
            {"document": {"walls": [wall()]}, "parent": None, "message": "footings"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["sibling"])
        self.design.refresh_from_db()
        self.assertEqual(self.design.head_id, data["version"]["id"])
        self.assertEqual(self.design.head.message, "footings")
        self.assertEqual(self.design.head.author, self.alice)

    def test_commit_appends_a_child_and_clears_the_draft(self):
        first = self.post("/commit/", {"document": {}, "parent": None}).json()[
            "version"
        ]["id"]
        self.post("/draft/", {"document": {"walls": [wall()]}, "base_version": first})
        second = self.post(
            "/commit/", {"document": {"walls": [wall()]}, "parent": first}
        ).json()
        self.assertEqual(
            DesignVersion.objects.get(pk=second["version"]["id"]).parent_id, first
        )
        self.assertFalse(second["sibling"])
        self.assertFalse(DesignDraft.objects.exists())

    def test_committing_from_a_parent_that_moved_on_reports_a_sibling(self):
        root = self.post("/commit/", {"document": {}, "parent": None}).json()[
            "version"
        ]["id"]
        self.post("/commit/", {"document": {"walls": [wall()]}, "parent": root})
        late = self.post(
            "/commit/", {"document": {"walls": [wall("w2")]}, "parent": root}
        ).json()
        self.assertTrue(late["sibling"])
        self.assertEqual(DesignVersion.objects.get(pk=root).children.count(), 2)
        self.design.refresh_from_db()
        self.assertEqual(self.design.head_id, late["version"]["id"])

    def test_overlapping_shapes_are_refused(self):
        crossing = {"walls": [wall(), wall("w2", points=[(10, -10), (10, 10)])]}
        response = self.post("/commit/", {"document": crossing, "parent": None})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["problems"], ["wall w1 overlaps wall w2 by 4.00 ft²"]
        )
        self.assertFalse(DesignVersion.objects.exists())

    def test_a_parent_from_another_building_is_refused(self):
        barn = Building.objects.create(name="Barn")
        foreign = DesignVersion.objects.create(
            building=barn, schema_version=1, document={}
        )
        response = self.post("/commit/", {"document": {}, "parent": foreign.pk})
        self.assertEqual(response.status_code, 400)

    def test_new_rooms_get_rows_and_their_ids_are_rewritten(self):
        response = self.post(
            "/commit/", {"document": {"rooms": [room(-1, "Armoury ")]}, "parent": None}
        )
        data = response.json()
        armoury = Room.objects.get()
        self.assertEqual(armoury.name, "Armoury")
        self.assertEqual(armoury.building, self.mill)
        self.assertEqual(data["rooms"], {"-1": armoury.pk})
        self.assertEqual(data["version"]["document"]["rooms"][0]["id"], armoury.pk)

    def test_renaming_a_room_renames_its_row(self):
        hall = Room.objects.create(building=self.mill, name="Hall")
        self.post(
            "/commit/",
            {"document": {"rooms": [room(hall.pk, "Great Hall")]}, "parent": None},
        )
        hall.refresh_from_db()
        self.assertEqual(hall.name, "Great Hall")

    def test_a_room_of_another_building_is_refused(self):
        barn_room = Room.objects.create(
            building=Building.objects.create(name="Barn"), name="Loft"
        )
        response = self.post(
            "/commit/", {"document": {"rooms": [room(barn_room.pk)]}, "parent": None}
        )
        self.assertEqual(response.status_code, 400)

    def test_a_non_owner_cannot_commit(self):
        self.client.login(username="carol", password="pass")
        response = self.post("/commit/", {"document": {}, "parent": None})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DesignVersion.objects.exists())

    def test_not_json(self):
        response = self.client.post(
            self.base + "/commit/", "walls!", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)


class BomEndpointTests(DesignEndpointBase):
    def test_costs_a_document(self):
        """20 ft × 10 ft of face = 200 ft² = 4 1/6 sections × 4.5 gp = 18.75 gp."""
        data = self.post("/bom/", {"document": {"walls": [wall()]}}).json()
        self.assertEqual(data["problems"], [])
        (line,) = data["lines"]
        self.assertEqual(line["quantity"], "200 ft²")
        self.assertEqual(line["sale_unit"], "48 ft²")
        self.assertEqual(line["units"], "4.167")
        self.assertEqual(line["price"], "4.5 gp")
        self.assertEqual(data["total"], "18.75 gp")
        self.assertEqual(D(data["total_cp"]), D(3600))

    def test_overlaps_are_reported_beside_the_bill(self):
        crossing = {"walls": [wall(), wall("w2", points=[(10, -10), (10, 10)])]}
        data = self.post("/bom/", {"document": crossing}).json()
        self.assertEqual(len(data["problems"]), 1)
        self.assertEqual(len(data["lines"]), 1)

    def test_sound_shapes_are_priced_and_broken_ones_listed(self):
        """One good wall is priced; the other, missing its geometry, waits."""
        document = {"walls": [wall(), {"id": "w2", "material": "limestone-wall"}]}
        data = self.post("/bom/", {"document": document}).json()
        self.assertEqual(len(data["lines"]), 1)
        self.assertEqual(data["total"], "18.75 gp")
        (broken,) = data["broken"]
        self.assertEqual(broken["shape"], "wall w2")
        self.assertEqual(broken["name"], "Limestone wall")
        self.assertTrue(broken["problems"])
        self.assertEqual(data["problems"], broken["problems"])

    def test_a_document_that_is_not_an_object_prices_nothing(self):
        data = self.post("/bom/", {"document": []}).json()
        self.assertEqual(data["problems"], ["the design is not a JSON object"])
        self.assertEqual((data["lines"], data["broken"]), ([], []))

    def test_non_owners_may_see_the_cost(self):
        self.client.login(username="carol", password="pass")
        self.assertEqual(self.post("/bom/", {"document": {}}).status_code, 200)
