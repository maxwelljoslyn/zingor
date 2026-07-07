"""Template tags and filters for character display."""

from django import template

from characters.wiki_links import linkify_field, linkify_spell, linkify_study

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


@register.filter
def format_duration(minutes):
    """Render a whole number of minutes as "H hr M min": {{ mins|format_duration }}"""
    try:
        total = int(minutes)
    except (TypeError, ValueError):
        return None
    hours, mins = divmod(total, 60)
    parts = []
    if hours:
        parts.append(str(hours) + " hr")
    if mins or not hours:
        parts.append(str(mins) + " min")
    return " ".join(parts)


@register.simple_tag
def spell_url(name: str, level: int) -> str:
    """Return the wiki URL for a spell at the given level."""
    return linkify_spell(name, level)


@register.filter
def study_url(name: str) -> str:
    """Return the wiki URL for a sage study."""
    return linkify_study(name)


@register.filter
def field_url(name: str) -> str:
    """Return the wiki URL for a sage field."""
    return linkify_field(name)


@register.inclusion_tag("characters/partials/unknown_or_value.html", takes_context=True)
def unknown_or_value(context, value, field_name, character_id, display_value=None):
    """Render a value or a clickable 'Unknown' placeholder."""
    return {
        "value": value,
        "display_value": value if display_value is None else display_value,
        "field_name": field_name,
        "character_id": character_id,
        "is_set": value is not None and value != "",
        "is_owner": context.get("is_owner", False),
    }
