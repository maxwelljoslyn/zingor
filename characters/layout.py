"""Per-user display-layout preferences for the character sheet.

The sheet is composed of named sections, and some sections contain reorderable
rows (e.g. the six ability scores, the notes blocks). A user may choose the order
these appear in; the choice is stored per-user and applies whenever that user
views any character sheet. This module is the single source of truth for the
canonical keys and their default order across every orderable axis ("scope"),
plus the logic that reconciles a stored order against the keys that currently
exist in code.
"""

from .models import Character, LayoutOrder

# The scope under which the top-level section order is stored.
SECTIONS_SCOPE = "sections"

# Canonical sections in default top-to-bottom order: (key, template).
SECTIONS: list[tuple[str, str]] = [
    ("identity", "characters/partials/identity.html"),
    ("abilities", "characters/partials/abilities.html"),
    ("hp", "characters/partials/hp.html"),
    ("inventory", "characters/partials/inventory.html"),
    ("conditions", "characters/partials/conditions.html"),
    ("spells", "characters/partials/spells.html"),
    ("notes", "characters/partials/notes.html"),
    ("sage", "characters/partials/sage.html"),
]
SECTION_KEYS: list[str] = [key for key, _ in SECTIONS]

# Reorderable rows within a section, keyed by section key. Each value is both the
# default order and the closed set of valid keys for that scope.
SUBSECTIONS: dict[str, list[str]] = {
    "abilities": list(Character.ABILITY_NAMES),
    "notes": ["background", "appearance", "notes"],
}


def valid_keys(scope: str) -> list[str] | None:
    """The default/allowed keys for an orderable scope, or None if unknown."""
    if scope == SECTIONS_SCOPE:
        return SECTION_KEYS
    return SUBSECTIONS.get(scope)


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


def _stored_order(user, scope: str) -> list[str]:
    """The keys this user has saved for `scope`, in saved order (empty if none)."""
    if not getattr(user, "is_authenticated", False):
        return []
    return list(
        LayoutOrder.objects.filter(user=user, scope=scope)
        .order_by("position")
        .values_list("key", flat=True)
    )


def order_for(user, scope: str) -> list[str]:
    """The resolved key order for any scope as `user` should see it."""
    return resolve_order(_stored_order(user, scope), valid_keys(scope))


def section_order(user) -> list[tuple[str, str]]:
    """The resolved sections as (key, template) pairs in the user's order."""
    template_for = dict(SECTIONS)
    return [(key, template_for[key]) for key in order_for(user, SECTIONS_SCOPE)]
