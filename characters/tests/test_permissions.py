"""Tests for the view-open/edit-closed permissions model.

Any logged-in user can view any character. Only the character's owner can
hit mutation endpoints; non-owners get 403.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from characters.models import Character, Condition, HitDie, Item, SageStudyPoints, Spell


class PermissionsTestBase(TestCase):
    """Shared setUp: two users, a character owned by user_a, and related objects."""

    def setUp(self):
        self.user_a = User.objects.create_user(username="owner", password="pass")
        self.user_b = User.objects.create_user(username="viewer", password="pass")
        self.character = Character.objects.create(
            user=self.user_a,
            name="Thorn",
            strength=16,
            char_class="fighter",
            level=3,
        )
        self.item = Item.objects.create(
            owner=self.character, name="Sword", weight="3 lb"
        )
        self.container = Item.objects.create(
            owner=self.character,
            name="Backpack",
            weight="2 lb",
            is_container=True,
        )
        self.condition = Condition.objects.create(
            character=self.character,
            modifier_type="ability",
            target="strength",
            value=2,
            source="Bull's Strength",
        )
        self.hit_die = HitDie.objects.create(
            character=self.character, level=1, die_type="d10", roll=8, con_bonus=1
        )
        self.spell = Spell.objects.create(
            character=self.character, name="Magic Missile", level=1
        )
        self.sage_row = SageStudyPoints.objects.create(
            character=self.character, study="Forgery", points=5
        )

    def login_as_owner(self):
        self.client.login(username="owner", password="pass")

    def login_as_viewer(self):
        self.client.login(username="viewer", password="pass")


class ViewPermissionsTests(PermissionsTestBase):
    """Non-owners can view character sheets and related read-only endpoints."""

    def test_viewer_can_see_character_sheet(self):
        self.login_as_viewer()
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thorn")

    def test_viewer_sees_owner_attribution(self):
        self.login_as_viewer()
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, "'s character)")
        self.assertContains(response, 'href="/users/owner/"')

    def test_owner_does_not_see_attribution(self):
        self.login_as_owner()
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertNotContains(response, "'s character)")

    def test_viewer_can_refresh_section(self):
        self.login_as_viewer()
        response = self.client.get(f"/character/{self.character.pk}/section/identity/")
        self.assertEqual(response.status_code, 200)

    def test_viewer_can_access_wiki_export(self):
        self.login_as_viewer()
        response = self.client.get(f"/character/{self.character.pk}/wiki-export/")
        self.assertEqual(response.status_code, 200)

    def test_viewer_sheet_hides_edit_controls(self):
        self.login_as_viewer()
        response = self.client.get(f"/character/{self.character.pk}/")
        content = response.content.decode()
        self.assertNotIn("click to set", content.lower())
        self.assertNotIn("hx-post", content)
        self.assertNotIn("hx-delete", content)

    def test_owner_sheet_shows_edit_controls(self):
        self.login_as_owner()
        response = self.client.get(f"/character/{self.character.pk}/")
        content = response.content.decode()
        self.assertIn("hx-post", content)


class CharacterFieldPermissionsTests(PermissionsTestBase):
    """edit_field and update_field are owner-only."""

    def test_owner_can_edit_field(self):
        self.login_as_owner()
        response = self.client.get(
            f"/character/{self.character.pk}/edit-field/?field=strength"
        )
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_edit_field(self):
        self.login_as_viewer()
        response = self.client.get(
            f"/character/{self.character.pk}/edit-field/?field=strength"
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_update_field(self):
        self.login_as_owner()
        response = self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "strength", "value": "17"},
        )
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertEqual(self.character.strength, 17)

    def test_viewer_cannot_update_field(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "strength", "value": "17"},
        )
        self.assertEqual(response.status_code, 403)
        self.character.refresh_from_db()
        self.assertEqual(self.character.strength, 16)


class ItemPermissionsTests(PermissionsTestBase):
    """Item CRUD and field editing are owner-only."""

    def test_owner_can_add_item(self):
        self.login_as_owner()
        response = self.client.post(
            f"/character/{self.character.pk}/add-item/",
            {"name": "Shield", "weight": "5 lb"},
        )
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_add_item(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/character/{self.character.pk}/add-item/",
            {"name": "Shield", "weight": "5 lb"},
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_delete_item(self):
        self.login_as_owner()
        response = self.client.delete(f"/item/{self.item.pk}/delete/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Item.objects.filter(pk=self.item.pk).exists())

    def test_viewer_cannot_delete_item(self):
        self.login_as_viewer()
        response = self.client.delete(f"/item/{self.item.pk}/delete/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Item.objects.filter(pk=self.item.pk).exists())

    def test_viewer_cannot_edit_item_field(self):
        self.login_as_viewer()
        response = self.client.get(f"/item/{self.item.pk}/edit-field/?field=name")
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_update_item_field(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/item/{self.item.pk}/update-field/",
            {"field_name": "name", "value": "Stolen Sword"},
        )
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, "Sword")


class ContainerPermissionsTests(PermissionsTestBase):
    """put_in_container and remove_from_container are owner-only."""

    def test_owner_can_put_in_container(self):
        self.login_as_owner()
        response = self.client.post(
            f"/item/{self.container.pk}/put-in-container/",
            {"item_id": self.item.pk},
        )
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_put_in_container(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/item/{self.container.pk}/put-in-container/",
            {"item_id": self.item.pk},
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_remove_from_container(self):
        self.login_as_owner()
        self.item.container = self.container
        self.item.save(update_fields=["container"])
        response = self.client.post(f"/item/{self.item.pk}/remove-from-container/")
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_remove_from_container(self):
        self.login_as_viewer()
        self.item.container = self.container
        self.item.save(update_fields=["container"])
        response = self.client.post(f"/item/{self.item.pk}/remove-from-container/")
        self.assertEqual(response.status_code, 403)


class ConditionPermissionsTests(PermissionsTestBase):
    """Condition add/delete are owner-only."""

    def test_owner_can_add_condition(self):
        self.login_as_owner()
        response = self.client.post(
            f"/character/{self.character.pk}/add-condition/",
            {
                "modifier_type": "ability",
                "target": "dexterity",
                "value": "1",
                "source": "Cat's Grace",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_add_condition(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/character/{self.character.pk}/add-condition/",
            {
                "modifier_type": "ability",
                "target": "dexterity",
                "value": "1",
                "source": "Cat's Grace",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_delete_condition(self):
        self.login_as_owner()
        response = self.client.delete(f"/condition/{self.condition.pk}/delete/")
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_delete_condition(self):
        self.login_as_viewer()
        response = self.client.delete(f"/condition/{self.condition.pk}/delete/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Condition.objects.filter(pk=self.condition.pk).exists())


class HitDiePermissionsTests(PermissionsTestBase):
    """Hit die add/delete are owner-only."""

    def test_owner_can_add_hit_die(self):
        self.login_as_owner()
        response = self.client.post(
            f"/character/{self.character.pk}/add-hit-die/",
            {"level": "2", "die_type": "d10", "roll": "7", "con_bonus": "1"},
        )
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_add_hit_die(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/character/{self.character.pk}/add-hit-die/",
            {"level": "2", "die_type": "d10", "roll": "7", "con_bonus": "1"},
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_delete_hit_die(self):
        self.login_as_owner()
        response = self.client.delete(f"/hit-die/{self.hit_die.pk}/delete/")
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_delete_hit_die(self):
        self.login_as_viewer()
        response = self.client.delete(f"/hit-die/{self.hit_die.pk}/delete/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(HitDie.objects.filter(pk=self.hit_die.pk).exists())


class SpellPermissionsTests(PermissionsTestBase):
    """Spell add/delete/toggle are owner-only."""

    def test_owner_can_add_spell(self):
        self.login_as_owner()
        response = self.client.post(
            f"/character/{self.character.pk}/add-spell/",
            {"name": "Fireball", "level": "3"},
        )
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_add_spell(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/character/{self.character.pk}/add-spell/",
            {"name": "Fireball", "level": "3"},
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_delete_spell(self):
        self.login_as_owner()
        response = self.client.delete(f"/spell/{self.spell.pk}/delete/")
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_delete_spell(self):
        self.login_as_viewer()
        response = self.client.delete(f"/spell/{self.spell.pk}/delete/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Spell.objects.filter(pk=self.spell.pk).exists())

    def test_owner_can_toggle_memorized(self):
        self.login_as_owner()
        response = self.client.post(
            f"/spell/{self.spell.pk}/toggle-memorized/", {"value": "on"}
        )
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_toggle_memorized(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/spell/{self.spell.pk}/toggle-memorized/", {"value": "on"}
        )
        self.assertEqual(response.status_code, 403)


class SagePermissionsTests(PermissionsTestBase):
    """Sage mutation endpoints are owner-only."""

    def test_viewer_cannot_get_chosen_field_form(self):
        self.login_as_viewer()
        response = self.client.get(
            f"/character/{self.character.pk}/sage/chosen-field/form/"
        )
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_post_chosen_field(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/character/{self.character.pk}/sage/chosen-field/",
            {"chosen_field": "Animal Training", "chosen_study": "Falconry"},
        )
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_get_study_options(self):
        self.login_as_viewer()
        response = self.client.get(
            f"/character/{self.character.pk}/sage/study-options/?chosen_field=Animal+Training"
        )
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_update_study_points(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/character/{self.character.pk}/sage/study/{self.sage_row.pk}/points/",
            {"points": "99"},
        )
        self.assertEqual(response.status_code, 403)
        self.sage_row.refresh_from_db()
        self.assertEqual(self.sage_row.points, 5)

    def test_viewer_cannot_add_study(self):
        self.login_as_viewer()
        response = self.client.post(
            f"/character/{self.character.pk}/sage/study/add/",
            {"study": "Forgery"},
        )
        self.assertEqual(response.status_code, 403)


class HomepageTests(TestCase):
    """The homepage shows all characters and all items across users."""

    def setUp(self):
        self.user_a = User.objects.create_user(username="alice", password="pass")
        self.user_b = User.objects.create_user(username="bob", password="pass")
        self.char_a = Character.objects.create(user=self.user_a, name="Alice's Fighter")
        self.char_b = Character.objects.create(user=self.user_b, name="Bob's Mage")
        self.item_a = Item.objects.create(
            owner=self.char_a, name="Longsword", weight="4 lb"
        )
        self.item_b = Item.objects.create(
            owner=self.char_b, name="Spellbook", weight="3 lb"
        )
        self.client.login(username="alice", password="pass")

    def test_homepage_shows_all_characters(self):
        response = self.client.get("/")
        self.assertContains(response, "Alice&#x27;s Fighter")
        self.assertContains(response, "Bob&#x27;s Mage")

    def test_homepage_shows_player_column(self):
        response = self.client.get("/")
        self.assertContains(response, "alice")
        self.assertContains(response, "bob")

    def test_homepage_shows_party_inventory(self):
        response = self.client.get("/")
        self.assertContains(response, "Party Inventory")
        self.assertContains(response, "Longsword")
        self.assertContains(response, "Spellbook")
