"""Parse "zingormats" — Zingor's HTML microformats — out of a character's wiki page.

A page describes exactly one character. Data is hooked via ``class`` tokens prefixed
``zingor-`` (``class`` survives MediaWiki's sanitizer; ``data-*`` does not). Values are
read from each element's trimmed text content.

Two shapes, mirroring the data model:

* **Scalar fields** map 1:1 to ``Character`` columns::

      <td class="zingor-strength">14</td>          -> character.strength = 14

* **Repeating records** use exactly one level of nesting: a *root* element carries
  ``zingor-<record>`` and its descendants carry ``zingor-<record>-<subfield>``::

      <tr class="zingor-sage-study">
        <td class="zingor-sage-study-name">Faith</td>
        <td class="zingor-sage-study-points">27</td>
      </tr>

  A few studies split their points into named buckets (see ``sage.Concentrations``).
  Those are ``sage-concentration`` records, siblings of the study's own rather than
  nested inside it, so a bucket names its study instead of living within it. Nesting
  would suit the data better — a bucket really is a child of a study — but a wiki
  page's sage section is a table and ``<tr>`` cannot contain ``<tr>``, so nesting
  would cost the player their table. See ``adr/0001-zmf-stays-flat.md``::

      <tr class="zingor-sage-concentration">
        <td class="zingor-sage-concentration-study">History</td>
        <td class="zingor-sage-concentration-name">Ancient Asia</td>
        <td class="zingor-sage-concentration-points">22</td>
      </tr>

  Resolving that study name to a row is ``wiki_sync``'s job; the parser reports every
  record it finds.

The vocabulary is closed (see SCALARS / RECORDS below), so the parser never has to
guess: ``zingor-spell-name`` is unambiguously the ``name`` subfield of a ``spell``
record, never a scalar called ``spell-name``. Coercion is by declared type; on failure
the value is skipped and a human-readable warning is recorded rather than inventing data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Callable

from bs4 import BeautifulSoup

from .models import (
    Character,
    SageAbilityPoints,
    SageChosenField,
    SageConcentration,
    SageStudyPoints,
    Spell,
)

PREFIX = "zingor-"

# --- Coercers: str -> Python value, raising on bad input -------------------------------

_NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")


def _num(text: str) -> str:
    """Pull the first number out of free text, dropping thousands separators."""
    m = _NUM_RE.search(text)
    if not m:
        raise ValueError(f"no number found in {text!r}")
    return m.group(0).replace(",", "")


def _coerce_int(text: str) -> int:
    return int(_num(text))


def _coerce_str(text: str) -> str:
    return text


def _coerce_bool(text: str) -> bool:
    """Truthy marks like Joey's "X" (memorized / used) columns."""
    return text.strip().lower() in {"x", "yes", "true", "y", "✓", "1"}


# --- Vocabulary ------------------------------------------------------------------------

# (class suffix, Character attribute, coercer). Suffix uses hyphens; a couple of
# wiki-facing names are friendlier aliases for the underlying column.
SCALARS: list[tuple[str, str, Callable[[str], object]]] = [
    ("name", "name", _coerce_str),
    ("race", "race", _coerce_str),
    ("sex", "sex", _coerce_str),
    ("class", "char_class", _coerce_str),
    ("level", "level", _coerce_int),
    ("xp", "xp", _coerce_int),
    ("strength", "strength", _coerce_int),
    ("percentile-strength", "percentile_strength", _coerce_int),
    ("dexterity", "dexterity", _coerce_int),
    ("constitution", "constitution", _coerce_int),
    ("intelligence", "intelligence", _coerce_int),
    ("wisdom", "wisdom", _coerce_int),
    ("charisma", "charisma", _coerce_int),
    ("current-hp", "current_hp", _coerce_int),
    ("armor-class", "armor_class", _coerce_int),
    ("notes", "notes", _coerce_str),
    ("background", "background", _coerce_str),
    ("appearance", "appearance", _coerce_str),
]


