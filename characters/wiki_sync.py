"""Fetch a character's wiki page and apply its Zingor microformats to the DB.

``microformats.py`` stays a pure parser; this module owns HTTP and persistence.
The wiki is treated as the source of truth for the scalar fields, spells,
chosen sage fields, sage studies, and standalone sage abilities it carries.
Inventory — including
coins, which are inventory
items — is intentionally out of scope: money belongs to whichever character
carries it, and stack/container arrangement can't round-trip through a flat
wiki page.
"""

from __future__ import annotations

import requests
from django.db import transaction

from .microformats import SCALARS, parse_sheet
from .models import (
    Character,
    SageAbilityPoints,
    SageChosenField,
    SageStudyPoints,
    Spell,
)

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
    nukes existing data. Spells, chosen fields, sage studies, and sage
    abilities are
    replace-all, but only when that collection's root markup is actually
    present on the page: the wiki is
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

    if SageChosenField in parsed.sections_present:
        character.chosen_fields.all().delete()
        seen_fields = set()
        for chosen in parsed.chosen_fields:
            if chosen.field in seen_fields:
                continue
            seen_fields.add(chosen.field)
            chosen.pk = None
            chosen.character = character
            chosen.save()

    if SageStudyPoints in parsed.sections_present:
        # Preserve soft-deleted (hidden) studies across a sync: keep their rows
        # and retained points, and don't let the wiki resurrect them.
        # Keyed by study and area of concentration together, since that is what
        # tells one row of History from another.
        hidden_studies = set(
            character.sage_studies.filter(hidden=True).values_list(
                "study", "concentration"
            )
        )
        character.sage_studies.filter(hidden=False).delete()
        # A hand-edited page can list one study under two field headings; the
        # first listing wins rather than tripping the per-character unique key.
        seen_studies = set(hidden_studies)
        for study in parsed.sage_studies:
            key = (study.study, study.concentration)
            if key in seen_studies:
                continue
            seen_studies.add(key)
            study.pk = None
            study.character = character
            study.save()

    if SageAbilityPoints in parsed.sections_present:
        # Same soft-delete preservation as studies: hidden abilities keep their
        # rows and points, and the wiki can't resurrect them.
        hidden_abilities = set(
            character.sage_abilities.filter(hidden=True).values_list(
                "ability", flat=True
            )
        )
        character.sage_abilities.filter(hidden=False).delete()
        for ability in parsed.sage_abilities:
            if ability.ability in hidden_abilities:
                continue
            ability.pk = None
            ability.character = character
            ability.save()

    return parsed.warnings
