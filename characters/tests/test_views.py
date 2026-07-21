"""Tests for the views."""

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
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
    SageAbilityPoints,
    SageStudyPoints,
    Spell,
)
from characters.units import D, u


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

    def test_inactive_character_shows_pill(self):
        Character.objects.create(user=self.user, name="Alive")
        Character.objects.create(user=self.user, name="Ghost", is_active=False)
        response = self.client.get("/users/testuser/")
        self.assertContains(response, "Alive")
        self.assertContains(response, "Ghost")
        self.assertContains(response, "badge-inactive")

    def test_last_updated_is_localizable(self):
        """The timestamp ships as a <time> the client can localize, with a
        UTC-labelled fallback for the no-JS case."""
        Character.objects.create(user=self.user, name="Thorn")
        response = self.client.get("/users/testuser/")
        self.assertContains(response, "data-localize-time")
        self.assertContains(response, "UTC")


class DisplayNameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

    def test_defaults_to_username(self):
        response = self.client.get("/users/testuser/")
        self.assertContains(response, "<h1>testuser</h1>", html=True)

    def test_own_profile_shows_edit_form(self):
        response = self.client.get("/users/testuser/")
        self.assertContains(response, 'name="display_name"')

    def test_other_profile_hides_edit_form(self):
        User.objects.create_user(username="otheruser", password="testpass")
        response = self.client.get("/users/otheruser/")
        self.assertNotContains(response, 'name="display_name"')

    def test_set_display_name(self):
        response = self.client.post(
            "/users/testuser/", {"display_name": "Maxwell of Zingor"}
        )
        self.assertRedirects(response, "/users/testuser/")
        self.assertEqual(self.user.profile.display_name, "Maxwell of Zingor")
        response = self.client.get("/users/testuser/")
        self.assertContains(response, "<h1>Maxwell of Zingor</h1>", html=True)
        self.assertContains(response, "username: testuser")

    def test_display_name_used_in_character_list(self):
        Character.objects.create(user=self.user, name="Thorn")
        self.client.post("/users/testuser/", {"display_name": "Maxwell of Zingor"})
        response = self.client.get("/")
        self.assertContains(response, "Maxwell of Zingor")

    def test_blank_resets_to_username(self):
        self.client.post("/users/testuser/", {"display_name": "Maxwell of Zingor"})
        self.client.post("/users/testuser/", {"display_name": "  "})
        response = self.client.get("/users/testuser/")
        self.assertContains(response, "<h1>testuser</h1>", html=True)

    def test_cannot_edit_another_users_display_name(self):
        other = User.objects.create_user(username="otheruser", password="testpass")
        response = self.client.post("/users/otheruser/", {"display_name": "Impostor"})
        self.assertEqual(response.status_code, 403)
        profile = Profile.objects.filter(user=other).first()
        self.assertTrue(profile is None or profile.display_name == "")


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

    def test_last_updated_is_localizable(self):
        """The timestamp ships as a <time> the client can localize, with a
        UTC-labelled fallback for the no-JS case."""
        Character.objects.create(user=self.user, name="Thorn")
        response = self.client.get("/")
        self.assertContains(response, "data-localize-time")
        self.assertContains(response, "UTC")

    def test_hp_column_shows_current_and_max(self):
        character = Character.objects.create(
            user=self.user, name="Thorn", char_class="fighter", current_hp=12
        )
        character.hit_dice.create(level=1, die_type="d10", roll=8, con_bonus=2)
        response = self.client.get("/")
        self.assertContains(response, "12 / 10")

    def test_hp_column_shows_zero_current_hp(self):
        """A character at exactly 0 HP shows 0, not an em dash."""
        Character.objects.create(user=self.user, name="Downed", current_hp=0)
        response = self.client.get("/")
        self.assertContains(response, "0 / —")

    def test_inactive_character_moves_to_inactive_section(self):
        Character.objects.create(user=self.user, name="Alive")
        Character.objects.create(user=self.user, name="Ghost", is_active=False)
        response = self.client.get("/")
        self.assertContains(response, "Alive")
        self.assertContains(response, "Ghost")
        self.assertContains(response, "Inactive characters")
        active_names = [c.name for c in response.context["party_characters"]]
        inactive_names = [c.name for c in response.context["inactive_characters"]]
        self.assertEqual(active_names, ["Alive"])
        self.assertEqual(inactive_names, ["Ghost"])

    def test_active_roster_split_by_kind(self):
        """Primaries and henchmen go in the party table; the rest in the other table."""
        Character.objects.create(user=self.user, name="Hero", kind="primary")
        Character.objects.create(user=self.user, name="Squire", kind="hench")
        Character.objects.create(user=self.user, name="Torchbearer", kind="hireling")
        Character.objects.create(user=self.user, name="Rex", kind="pet")
        response = self.client.get("/")
        party = [c.name for c in response.context["party_characters"]]
        others = [c.name for c in response.context["other_characters"]]
        self.assertEqual(sorted(party), ["Hero", "Squire"])
        self.assertEqual(sorted(others), ["Rex", "Torchbearer"])
        self.assertContains(response, "Followers, Hirelings")

    def test_party_table_shows_fel_and_total(self):
        Character.objects.create(
            user=self.user, name="Hero", kind="primary", char_class="mage", xp=4_001
        )
        Character.objects.create(
            user=self.user, name="Squire", kind="hench", char_class="fighter", xp=2_001
        )
        response = self.client.get("/")
        fels = [c.fel for c in response.context["party_characters"]]
        self.assertEqual(sorted(fels), [2, 3])
        self.assertEqual(response.context["party_fel_total"], 5)
        self.assertContains(response, "Party total fighter equivalent levels: 5")

    def test_party_fel_total_ignores_characters_without_xp(self):
        Character.objects.create(
            user=self.user, name="Hero", kind="primary", char_class="mage", xp=4_001
        )
        Character.objects.create(user=self.user, name="Rookie", kind="primary")
        response = self.client.get("/")
        self.assertEqual(response.context["party_fel_total"], 3)

    def test_fel_column_only_on_party_table(self):
        Character.objects.create(user=self.user, name="Rex", kind="pet", xp=4_001)
        response = self.client.get("/")
        self.assertNotContains(response, "F.E.L.")

    def test_no_inactive_section_when_all_active(self):
        Character.objects.create(user=self.user, name="Alive")
        response = self.client.get("/")
        self.assertNotContains(response, "Inactive characters")

    def test_inactive_character_items_excluded_from_party_inventory(self):
        active = Character.objects.create(user=self.user, name="Alive")
        dead = Character.objects.create(user=self.user, name="Ghost", is_active=False)
        Item.objects.create(owner=active, name="Torch", weight="1 lb")
        Item.objects.create(owner=dead, name="Cursed Sword", weight="3 lb")
        response = self.client.get("/")
        self.assertContains(response, "Torch")
        self.assertNotContains(response, "Cursed Sword")

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
        self.assertContains(response, "(7 lb total)")

    def test_deeply_nested_containers_do_not_cause_n_plus_one(self):
        """The party item list stitches the container tree in one query.

        The item table and total_weight recurse through contents.all() to any
        depth, so a fixed prefetch depth would leave deeper containers issuing
        one query apiece. Assert the query count is the same for a shallow and
        a deeply nested inventory (no growth per nesting level).
        """
        character = Character.objects.create(user=self.user, name="Thorn")

        def build_chain(depth: int) -> None:
            parent = None
            for i in range(depth):
                parent = Item.objects.create(
                    owner=character,
                    name="Box " + str(i),
                    weight="1 lb",
                    is_container=True,
                    container=parent,
                )

        build_chain(1)
        with CaptureQueriesContext(connection) as shallow:
            self.assertEqual(self.client.get("/").status_code, 200)
        build_chain(8)
        with CaptureQueriesContext(connection) as deep:
            self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(len(deep.captured_queries), len(shallow.captured_queries))


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
        self.assertContains(response, "(7 lb total)")

    def test_deeply_nested_containers_do_not_cause_n_plus_one(self):
        """The sheet stitches the container tree in one query at any depth.

        The inventory table and total_weight recurse through contents.all() to
        any depth; assert the query count is the same for a shallow and a
        deeply nested inventory (no growth per nesting level).
        """

        def build_chain(depth: int) -> None:
            parent = None
            for i in range(depth):
                parent = Item.objects.create(
                    owner=self.character,
                    name="Box " + str(i),
                    weight="1 lb",
                    is_container=True,
                    container=parent,
                )

        url = f"/character/{self.character.pk}/"
        build_chain(1)
        with CaptureQueriesContext(connection) as shallow:
            self.assertEqual(self.client.get(url).status_code, 200)
        build_chain(8)
        with CaptureQueriesContext(connection) as deep:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(len(deep.captured_queries), len(shallow.captured_queries))

    def test_other_users_character_viewable(self):
        other_user = User.objects.create_user(username="other", password="testpass")
        other_char = Character.objects.create(user=other_user, name="Ally")
        response = self.client.get(f"/character/{other_char.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ally")

    def test_inactive_character_sheet_still_renders(self):
        self.character.is_active = False
        self.character.save(update_fields=["is_active"])
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thorn")
        self.assertContains(response, "Inactive")


class ToggleActiveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_owner_can_toggle_inactive_and_back(self):
        response = self.client.post(f"/character/{self.character.pk}/toggle-active/")
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertFalse(self.character.is_active)
        self.client.post(f"/character/{self.character.pk}/toggle-active/")
        self.character.refresh_from_db()
        self.assertTrue(self.character.is_active)

    def test_non_owner_forbidden(self):
        other = User.objects.create_user(username="other", password="testpass")
        self.client.force_login(other)
        response = self.client.post(f"/character/{self.character.pk}/toggle-active/")
        self.assertEqual(response.status_code, 403)
        self.character.refresh_from_db()
        self.assertTrue(self.character.is_active)

    def test_get_not_allowed(self):
        response = self.client.get(f"/character/{self.character.pk}/toggle-active/")
        self.assertEqual(response.status_code, 405)


class WikiUrlControlTests(TestCase):
    URL = "https://adventure.alexissmolensk.com/index.php/Lexent"

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_add_button_shown_when_no_url(self):
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, "Add Wiki URL")
        self.assertNotContains(response, ">Wiki Page<")

    def test_link_and_edit_button_shown_when_url_set(self):
        self.character.wiki_url = self.URL
        self.character.save(update_fields=["wiki_url"])
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, "Edit Wiki URL")
        self.assertContains(response, ">Wiki Page<")
        self.assertContains(response, f'href="{self.URL}"')

    def test_owner_can_set_url(self):
        response = self.client.post(
            f"/character/{self.character.pk}/wiki-url/", {"wiki_url": self.URL}
        )
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertEqual(self.character.wiki_url, self.URL)
        self.assertContains(response, "Edit Wiki URL")

    def test_saving_url_refreshes_identity_section_oob(self):
        response = self.client.post(
            f"/character/{self.character.pk}/wiki-url/", {"wiki_url": self.URL}
        )
        self.assertContains(response, 'id="section-identity" hx-swap-oob="outerHTML"')
        self.assertContains(response, "Sync from wiki")

    def test_anchor_stripped_from_url(self):
        self.client.post(
            f"/character/{self.character.pk}/wiki-url/",
            {"wiki_url": self.URL + "#Equipment"},
        )
        self.character.refresh_from_db()
        self.assertEqual(self.character.wiki_url, self.URL)

    def test_owner_can_clear_url(self):
        self.character.wiki_url = self.URL
        self.character.save(update_fields=["wiki_url"])
        self.client.post(f"/character/{self.character.pk}/wiki-url/", {"wiki_url": ""})
        self.character.refresh_from_db()
        self.assertIsNone(self.character.wiki_url)

    def test_edit_form_prefilled(self):
        self.character.wiki_url = self.URL
        self.character.save(update_fields=["wiki_url"])
        response = self.client.get(f"/character/{self.character.pk}/wiki-url/edit/")
        self.assertContains(response, 'name="wiki_url"')
        self.assertContains(response, f'value="{self.URL}"')

    def test_non_owner_cannot_edit_or_save(self):
        other = User.objects.create_user(username="other", password="testpass")
        self.client.force_login(other)
        edit = self.client.get(f"/character/{self.character.pk}/wiki-url/edit/")
        self.assertEqual(edit.status_code, 403)
        save = self.client.post(
            f"/character/{self.character.pk}/wiki-url/", {"wiki_url": self.URL}
        )
        self.assertEqual(save.status_code, 403)
        self.character.refresh_from_db()
        self.assertIsNone(self.character.wiki_url)

    def test_non_owner_sees_link_but_no_button(self):
        self.character.wiki_url = self.URL
        self.character.save(update_fields=["wiki_url"])
        other = User.objects.create_user(username="other", password="testpass")
        self.client.force_login(other)
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, ">Wiki Page<")
        self.assertNotContains(response, "Edit Wiki URL")


