# Undo/Redo Feature (Removed 2026-05-21)

Archived from the main codebase. This documents how the feature worked and why it was removed.

## Why it was removed

Direct inline editing of fields/items/etc. makes correcting mistakes easy enough that undo/redo adds complexity without proportionate value. The harder problem — cross-character undo (e.g. "character X transfers item to character Y, Y deletes it, X undoes the transfer") — would require a much more sophisticated implementation. Better to remove the half-baked version and reintroduce if actually needed.

## How it worked

### Action recording

Every mutation (field update, item add/delete, condition add/delete, hit die add/delete, spell add/delete) created an `Action` record via `Action.record()`. Each Action stored:

- `character` — FK to the character
- `action_type` — string like `"set_field"`, `"add_item"`, `"remove_spell"`, etc.
- `forward_data` — JSON dict with data needed to replay the action
- `reverse_data` — JSON dict with data needed to reverse the action
- `is_undone` — boolean tracking whether the action has been undone
- `timestamp` — when the action was recorded
- `group_id` / `sequence` — for grouping related actions (not fully used)

`Action.record()` also deleted any previously-undone actions (branching history: once you make a new change after undoing, you can't redo the undone actions).

### Action handlers (`action_handlers.py`)

Each action type had a handler class with `apply_forward()` and `apply_reverse()` methods:

- `SetFieldHandler` — uses `setattr`/`getattr` on Character model fields
- `AddItemHandler` / `RemoveItemHandler` — create/delete Item rows
- `UpdateItemHandler` — update fields on an existing Item
- `AddConditionHandler` / `RemoveConditionHandler` — create/delete Condition rows
- `AddHitDieHandler` / `RemoveHitDieHandler` — create/delete HitDie rows
- `AddSpellHandler` / `RemoveSpellHandler` — create/delete Spell rows

`get_handler(action_type)` dispatched to the right handler.

### Character model methods

On `Character`:

- `can_undo()` — checks if any non-undone actions exist
- `undo()` — finds the most recent non-undone action, calls `handler.apply_reverse()`, marks `is_undone=True`
- `can_redo()` — checks if any undone actions exist
- `redo()` — finds the oldest undone action, calls `handler.apply_forward()`, marks `is_undone=False`

### Views and URLs

Two POST endpoints:
- `POST /character/<pk>/undo/` — calls `character.undo()`, returns full sheet body HTML
- `POST /character/<pk>/redo/` — calls `character.redo()`, returns full sheet body HTML

### Template

Two HTMX buttons in `character_sheet.html` toolbar, targeting `#sheet-body` with `innerHTML` swap.

### Where Action.record() was called

In `views.py`, after every mutation:
- `update_field()` — records `set_field` with old/new values as strings
- `add_item()` — records `add_item` per item created (respects quantity)
- `delete_item()` — records `remove_item` with item snapshot
- `add_condition()` — records `add_condition`
- `delete_condition()` — records `remove_condition`
- `add_hit_die()` — records `add_hit_die`
- `delete_hit_die()` — records `remove_hit_die`
- `add_spell()` — records `add_spell`
- `delete_spell()` — records `remove_spell`

## Archived files

- `action_handlers.py` — all handler classes
- `views_undo_redo.py` — the undo/redo view functions (extracted from views.py)
- `models_action.py` — the Action model and Character undo/redo methods (extracted from models.py)
- `urls_undo_redo.py` — the URL patterns
- `template_buttons.html` — the toolbar button HTML
- `test_models_undo_redo.py` — model-level tests
- `test_views_undo_redo.py` — view-level tests
