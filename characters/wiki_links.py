"""Pure functions for building wiki.alexissmolensk.com URLs."""

import re

WIKI_BASE = "https://wiki.alexissmolensk.com/index.php"

# Class-specific variants — "Civitas (Mage)", "Animal Training (Assassin)" —
# are Zingor's own disambiguators for fields a class reaches on its own terms.
# The wiki has a single page per base name, so the suffix is dropped when
# building the URL or it 404s.
_VARIANT_SUFFIX = re.compile(r"\s+\(.*\)$")


def _slug(name: str) -> str:
    """Turn a study or field name into its wiki page slug."""
    return _VARIANT_SUFFIX.sub("", name).replace(" ", "_")


def linkify_spell(name: str, level: int) -> str:
    """Return the wiki URL for a spell by name."""
    slug = name.replace(" ", "_")
    if level == 0:
        return f"{WIKI_BASE}/{slug}_(cantrip)"
    else:
        return f"{WIKI_BASE}/{slug}_(spell)"


def linkify_study(name: str) -> str:
    """Return the wiki URL for a sage study by name."""
    return f"{WIKI_BASE}/{_slug(name)}_(sage_study)"


def linkify_field(name: str) -> str:
    """Return the wiki URL for a sage field by name."""
    return f"{WIKI_BASE}/{_slug(name)}_(sage_field)"
