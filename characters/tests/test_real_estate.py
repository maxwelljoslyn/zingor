"""Tests for parcels and buildings: the party's real estate (#196)."""

from django.contrib.auth.models import AnonymousUser, User
from django.db import IntegrityError
from django.test import TestCase

from characters.models import Building, Character, Item, Parcel
from characters.units import D, u


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


class RealEstatePageTests(RealEstateBase):
    def setUp(self):
        super().setUp()
        self.mill = Building.objects.create(name="Mill", parcel=self.parcel)
        self.mill.owners.set([self.bela])
        self.client.login(username="alice", password="pass")

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get("/real-estate/")
        self.assertEqual(response.status_code, 302)

    def test_lists_parcels_and_buildings_with_owners(self):
        response = self.client.get("/real-estate/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Home Parcel")
        self.assertContains(response, "Mill")
        self.assertContains(response, "Ferenc")
        self.assertContains(response, f"/parcel/{self.parcel.pk}/")
        self.assertContains(response, f"/building/{self.mill.pk}/")

    def test_header_links_to_the_page(self):
        response = self.client.get("/")
        self.assertContains(response, 'href="/real-estate/"')

    def test_create_forms_offer_only_the_users_characters(self):
        response = self.client.get("/real-estate/")
        self.assertContains(response, f'<option value="{self.bela.pk}">Bela')
        self.assertNotContains(response, f'<option value="{self.ferenc.pk}">Ferenc')

    def test_no_characters_means_no_create_forms(self):
        self.client.login(username="carol", password="pass")
        self.gizi.delete()
        response = self.client.get("/real-estate/")
        self.assertContains(response, "Create a character first")
        self.assertNotContains(response, "Add Parcel")

    def test_create_parcel(self):
        response = self.client.post(
            "/parcel/create/", {"name": "East Field", "owner": self.bela.pk}
        )
        parcel = Parcel.objects.get(name="East Field")
        self.assertRedirects(response, f"/parcel/{parcel.pk}/")
        self.assertEqual(list(parcel.owners.all()), [self.bela])

    def test_create_building_on_a_parcel(self):
        response = self.client.post(
            "/building/create/",
            {"name": "Barn", "owner": self.bela.pk, "parcel": self.parcel.pk},
        )
        barn = Building.objects.get(name="Barn")
        self.assertRedirects(response, f"/building/{barn.pk}/")
        self.assertEqual(barn.parcel, self.parcel)

    def test_create_building_without_a_parcel(self):
        self.client.post(
            "/building/create/", {"name": "Town house", "owner": self.bela.pk}
        )
        self.assertIsNone(Building.objects.get(name="Town house").parcel)

    def test_create_refuses_someone_elses_character_as_first_owner(self):
        response = self.client.post(
            "/parcel/create/", {"name": "Stolen", "owner": self.ferenc.pk}
        )
        self.assertRedirects(response, "/real-estate/")
        self.assertFalse(Parcel.objects.filter(name="Stolen").exists())

    def test_create_refuses_a_blank_name(self):
        self.client.post("/parcel/create/", {"name": "   ", "owner": self.bela.pk})
        self.assertEqual(Parcel.objects.count(), 1)

    def test_unknown_kind_is_not_a_real_estate_url(self):
        self.assertEqual(self.client.get("/castle/1/").status_code, 404)

    def test_detail_page_shows_owners_players_and_buildings(self):
        response = self.client.get(f"/parcel/{self.parcel.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bela")
        self.assertContains(response, "Ferenc")
        self.assertContains(response, "/users/bob/")
        self.assertContains(response, "Mill")

    def test_building_page_links_its_parcel(self):
        response = self.client.get(f"/building/{self.mill.pk}/")
        self.assertContains(response, f'href="/parcel/{self.parcel.pk}/"')

    def test_non_owner_sees_no_edit_controls(self):
        self.client.login(username="carol", password="pass")
        response = self.client.get(f"/parcel/{self.parcel.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add Owner")
        self.assertNotContains(response, "/update/")
        self.assertNotContains(response, "/delete/")

    def test_owner_sees_edit_controls(self):
        response = self.client.get(f"/parcel/{self.parcel.pk}/")
        self.assertContains(response, "Add Owner")
        self.assertContains(response, f"/parcel/{self.parcel.pk}/update/")
        self.assertContains(response, f"/parcel/{self.parcel.pk}/delete/")

    def test_update_name_and_notes(self):
        response = self.client.post(
            f"/parcel/{self.parcel.pk}/update/",
            {"name": "Homestead", "notes": "By the stream."},
        )
        self.assertRedirects(response, f"/parcel/{self.parcel.pk}/")
        self.parcel.refresh_from_db()
        self.assertEqual(self.parcel.name, "Homestead")
        self.assertEqual(self.parcel.notes, "By the stream.")

    def test_update_keeps_the_old_name_when_blank(self):
        self.client.post(
            f"/parcel/{self.parcel.pk}/update/", {"name": "", "notes": "x"}
        )
        self.parcel.refresh_from_db()
        self.assertEqual(self.parcel.name, "Home Parcel")

    def test_update_moves_a_building_between_parcels(self):
        other = Parcel.objects.create(name="Other")
        self.client.post(
            f"/building/{self.mill.pk}/update/",
            {"name": "Mill", "notes": "", "parcel": other.pk},
        )
        self.mill.refresh_from_db()
        self.assertEqual(self.mill.parcel, other)
        self.client.post(
            f"/building/{self.mill.pk}/update/",
            {"name": "Mill", "notes": "", "parcel": ""},
        )
        self.mill.refresh_from_db()
        self.assertIsNone(self.mill.parcel)

    def test_add_owner_accepts_any_character(self):
        self.client.post(
            f"/parcel/{self.parcel.pk}/owners/add/", {"character": self.gizi.pk}
        )
        self.assertIn(self.gizi, self.parcel.owners.all())
        self.assertTrue(self.parcel.can_edit(self.carol))

    def test_add_owner_form_omits_current_owners(self):
        response = self.client.get(f"/parcel/{self.parcel.pk}/")
        self.assertContains(response, f'<option value="{self.gizi.pk}">Gizi')
        self.assertNotContains(response, f'<option value="{self.bela.pk}">Bela')

    def test_remove_owner(self):
        self.client.post(f"/parcel/{self.parcel.pk}/owners/{self.ferenc.pk}/remove/")
        self.assertEqual(list(self.parcel.owners.all()), [self.bela])

    def test_removing_own_last_character_hands_it_over(self):
        self.client.post(f"/parcel/{self.parcel.pk}/owners/{self.bela.pk}/remove/")
        self.assertFalse(self.parcel.can_edit(self.alice))
        self.assertEqual(self.client.get(f"/parcel/{self.parcel.pk}/").status_code, 200)

    def test_cannot_remove_the_last_owner(self):
        response = self.client.post(
            f"/building/{self.mill.pk}/owners/{self.bela.pk}/remove/"
        )
        self.assertRedirects(response, f"/building/{self.mill.pk}/")
        self.assertEqual(list(self.mill.owners.all()), [self.bela])

    def test_last_owner_has_no_remove_button(self):
        response = self.client.get(f"/building/{self.mill.pk}/")
        self.assertNotContains(response, f"/owners/{self.bela.pk}/remove/")

    def test_remove_of_a_non_owner_is_404(self):
        response = self.client.post(
            f"/parcel/{self.parcel.pk}/owners/{self.gizi.pk}/remove/"
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_redirects_to_the_list(self):
        response = self.client.post(f"/building/{self.mill.pk}/delete/")
        self.assertRedirects(response, "/real-estate/")
        self.assertFalse(Building.objects.filter(pk=self.mill.pk).exists())

    def test_delete_from_htmx_navigates_with_hx_redirect(self):
        response = self.client.post(
            f"/parcel/{self.parcel.pk}/delete/", headers={"HX-Request": "true"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["HX-Redirect"], "/real-estate/")
        self.assertFalse(Parcel.objects.filter(pk=self.parcel.pk).exists())
        self.mill.refresh_from_db()
        self.assertIsNone(self.mill.parcel)

    def test_get_is_not_a_delete(self):
        response = self.client.get(f"/parcel/{self.parcel.pk}/delete/")
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Parcel.objects.filter(pk=self.parcel.pk).exists())


class RealEstatePermissionTests(RealEstateBase):
    """Only the players of owning characters may change a parcel/building."""

    def setUp(self):
        super().setUp()
        self.client.login(username="carol", password="pass")

    def test_non_owner_cannot_update(self):
        response = self.client.post(
            f"/parcel/{self.parcel.pk}/update/", {"name": "Mine now", "notes": ""}
        )
        self.assertEqual(response.status_code, 403)
        self.parcel.refresh_from_db()
        self.assertEqual(self.parcel.name, "Home Parcel")

    def test_non_owner_cannot_add_themselves(self):
        response = self.client.post(
            f"/parcel/{self.parcel.pk}/owners/add/", {"character": self.gizi.pk}
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(self.gizi, self.parcel.owners.all())

    def test_non_owner_cannot_remove_an_owner(self):
        response = self.client.post(
            f"/parcel/{self.parcel.pk}/owners/{self.bela.pk}/remove/"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.parcel.owners.count(), 2)

    def test_non_owner_cannot_delete(self):
        response = self.client.post(f"/parcel/{self.parcel.pk}/delete/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Parcel.objects.filter(pk=self.parcel.pk).exists())

    def test_co_owner_through_a_second_player_can_edit(self):
        """Ownership through Ferenc gives Bob, not just Alice, the edit right."""
        self.client.login(username="bob", password="pass")
        response = self.client.post(
            f"/parcel/{self.parcel.pk}/update/", {"name": "Ours", "notes": ""}
        )
        self.assertRedirects(response, f"/parcel/{self.parcel.pk}/")


class ItemLocationModelTests(RealEstateBase):
    """Item.location: where a not-carried item is kept (#196)."""

    def setUp(self):
        super().setUp()
        self.mill = Building.objects.create(name="Mill", parcel=self.parcel)
        self.chest = Item.objects.create(owner=self.bela, name="Chest", weight="10 lb")

    def test_new_item_is_carried_with_no_location(self):
        self.assertTrue(self.chest.is_carried)
        self.assertIsNone(self.chest.location)
        self.assertEqual(self.chest.location_key, "carried")

    def test_move_to_a_building(self):
        self.chest.move_to(self.mill)
        self.chest.save()
        self.chest.refresh_from_db()
        self.assertFalse(self.chest.is_carried)
        self.assertEqual(self.chest.location, self.mill)
        self.assertEqual(self.chest.location_key, f"building-{self.mill.pk}")

    def test_move_to_a_parcel(self):
        self.chest.move_to(self.parcel)
        self.assertEqual(self.chest.location, self.parcel)
        self.assertEqual(self.chest.location_key, f"parcel-{self.parcel.pk}")

    def test_move_between_parcel_and_building_clears_the_other_link(self):
        self.chest.move_to(self.parcel)
        self.chest.move_to(self.mill)
        self.assertIsNone(self.chest.location_parcel)
        self.assertEqual(self.chest.location_building, self.mill)

    def test_stashed_is_not_carried_and_nowhere_in_particular(self):
        self.chest.move_to(Item.STASHED)
        self.assertFalse(self.chest.is_carried)
        self.assertIsNone(self.chest.location)
        self.assertEqual(self.chest.location_key, "stashed")

    def test_picking_up_again_clears_the_location(self):
        self.chest.move_to(self.mill)
        self.chest.move_to(Item.CARRIED)
        self.assertTrue(self.chest.is_carried)
        self.assertIsNone(self.chest.location)

    def test_leaving_the_character_takes_the_item_off(self):
        self.chest.is_worn = True
        self.chest.move_to(self.mill)
        self.assertFalse(self.chest.is_worn)

    def test_item_at_a_building_does_not_count_toward_encumbrance(self):
        self.chest.move_to(self.mill)
        self.chest.save()
        self.assertEqual(self.bela.current_encumbrance.to(u.lb).magnitude, D(0))

    def test_cannot_be_at_a_parcel_and_a_building_at_once(self):
        with self.assertRaises(IntegrityError):
            Item.objects.create(
                owner=self.bela,
                name="Impossible",
                is_carried=False,
                location_parcel=self.parcel,
                location_building=self.mill,
            )

    def test_cannot_be_carried_and_at_a_building_at_once(self):
        with self.assertRaises(IntegrityError):
            Item.objects.create(
                owner=self.bela,
                name="Impossible",
                is_carried=True,
                location_building=self.mill,
            )

    def test_deleting_the_building_leaves_the_item_stashed(self):
        self.chest.move_to(self.mill)
        self.chest.save()
        self.mill.delete()
        self.chest.refresh_from_db()
        self.assertFalse(self.chest.is_carried)
        self.assertIsNone(self.chest.location)

    def test_building_lists_what_is_kept_there(self):
        self.chest.move_to(self.mill)
        self.chest.save()
        self.assertEqual(list(self.mill.stored_items.all()), [self.chest])


class ItemLocationViewTests(RealEstateBase):
    """The inventory row's Location control and its knock-on effects."""

    def setUp(self):
        super().setUp()
        self.mill = Building.objects.create(name="Mill", parcel=self.parcel)
        self.mill.owners.set([self.bela])
        self.chest = Item.objects.create(
            owner=self.bela, name="Chest", weight="10 lb", is_container=True
        )
        self.coins = Item.objects.create(
            owner=self.bela,
            name="gold pieces",
            weight=None,
            currency="gp",
            quantity=40,
            container=self.chest,
        )
        self.client.login(username="alice", password="pass")

    def _set_location(self, item, key):
        return self.client.post(
            f"/item/{item.pk}/update-field/", {"field_name": "location", "value": key}
        )

    def test_row_offers_every_parcel_and_building_as_a_location(self):
        response = self.client.get(f"/character/{self.bela.pk}/")
        self.assertContains(response, 'value="carried" selected')
        self.assertContains(response, 'value="stashed"')
        self.assertContains(response, f'value="parcel-{self.parcel.pk}"')
        self.assertContains(
            response, f'value="building-{self.mill.pk}">Mill (Home Parcel)'
        )

    def test_leave_at_a_building(self):
        response = self._set_location(self.chest, f"building-{self.mill.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="section-inventory"')
        self.assertContains(response, 'id="section-abilities" hx-swap-oob="outerHTML"')
        self.chest.refresh_from_db()
        self.assertEqual(self.chest.location, self.mill)
        self.assertFalse(self.chest.is_carried)

    def test_leave_at_a_parcel_anyone_owns(self):
        """Any parcel/building will do, not only the character's own."""
        field = Parcel.objects.create(name="Gizi's Field")
        field.owners.set([self.gizi])
        self._set_location(self.chest, f"parcel-{field.pk}")
        self.chest.refresh_from_db()
        self.assertEqual(self.chest.location, field)

    def test_a_container_takes_its_contents_along(self):
        self._set_location(self.chest, f"building-{self.mill.pk}")
        self.coins.refresh_from_db()
        self.assertEqual(self.coins.location, self.mill)
        self.assertFalse(self.coins.is_carried)
        self._set_location(self.chest, "carried")
        self.coins.refresh_from_db()
        self.assertTrue(self.coins.is_carried)
        self.assertIsNone(self.coins.location)

    def test_wearing_brings_the_item_back(self):
        cloak = Item.objects.create(owner=self.bela, name="Cloak")
        self._set_location(cloak, f"building-{self.mill.pk}")
        self.client.post(
            f"/item/{cloak.pk}/update-field/", {"field_name": "is_worn", "value": "on"}
        )
        cloak.refresh_from_db()
        self.assertTrue(cloak.is_worn)
        self.assertTrue(cloak.is_carried)
        self.assertIsNone(cloak.location)

    def test_unknown_location_is_refused(self):
        for bad in ("", "castle-1", f"building-{self.mill.pk + 99}", "building-x"):
            response = self._set_location(self.chest, bad)
            self.assertEqual(response.status_code, 400, bad)
        self.chest.refresh_from_db()
        self.assertTrue(self.chest.is_carried)

    def test_putting_an_item_in_a_container_takes_it_where_the_container_is(self):
        self._set_location(self.chest, f"building-{self.mill.pk}")
        rope = Item.objects.create(owner=self.bela, name="Rope", weight="5 lb")
        self.client.post(
            f"/item/{self.chest.pk}/put-in-container/", {"item_id": rope.pk}
        )
        rope.refresh_from_db()
        self.assertEqual(rope.container, self.chest)
        self.assertEqual(rope.location, self.mill)
        self.assertFalse(rope.is_carried)

    def test_split_keeps_the_location(self):
        rope = Item.objects.create(
            owner=self.bela, name="Rope", weight="5 lb", quantity=3
        )
        self._set_location(rope, f"parcel-{self.parcel.pk}")
        self.client.post(f"/item/{rope.pk}/split/", {"count": 1})
        new = Item.objects.filter(name="Rope").exclude(pk=rope.pk).get()
        self.assertEqual(new.location, self.parcel)
        self.assertFalse(new.is_carried)

    def test_only_the_owner_moves_an_item(self):
        self.client.login(username="bob", password="pass")
        response = self._set_location(self.chest, f"building-{self.mill.pk}")
        self.assertEqual(response.status_code, 403)

    def test_building_page_shows_what_is_kept_there(self):
        self._set_location(self.chest, f"building-{self.mill.pk}")
        response = self.client.get(f"/building/{self.mill.pk}/")
        self.assertContains(response, "Kept Here")
        self.assertContains(response, "Chest")
        # The coins are inside the chest: shown as its contents, once, not as a second root.
        self.assertContains(response, f'data-item-id="{self.coins.pk}"', count=1)
        self.assertContains(response, f'data-parent-id="{self.chest.pk}"')

    def test_parcel_page_with_nothing_kept(self):
        response = self.client.get(f"/parcel/{self.parcel.pk}/")
        self.assertContains(response, "Nothing is kept here")

    def test_other_players_see_the_location_as_a_link(self):
        self._set_location(self.chest, f"building-{self.mill.pk}")
        self.client.login(username="bob", password="pass")
        response = self.client.get(f"/character/{self.bela.pk}/")
        self.assertContains(response, f'href="/building/{self.mill.pk}/"')
        self.assertNotContains(response, 'name="field_name" value="location"')

    def test_party_inventory_names_the_location(self):
        self._set_location(self.chest, f"building-{self.mill.pk}")
        response = self.client.get("/")
        self.assertContains(response, "<th>Location</th>")
        self.assertContains(response, f'href="/building/{self.mill.pk}/"')

    def test_wiki_export_names_the_building(self):
        self._set_location(self.chest, f"building-{self.mill.pk}")
        response = self.client.get(f"/character/{self.bela.pk}/wiki-export/")
        self.assertContains(response, "at Mill")
