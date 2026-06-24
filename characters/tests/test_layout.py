"""Tests for per-user sheet layout ordering (Phase 2: ability rows)."""

import json

from django.contrib.auth.models import User
from django.test import TestCase

from characters import layout
from characters.models import Character, LayoutOrder

ABILITIES = [
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
]


class ResolveOrderTests(TestCase):
    def test_empty_stored_returns_default(self):
        self.assertEqual(layout.resolve_order([], ABILITIES), ABILITIES)

    def test_stored_order_is_followed(self):
        stored = ["charisma", "strength"]
        result = layout.resolve_order(stored, ABILITIES)
        self.assertEqual(result[:2], ["charisma", "strength"])

    def test_missing_keys_appended_in_default_position(self):
        result = layout.resolve_order(["wisdom"], ABILITIES)
        self.assertEqual(result[0], "wisdom")
        self.assertEqual(set(result), set(ABILITIES))
        self.assertEqual(len(result), len(ABILITIES))

    def test_unknown_keys_dropped(self):
        result = layout.resolve_order(["bogus", "dexterity"], ABILITIES)
        self.assertNotIn("bogus", result)
        self.assertEqual(result[0], "dexterity")

    def test_duplicates_collapsed(self):
        result = layout.resolve_order(["strength", "strength"], ABILITIES)
        self.assertEqual(result.count("strength"), 1)
        self.assertEqual(len(result), len(ABILITIES))


class ReorderEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

    def _post(self, order, section="abilities"):
        return self.client.post(
            f"/layout/rows/{section}/",
            data=json.dumps(order),
            content_type="application/json",
        )

    def test_persists_order(self):
        order = [
            "charisma",
            "wisdom",
            "intelligence",
            "constitution",
            "dexterity",
            "strength",
        ]
        response = self._post(order)
        self.assertEqual(response.status_code, 204)
        stored = list(
            LayoutOrder.objects.filter(user=self.user, scope="abilities")
            .order_by("position")
            .values_list("key", flat=True)
        )
        self.assertEqual(stored, order)

    def test_reposting_replaces_previous_order(self):
        self._post(list(reversed(ABILITIES)))
        self._post(ABILITIES)
        stored = list(
            LayoutOrder.objects.filter(user=self.user, scope="abilities")
            .order_by("position")
            .values_list("key", flat=True)
        )
        self.assertEqual(stored, ABILITIES)

    def test_unknown_keys_are_dropped(self):
        self._post(["charisma", "bogus", "strength"])
        stored = list(
            LayoutOrder.objects.filter(user=self.user, scope="abilities")
            .order_by("position")
            .values_list("key", flat=True)
        )
        self.assertEqual(stored, ["charisma", "strength"])

    def test_unknown_section_rejected(self):
        self.assertEqual(self._post(ABILITIES, section="nope").status_code, 400)

    def test_non_list_body_rejected(self):
        response = self.client.post(
            "/layout/rows/abilities/",
            data=json.dumps({"not": "a list"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_json_rejected(self):
        response = self.client.post(
            "/layout/rows/abilities/",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_requires_login(self):
        self.client.logout()
        response = self._post(ABILITIES)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LayoutOrder.objects.exists())

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get("/layout/rows/abilities/").status_code, 405)


class AbilityOrderRenderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def _set_order(self, user, order):
        LayoutOrder.objects.bulk_create(
            [
                LayoutOrder(user=user, scope="abilities", key=key, position=i)
                for i, key in enumerate(order)
            ]
        )

    def _ability_sequence(self, html):
        """Order in which ability data-row markers appear in the rendered HTML."""
        positions = [(html.index(f'data-row="{a}"'), a) for a in ABILITIES]
        return [a for _, a in sorted(positions)]

    def test_default_order_when_no_preference(self):
        html = self.client.get(f"/character/{self.character.pk}/").content.decode()
        self.assertEqual(self._ability_sequence(html), ABILITIES)

    def test_custom_order_reflected(self):
        custom = [
            "charisma",
            "wisdom",
            "intelligence",
            "constitution",
            "dexterity",
            "strength",
        ]
        self._set_order(self.user, custom)
        html = self.client.get(f"/character/{self.character.pk}/").content.decode()
        self.assertEqual(self._ability_sequence(html), custom)

    def test_preference_applies_to_other_users_character(self):
        custom = [
            "charisma",
            "wisdom",
            "intelligence",
            "constitution",
            "dexterity",
            "strength",
        ]
        self._set_order(self.user, custom)
        other = User.objects.create_user(username="other", password="testpass")
        other_char = Character.objects.create(user=other, name="Ally")
        html = self.client.get(f"/character/{other_char.pk}/").content.decode()
        self.assertEqual(self._ability_sequence(html), custom)

    def test_other_users_preference_does_not_leak(self):
        other = User.objects.create_user(username="other", password="testpass")
        self._set_order(other, list(reversed(ABILITIES)))
        html = self.client.get(f"/character/{self.character.pk}/").content.decode()
        self.assertEqual(self._ability_sequence(html), ABILITIES)
