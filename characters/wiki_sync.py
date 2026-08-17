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
    SageConcentration,
    SageStudyPoints,
    Spell,
)
from .sage import (
    canonical_concentration,
    canonical_field,
    canonical_study,
    concentration_spec,
)

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


def _group_concentrations(parsed) -> dict[str, dict[str, int | None]]:
    """Fold the page's sage-concentration records into {study: {bucket: points}}.

    Points stay as the page gave them — None where it gave none — because what a
    bucket is actually worth depends on its study's rule, which only
    ``_apply_concentrations`` is in a position to apply.
    """
    groups: dict[str, dict[str, int | None]] = {}
    for record in parsed.concentrations:
        study = _canonicalize(
            record.study_name, canonical_study, "sage study", parsed.warnings
        )
        spec = concentration_spec(study)
        if spec is None:
            parsed.warnings.append(
                f"sage concentration {record.name!r}: {study!r} has no "
                + "concentrations, so it was ignored"
            )
            continue
        if spec.are_abilities:
            parsed.warnings.append(
                f"sage concentration {record.name!r}: {study!r} keeps its "
                + "concentrations as standalone sage abilities, so this belongs "
                + "in a zingor-sage-ability record and was ignored"
            )
            continue
        name = _canonicalize(
            record.name,
            lambda value: canonical_concentration(study, value),
            f"sage concentration under {study}",
            parsed.warnings,
        )
        if not spec.permits(name):
            # Unlike a study or field name, this is not a spelling Zingor has
            # merely failed to hear of: the rules define the whole list, so a
            # name off it is not an allocation the character could have made.
            # The valid names are not spelled out here: there are twenty-two of
            # them for the Outer Planes, and the warning list is capped. The
            # sheet's picker for the study is the place to see them.
            parsed.warnings.append(
                f"sage concentration {name!r}: not one of the concentrations "
                + f"{study} allows, so it was ignored"
            )
            continue
        buckets = groups.setdefault(study, {})
        if name in buckets:
            parsed.warnings.append(
                f"sage concentration {name!r} under {study!r}: listed twice; "
                + "the first listing wins"
            )
            continue
        buckets[name] = record.page_points
    return groups


def _apply_studies(character: Character, parsed) -> None:
    """Make the character's visible study rows match the page's.

    Rows are updated in place rather than deleted and rebuilt: a study's
    concentrations hang off its pk, so rebuilding the row would cascade them
    away — including the hidden ones a sync is supposed to leave alone.

    Studies and concentrations are separate ZMF sections, and each is
    authoritative only when the page carries it — the same contract spells and
    the rest have. That cuts both ways here, because either section can reach a
    study row:

    * No concentration table: concentrations are left exactly as they are. The
      page is saying nothing about them, not saying there are none.
    * No study table: study rows are neither created from nothing nor deleted
      for going unmentioned. Concentrations still apply, to the studies they
      name; a study named only by a concentration keeps whatever points it
      already had, and is invented from its buckets only if it is new.
    """
    # Soft-deleted (hidden) studies keep their rows and retained points, and
    # the wiki cannot resurrect them. Hidden rows predating the name
    # corrections still carry the old spelling, so they are matched
    # canonically or the wiki resurrects them anyway.
    hidden_studies = {
        canonical_study(study)
        for study in character.sage_studies.filter(hidden=True).values_list(
            "study", flat=True
        )
    }
    stale = {
        canonical_study(row.study): row
        for row in character.sage_studies.filter(hidden=False)
    }
    studies_present = SageStudyPoints in parsed.sections_present
    concentrations_present = SageConcentration in parsed.sections_present
    buckets_by_study = _group_concentrations(parsed) if concentrations_present else {}
    seen: set[str] = set()
    for record in parsed.sage_studies:
        study = _canonicalize(
            record.study, canonical_study, "sage study", parsed.warnings
        )
        if study in hidden_studies:
            continue
        if study in seen:
            # A hand-edited page can list one study under two field headings;
            # the first listing wins rather than the second silently
            # overwriting its points.
            parsed.warnings.append(
                f"sage study {study!r}: listed twice; the first listing's points win"
            )
            continue
        seen.add(study)
        row = stale.pop(study, None) or SageStudyPoints(character=character)
        row.study = study
        row.points = record.points
        row.chosen = record.chosen
        row.save()
        if concentrations_present:
            _apply_concentrations(row, buckets_by_study.pop(study, {}), parsed.warnings)

    # Buckets naming a study the page never lists among its studies. The study
    # is real enough — the player committed points inside it — so it is kept
    # rather than the buckets being dropped.
    for study, buckets in buckets_by_study.items():
        if study in hidden_studies:
            continue
        row = stale.pop(study, None)
        if row is None:
            # Nothing to go on but the buckets, so the total is inferred from
            # them. This is the only place a study's points are invented.
            spec = concentration_spec(study)
            row = SageStudyPoints(
                character=character,
                study=study,
                points=spec.total_from_buckets(
                    [points for points in buckets.values() if points is not None]
                ),
            )
            parsed.warnings.append(
                f"sage study {study!r}: not listed, but its concentrations are; "
                + "its points were worked out from them"
            )
            row.save()
        elif studies_present:
            # The page has a study table and left this one out of it while still
            # naming it on a concentration. Its own points are the ones Zingor
            # already holds; the page has given no reason to change them.
            parsed.warnings.append(
                f"sage study {study!r}: not in the study table, but its "
                + "concentrations are listed; its existing points were kept"
            )
        _apply_concentrations(row, buckets, parsed.warnings)

    # The wiki is authoritative for the studies it carries, so a visible row it
    # no longer lists is gone — but only when the page actually carries a study
    # table. A page of concentrations alone says nothing about which studies the
    # character has, and must not be read as saying they have none.
    if studies_present:
        for row in stale.values():
            row.delete()


