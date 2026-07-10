"""Tests for the views."""

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from characters.models import (
    BonusHitPoints,
    Character,
    Condition,
    HitDie,
    Item,
    Profile,
    Spell,
)


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
                "email": "newuser@example.com",
                "password1": "testpass123!",
                "password2": "testpass123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    @override_settings(REGISTRATION_ENABLED=False)
    def test_register_page_redirects_when_disabled(self):
        response = self.client.get("/register/")
        self.assertRedirects(response, "/login/")

    @override_settings(REGISTRATION_ENABLED=False)
    def test_register_post_creates_no_user_when_disabled(self):
        response = self.client.post(
            "/register/",
            {
                "username": "spammer",
                "email": "spammer@example.com",
                "password1": "testpass123!",
                "password2": "testpass123!",
            },
        )
        self.assertRedirects(response, "/login/")
        self.assertFalse(User.objects.filter(username="spammer").exists())

    def test_redirect_when_not_logged_in(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)


class PasswordResetTests(TestCase):
    def test_password_reset_sends_email(self):
        User.objects.create_user(
            username="forgot", email="forgot@example.com", password="oldpass123!"
        )
        response = self.client.post(
            reverse("characters:password_reset"), {"email": "forgot@example.com"}
        )
        self.assertRedirects(response, reverse("characters:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("forgot@example.com", mail.outbox[0].to)

    def test_password_reset_unknown_email_is_silent(self):
        response = self.client.post(
            reverse("characters:password_reset"), {"email": "nobody@example.com"}
        )
        self.assertRedirects(response, reverse("characters:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_confirm_sets_password_and_confirms_email(self):
        user = User.objects.create_user(
            username="resetme", email="reset@example.com", password="oldpass123!"
        )
        Profile.objects.create(user=user, email_confirmed=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        # The first GET stores the token in the session and redirects to the
        # set-password URL (the token in the URL becomes a fixed sentinel).
        response = self.client.get(
            reverse(
                "characters:password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            )
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            response.url,
            {"new_password1": "brandnew456!", "new_password2": "brandnew456!"},
        )
        self.assertRedirects(response, reverse("characters:password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("brandnew456!"))
        # Completing the reset proves email control, so the account is confirmed too.
        self.assertTrue(user.profile.email_confirmed)

    def test_password_reset_confirm_invalid_link(self):
        user = User.objects.create_user(
            username="resetbad", email="resetbad@example.com", password="oldpass123!"
        )
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        response = self.client.get(
            reverse(
                "characters:password_reset_confirm",
                kwargs={"uidb64": uid, "token": "bad-token"},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"invalid or has expired", response.content.lower())


class UserProfileViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get("/users/testuser/")
        self.assertEqual(response.status_code, 302)

    def test_own_profile(self):
        response = self.client.get("/users/testuser/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "testuser")
        self.assertContains(response, "No characters yet")

    def test_other_users_profile(self):
        other = User.objects.create_user(username="otheruser", password="testpass")
        Character.objects.create(user=other, name="Grimble")
        response = self.client.get("/users/otheruser/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grimble")

    def test_unknown_username_404s(self):
        response = self.client.get("/users/nosuchuser/")
        self.assertEqual(response.status_code, 404)

    def test_lists_only_that_users_characters(self):
        other = User.objects.create_user(username="otheruser", password="testpass")
        Character.objects.create(user=self.user, name="Thorn")
        Character.objects.create(user=other, name="Grimble")
        response = self.client.get("/users/testuser/")
        self.assertContains(response, "Thorn")
        self.assertNotContains(response, "Grimble")


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

    def test_party_inventory_sorts_containers_by_total_weight(self):
        """A container's weight cell sorts by its total weight, contents included."""
        character = Character.objects.create(user=self.user, name="Thorn")
        backpack = Item.objects.create(
            owner=character, name="Backpack", weight="2 lb", is_container=True
        )
        Item.objects.create(
            owner=character, name="Rope", weight="5 lb", container=backpack
        )
        response = self.client.get("/")
        self.assertContains(response, f'data-sort-value="{backpack.total_weight_oz}"')
        self.assertContains(response, f"({backpack.total_weight} total)")


class CharacterSheetViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_sheet_loads(self):
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thorn")

    def test_inventory_sorts_containers_by_total_weight(self):
        """The sheet's weight cell sorts by total weight, contents included."""
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", weight="2 lb", is_container=True
        )
        Item.objects.create(
            owner=self.character, name="Rope", weight="5 lb", container=backpack
        )
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, f'data-sort-value="{backpack.total_weight_oz}"')
        self.assertContains(response, f"({backpack.total_weight} total)")

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

    def test_edit_height_offers_feet_and_inches(self):
        """Height edit form has separate feet and inches inputs (#35)."""
        response = self.client.get(
            f"/character/{self.character.pk}/edit-field/?field=height"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="feet"')
        self.assertContains(response, 'name="inches"')

    def test_update_height_feet_and_inches(self):
        """Feet + inches combine into a single inches Quantity (#35)."""
        self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "height", "feet": "5", "inches": "7"},
        )
        self.character.refresh_from_db()
        self.assertEqual(str(self.character.height), "67 inch")
        self.assertEqual(self.character.height_display, "5' 7\"")

    def test_edit_height_prefills_feet_and_inches(self):
        """An existing inches height is split back into feet and inches for editing."""
        self.character.height = "67 inch"
        self.character.save(update_fields=["height"])
        response = self.client.get(
            f"/character/{self.character.pk}/edit-field/?field=height"
        )
        self.assertContains(response, 'name="feet" value="5"')
        self.assertContains(response, 'name="inches" value="7"')

    def test_update_height_normalizes_excess_inches(self):
        """Inches >= 12 carry into feet server-side (#35)."""
        self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "height", "feet": "5", "inches": "15"},
        )
        self.character.refresh_from_db()
        self.assertEqual(str(self.character.height), "75 inch")
        self.assertEqual(self.character.height_display, "6' 3\"")

    def test_update_height_rejects_negatives(self):
        """A negative POST is rejected and leaves the existing height untouched (#35)."""
        self.character.height = "67 inch"
        self.character.save(update_fields=["height"])
        response = self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "height", "feet": "-3", "inches": "-5"},
        )
        self.assertEqual(response.status_code, 400)
        self.character.refresh_from_db()
        self.assertEqual(str(self.character.height), "67 inch")

    def test_update_height_feet_only(self):
        """Feet alone, with inches blank, stores cleanly (#35)."""
        self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "height", "feet": "6", "inches": ""},
        )
        self.character.refresh_from_db()
        self.assertEqual(str(self.character.height), "72 inch")
        self.assertEqual(self.character.height_display, "6'")


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

    def test_update_item_weight_decimal(self):
        """Item weights accept decimals after entry (#37)."""
        item = Item.objects.create(owner=self.character, name="Sword", weight="3 lb")
        self.client.post(
            f"/item/{item.pk}/update-field/",
            {"field_name": "weight", "value": "2.5", "pint_unit": "pound"},
        )
        item.refresh_from_db()
        self.assertEqual(str(item.weight), "2.5 pound")

    def test_edit_capacity_offers_unit_dropdown(self):
        """Capacity edit form is split into a number input and a unit <select> (#25)."""
        item = Item.objects.create(
            owner=self.character, name="Flask", is_container=True
        )
        response = self.client.get(f"/item/{item.pk}/edit-field/?field=capacity")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="pint_unit"')
        self.assertContains(response, "<select")
        self.assertContains(response, 'value="fluid_ounce"')

    def test_update_capacity_with_unit(self):
        """Capacity magnitude + unit dropdown combine into a valid Quantity (#25)."""
        item = Item.objects.create(
            owner=self.character, name="Flask", is_container=True
        )
        self.client.post(
            f"/item/{item.pk}/update-field/",
            {"field_name": "capacity", "value": "64", "pint_unit": "fluid_ounce"},
        )
        item.refresh_from_db()
        self.assertEqual(str(item.capacity), "64 fluid_ounce")

    def test_unwearing_keeps_item_carried(self):
        """Taking off a worn item leaves it carried (it isn't dropped)."""
        item = Item.objects.create(
            owner=self.character, name="Armor", weight="40 lb", is_worn=True
        )
        self.client.post(
            f"/item/{item.pk}/update-field/",
            {"field_name": "is_worn", "value": ""},
        )
        item.refresh_from_db()
        self.assertFalse(item.is_worn)
        self.assertTrue(item.is_carried)

    def test_wearing_item_marks_it_carried(self):
        """Wearing an uncarried item implies it is now carried."""
        item = Item.objects.create(
            owner=self.character, name="Cloak", is_carried=False, is_worn=False
        )
        self.client.post(
            f"/item/{item.pk}/update-field/",
            {"field_name": "is_worn", "value": "on"},
        )
        item.refresh_from_db()
        self.assertTrue(item.is_worn)
        self.assertTrue(item.is_carried)

    def test_uncarrying_item_unwears_it(self):
        """Marking an item not carried also takes it off."""
        item = Item.objects.create(
            owner=self.character, name="Helm", is_carried=True, is_worn=True
        )
        self.client.post(
            f"/item/{item.pk}/update-field/",
            {"field_name": "is_carried", "value": ""},
        )
        item.refresh_from_db()
        self.assertFalse(item.is_carried)
        self.assertFalse(item.is_worn)


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


class BonusHitPointsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_add_bonus_hp(self):
        response = self.client.post(
            f"/character/{self.character.pk}/add-bonus-hp/",
            {"amount": "4", "note": "soldier at arms"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            BonusHitPoints.objects.filter(character=self.character).count(), 1
        )

    def test_add_bonus_hp_requires_note(self):
        response = self.client.post(
            f"/character/{self.character.pk}/add-bonus-hp/",
            {"amount": "4", "note": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            BonusHitPoints.objects.filter(character=self.character).count(), 0
        )

    def test_delete_bonus_hp(self):
        bonus = BonusHitPoints.objects.create(
            character=self.character, amount=4, note="soldier at arms"
        )
        response = self.client.delete(f"/bonus-hp/{bonus.pk}/delete/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            BonusHitPoints.objects.filter(character=self.character).count(), 0
        )
