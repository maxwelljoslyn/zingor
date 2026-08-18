"""Tests for Steam & Gasgear's built inventions and maintenance points.

Covers the invention catalogue, the InventionMaintenance model, the sheet's
flag/unflag/points views with their per-device cost caps, the pool summary,
and the plain-text mention a built invention gets in the wiki export.
"""

from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from characters import wiki_sync
from characters.models import (
    Character,
    InventionMaintenance,
    Item,
    SageStudyPoints,
)
from characters.sage import (
    Invention,
    canonical_invention,
    invention_catalogue,
    steam_gasgear_inventions,
)
from characters.wiki_export import character_to_wiki


class InventionCatalogueTests(TestCase):
    def test_an_ordinary_study_has_no_inventions(self):
        self.assertIsNone(invention_catalogue("Faith"))

    def test_a_concentrated_study_has_no_inventions_either(self):
        self.assertIsNone(invention_catalogue("History"))

    def test_steam_and_gasgear_has_the_wikis_devices(self):
        inventions = invention_catalogue("Steam & Gasgear")
        self.assertIs(inventions, steam_gasgear_inventions)
        by_name = {invention.name: invention for invention in inventions}
        self.assertEqual(by_name["Armoured Weave"].cost, 2)
        self.assertEqual(by_name["Gas Pistol"].cost, 3)
        self.assertEqual(by_name["Airship"].cost, 62)
        self.assertEqual(by_name["Airship"].rank, "sage")

    def test_mechanical_repair_is_a_skill_not_a_device(self):
        self.assertIsNone(canonical_invention("Steam & Gasgear", "Mechanical Repair I"))

    def test_the_catalogue_resolves_spelling_variants(self):
        # canonical_study's variants apply to the study's own name, and
        # _normalize's armour/armor fold applies to the device's.
        self.assertIsNotNone(invention_catalogue("steam and gasgear"))
        found = canonical_invention("Steam & Gasgear", "armored weave")
        self.assertEqual(found.name, "Armoured Weave")

    def test_an_unknown_device_has_no_catalogue_entry(self):
        # Unlike concentration names, an unheard-of device does not pass
        # through: without a catalogue entry it has no cost to look up.
        self.assertIsNone(canonical_invention("Steam & Gasgear", "Difference Engine"))

    def test_a_devices_cost_must_be_positive(self):
        with self.assertRaises(ValueError):
            Invention("Perpetual Motion Machine", 0, "sage")

    def test_a_catalogue_entry_cannot_be_edited_in_passing(self):
        with self.assertRaises(Exception):
            steam_gasgear_inventions[0].cost = 1


class InventionMaintenanceModelTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="marlys", password="pw")
        self.character = Character.objects.create(user=user, name="Marlys")
        self.study = SageStudyPoints.objects.create(
            character=self.character, study="Steam & Gasgear", points=12
        )
        self.pistol = Item.objects.create(
            owner=self.character, name="Pistol", props={"invention": "Gas Pistol"}
        )

    def test_maintenance_hangs_off_the_study_row(self):
        InventionMaintenance.objects.create(
            study=self.study, item=self.pistol, points=3
        )
        self.assertEqual(self.study.maintenance.count(), 1)

    def test_one_row_per_study_and_item(self):
        InventionMaintenance.objects.create(study=self.study, item=self.pistol)
        with self.assertRaises(Exception):
            InventionMaintenance.objects.create(study=self.study, item=self.pistol)

    def test_deleting_the_item_takes_its_maintenance(self):
        InventionMaintenance.objects.create(
            study=self.study, item=self.pistol, points=3
        )
        self.pistol.delete()
        self.assertEqual(InventionMaintenance.objects.count(), 0)

    def test_deleting_the_study_takes_its_maintenance(self):
        InventionMaintenance.objects.create(
            study=self.study, item=self.pistol, points=3
        )
        self.study.delete()
        self.assertEqual(InventionMaintenance.objects.count(), 0)
        self.assertTrue(Item.objects.filter(pk=self.pistol.pk).exists())


