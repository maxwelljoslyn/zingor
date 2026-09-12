"""Tests for the building design pages: starting a design and the editor page (#197)."""

from django.contrib.auth.models import User
from django.test import TestCase

from characters.design_document import SCHEMA_VERSION, empty_document
from characters.models import Building, Character, Design, DesignVersion


class DesignPageTests(TestCase):
    """Alice owns the mill through Bela; Carol owns nothing."""

    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pass")
        User.objects.create_user(username="carol", password="pass")
        bela = Character.objects.create(user=self.alice, name="Bela")
        self.mill = Building.objects.create(name="Mill")
        self.mill.owners.set([bela])
        self.client.login(username="alice", password="pass")

    def test_owner_starts_a_design_and_lands_in_the_editor(self):
        response = self.client.post(
            f"/building/{self.mill.pk}/designs/create/", {"name": "Main"}
        )
        design = Design.objects.get()
        self.assertRedirects(response, f"/building/{self.mill.pk}/design/{design.pk}/")
        self.assertIsNone(design.head)

    def test_a_design_may_start_from_an_existing_version(self):
        version = DesignVersion.objects.create(
            building=self.mill, schema_version=SCHEMA_VERSION, document=empty_document()
        )
        self.client.post(
            f"/building/{self.mill.pk}/designs/create/",
            {"name": "East wing", "from_version": version.pk},
        )
        self.assertEqual(Design.objects.get().head, version)

    def test_a_version_of_another_building_is_refused(self):
        barn = Building.objects.create(name="Barn")
        version = DesignVersion.objects.create(
            building=barn, schema_version=SCHEMA_VERSION, document=empty_document()
        )
        response = self.client.post(
            f"/building/{self.mill.pk}/designs/create/",
            {"name": "X", "from_version": version.pk},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Design.objects.exists())

    def test_names_must_be_given_and_unique(self):
        self.client.post(f"/building/{self.mill.pk}/designs/create/", {"name": "Main"})
        self.client.post(f"/building/{self.mill.pk}/designs/create/", {"name": "Main"})
        self.client.post(f"/building/{self.mill.pk}/designs/create/", {"name": " "})
        self.assertEqual(Design.objects.count(), 1)

    def test_a_non_owner_cannot_start_a_design(self):
        self.client.login(username="carol", password="pass")
        response = self.client.post(
            f"/building/{self.mill.pk}/designs/create/", {"name": "Main"}
        )
        self.assertEqual(response.status_code, 403)

    def test_parcels_have_no_designs(self):
        response = self.client.post("/parcel/1/designs/create/", {"name": "Main"})
        self.assertEqual(response.status_code, 404)

    def test_building_page_lists_designs_and_offers_the_form_to_owners(self):
        design = Design.objects.create(building=self.mill, name="Main")
        response = self.client.get(f"/building/{self.mill.pk}/")
        self.assertContains(
            response, f'href="/building/{self.mill.pk}/design/{design.pk}/"'
        )
        self.assertContains(response, "New Design")
        self.client.login(username="carol", password="pass")
        self.assertNotContains(
            self.client.get(f"/building/{self.mill.pk}/"), "New Design"
        )

    def test_editor_page_wires_the_script_to_its_endpoints(self):
        design = Design.objects.create(building=self.mill, name="Main")
        response = self.client.get(f"/building/{self.mill.pk}/design/{design.pk}/")
        base = f"/building/{self.mill.pk}/design/{design.pk}"
        self.assertContains(response, f'data-commit-url="{base}/commit/"')
        self.assertContains(response, "building-editor.js")
        self.assertContains(response, 'data-tool="wall"')

    def test_non_owners_get_the_editor_without_drawing_tools(self):
        design = Design.objects.create(building=self.mill, name="Main")
        self.client.login(username="carol", password="pass")
        response = self.client.get(f"/building/{self.mill.pk}/design/{design.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-tool="wall"')
        self.assertNotContains(response, "Save Version")
