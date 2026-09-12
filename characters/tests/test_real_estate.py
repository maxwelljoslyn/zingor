"""Tests for parcels and buildings: the party's real estate (#196)."""

from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase

from characters.models import Building, Character, Parcel


class RealEstateBase(TestCase):
    """Two players, three characters, and a parcel two of them own together."""

    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pass")
        self.bob = User.objects.create_user(username="bob", password="pass")
        self.carol = User.objects.create_user(username="carol", password="pass")
        self.bela = Character.objects.create(user=self.alice, name="Bela")
        self.ferenc = Character.objects.create(user=self.bob, name="Ferenc")
        self.gizi = Character.objects.create(user=self.carol, name="Gizi")
        self.parcel = Parcel.objects.create(name="Home Parcel")
        self.parcel.owners.set([self.bela, self.ferenc])


class OwnershipTests(RealEstateBase):
    def test_owning_characters_players_can_edit(self):
        self.assertTrue(self.parcel.can_edit(self.alice))
        self.assertTrue(self.parcel.can_edit(self.bob))

    def test_other_players_cannot_edit(self):
        self.assertFalse(self.parcel.can_edit(self.carol))
        self.assertFalse(self.parcel.can_edit(AnonymousUser()))

    def test_inactive_owner_still_grants_edit(self):
        """A character's death must not lock their player out of the parcel."""
        self.bela.is_active = False
        self.bela.save()
        self.assertTrue(self.parcel.can_edit(self.alice))

    def test_ownership_is_a_character_fact(self):
        """A player who owns through one character owns through that character
        alone: the reverse relation lists the parcel under the character."""
        self.assertEqual(list(self.bela.parcels.all()), [self.parcel])
        self.assertEqual(list(self.gizi.parcels.all()), [])

    def test_editors_are_deduplicated_across_a_players_characters(self):
        second = Character.objects.create(user=self.alice, name="Bela's hench")
        self.parcel.owners.add(second)
        self.assertEqual(self.parcel.editors(), {self.alice, self.bob})


class BuildingTests(RealEstateBase):
    def test_building_may_stand_on_a_parcel(self):
        mill = Building.objects.create(name="Mill", parcel=self.parcel)
        self.assertEqual(list(self.parcel.buildings.all()), [mill])

    def test_building_may_stand_alone(self):
        inn = Building.objects.create(name="Town house")
        self.assertIsNone(inn.parcel)

    def test_deleting_a_parcel_leaves_its_buildings_standing(self):
        mill = Building.objects.create(name="Mill", parcel=self.parcel)
        self.parcel.delete()
        mill.refresh_from_db()
        self.assertIsNone(mill.parcel)

    def test_building_ownership_is_independent_of_the_parcels(self):
        mill = Building.objects.create(name="Mill", parcel=self.parcel)
        mill.owners.set([self.gizi])
        self.assertTrue(mill.can_edit(self.carol))
        self.assertFalse(mill.can_edit(self.alice))

    def test_deleting_an_owner_character_drops_them_from_the_set(self):
        self.ferenc.delete()
        self.assertEqual(list(self.parcel.owners.all()), [self.bela])
