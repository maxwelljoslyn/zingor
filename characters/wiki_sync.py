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
from django.utils import timezone

from .limits import MAX_SYNC_WARNINGS
from .microformats import SCALARS, parse_sheet
from .models import (
    Character,
    SageAbilityPoints,
    SageChosenField,
    SageStudyPoints,
    Spell,
)
from .sage import canonical_field, canonical_study

USER_AGENT = "Zingor wiki-sync (https://github.com/; character sheet importer)"
FETCH_TIMEOUT = 20


def _canonicalize(name, resolve, label: str, warnings: list[str]) -> str:
    """Snap a parsed sage name to the catalogue, noting any name it rewrote.

    Adventure wiki pages are hand-written and spell studies and fields
    inconsistently, so storing the page's spelling verbatim would scatter one
    study across several names and re-import the old spelling on every sync.
    The rewrite is recorded as a warning so ``sync_wiki`` reports which pages
    still want tidying; it is not an error, and the sync proceeds either way.
    """
    canonical = resolve(name)
    if canonical != name:
        warnings.append(f"{label} {name!r}: stored under catalogue name {canonical!r}")
    return canonical


def cap_warnings(warnings: list[str]) -> list[str]:
    """Trim a warning list to MAX_SYNC_WARNINGS, noting how many were dropped.

    The count is appended as a final warning rather than stored separately, so
    everything the sheet shows is one plain list of strings.
    """
    if len(warnings) <= MAX_SYNC_WARNINGS:
        return warnings
    dropped = len(warnings) - MAX_SYNC_WARNINGS
    return warnings[:MAX_SYNC_WARNINGS] + [f"and {dropped} more warnings not shown"]


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

    Returns warnings for logging: the parser's, plus one for every sage name
    rewritten to its catalogue spelling. The same list, capped at
    MAX_SYNC_WARNINGS, is stored on the row (``sync_warnings``, dated by
    ``last_synced_at``) so the sheet can show the player what this run could not
    read. Scalars are copied only when the
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
            chosen.field = _canonicalize(
                chosen.field, canonical_field, "sage field", parsed.warnings
            )
            if chosen.field in seen_fields:
                continue
            seen_fields.add(chosen.field)
            chosen.pk = None
            chosen.character = character
            chosen.save()

    if SageStudyPoints in parsed.sections_present:
        # Preserve soft-deleted (hidden) studies across a sync: keep their rows
        # and retained points, and don't let the wiki resurrect them. Hidden
        # rows predating the name corrections still carry the old spelling, so
        # they are matched canonically or the wiki resurrects them anyway.
        hidden_studies = {
            canonical_study(study)
            for study in character.sage_studies.filter(hidden=True).values_list(
                "study", flat=True
            )
        }
        character.sage_studies.filter(hidden=False).delete()
        # A hand-edited page can list one study under two field headings; the
        # first listing wins rather than tripping the per-character unique key.
        seen_studies = set(hidden_studies)
        for study in parsed.sage_studies:
            study.study = _canonicalize(
                study.study, canonical_study, "sage study", parsed.warnings
            )
            if study.study in seen_studies:
                continue
            seen_studies.add(study.study)
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

    # Saved last, not alongside the scalars: _canonicalize appends to
    # parsed.warnings as the sage records above are written, so the list is only
    # complete once they are. One save covers the scalars too — nothing between
    # here and their assignment reads them back off the row.
    character.sync_warnings = cap_warnings(parsed.warnings)
    character.last_synced_at = timezone.now()
    character.save()
    return parsed.warnings