class MaintenanceSheetTests(TestCase):
    """The device rows, the pool summary, and the mark form on the sheet."""

    def setUp(self):
        self.user = User.objects.create_user(username="marlys", password="pw")
        self.character = Character.objects.create(
            user=self.user, name="Marlys", char_class="illusionist"
        )
        self.study = SageStudyPoints.objects.create(
            character=self.character, study="Steam & Gasgear", points=4
        )
        self.pistol = Item.objects.create(
            owner=self.character, name="Pistol", props={"invention": "Gas Pistol"}
        )
        self.goggles = Item.objects.create(
            owner=self.character,
            name="Goggles",
            props={"invention": "Infravision Goggles"},
        )
        self.client.login(username="marlys", password="pw")

    def _entry(self):
        response = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        )
        return {
            entry["name"]: entry
            for group in response.context["sage_studies_by_field"]
            for entry in group["entries"]
        }["Steam & Gasgear"]

    def test_flagged_items_are_listed_with_their_catalogue_cost(self):
        entry = self._entry()
        self.assertTrue(entry["has_maintenance"])
        devices = {m["item_name"]: m for m in entry["maintenance_items"]}
        self.assertEqual(devices["Pistol"]["invention"], "Gas Pistol")
        self.assertEqual(devices["Pistol"]["cost"], 3)
        self.assertEqual(devices["Goggles"]["cost"], 1)

    def test_a_flagged_item_shows_at_zero_before_any_allocation(self):
        devices = {m["item_name"]: m for m in self._entry()["maintenance_items"]}
        self.assertEqual(devices["Pistol"]["points"], 0)

    def test_the_pool_is_the_studys_knowledge_points(self):
        entry = self._entry()
        self.assertEqual(entry["maintenance_pool"], 4)
        self.assertEqual(entry["maintenance_delta"], 4)

    def test_a_total_beyond_the_pool_is_costed_to_assistants(self):
        # 3 + 1 fills the pool of 4; a velocipede's 7 on top must come from
        # hired help, and the sheet says how much rather than objecting.
        InventionMaintenance.objects.create(
            study=self.study, item=self.pistol, points=3
        )
        InventionMaintenance.objects.create(
            study=self.study, item=self.goggles, points=1
        )
        velocipede = Item.objects.create(
            owner=self.character,
            name="Velocipede",
            props={"invention": "Brass-fired Velocipede"},
        )
        InventionMaintenance.objects.create(study=self.study, item=velocipede, points=7)
        entry = self._entry()
        self.assertEqual(entry["maintenance_total"], 11)
        self.assertEqual(entry["maintenance_delta"], -7)
        self.assertEqual(entry["maintenance_assist"], 7)

    def test_two_copies_of_one_device_each_get_a_row(self):
        Item.objects.create(
            owner=self.character, name="Spare pistol", props={"invention": "Gas Pistol"}
        )
        names = [m["item_name"] for m in self._entry()["maintenance_items"]]
        self.assertEqual(names.count("Pistol"), 1)
        self.assertEqual(names.count("Spare pistol"), 1)

    def test_unflagged_items_are_offered_by_the_mark_form(self):
        Item.objects.create(owner=self.character, name="Bedroll")
        flaggable = [item.name for item in self._entry()["maintenance_flaggable"]]
        self.assertIn("Bedroll", flaggable)
        self.assertNotIn("Pistol", flaggable)

    def test_coin_stacks_are_never_offered(self):
        Item.objects.create(
            owner=self.character, name="Gold", currency="gp", quantity=50, weight=None
        )
        flaggable = [item.name for item in self._entry()["maintenance_flaggable"]]
        self.assertNotIn("Gold", flaggable)

    def test_a_device_dropped_from_the_catalogue_keeps_its_row_uncosted(self):
        Item.objects.create(
            owner=self.character,
            name="Old contraption",
            props={"invention": "Difference Engine"},
        )
        devices = {m["item_name"]: m for m in self._entry()["maintenance_items"]}
        self.assertEqual(devices["Old contraption"]["invention"], "Difference Engine")
        self.assertIsNone(devices["Old contraption"]["cost"])

    def test_an_ordinary_study_gets_no_maintenance_rows(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Faith", points=20
        )
        response = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        )
        entries = {
            entry["name"]: entry
            for group in response.context["sage_studies_by_field"]
            for entry in group["entries"]
        }
        self.assertFalse(entries["Faith"]["has_maintenance"])


class MaintenanceViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="marlys", password="pw")
        self.character = Character.objects.create(user=self.user, name="Marlys")
        self.study = SageStudyPoints.objects.create(
            character=self.character, study="Steam & Gasgear", points=4
        )
        self.pistol = Item.objects.create(owner=self.character, name="Pistol")
        self.client.login(username="marlys", password="pw")

    def _flag(self, item, invention):
        return self.client.post(
            reverse(
                "characters:sage_invention_flag",
                args=[self.character.pk, self.study.pk],
            ),
            {"item": item.pk, "invention": invention},
        )

    def _points(self, item, points):
        return self.client.post(
            reverse(
                "characters:sage_maintenance_points",
                args=[self.character.pk, self.study.pk, item.pk],
            ),
            {"points": points},
        )

    def test_flagging_marks_the_item(self):
        response = self._flag(self.pistol, "Gas Pistol")
        self.assertEqual(response.status_code, 200)
        self.pistol.refresh_from_db()
        self.assertEqual(self.pistol.props["invention"], "Gas Pistol")

    def test_a_typed_device_is_snapped_to_the_catalogues_spelling(self):
        self._flag(self.pistol, "gas pistol")
        self.pistol.refresh_from_db()
        self.assertEqual(self.pistol.props["invention"], "Gas Pistol")

    def test_flagging_keeps_the_items_other_props(self):
        self.pistol.props = {"percent_left": 50}
        self.pistol.save(update_fields=["props"])
        self._flag(self.pistol, "Gas Pistol")
        self.pistol.refresh_from_db()
        self.assertEqual(self.pistol.props["percent_left"], 50)

    def test_an_unknown_device_is_refused(self):
        response = self._flag(self.pistol, "Difference Engine")
        self.assertEqual(response.status_code, 400)

    def test_an_already_flagged_item_is_refused(self):
        self._flag(self.pistol, "Gas Pistol")
        response = self._flag(self.pistol, "Pocket Timepiece")
        self.assertEqual(response.status_code, 400)

    def test_flagging_under_a_study_with_no_inventions_is_refused(self):
        history = SageStudyPoints.objects.create(
            character=self.character, study="History", points=10
        )
        response = self.client.post(
            reverse(
                "characters:sage_invention_flag",
                args=[self.character.pk, history.pk],
            ),
            {"item": self.pistol.pk, "invention": "Gas Pistol"},
        )
        self.assertEqual(response.status_code, 400)

    def test_another_characters_item_cannot_be_flagged(self):
        other_user = User.objects.create_user(username="rook", password="pw")
        other = Character.objects.create(user=other_user, name="Rook")
        their_item = Item.objects.create(owner=other, name="Their pistol")
        response = self._flag(their_item, "Gas Pistol")
        self.assertEqual(response.status_code, 404)

    def test_flag_response_updates_the_inventory_section_out_of_band(self):
        response = self._flag(self.pistol, "Gas Pistol")
        html = response.content.decode()
        self.assertIn('id="section-sage"', html)
        self.assertIn('id="section-inventory" hx-swap-oob="outerHTML"', html)

    def test_points_up_to_the_devices_cost_are_accepted(self):
        self._flag(self.pistol, "Gas Pistol")
        response = self._points(self.pistol, 3)
        self.assertEqual(response.status_code, 200)
        row = InventionMaintenance.objects.get(study=self.study, item=self.pistol)
        self.assertEqual(row.points, 3)

    def test_points_beyond_the_devices_cost_are_refused(self):
        self._flag(self.pistol, "Gas Pistol")
        response = self._points(self.pistol, 4)
        self.assertEqual(response.status_code, 400)
        self.assertIn("at most 3 MP", response.content.decode())

    def test_negative_points_are_refused(self):
        self._flag(self.pistol, "Gas Pistol")
        self.assertEqual(self._points(self.pistol, -1).status_code, 400)

    def test_points_on_an_unflagged_item_are_refused(self):
        self.assertEqual(self._points(self.pistol, 1).status_code, 400)

    def test_setting_points_twice_updates_the_one_row(self):
        self._flag(self.pistol, "Gas Pistol")
        self._points(self.pistol, 3)
        self._points(self.pistol, 1)
        rows = InventionMaintenance.objects.filter(study=self.study, item=self.pistol)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().points, 1)

    def test_the_pool_never_caps_an_allocation(self):
        # 20 mp toward a glider against a pool of 4: the overage is what
        # assistants cover, so the view takes it without complaint.
        glider = Item.objects.create(owner=self.character, name="Glider")
        self._flag(glider, "Gyro-stabilised Steam Glider")
        self.assertEqual(self._points(glider, 20).status_code, 200)

    def test_unflagging_clears_the_mark_and_discards_maintenance(self):
        self._flag(self.pistol, "Gas Pistol")
        self._points(self.pistol, 3)
        response = self.client.post(
            reverse(
                "characters:sage_invention_unflag",
                args=[self.character.pk, self.pistol.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.pistol.refresh_from_db()
        self.assertNotIn("invention", self.pistol.props)
        self.assertEqual(InventionMaintenance.objects.count(), 0)
        self.assertTrue(Item.objects.filter(pk=self.pistol.pk).exists())

    def test_unflagging_an_unflagged_item_is_refused(self):
        response = self.client.post(
            reverse(
                "characters:sage_invention_unflag",
                args=[self.character.pk, self.pistol.pk],
            )
        )
        self.assertEqual(response.status_code, 400)

    def test_a_non_owner_may_not_touch_any_of_it(self):
        self._flag(self.pistol, "Gas Pistol")
        User.objects.create_user(username="rook", password="pw")
        self.client.login(username="rook", password="pw")
        flag = self._flag(self.pistol, "Pocket Timepiece")
        points = self._points(self.pistol, 1)
        unflag = self.client.post(
            reverse(
                "characters:sage_invention_unflag",
                args=[self.character.pk, self.pistol.pk],
            )
        )
        for response in (flag, points, unflag):
            self.assertEqual(response.status_code, 403)


class MaintenanceLifecycleTests(TestCase):
    """The mark and the allocations across splits, deletion, and wiki sync."""

    def setUp(self):
        self.user = User.objects.create_user(username="marlys", password="pw")
        self.character = Character.objects.create(user=self.user, name="Marlys")
        self.study = SageStudyPoints.objects.create(
            character=self.character, study="Steam & Gasgear", points=4
        )
        self.pistols = Item.objects.create(
            owner=self.character,
            name="Pistol",
            quantity=2,
            props={"invention": "Gas Pistol"},
        )
        self.client.login(username="marlys", password="pw")

    def test_splitting_a_stack_carries_the_mark_to_the_new_row(self):
        self.client.post(
            reverse("characters:split_item", args=[self.pistols.pk]), {"count": 1}
        )
        marked = [
            item
            for item in self.character.inventory.all()
            if (item.props or {}).get("invention") == "Gas Pistol"
        ]
        self.assertEqual(len(marked), 2)

    def test_deleting_the_item_takes_its_allocation_with_it(self):
        InventionMaintenance.objects.create(
            study=self.study, item=self.pistols, points=3
        )
        self.client.delete(reverse("characters:delete_item", args=[self.pistols.pk]))
        self.assertEqual(InventionMaintenance.objects.count(), 0)

    def test_a_wiki_sync_leaves_marks_and_allocations_alone(self):
        # The page restates the study; the mark and the allocation are local
        # sheet state, so the sync must touch neither.
        InventionMaintenance.objects.create(
            study=self.study, item=self.pistols, points=3
        )
        self.character.wiki_url = "https://example.test/Marlys"
        self.character.save()
        page = (
            "<table><tr class='zingor-sage-study'>"
            + "<td class='zingor-sage-study-name'>Steam &amp; Gasgear</td>"
            + "<td class='zingor-sage-study-points'>6</td></tr></table>"
        )
        with mock.patch.object(wiki_sync, "fetch_page", return_value=page):
            wiki_sync.sync_character_from_wiki(self.character)
        self.study.refresh_from_db()
        self.assertEqual(self.study.points, 6)
        self.pistols.refresh_from_db()
        self.assertEqual(self.pistols.props["invention"], "Gas Pistol")
        row = InventionMaintenance.objects.get(study=self.study, item=self.pistols)
        self.assertEqual(row.points, 3)


class MaintenanceExportTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="marlys", password="pw")
        self.character = Character.objects.create(user=user, name="Marlys")

    def test_a_built_invention_is_mentioned_in_the_items_status(self):
        Item.objects.create(
            owner=self.character, name="Pistol", props={"invention": "Gas Pistol"}
        )
        wikitext = character_to_wiki(self.character)
        self.assertIn("invention (Gas Pistol)", wikitext)

    def test_the_mention_is_plain_text_never_zmf(self):
        # Items are not ZMF records; a zingor- class here would invite a
        # parser to read back what must stay local.
        Item.objects.create(
            owner=self.character, name="Pistol", props={"invention": "Gas Pistol"}
        )
        wikitext = character_to_wiki(self.character)
        for line in wikitext.splitlines():
            if "Gas Pistol" in line:
                self.assertNotIn("zingor-", line)

    def test_an_ordinary_item_gets_no_mention(self):
        Item.objects.create(owner=self.character, name="Bedroll")
        wikitext = character_to_wiki(self.character)
        self.assertNotIn("invention", wikitext)


class MaintenanceInventorySyncTests(TestCase):
    """Inventory mutations keep the sage section's item lists fresh.

    The mark-items picker and the device rows are read off the item table, so
    the views that add, remove, split, or rename items append an out-of-band
    re-render of the sage section — but only for characters whose sage section
    lists the inventory at all.
    """

    SAGE_OOB = 'id="section-sage" hx-swap-oob="outerHTML"'

    def setUp(self):
        self.user = User.objects.create_user(username="marlys", password="pw")
        self.character = Character.objects.create(user=self.user, name="Marlys")
        self.study = SageStudyPoints.objects.create(
            character=self.character, study="Steam & Gasgear", points=4
        )
        self.client.login(username="marlys", password="pw")

    def test_adding_an_item_refreshes_the_sage_section(self):
        response = self.client.post(
            reverse("characters:add_item", args=[self.character.pk]),
            {"name": "Brass whistle", "weight": "1", "pint_unit": "ounce"},
        )
        html = response.content.decode()
        self.assertIn(self.SAGE_OOB, html)
        # The new item is already offered by the mark-items picker: it appears
        # inside the out-of-band sage fragment, not just in the inventory table.
        sage_fragment = html.split(self.SAGE_OOB, 1)[1]
        self.assertIn("Brass whistle", sage_fragment)

    def test_no_sage_refresh_without_an_invention_study(self):
        self.study.delete()
        response = self.client.post(
            reverse("characters:add_item", args=[self.character.pk]),
            {"name": "Brass whistle", "weight": "1", "pint_unit": "ounce"},
        )
        self.assertNotIn(self.SAGE_OOB, response.content.decode())

    def test_a_hidden_invention_study_does_not_count(self):
        self.study.hidden = True
        self.study.save(update_fields=["hidden"])
        response = self.client.post(
            reverse("characters:add_item", args=[self.character.pk]),
            {"name": "Brass whistle", "weight": "1", "pint_unit": "ounce"},
        )
        self.assertNotIn(self.SAGE_OOB, response.content.decode())

    def test_deleting_an_item_refreshes_the_sage_section(self):
        item = Item.objects.create(owner=self.character, name="Bedroll")
        response = self.client.delete(reverse("characters:delete_item", args=[item.pk]))
        self.assertIn(self.SAGE_OOB, response.content.decode())

    def test_splitting_a_stack_refreshes_the_sage_section(self):
        stack = Item.objects.create(
            owner=self.character,
            name="Pistol",
            quantity=2,
            props={"invention": "Gas Pistol"},
        )
        response = self.client.post(
            reverse("characters:split_item", args=[stack.pk]), {"count": 1}
        )
        self.assertIn(self.SAGE_OOB, response.content.decode())

    def test_renaming_an_item_takes_the_section_path_and_refreshes_sage(self):
        item = Item.objects.create(
            owner=self.character, name="Pistol", props={"invention": "Gas Pistol"}
        )
        response = self.client.post(
            reverse("characters:update_item_field", args=[item.pk]),
            {"field_name": "name", "value": "Marlys's pistol"},
        )
        html = response.content.decode()
        self.assertIn('id="section-inventory"', html)
        self.assertIn(self.SAGE_OOB, html)
        # Once in the inventory row and once in the sage device row.
        self.assertGreaterEqual(html.count("Marlys&#x27;s pistol"), 2)

    def test_the_rename_edit_form_targets_the_section(self):
        # edit_item_field and update_item_field must agree on the target, or
        # the section response would be swapped into the bare row's place.
        item = Item.objects.create(owner=self.character, name="Pistol")
        response = self.client.get(
            reverse("characters:edit_item_field", args=[item.pk]),
            {"field": "name"},
        )
        self.assertIn('hx-target="#section-inventory"', response.content.decode())

    def test_a_rename_without_an_invention_study_stays_row_level(self):
        self.study.delete()
        item = Item.objects.create(owner=self.character, name="Pistol")
        form = self.client.get(
            reverse("characters:edit_item_field", args=[item.pk]),
            {"field": "name"},
        )
        self.assertIn(f'hx-target="#item-{item.pk}"', form.content.decode())
        response = self.client.post(
            reverse("characters:update_item_field", args=[item.pk]),
            {"field_name": "name", "value": "Bent pistol"},
        )
        html = response.content.decode()
        self.assertNotIn('id="section-inventory"', html)
        self.assertNotIn(self.SAGE_OOB, html)

    def test_a_capacity_edit_stays_row_level_even_with_the_study(self):
        item = Item.objects.create(
            owner=self.character, name="Satchel", is_container=True
        )
        form = self.client.get(
            reverse("characters:edit_item_field", args=[item.pk]),
            {"field": "capacity"},
        )
        self.assertIn(f'hx-target="#item-{item.pk}"', form.content.decode())
