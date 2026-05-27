"""Tests for the views."""

from django.contrib.auth.models import User
from django.test import TestCase

from characters.models import Character, Condition, HitDie, Item, Spell


class AuthViewTests(TestCase):
    def test_login_page(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)

    def test_register_page(self):
        response = self.client.get("/register/")
        self.assertEqual(response.status_code, 200)

    def test_register_creates_user(self):
        response = self.client.post(
            "/register/",
            {
                "username": "newuser",
                "password1": "testpass123!",
                "password2": "testpass123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_redirect_when_not_logged_in(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)


class CharacterListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

    def test_empty_list(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No characters yet")

    def test_list_with_character(self):
        Character.objects.create(user=self.user, name="Thorn")
        response = self.client.get("/")
        self.assertContains(response, "Thorn")

    def test_create_character(self):
        response = self.client.post("/character/create/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Character.objects.filter(user=self.user).count(), 1)


class CharacterSheetViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_sheet_loads(self):
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thorn")

    def test_other_users_character_viewable(self):
        other_user = User.objects.create_user(username="other", password="testpass")
        other_char = Character.objects.create(user=other_user, name="Ally")
        response = self.client.get(f"/character/{other_char.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ally")


class FieldUpdateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_update_strength(self):
        response = self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "strength", "value": "15"},
        )
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertEqual(self.character.strength, 15)

    def test_update_race(self):
        self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "race", "value": "elf"},
        )
        self.character.refresh_from_db()
        self.assertEqual(self.character.race, "elf")

    def test_edit_field_returns_form(self):
        response = self.client.get(
            f"/character/{self.character.pk}/edit-field/?field=strength"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="value"')


class ItemCRUDTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_add_item(self):
        response = self.client.post(
            f"/character/{self.character.pk}/add-item/",
            {"name": "Sword", "weight": "3 lb"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Item.objects.filter(owner=self.character).count(), 1)

    def test_add_item_with_quantity(self):
        response = self.client.post(
            f"/character/{self.character.pk}/add-item/",
            {"name": "Arrow", "weight": "1 oz", "quantity": "5"},
        )
        self.assertEqual(response.status_code, 200)
        items = Item.objects.filter(owner=self.character, name="Arrow")
        self.assertEqual(items.count(), 5)
        for item in items:
            self.assertEqual(str(item.weight), "1 ounce")

    def test_delete_item(self):
        item = Item.objects.create(owner=self.character, name="Sword", weight="3 lb")
        response = self.client.delete(f"/item/{item.pk}/delete/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Item.objects.filter(owner=self.character).count(), 0)


class ConditionViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_add_condition(self):
        response = self.client.post(
            f"/character/{self.character.pk}/add-condition/",
            {
                "modifier_type": "ability",
                "target": "strength",
                "value": "2",
                "source": "Bull's Strength",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Condition.objects.filter(character=self.character).count(), 1)

    def test_delete_condition(self):
        cond = Condition.objects.create(
            character=self.character,
            modifier_type="ability",
            target="strength",
            value=2,
            source="Bull's Strength",
        )
        response = self.client.delete(f"/condition/{cond.pk}/delete/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Condition.objects.filter(character=self.character).count(), 0)


class SpellViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Wizard")

    def test_add_spell(self):
        response = self.client.post(
            f"/character/{self.character.pk}/add-spell/",
            {"name": "Magic Missile", "level": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Spell.objects.filter(character=self.character).count(), 1)

    def test_delete_spell(self):
        spell = Spell.objects.create(
            character=self.character, name="Magic Missile", level=1
        )
        response = self.client.delete(f"/spell/{spell.pk}/delete/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Spell.objects.filter(character=self.character).count(), 0)


class HitDieViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_add_hit_die(self):
        response = self.client.post(
            f"/character/{self.character.pk}/add-hit-die/",
            {"level": "1", "die_type": "d10", "roll": "8", "con_bonus": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(HitDie.objects.filter(character=self.character).count(), 1)
