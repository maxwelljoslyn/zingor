"""Read a treasure hoard written as text into a name -> XP mapping.

No model imports — takes text, returns values. Both the ``split_treasure``
management command and the web splitter parse hoards through here, so a hoard
you can paste into one is a hoard you can feed to the other.

Three formats are accepted, tried in that order: JSON, a Python dict literal,
and the loosest form — one ``name: value`` per line::

    # cavern of the frog king
    gem of true seeing: 4,200
    platinum crown 3100
    healing potion: 400 xp

Repeated names are numbered rather than collapsed, so listing "gem" three
times gives you three gems.
"""

from __future__ import annotations

import ast
import json


class HoardError(ValueError):
    """A hoard that could not be read: wrong shape, or a bad name or value in it.

    Messages name the offending item or line but never the source, so a caller
    that has one (a file path, a form field) can prefix its own.
    """


def parse_hoard(text: str) -> dict[str, int]:
    """Parse `text` in whichever of the three supported formats it is in.

    Raises `HoardError` if the text is empty, holds no items, or names an item
    whose value is not a non-negative whole number of XP.
    """
    if not text.strip():
        raise HoardError("the hoard is empty.")
    for parse in (json.loads, ast.literal_eval):
        try:
            data = parse(text)
        except (ValueError, SyntaxError):
            continue
        return _as_hoard(data)
    return _parse_lines(text)


def _as_hoard(data: object) -> dict[str, int]:
    """Validate a parsed JSON/literal payload as a name -> XP mapping."""
    if not isinstance(data, dict):
        raise HoardError(f"the hoard is a {type(data).__name__}, not a dict.")
    hoard: dict[str, int] = {}
    for name, value in data.items():
        if not isinstance(name, str):
            raise HoardError(f"item name {name!r} is not a string.")
        hoard[name] = _as_xp(value, name)
    # An empty mapping parses fine but divides to nothing, which is a mistake
    # worth naming rather than a division worth showing.
    if not hoard:
        raise HoardError("the hoard has no items in it.")
    return hoard


def _parse_lines(text: str) -> dict[str, int]:
    """Parse the loose 'name: value' format, numbering any repeated names."""
    hoard: dict[str, int] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip().rstrip(",")
        # Only whole-line comments, so an item may be named "potion #2".
        if not line or line.startswith("#"):
            continue
        # Drop a trailing unit so "handbell 50 xp" splits on the right space.
        if line.lower().endswith("xp"):
            line = line[:-2].rstrip()
        name, _, value = line.rpartition(":" if ":" in line else " ")
        name = name.strip().strip("\"'")
        if not name:
            raise HoardError(f"line {number}: no name before the value.")
        hoard[_unique(name, hoard)] = _as_xp(value.strip(), name)
    if not hoard:
        raise HoardError("the hoard has no items in it.")
    return hoard


def _unique(name: str, hoard: dict[str, int]) -> str:
    """Number a repeated name so a hoard can hold three separate gems."""
    if name not in hoard:
        return name
    copy = 2
    while f"{name} ({copy})" in hoard:
        copy += 1
    return f"{name} ({copy})"


def _as_xp(value: object, name: str) -> int:
    """Coerce one XP value, tolerating '4,200' and a trailing 'xp'."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise HoardError(f"{name!r} has a non-numeric value {value!r}.")
    if isinstance(value, str):
        cleaned = value.strip().lower().removesuffix("xp").strip().replace(",", "")
        try:
            value = int(cleaned)
        except ValueError:
            raise HoardError(f"{name!r} has a non-numeric value {value!r}.") from None
    if value < 0:
        raise HoardError(f"{name!r} has a negative value {value!r}.")
    return value
