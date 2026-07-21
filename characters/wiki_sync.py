"""Fetch a character's wiki page and apply its Zingor microformats to the DB.

``microformats.py`` stays a pure parser; this module owns HTTP and persistence.
The wiki is treated as the source of truth for the scalar fields, spells, and
sage studies it carries. Inventory — including coins, which are inventory
items — is intentionally out of scope: money belongs to whichever character
carries it, and stack/container arrangement can't round-trip through a flat
wiki page.
"""

from __future__ import annotations

import requests
from django.db import transaction

from .microformats import SCALARS, parse_sheet
from .models import Character, SageStudyPoints, Spell

USER_AGENT = "Zingor wiki-sync (https://github.com/; character sheet importer)"
FETCH_TIMEOUT = 20


def fetch_page(url: str) -> str:
    """GET a wiki page's HTML, raising on a non-2xx response."""
    response = requests.get(
        url, timeout=FETCH_TIMEOUT, headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    return response.text


@transaction.atomic
def sync_character_from_wiki(character: Character) -> list[str]:
    """Parse the character's wiki page and update the row in place.

    Returns the parser's warnings for logging. Scalars are copied only when the
    parsed value is present, so a temporarily-absent field on the wiki never
    nukes existing data. Spells and sage studies are replace-all, but only when
    that collection's root markup is actually present on the page: the wiki is
    authoritative for a section it carries, yet a missing/broken section leaves
    the existing rows alone rather than wiping them.
    """
    parsed = parse_sheet(fetch_page(character.wiki_url))
    for _suffix, attr, _coerce in SCALARS:
        value = getattr(parsed.character, attr)
        if value is None:
            continue
        if attr == "name" and value == "":
            continue
        setattr(character, attr, value)
    character.save()

    if Spell in parsed.sections_present:
        character.spells.all().delete()
        for spell in parsed.spells:
            spell.pk = None
            spell.character = character
            spell.save()

    if SageStudyPoints in parsed.sections_present:
        # Preserve soft-deleted (hidden) studies across a sync: keep their rows
        # and retained points, and don't let the wiki resurrect them.
        hidden_studies = set(
            character.sage_studies.filter(hidden=True).values_list("study", flat=True)
        )
        character.sage_studies.filter(hidden=False).delete()
        for study in parsed.sage_studies:
            if study.study in hidden_studies:
                continue
            study.pk = None
            study.character = character
            study.save()

    return parsed.warnings
