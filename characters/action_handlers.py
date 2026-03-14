"""Action handlers for undo/redo system.

Each handler implements apply_forward() and apply_reverse() for a specific action type.
"""


def get_handler(action_type):
    """Return the appropriate handler for an action type."""
    handlers = {
        "set_field": SetFieldHandler(),
        "add_item": AddItemHandler(),
        "remove_item": RemoveItemHandler(),
        "update_item": UpdateItemHandler(),
        "add_condition": AddConditionHandler(),
        "remove_condition": RemoveConditionHandler(),
        "add_hit_die": AddHitDieHandler(),
        "remove_hit_die": RemoveHitDieHandler(),
        "add_spell": AddSpellHandler(),
        "remove_spell": RemoveSpellHandler(),
    }
    handler = handlers.get(action_type)
    if handler is None:
        raise ValueError(f"Unknown action type: {action_type}")
    return handler


class SetFieldHandler:
    """Set a model-level field on Character."""

    def apply_forward(self, action):
        character = action.character
        for field_name, value in action.forward_data.items():
            setattr(character, field_name, value)
        character.save()

    def apply_reverse(self, action):
        character = action.character
        for field_name, value in action.reverse_data.items():
            setattr(character, field_name, value)
        character.save()


class AddItemHandler:
    def apply_forward(self, action):
        from .models import Item

        data = action.forward_data.copy()
        data["owner"] = action.character
        if "container_id" in data:
            data["container_id"] = data.pop("container_id")
        Item.objects.create(**data)

    def apply_reverse(self, action):
        from .models import Item

        Item.objects.filter(
            owner=action.character, name=action.forward_data["name"]
        ).last().delete()


class RemoveItemHandler:
    def apply_forward(self, action):
        from .models import Item

        item_id = action.forward_data.get("item_id")
        if item_id:
            Item.objects.filter(id=item_id).delete()

    def apply_reverse(self, action):
        from .models import Item

        data = action.reverse_data.copy()
        data["owner"] = action.character
        Item.objects.create(**data)


class UpdateItemHandler:
    def apply_forward(self, action):
        from .models import Item

        item_id = action.forward_data["item_id"]
        fields = action.forward_data.get("fields", {})
        Item.objects.filter(id=item_id).update(**fields)

    def apply_reverse(self, action):
        from .models import Item

        item_id = action.reverse_data["item_id"]
        fields = action.reverse_data.get("fields", {})
        Item.objects.filter(id=item_id).update(**fields)


class AddConditionHandler:
    def apply_forward(self, action):
        from .models import Condition

        data = action.forward_data.copy()
        data["character"] = action.character
        Condition.objects.create(**data)

    def apply_reverse(self, action):
        from .models import Condition

        Condition.objects.filter(
            character=action.character,
            source=action.forward_data["source"],
        ).last().delete()


class RemoveConditionHandler:
    def apply_forward(self, action):
        from .models import Condition

        condition_id = action.forward_data.get("condition_id")
        if condition_id:
            Condition.objects.filter(id=condition_id).delete()

    def apply_reverse(self, action):
        from .models import Condition

        data = action.reverse_data.copy()
        data["character"] = action.character
        Condition.objects.create(**data)


class AddHitDieHandler:
    def apply_forward(self, action):
        from .models import HitDie

        data = action.forward_data.copy()
        data["character"] = action.character
        HitDie.objects.create(**data)

    def apply_reverse(self, action):
        from .models import HitDie

        if action.forward_data.get("is_bodymass"):
            HitDie.objects.filter(
                character=action.character,
                is_bodymass=True,
            ).last().delete()
        else:
            HitDie.objects.filter(
                character=action.character,
                level=action.forward_data["level"],
            ).last().delete()


class RemoveHitDieHandler:
    def apply_forward(self, action):
        from .models import HitDie

        hit_die_id = action.forward_data.get("hit_die_id")
        if hit_die_id:
            HitDie.objects.filter(id=hit_die_id).delete()

    def apply_reverse(self, action):
        from .models import HitDie

        data = action.reverse_data.copy()
        data["character"] = action.character
        HitDie.objects.create(**data)


class AddSpellHandler:
    def apply_forward(self, action):
        from .models import Spell

        data = action.forward_data.copy()
        data["character"] = action.character
        Spell.objects.create(**data)

    def apply_reverse(self, action):
        from .models import Spell

        Spell.objects.filter(
            character=action.character,
            name=action.forward_data["name"],
        ).delete()


class RemoveSpellHandler:
    def apply_forward(self, action):
        from .models import Spell

        spell_id = action.forward_data.get("spell_id")
        if spell_id:
            Spell.objects.filter(id=spell_id).delete()

    def apply_reverse(self, action):
        from .models import Spell

        data = action.reverse_data.copy()
        data["character"] = action.character
        Spell.objects.create(**data)
