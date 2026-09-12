"""Tests for design versions, drafts and rooms, and for items left in rooms (#197)."""

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models import RestrictedError
from django.test import TestCase
from django.utils import timezone

from characters.design_document import SCHEMA_VERSION, empty_document
from characters.models import (
    Building,
    Character,
    Design,
    DesignDraft,
    DesignVersion,
    Item,
    Room,
)
from characters.views import _location_choices, _location_from_key


class DesignBase(TestCase):
    """A mill owned by Alice's character, with one design on it."""

    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pass")
        self.bela = Character.objects.create(user=self.alice, name="Bela")
        self.mill = Building.objects.create(name="Mill")
        self.mill.owners.set([self.bela])
        self.design = Design.objects.create(building=self.mill, name="Main")

    def version(self, parent=None, **fields) -> DesignVersion:
        return DesignVersion.objects.create(
            building=self.mill,
            parent=parent,
            design=self.design,
            schema_version=SCHEMA_VERSION,
            document=empty_document(),
            **fields,
        )


class DesignVersionTests(DesignBase):
    def test_a_saved_version_cannot_change(self):
        version = self.version()
        version.message = "rewritten history"
        with self.assertRaises(ValueError):
            version.save()
        with self.assertRaises(ValueError):
            version.save(update_fields=["message"])

    def test_built_at_may_be_stamped(self):
        version = self.version()
        version.built_at = timezone.now()
        version.save(update_fields=["built_at"])
        version.refresh_from_db()
        self.assertIsNotNone(version.built_at)

    def test_two_commits_from_one_parent_are_siblings(self):
        root = self.version()
        self.version(parent=root)
        self.version(parent=root)
        self.assertEqual(root.children.count(), 2)

    def test_a_parent_cannot_be_deleted_from_under_its_children(self):
        root = self.version()
        self.version(parent=root)
        with self.assertRaises(RestrictedError):
            root.delete()

    def test_deleting_the_building_takes_its_whole_design_tree(self):
        root = self.version()
        child = self.version(parent=root)
        self.design.head = child
        self.design.save()
        DesignDraft.objects.create(
            design=self.design,
            user=self.alice,
            base_version=child,
            schema_version=SCHEMA_VERSION,
            document={},
        )
        self.mill.delete()
        self.assertFalse(Design.objects.exists())
        self.assertFalse(DesignVersion.objects.exists())
        self.assertFalse(DesignDraft.objects.exists())

    def test_design_names_are_unique_per_building(self):
        with self.assertRaises(IntegrityError):
            Design.objects.create(building=self.mill, name="Main")

    def test_read_document(self):
        self.assertEqual(self.version().read_document(), empty_document())


class DesignDraftTests(DesignBase):
    def test_one_draft_per_player_per_design(self):
        fields = {
            "design": self.design,
            "user": self.alice,
            "schema_version": SCHEMA_VERSION,
            "document": {},
        }
        DesignDraft.objects.create(**fields)
        with self.assertRaises(IntegrityError):
            DesignDraft.objects.create(**fields)


class RoomLocationTests(DesignBase):
    """Item.location_room: an item left in a room of a building."""

    def setUp(self):
        super().setUp()
        self.armoury = Room.objects.create(building=self.mill, name="Armoury")
        self.chest = Item.objects.create(owner=self.bela, name="Chest", weight="10 lb")

    def test_move_to_a_room(self):
        self.chest.move_to(self.armoury)
        self.chest.save()
        self.chest.refresh_from_db()
        self.assertFalse(self.chest.is_carried)
        self.assertEqual(self.chest.location, self.armoury)
        self.assertEqual(self.chest.location_key, f"room-{self.armoury.pk}")

    def test_moving_to_the_building_clears_the_room(self):
        self.chest.move_to(self.armoury)
        self.chest.move_to(self.mill)
        self.assertIsNone(self.chest.location_room)
        self.assertEqual(self.chest.location, self.mill)

    def test_cannot_be_in_a_room_and_at_a_building_at_once(self):
        with self.assertRaises(IntegrityError):
            Item.objects.create(
                owner=self.bela,
                name="Impossible",
                is_carried=False,
                location_building=self.mill,
                location_room=self.armoury,
            )

    def test_cannot_be_carried_and_in_a_room_at_once(self):
        with self.assertRaises(IntegrityError):
            Item.objects.create(
                owner=self.bela,
                name="Impossible",
                is_carried=True,
                location_room=self.armoury,
            )

    def test_deleting_the_room_leaves_the_item_stashed(self):
        self.chest.move_to(self.armoury)
        self.chest.save()
        self.armoury.delete()
        self.chest.refresh_from_db()
        self.assertFalse(self.chest.is_carried)
        self.assertIsNone(self.chest.location)

    def test_location_choices_list_a_buildings_rooms_after_it(self):
        choices = _location_choices()
        keys = [key for key, _ in choices]
        self.assertIn((f"room-{self.armoury.pk}", "Mill: Armoury"), choices)
        self.assertEqual(
            keys.index(f"room-{self.armoury.pk}"),
            keys.index(f"building-{self.mill.pk}") + 1,
        )

    def test_a_room_key_resolves_to_the_room(self):
        self.assertEqual(_location_from_key(f"room-{self.armoury.pk}"), self.armoury)
        self.assertIsNone(_location_from_key("room-99999"))

    def test_the_sheet_control_moves_an_item_into_a_room(self):
        self.client.login(username="alice", password="pass")
        response = self.client.post(
            f"/item/{self.chest.pk}/update-field/",
            {"field_name": "location", "value": f"room-{self.armoury.pk}"},
        )
        self.assertEqual(response.status_code, 200)
        self.chest.refresh_from_db()
        self.assertEqual(self.chest.location_room, self.armoury)

    def test_building_page_lists_items_in_its_rooms(self):
        self.chest.move_to(self.armoury)
        self.chest.save()
        self.client.login(username="alice", password="pass")
        response = self.client.get(f"/building/{self.mill.pk}/")
        self.assertContains(response, "Chest")

    def test_party_inventory_names_the_room_and_its_building(self):
        self.chest.move_to(self.armoury)
        self.chest.save()
        self.client.login(username="alice", password="pass")
        response = self.client.get("/party-inventory/")
        self.assertContains(response, "Mill: Armoury")
