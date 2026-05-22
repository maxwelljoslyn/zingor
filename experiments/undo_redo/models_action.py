"""Action model and Character undo/redo methods, extracted from characters/models.py."""

from django.db import models

# --- Character methods (were on the Character model) ---


def can_undo(self):
    return self.actions.filter(is_undone=False).exists()


def undo(self):
    from .action_handlers import get_handler

    action = self.actions.filter(is_undone=False).order_by("-timestamp").first()
    if action is None:
        return False
    handler = get_handler(action.action_type)
    handler.apply_reverse(action)
    action.is_undone = True
    action.save(update_fields=["is_undone"])
    return True


def can_redo(self):
    return self.actions.filter(is_undone=True).exists()


def redo(self):
    from .action_handlers import get_handler

    action = self.actions.filter(is_undone=True).order_by("timestamp").first()
    if action is None:
        return False
    handler = get_handler(action.action_type)
    handler.apply_forward(action)
    action.is_undone = False
    action.save(update_fields=["is_undone"])
    return True


# --- Action model ---


class Action(models.Model):
    """Records a mutation for undo/redo support."""

    character = models.ForeignKey(
        "Character",
        on_delete=models.CASCADE,
        related_name="actions",
        null=True,
        blank=True,
    )
    action_type = models.CharField(max_length=50)
    forward_data = models.JSONField(
        default=dict,
        encoder=None,
    )
    reverse_data = models.JSONField(
        default=dict,
        encoder=None,
    )
    is_undone = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    group_id = models.CharField(max_length=100, null=True, blank=True)
    sequence = models.IntegerField(default=0)

    class Meta:
        ordering = ["timestamp", "sequence"]

    def __str__(self):
        status = " (undone)" if self.is_undone else ""
        return f"{self.action_type}{status}"

    @classmethod
    def record(cls, character, action_type, forward_data, reverse_data, **kwargs):
        """Create a new action, discarding any undone actions (branching history)."""
        character.actions.filter(is_undone=True).delete()
        return cls.objects.create(
            character=character,
            action_type=action_type,
            forward_data=forward_data,
            reverse_data=reverse_data,
            **kwargs,
        )
