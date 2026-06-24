"""Pure functions for building wiki.alexissmolensk.com URLs."""

WIKI_BASE = "https://wiki.alexissmolensk.com/index.php"


def linkify_spell(name: str, level: int) -> str:
    """Return the wiki URL for a spell by name."""
    slug = name.replace(" ", "_")
    if level == 0:
        return f"{WIKI_BASE}/{slug}_(cantrip)"
    else:
        return f"{WIKI_BASE}/{slug}_(spell)"


def linkify_study(name: str) -> str:
    """Return the wiki URL for a sage study by name."""
    slug = name.replace(" ", "_")
    return f"{WIKI_BASE}/{slug}_(sage_study)"


def linkify_field(name: str) -> str:
    """Return the wiki URL for a sage field by name."""
    slug = name.replace(" ", "_")
    return f"{WIKI_BASE}/{slug}_(sage_field)"
