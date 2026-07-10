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

from .models import Character, SageStudyPoints, Spell
from .units import D, u

PREFIX = "zingor-"

# --- Coercers: str -> Python value, raising on bad input -------------------------------

_NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")
_HEIGHT_RE = re.compile(r"\s*(\d+)\s*'\s*(\d+)?")


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


def _coerce_weight(text: str) -> object:
    """e.g. "75 Lbs." -> 75 lb."""
    return D(_num(text)) * u.lb


def _coerce_height(text: str) -> object:
    """e.g. ``3'4"`` -> 40 inches."""
    m = _HEIGHT_RE.match(text)
    if not m:
        raise ValueError(f"unrecognized height {text!r} (want feet'inches\")")
    feet = int(m.group(1))
    inches = int(m.group(2) or 0)
    return D(feet * 12 + inches) * u.inch


# --- Vocabulary ------------------------------------------------------------------------

# (class suffix, Character attribute, coercer). Suffix uses hyphens; a couple of
# wiki-facing names are friendlier aliases for the underlying column.
SCALARS: list[tuple[str, str, Callable[[str], object]]] = [
    ("character-id", "id", _coerce_int),
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
    ("height", "height", _coerce_height),
    ("weight", "weight", _coerce_weight),
    ("current-hp", "current_hp", _coerce_int),
    ("notes", "notes", _coerce_str),
    ("background", "background", _coerce_str),
    ("appearance", "appearance", _coerce_str),
    ("chosen-field", "chosen_field", _coerce_str),
    ("chosen-study", "chosen_study", _coerce_str),
]

# Coins are inventory items, not Character columns, so they parse into
# ParsedSheet.money (currency -> coin count) for the save step to turn into items.
MONEY_SUFFIXES = ["gp", "sp", "cp"]


@dataclass(frozen=True)
class Subfield:
    suffix: str
    attr: str
    coerce: Callable[[str], object]
    required: bool = False


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
        "sage-study",
        SageStudyPoints,
        [
            Subfield("name", "study", _coerce_str, required=True),
            Subfield("points", "points", _coerce_int, required=True),
        ],
    ),
]


@dataclass
class ParsedSheet:
    character: Character
    spells: list[Spell] = dc_field(default_factory=list)
    sage_studies: list[SageStudyPoints] = dc_field(default_factory=list)
    money: dict[str, int] = dc_field(default_factory=dict)
    warnings: list[str] = dc_field(default_factory=list)


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

    for suffix in MONEY_SUFFIXES:
        els = soup.select(f".{PREFIX}{suffix}")
        if not els:
            continue
        if len(els) > 1:
            sheet.warnings.append(
                f"scalar '{suffix}': {len(els)} elements found; using the first"
            )
        raw = _text(els[0])
        try:
            sheet.money[suffix] = _coerce_int(raw)
        except Exception as exc:
            sheet.warnings.append(f"scalar '{suffix}': could not parse {raw!r} ({exc})")

    buckets: dict[type, list] = {
        Spell: sheet.spells,
        SageStudyPoints: sheet.sage_studies,
    }
    for rt in RECORDS:
        for n, root in enumerate(soup.select(f".{PREFIX}{rt.root}"), start=1):
            record = _build_record(rt, root, n, sheet.warnings)
            if record is not None:
                buckets[rt.model].append(record)

    return sheet


def _build_record(rt: RecordType, root, index: int, warnings: list[str]):
    """Build one (unsaved) record instance from a root element, or None on failure."""
    values: dict[str, object] = {}
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
            values[sub.attr] = sub.coerce(raw)
        except Exception as exc:
            warnings.append(
                f"{rt.root} #{index}: could not parse '{sub.suffix}'={raw!r} ({exc}); skipped"
            )
            return None
    return rt.model(**values)


# --- Rendering (for the runner) --------------------------------------------------------

_DISPLAY_FIELDS = [
    ("id", "id"),
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
    ("height_display", "height"),
    ("weight", "weight"),
    ("current_hp", "current_hp"),
]


def render_sheet(sheet: ParsedSheet) -> str:
    c = sheet.character
    lines = ["=== Character (unsaved) ==="]
    for attr, label in _DISPLAY_FIELDS:
        val = getattr(c, attr)
        if val is not None and val != "":
            lines.append(f"  {label:<14} {val}")
    for currency in MONEY_SUFFIXES:
        if currency in sheet.money:
            lines.append(f"  {currency:<14} {sheet.money[currency]}")

    lines.append("")
    lines.append(f"=== Spells ({len(sheet.spells)}) ===")
    for s in sheet.spells:
        mem = "memorized" if s.is_memorized else "not memorized"
        lines.append(f"  L{s.level} {s.name} ({mem})")
    if not sheet.spells:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"=== Sage studies ({len(sheet.sage_studies)}) ===")
    for ss in sheet.sage_studies:
        lines.append(f"  {ss.study}: {ss.points}")
    if not sheet.sage_studies:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"=== Warnings ({len(sheet.warnings)}) ===")
    for w in sheet.warnings:
        lines.append(f"  ! {w}")
    if not sheet.warnings:
        lines.append("  (none)")

    return "\n".join(lines)