def _apply_concentrations(
    row: SageStudyPoints, buckets: dict[str, int | None], warnings: list[str]
) -> None:
    """Make one study's visible concentration rows match the page's.

    What a bucket is worth is the study's rule, not the page's claim: a
    block-priced subject costs a fixed amount and a mirrored one holds the
    study's whole total. A number the page gives anyway is not silently
    discarded — where it contradicts the rule, it is reported.

    ``granted`` is deliberately not read from the page. Like ``hidden`` it is
    local sheet state, so it is carried across by name rather than overwritten
    by a sync that has nothing to say about it.
    """
    spec = concentration_spec(row.study)
    hidden = {
        canonical_concentration(row.study, name)
        for name in row.concentrations.filter(hidden=True).values_list(
            "name", flat=True
        )
    }
    stale = {c.name: c for c in row.concentrations.filter(hidden=False)}
    # Buckets are only ever collected for a study that has a spec, so this is
    # empty for the great majority of studies — but the delete pass below still
    # has to run, to clear rows a study kept from before it lost its spec.
    for name, page_points in buckets.items() if spec else ():
        if name in hidden:
            continue
        points = spec.stored_points(page_points or 0)
        if page_points is not None and spec.page_disagrees(page_points, row.points):
            warnings.append(_points_disagreement(row, spec, name, page_points, points))
        concentration = stale.pop(name, None) or SageConcentration(study=row, name=name)
        concentration.points = points
        concentration.save()
    for concentration in stale.values():
        concentration.delete()


def _points_disagreement(row, spec, name: str, page_points: int, stored: int) -> str:
    """Explain why a bucket is not worth what the page said it was."""
    where = f"sage concentration {name!r} under {row.study!r}: page says {page_points}"
    if spec.mirrored:
        return (
            f"{where}, but every concentration of this study is worth the "
            + f"study's whole total ({row.points}); no separate figure is kept"
        )
    return (
        f"{where}, but this study grants one subject per {spec.block} points, "
        + f"so {stored} was stored"
    )


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
    the existing rows alone rather than wiping them. Studies replace their
    contents in place rather than by delete-and-rebuild — see ``_apply_studies``.
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

    # Either section can bring study rows into play: concentrations name the
    # study they belong to, so a page carrying only those still has something to
    # say about studies. Which of the two is present decides how far that goes,
    # inside _apply_studies.
    if parsed.sections_present & {SageStudyPoints, SageConcentration}:
        _apply_studies(character, parsed)

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
            if ability.study:
                ability.study = _canonicalize(
                    ability.study, canonical_study, "sage study", parsed.warnings
                )
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