@dataclass(frozen=True)
class Subfield:
    suffix: str
    attr: str
    coerce: Callable[[str], object]
    required: bool = False
    # Not a column on the record's model: set on the built instance afterwards
    # rather than passed to its constructor, and set to ``default`` when the page
    # omits it. A sage study's concentration is one of these — it names a bucket
    # that ``wiki_sync`` resolves into a row of another model entirely.
    transient: bool = False
    default: object = ""


@dataclass(frozen=True)
class RecordType:
    root: str
    model: type
    subfields: list[Subfield]


RECORDS: list[RecordType] = [
    RecordType(
        "spell",
        Spell,
        [
            Subfield("name", "name", _coerce_str, required=True),
            Subfield("level", "level", _coerce_int, required=True),
            Subfield("memorized", "is_memorized", _coerce_bool),
        ],
    ),
    RecordType(
        "chosen-field",
        SageChosenField,
        [Subfield("name", "field", _coerce_str, required=True)],
    ),
    RecordType(
        "sage-study",
        SageStudyPoints,
        [
            Subfield("name", "study", _coerce_str, required=True),
            Subfield("points", "points", _coerce_int, required=True),
            Subfield("chosen", "chosen", _coerce_bool),
        ],
    ),
    RecordType(
        "sage-ability",
        SageAbilityPoints,
        [
            Subfield("name", "ability", _coerce_str, required=True),
            Subfield("points", "points", _coerce_int, required=True),
            Subfield("source", "source", _coerce_str),
            # Names the study this ability is a concentration of, for the studies
            # whose concentrations are sage abilities outright (Athletics). The
            # wiki-facing name is spelled out because "sage-ability-study" reads
            # as a kind of study rather than as where the ability came from.
            Subfield("from-study", "study", _coerce_str),
        ],
    ),
    RecordType(
        "sage-concentration",
        SageConcentration,
        [
            # The study is transient because the model reaches it by foreign key
            # and a parsed record has only a name; wiki_sync resolves it to a row.
            Subfield("study", "study_name", _coerce_str, required=True, transient=True),
            Subfield("name", "name", _coerce_str, required=True),
            # Transient, and None when the page gives no number at all: a
            # block-priced study's subjects cost a fixed amount and a mirrored
            # study's hold the study's whole total, so neither has a figure worth
            # writing down. Only wiki_sync knows the study's rule, so it works out
            # what the row's points should actually be — and telling "page said
            # nothing" apart from "page said zero" is what lets it warn when a
            # number the page did give contradicts that rule.
            Subfield(
                "points", "page_points", _coerce_int, transient=True, default=None
            ),
        ],
    ),
]


@dataclass
class ParsedSheet:
    character: Character
    spells: list[Spell] = dc_field(default_factory=list)
    chosen_fields: list[SageChosenField] = dc_field(default_factory=list)
    sage_studies: list[SageStudyPoints] = dc_field(default_factory=list)
    sage_abilities: list[SageAbilityPoints] = dc_field(default_factory=list)
    # Each carries a transient ``study_name`` naming the study it belongs to.
    concentrations: list[SageConcentration] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    # Record models whose root markup appeared on the page, even if every row
    # failed to parse. Lets the save step tell "section absent" (leave the DB
    # alone) apart from "section present but empty" (an authoritative wipe).
    sections_present: set[type] = dc_field(default_factory=set)


# --- Parsing ---------------------------------------------------------------------------


def _text(el) -> str:
    return el.get_text(strip=True)


def parse_sheet(html: str) -> ParsedSheet:
    """Parse one character's worth of zingormats from an HTML document."""
    soup = BeautifulSoup(html, "html.parser")
    sheet = ParsedSheet(character=Character())

    for suffix, attr, coerce in SCALARS:
        els = soup.select(f".{PREFIX}{suffix}")
        if not els:
            continue
        if len(els) > 1:
            sheet.warnings.append(
                f"scalar '{suffix}': {len(els)} elements found; using the first"
            )
        raw = _text(els[0])
        try:
            setattr(sheet.character, attr, coerce(raw))
        except Exception as exc:
            sheet.warnings.append(f"scalar '{suffix}': could not parse {raw!r} ({exc})")

    buckets: dict[type, list] = {
        Spell: sheet.spells,
        SageChosenField: sheet.chosen_fields,
        SageStudyPoints: sheet.sage_studies,
        SageAbilityPoints: sheet.sage_abilities,
        SageConcentration: sheet.concentrations,
    }
    for rt in RECORDS:
        roots = soup.select(f".{PREFIX}{rt.root}")
        if roots:
            sheet.sections_present.add(rt.model)
        for n, root in enumerate(roots, start=1):
            record = _build_record(rt, root, n, sheet.warnings)
            if record is not None:
                buckets[rt.model].append(record)

    return sheet


