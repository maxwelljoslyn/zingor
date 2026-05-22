"""Undo/redo model tests, extracted from characters/tests/test_models.py."""

from django.contrib.auth.models import User
from django.test import TestCase

from characters.models import Action, Character


class ActionUndoRedoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.character = Character.objects.create(
            user=self.user, name="Thorn", strength=10
        )

    def test_undo_redo_set_field(self):
        """Set strength, undo, verify old value, redo, verify new value."""
        old_value = self.character.strength

        # Simulate setting strength to 15
        self.character.strength = 15
        self.character.save(update_fields=["strength"])
        Action.record(
            character=self.character,
            action_type="set_field",
            forward_data={"strength": "15"},
            reverse_data={"strength": str(old_value)},
        )

        self.assertEqual(self.character.strength, 15)

        # Undo
        self.assertTrue(self.character.can_undo())
        self.character.undo()
        self.character.refresh_from_db()
        self.assertEqual(self.character.strength, 10)

        # Redo
        self.assertTrue(self.character.can_redo())
        self.character.redo()
        self.character.refresh_from_db()
        self.assertEqual(self.character.strength, 15)

    def test_new_action_discards_undone(self):
        """Recording a new action should discard any undone actions."""
        self.character.strength = 15
        self.character.save()
        Action.record(
            character=self.character,
            action_type="set_field",
            forward_data={"strength": "15"},
            reverse_data={"strength": "10"},
        )

        # Undo
        self.character.undo()

        # Record a different action
        self.character.dexterity = 12
        self.character.save()
        Action.record(
            character=self.character,
            action_type="set_field",
            forward_data={"dexterity": "12"},
            reverse_data={"dexterity": None},
        )

        # The undone strength action should be gone
        self.assertFalse(self.character.can_redo())
