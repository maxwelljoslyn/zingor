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
times gives you three gems: "gem (1 of 3)", "gem (2 of 3)", "gem (3 of 3)".
That holds in all three formats, which is why the two structured ones are read
as key/value pairs: both ``json.loads`` and ``ast.literal_eval`` would quietly
drop all but the last of a repeated key, losing an item out of the hoard.
"""

from __future__ import annotations

import ast
import json
from collections import Counter


class HoardError(ValueError):
    """A hoard that could not be read: wrong shape, or a bad name or value in it.

    Messages name the offending item or line but never the source, so a caller
    that has one (a file path, a form field) can prefix its own.
    """


class _Pairs(list):
    """One parsed object, kept as its raw key/value pairs so repeats survive.

    A `dict` cannot hold the same name twice, and both parsers below build one
    by default — so a hoard listing two potions would arrive as a single potion.
    Marking the pairs with a type of their own also keeps a JSON *array* (an
    ordinary `list`) distinguishable from an object, which is what lets the
    wrong shape still be named as one in the error.
    """

    def __repr__(self) -> str:
        """Print as the object it came from, for error messages quoting a value."""
        return "{" + ", ".join(f"{k!r}: {v!r}" for k, v in self) + "}"


def parse_hoard(text: str) -> dict[str, int]:
    """Parse `text` in whichever of the three supported formats it is in.

    Raises `HoardError` if the text is empty, holds no items, or names an item
    whose value is not a non-negative whole number of XP.
    """
    if not text.strip():
        raise HoardError("the hoard is empty.")
    for parse in (_json_pairs, _literal_pairs):
        try:
            data = parse(text)
        except (ValueError, SyntaxError):
            continue
        return _as_hoard(data)
    return _parse_lines(text)


def _json_pairs(text: str) -> object:
    """Read JSON, keeping every object as pairs rather than as a dict."""
    return json.loads(text, object_pairs_hook=_Pairs)


def _literal_pairs(text: str) -> object:
    """Read a Python literal, keeping a dict literal's repeated keys apart.

    `ast.literal_eval` builds the dict itself, with nothing to hook, so a dict
    is walked as source instead and its keys and values evaluated one by one.
    Anything else is left to `literal_eval`, which rejects what it should.
    """
    node = ast.parse(text.strip(), mode="eval").body
    if not isinstance(node, ast.Dict):
        return ast.literal_eval(node)
    return _Pairs(
        (ast.literal_eval(key), ast.literal_eval(value))
        for key, value in zip(node.keys, node.values, strict=True)
    )


def _as_hoard(data: object) -> dict[str, int]:
    """Validate a parsed JSON/literal payload as a name -> XP mapping."""
    if not isinstance(data, _Pairs):
        raise HoardError(f"the hoard is a {type(data).__name__}, not a dict.")
    entries: list[tuple[str, int]] = []
    for name, value in data:
        if not isinstance(name, str):
            raise HoardError(f"item name {name!r} is not a string.")
        entries.append((name, _as_xp(value, name)))
    # An empty mapping parses fine but divides to nothing, which is a mistake
    # worth naming rather than a division worth showing.
    if not entries:
        raise HoardError("the hoard has no items in it.")
    return _numbered(entries)


def _parse_lines(text: str) -> dict[str, int]:
    """Parse the loose 'name: value' format, numbering any repeated names."""
    entries: list[tuple[str, int]] = []
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
        entries.append((name, _as_xp(value.strip(), name)))
    if not entries:
        raise HoardError("the hoard has no items in it.")
    return _numbered(entries)


def _numbered(entries: list[tuple[str, int]]) -> dict[str, int]:
    """Key the items by name, numbering every copy of a repeated name.

    A repeated name is numbered "(1 of 3)" through "(3 of 3)" rather than
    leaving the first bare and calling the next "(2)": the count has to be read
    off a single row in the division, where the other copies may well sit in
    somebody else's take.
    """
    totals = Counter(name for name, _ in entries)
    seen: Counter[str] = Counter()
    hoard: dict[str, int] = {}
    for name, xp in entries:
        key = name
        if totals[name] > 1:
            seen[name] += 1
            key = f"{name} ({seen[name]} of {totals[name]})"
        hoard[_free(key, hoard)] = xp
    return hoard


def _free(key: str, hoard: dict[str, int]) -> str:
    """Nudge a key aside if the hoard already holds it.

    Only reachable when a hoard names an item exactly as the numbering above
    would have written it — "gem (1 of 2)" typed out by hand — which is rare
    enough to settle with a suffix rather than with a scheme of its own.
    """
    if key not in hoard:
        return key
    copy = 2
    while f"{key} ({copy})" in hoard:
        copy += 1
    return f"{key} ({copy})"


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
