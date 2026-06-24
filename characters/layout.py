"""Per-user display-layout preferences for the character sheet.

The sheet is composed of named sections, and some sections contain reorderable
rows (e.g. the six ability scores). A user may choose the order these appear in;
the choice is stored per-user and applies whenever that user views any character
sheet. This module is the single source of truth for the canonical keys and
their default order, plus the logic that reconciles a stored order against the
keys that currently exist in code.
"""

from .models import Character, LayoutOrder

# Reorderable rows within a section, keyed by section key. Each value is both
# the default order and the closed set of valid keys for that section.
SUBSECTIONS: dict[str, list[str]] = {
    "abilities": list(Character.ABILITY_NAMES),
}


def resolve_order(stored: list[str], default: list[str]) -> list[str]:
    """Reconcile a stored order with the current key set.

    Returns the keys in `default`, ordered to follow `stored`. Keys in `stored`
    that are no longer valid (or duplicated) are dropped; keys in `default` that
    are absent from `stored` are appended in their default position. This keeps a
    saved layout working when the set of keys changes in code.
    """
    valid = set(default)
    seen: set[str] = set()
    result: list[str] = []
    for key in stored or []:
        if key in valid and key not in seen:
            result.append(key)
            seen.add(key)
    for key in default:
        if key not in seen:
            result.append(key)
    return result


def row_order(user, section: str) -> list[str]:
    """The resolved order of `section`'s rows as `user` should see them."""
    default = SUBSECTIONS[section]
    if not getattr(user, "is_authenticated", False):
        return list(default)
    stored = list(
        LayoutOrder.objects.filter(user=user, scope=section)
        .order_by("position")
        .values_list("key", flat=True)
    )
    return resolve_order(stored, default)