def _build_record(rt: RecordType, root, index: int, warnings: list[str]):
    """Build one (unsaved) record instance from a root element, or None on failure."""
    values: dict[str, object] = {}
    transient: dict[str, object] = {
        sub.attr: sub.default for sub in rt.subfields if sub.transient
    }
    for sub in rt.subfields:
        el = root.select_one(f".{PREFIX}{rt.root}-{sub.suffix}")
        raw = _text(el) if el is not None else ""
        if not raw:
            if sub.required:
                warnings.append(
                    f"{rt.root} #{index}: missing required '{sub.suffix}'; skipped"
                )
                return None
            continue
        try:
            value = sub.coerce(raw)
        except Exception as exc:
            warnings.append(
                f"{rt.root} #{index}: could not parse '{sub.suffix}'={raw!r} ({exc}); skipped"
            )
            return None
        if sub.transient:
            transient[sub.attr] = value
        else:
            values[sub.attr] = value
    record = rt.model(**values)
    for attr, value in transient.items():
        setattr(record, attr, value)
    return record


# --- Rendering (for the runner) --------------------------------------------------------

_DISPLAY_FIELDS = [
    ("name", "name"),
    ("race", "race"),
    ("sex", "sex"),
    ("char_class", "class"),
    ("level", "level"),
    ("xp", "xp"),
    ("strength", "strength"),
    ("dexterity", "dexterity"),
    ("constitution", "constitution"),
    ("intelligence", "intelligence"),
    ("wisdom", "wisdom"),
    ("charisma", "charisma"),
    ("current_hp", "current_hp"),
]


def render_sheet(sheet: ParsedSheet) -> str:
    c = sheet.character
    lines = ["=== Character (unsaved) ==="]
    for attr, label in _DISPLAY_FIELDS:
        val = getattr(c, attr)
        if val is not None and val != "":
            lines.append(f"  {label:<14} {val}")

    lines.append("")
    lines.append(f"=== Spells ({len(sheet.spells)}) ===")
    for s in sheet.spells:
        mem = "memorized" if s.is_memorized else "not memorized"
        lines.append(f"  L{s.level} {s.name} ({mem})")
    if not sheet.spells:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"=== Chosen fields ({len(sheet.chosen_fields)}) ===")
    for cf in sheet.chosen_fields:
        lines.append(f"  {cf.field}")
    if not sheet.chosen_fields:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"=== Sage studies ({len(sheet.sage_studies)}) ===")
    for ss in sheet.sage_studies:
        chosen = " (chosen)" if ss.chosen else ""
        lines.append(f"  {ss.study}: {ss.points}{chosen}")
    if not sheet.sage_studies:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"=== Sage concentrations ({len(sheet.concentrations)}) ===")
    for conc in sheet.concentrations:
        points = "" if conc.page_points is None else f": {conc.page_points}"
        lines.append(f"  {conc.study_name} / {conc.name}{points}")
    if not sheet.concentrations:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"=== Sage abilities ({len(sheet.sage_abilities)}) ===")
    for sa in sheet.sage_abilities:
        source = f" [{sa.source}]" if sa.source else ""
        study = f" (under {sa.study})" if sa.study else ""
        lines.append(f"  {sa.ability}{study}: {sa.points}{source}")
    if not sheet.sage_abilities:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"=== Warnings ({len(sheet.warnings)}) ===")
    for w in sheet.warnings:
        lines.append(f"  ! {w}")
    if not sheet.warnings:
        lines.append("  (none)")

    return "\n".join(lines)
