"""Template tags and filters for character display."""

from django import template

register = template.Library()


@register.filter
def format_modifier(value):
    """Format a modifier value with +/- sign. E.g. 3 -> '+3', -2 -> '-2'."""
    if value is None:
        return "—"
    if value >= 0:
        return f"+{value}"
    return str(value)


@register.filter
def format_pct(value):
    """Format a percentage value."""
    if value is None:
        return "—"
    return f"{value}%"


@register.filter
def floordiv(value, arg):
    """Integer division: {{ value|floordiv:4 }}"""
    try:
        return int(value) // int(arg)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


@register.filter
def ceildiv(value, arg):
    """Ceiling division: {{ value|ceildiv:4 }}"""
    try:
        v, a = int(value), int(arg)
        return -(-v // a)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


@register.inclusion_tag("characters/partials/unknown_or_value.html")
def unknown_or_value(value, field_name, character_id, display_value=None):
    """Render a value or a clickable 'Unknown' placeholder."""
    return {
        "value": value,
        "display_value": value if display_value is None else display_value,
        "field_name": field_name,
        "character_id": character_id,
        "is_set": value is not None and value != "",
    }