class ToggleWikiSyncTests(TestCase):
    URL = "https://adventure.alexissmolensk.com/index.php/Lexent"

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(
            user=self.user, name="Thorn", wiki_url=self.URL
        )

    def test_owner_can_toggle_on_and_off(self):
        response = self.client.post(f"/character/{self.character.pk}/toggle-wiki-sync/")
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertTrue(self.character.sync_from_wiki)
        self.client.post(f"/character/{self.character.pk}/toggle-wiki-sync/")
        self.character.refresh_from_db()
        self.assertFalse(self.character.sync_from_wiki)

    def test_cannot_enable_without_wiki_url(self):
        self.character.wiki_url = None
        self.character.save(update_fields=["wiki_url"])
        response = self.client.post(f"/character/{self.character.pk}/toggle-wiki-sync/")
        self.assertEqual(response.status_code, 400)
        self.character.refresh_from_db()
        self.assertFalse(self.character.sync_from_wiki)

    def test_toggle_control_hidden_without_wiki_url(self):
        self.character.wiki_url = None
        self.character.save(update_fields=["wiki_url"])
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertNotContains(response, "Sync from wiki")

    def test_sync_pill_shown_when_enabled(self):
        self.character.sync_from_wiki = True
        self.character.save(update_fields=["sync_from_wiki"])
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, "badge-sync")
        self.assertContains(response, "Stop wiki sync")

    def test_non_owner_forbidden(self):
        other = User.objects.create_user(username="other", password="testpass")
        self.client.force_login(other)
        response = self.client.post(f"/character/{self.character.pk}/toggle-wiki-sync/")
        self.assertEqual(response.status_code, 403)
        self.character.refresh_from_db()
        self.assertFalse(self.character.sync_from_wiki)

    def test_get_not_allowed(self):
        response = self.client.get(f"/character/{self.character.pk}/toggle-wiki-sync/")
        self.assertEqual(response.status_code, 405)


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

    def test_update_armor_class(self):
        response = self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "armor_class", "value": "4"},
        )
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertEqual(self.character.armor_class, 4)

    def test_update_race(self):
        self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "race", "value": "elf"},
        )
        self.character.refresh_from_db()
        self.assertEqual(self.character.race, "elf")

    def test_default_kind_is_primary(self):
        self.assertEqual(self.character.kind, "primary")

    def test_update_kind(self):
        response = self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "kind", "value": "hench"},
        )
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertEqual(self.character.kind, "hench")

    def test_update_kind_ignores_blank_option(self):
        """The generic select's blank option must not null a required field."""
        self.character.kind = "pet"
        self.character.save(update_fields=["kind"])
        self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "kind", "value": ""},
        )
        self.character.refresh_from_db()
        self.assertEqual(self.character.kind, "pet")

    def test_kind_shows_on_identity_section(self):
        self.character.kind = "follower"
        self.character.save(update_fields=["kind"])
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, "Follower")

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
        """Quantity creates a single stacked row, not N duplicate rows (#74)."""
        response = self.client.post(
            f"/character/{self.character.pk}/add-item/",
            {"name": "Arrow", "weight": "1 oz", "quantity": "5"},
        )
        self.assertEqual(response.status_code, 200)
        items = Item.objects.filter(owner=self.character, name="Arrow")
        self.assertEqual(items.count(), 1)
        item = items.get()
        self.assertEqual(item.quantity, 5)
        # Compare the stored Quantity, not pint's canonical string ("1 ounce"),
        # so the test tracks the value rather than pint's repr formatting.
        self.assertEqual(item.weight, D(1) * u.oz)
        self.assertEqual(item.adjusted_weight.magnitude, D(5))

    def test_update_item_quantity(self):
        item = Item.objects.create(
            owner=self.character, name="Torch", weight="1 lb", quantity=3
        )
        response = self.client.post(
            f"/item/{item.pk}/update-field/",
            {"field_name": "quantity", "value": "7"},
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 7)

    def test_update_item_quantity_rejects_below_one(self):
        item = Item.objects.create(
            owner=self.character, name="Torch", weight="1 lb", quantity=3
        )
        for bad in ("0", "-2", "junk"):
            response = self.client.post(
                f"/item/{item.pk}/update-field/",
                {"field_name": "quantity", "value": bad},
            )
            self.assertEqual(response.status_code, 400)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    def test_update_quantity_on_container_rejected(self):
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", weight="2 lb", is_container=True
        )
        response = self.client.post(
            f"/item/{backpack.pk}/update-field/",
            {"field_name": "quantity", "value": "2"},
        )
        self.assertEqual(response.status_code, 400)
        backpack.refresh_from_db()
        self.assertEqual(backpack.quantity, 1)

    def test_make_stack_a_container_rejected(self):
        item = Item.objects.create(
            owner=self.character, name="Sack", weight="1 lb", quantity=6
        )
        response = self.client.post(
            f"/item/{item.pk}/update-field/",
            {"field_name": "is_container", "value": "on"},
        )
        self.assertEqual(response.status_code, 400)
        item.refresh_from_db()
        self.assertFalse(item.is_container)

    def test_edit_quantity_field_form(self):
        item = Item.objects.create(
            owner=self.character, name="Torch", weight="1 lb", quantity=3
        )
        response = self.client.get(f"/item/{item.pk}/edit-field/?field=quantity")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="field_name" value="quantity"')

    def test_inventory_shows_stack_quantity(self):
        Item.objects.create(
            owner=self.character, name="Torch", weight="1 lb", quantity=28
        )
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, "×28")


class MoneyViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def _coins(self, currency, quantity, **overrides):
        defaults = {
            "owner": self.character,
            "name": f"{currency} coins",
            "weight": None,
            "currency": currency,
            "quantity": quantity,
        }
        defaults.update(overrides)
        return Item.objects.create(**defaults)

    def test_add_money_creates_stack(self):
        response = self.client.post(
            f"/character/{self.character.pk}/add-money/",
            {"quantity": "40", "currency": "gp"},
        )
        self.assertEqual(response.status_code, 200)
        coins = Item.objects.get(owner=self.character, currency="gp")
        self.assertEqual(coins.quantity, 40)
        self.assertIsNone(coins.weight)
        self.assertEqual(coins.name, "gold pieces")

    def test_add_money_merges_into_top_level_stack(self):
        """Adding coins tops up an existing loose stack instead of splitting it."""
        existing = self._coins("gp", 10, name="gold pieces")
        self.client.post(
            f"/character/{self.character.pk}/add-money/",
            {"quantity": "5", "currency": "gp"},
        )
        existing.refresh_from_db()
        self.assertEqual(existing.quantity, 15)
        self.assertEqual(
            Item.objects.filter(owner=self.character, currency="gp").count(), 1
        )

    def test_add_money_does_not_merge_into_contained_or_stashed_stacks(self):
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", weight="2 lb", is_container=True
        )
        self._coins("gp", 10, container=backpack)
        self._coins("gp", 99, is_carried=False)
        self.client.post(
            f"/character/{self.character.pk}/add-money/",
            {"quantity": "5", "currency": "gp"},
        )
        stacks = Item.objects.filter(owner=self.character, currency="gp")
        self.assertEqual(stacks.count(), 3)

    def test_add_money_rejects_bad_input(self):
        for payload in (
            {"quantity": "5", "currency": "euro"},
            {"quantity": "0", "currency": "gp"},
            {"quantity": "junk", "currency": "gp"},
        ):
            response = self.client.post(
                f"/character/{self.character.pk}/add-money/", payload
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Item.objects.filter(owner=self.character).count(), 0)

    def test_money_quantity_zero_deletes_stack(self):
        """Spending your last copper empties the purse instead of erroring."""
        coins = self._coins("cp", 3)
        response = self.client.post(
            f"/item/{coins.pk}/update-field/",
            {"field_name": "quantity", "value": "0"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Item.objects.filter(pk=coins.pk).exists())

    def test_money_weight_cannot_be_edited(self):
        coins = self._coins("gp", 40)
        response = self.client.post(
            f"/item/{coins.pk}/update-field/",
            {"field_name": "weight", "value": "5", "pint_unit": "pound"},
        )
        self.assertEqual(response.status_code, 400)
        edit = self.client.get(f"/item/{coins.pk}/edit-field/?field=weight")
        self.assertEqual(edit.status_code, 400)

    def test_money_cannot_become_container(self):
        coins = self._coins("gp", 40)
        response = self.client.post(
            f"/item/{coins.pk}/update-field/",
            {"field_name": "is_container", "value": "on"},
        )
        self.assertEqual(response.status_code, 400)

    def test_money_edit_refreshes_identity_section(self):
        """Coin changes re-render the identity section's money row out-of-band."""
        coins = self._coins("gp", 40)
        response = self.client.post(
            f"/item/{coins.pk}/update-field/",
            {"field_name": "quantity", "value": "10"},
        )
        self.assertContains(response, 'id="section-identity"')
        response = self.client.post(
            f"/character/{self.character.pk}/add-money/",
            {"quantity": "5", "currency": "sp"},
        )
        self.assertContains(response, 'id="section-identity"')

    def test_identity_shows_derived_money(self):
        self._coins("gp", 670)
        self._coins("sp", 224)
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, "670 gp")
        self.assertContains(response, "224 sp")
        self.assertContains(response, "0 cp")

    def test_character_money_fields_no_longer_editable(self):
        for field in ("gp", "sp", "cp"):
            response = self.client.post(
                f"/character/{self.character.pk}/update-field/",
                {"field_name": field, "value": "10"},
            )
            self.assertEqual(response.status_code, 400)


class SplitStackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def _split(self, item, count):
        return self.client.post(f"/item/{item.pk}/split/", {"count": count})

    def test_split_creates_sibling_stack(self):
        torches = Item.objects.create(
            owner=self.character, name="Torch", weight="1.5 lb", quantity=28
        )
        response = self._split(torches, 3)
        self.assertEqual(response.status_code, 200)
        torches.refresh_from_db()
        self.assertEqual(torches.quantity, 25)
        new = Item.objects.filter(name="Torch").exclude(pk=torches.pk).get()
        self.assertEqual(new.quantity, 3)
        self.assertEqual(str(new.weight), str(torches.weight))
        self.assertIsNone(new.container)

    def test_split_inside_container_stays_in_container(self):
        backpack = Item.objects.create(
            owner=self.character, name="Backpack", weight="2 lb", is_container=True
        )
        oil = Item.objects.create(
            owner=self.character,
            name="Lamp oil",
            weight="1 lb",
            quantity=5,
            container=backpack,
            props={"percent_left": 50},
        )
        self._split(oil, 2)
        new = Item.objects.filter(name="Lamp oil").exclude(pk=oil.pk).get()
        self.assertEqual(new.container, backpack)
        self.assertEqual(new.props, {"percent_left": 50})

    def test_split_money_stack(self):
        coins = Item.objects.create(
            owner=self.character,
            name="gold pieces",
            weight=None,
            currency="gp",
            quantity=650,
        )
        self._split(coins, 200)
        coins.refresh_from_db()
        self.assertEqual(coins.quantity, 450)
        new = Item.objects.filter(currency="gp").exclude(pk=coins.pk).get()
        self.assertEqual(new.quantity, 200)
        self.assertIsNone(new.weight)
        self.assertEqual(self.character.gp.magnitude, D(650))

    def test_split_preserves_carried_and_worn_flags(self):
        stash = Item.objects.create(
            owner=self.character,
            name="Ring",
            weight="1 oz",
            quantity=4,
            is_carried=False,
        )
        self._split(stash, 1)
        new = Item.objects.filter(name="Ring").exclude(pk=stash.pk).get()
        self.assertFalse(new.is_carried)

    def test_split_rejects_bad_counts(self):
        torches = Item.objects.create(
            owner=self.character, name="Torch", weight="1.5 lb", quantity=5
        )
        for bad in ("0", "-1", "5", "6", "junk", ""):
            response = self._split(torches, bad)
            self.assertEqual(response.status_code, 400)
        torches.refresh_from_db()
        self.assertEqual(torches.quantity, 5)
        self.assertEqual(Item.objects.filter(name="Torch").count(), 1)

    def test_split_rejects_single_item(self):
        sword = Item.objects.create(owner=self.character, name="Sword", weight="3 lb")
        response = self._split(sword, 1)
        self.assertEqual(response.status_code, 400)

    def test_split_button_rendered_for_stacks_only(self):
        torches = Item.objects.create(
            owner=self.character, name="Torch", weight="1.5 lb", quantity=28
        )
        sword = Item.objects.create(owner=self.character, name="Sword", weight="3 lb")
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertContains(response, f"/item/{torches.pk}/split-form/")
        self.assertNotContains(response, f"/item/{sword.pk}/split-form/")

    def test_split_form_endpoint_returns_count_form(self):
        torches = Item.objects.create(
            owner=self.character, name="Torch", weight="1.5 lb", quantity=28
        )
        response = self.client.get(f"/item/{torches.pk}/split-form/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="count"')
        self.assertContains(response, f"/item/{torches.pk}/split/")

    def test_split_form_rejects_single_item(self):
        sword = Item.objects.create(owner=self.character, name="Sword", weight="3 lb")
        response = self.client.get(f"/item/{sword.pk}/split-form/")
        self.assertEqual(response.status_code, 400)

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


class SageStudySoftDeleteTests(TestCase):
    """Deleting a sage study hides it but keeps its points; re-adding restores them."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(
            user=self.user, name="Thorn", char_class="fighter"
        )

    def test_hide_soft_deletes_and_keeps_points(self):
        row = SageStudyPoints.objects.create(
            character=self.character, study="Athletics", points=45
        )
        response = self.client.post(
            f"/character/{self.character.pk}/sage/study/{row.pk}/hide/"
        )
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertTrue(row.hidden)
        self.assertEqual(row.points, 45)
        # The dropdown lists every study, so assert the visible row link is gone.
        self.assertNotContains(response, ">Athletics</a>")

    def test_readd_restores_hidden_points_with_notice(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Athletics", points=45, hidden=True
        )
        response = self.client.post(
            f"/character/{self.character.pk}/sage/study/add/",
            {"study": "Athletics"},
        )
        self.assertEqual(response.status_code, 200)
        row = SageStudyPoints.objects.get(character=self.character, study="Athletics")
        self.assertFalse(row.hidden)
        self.assertEqual(row.points, 45)
        self.assertContains(response, "45 points")
        self.assertContains(response, ">Athletics</a>")

    def test_hidden_study_excluded_from_section(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Athletics", points=45, hidden=True
        )
        SageStudyPoints.objects.create(
            character=self.character, study="Judgment", points=12
        )
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">Judgment</a>")
        self.assertNotContains(response, ">Athletics</a>")

    def test_hide_requires_owner(self):
        other = User.objects.create_user(username="otheruser", password="testpass")
        victim = Character.objects.create(user=other, name="Grimble")
        row = SageStudyPoints.objects.create(
            character=victim, study="Athletics", points=45
        )
        response = self.client.post(f"/character/{victim.pk}/sage/study/{row.pk}/hide/")
        self.assertNotEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertFalse(row.hidden)


class SageAbilityTests(TestCase):
    """Creating and (soft-)deleting standalone, freetext sage abilities."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(
            user=self.user, name="Thorn", char_class="fighter"
        )

    def test_add_creates_ability(self):
        response = self.client.post(
            f"/character/{self.character.pk}/sage/ability/add/",
            {"ability": "Pick Locks"},
        )
        self.assertEqual(response.status_code, 200)
        row = SageAbilityPoints.objects.get(
            character=self.character, ability="Pick Locks"
        )
        self.assertEqual(row.points, 0)
        self.assertFalse(row.hidden)
        self.assertContains(response, "Pick Locks")

    def test_add_requires_nonblank_name(self):
        response = self.client.post(
            f"/character/{self.character.pk}/sage/ability/add/",
            {"ability": "   "},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            SageAbilityPoints.objects.filter(character=self.character).exists()
        )

    def test_add_is_idempotent(self):
        self.client.post(
            f"/character/{self.character.pk}/sage/ability/add/",
            {"ability": "Pick Locks"},
        )
        self.client.post(
            f"/character/{self.character.pk}/sage/ability/add/",
            {"ability": "Pick Locks"},
        )
        self.assertEqual(
            SageAbilityPoints.objects.filter(
                character=self.character, ability="Pick Locks"
            ).count(),
            1,
        )

    def test_hide_soft_deletes_and_keeps_points(self):
        row = SageAbilityPoints.objects.create(
            character=self.character, ability="Pick Locks", points=30
        )
        response = self.client.post(
            f"/character/{self.character.pk}/sage/ability/{row.pk}/hide/"
        )
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertTrue(row.hidden)
        self.assertEqual(row.points, 30)
        self.assertNotContains(response, "Pick Locks")

    def test_readd_restores_hidden_points_with_notice(self):
        SageAbilityPoints.objects.create(
            character=self.character, ability="Pick Locks", points=30, hidden=True
        )
        response = self.client.post(
            f"/character/{self.character.pk}/sage/ability/add/",
            {"ability": "Pick Locks"},
        )
        self.assertEqual(response.status_code, 200)
        row = SageAbilityPoints.objects.get(
            character=self.character, ability="Pick Locks"
        )
        self.assertFalse(row.hidden)
        self.assertEqual(row.points, 30)
        self.assertContains(response, "30 points")
        self.assertContains(response, "Pick Locks")

    def test_hidden_ability_excluded_from_section(self):
        SageAbilityPoints.objects.create(
            character=self.character, ability="Pick Locks", points=30, hidden=True
        )
        SageAbilityPoints.objects.create(
            character=self.character, ability="Disarm Traps", points=12
        )
        response = self.client.get(f"/character/{self.character.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disarm Traps")
        self.assertNotContains(response, "Pick Locks")

    def test_hide_requires_owner(self):
        other = User.objects.create_user(username="otheruser", password="testpass")
        victim = Character.objects.create(user=other, name="Grimble")
        row = SageAbilityPoints.objects.create(
            character=victim, ability="Pick Locks", points=30
        )
        response = self.client.post(
            f"/character/{victim.pk}/sage/ability/{row.pk}/hide/"
        )
        self.assertNotEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertFalse(row.hidden)
