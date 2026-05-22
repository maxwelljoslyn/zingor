"""Undo/redo view tests, extracted from characters/tests/test_views.py."""

from django.contrib.auth.models import User
from django.test import TestCase

from characters.models import Action, Character


class UndoRedoViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(
            user=self.user, name="Thorn", strength=10
        )

    def test_undo_redo_via_post(self):
        # Set strength
        self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "strength", "value": "15"},
        )
        self.character.refresh_from_db()
        self.assertEqual(self.character.strength, 15)

        # Undo
        response = self.client.post(f"/character/{self.character.pk}/undo/")
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertEqual(self.character.strength, 10)

        # Redo
        response = self.client.post(f"/character/{self.character.pk}/redo/")
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertEqual(self.character.strength, 15)


class FieldUpdateCreatesActionTest(TestCase):
    """update_field view used to create an Action record for undo/redo."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")
        self.character = Character.objects.create(user=self.user, name="Thorn")

    def test_update_creates_action(self):
        self.client.post(
            f"/character/{self.character.pk}/update-field/",
            {"field_name": "strength", "value": "15"},
        )
        self.assertEqual(Action.objects.filter(character=self.character).count(), 1)
