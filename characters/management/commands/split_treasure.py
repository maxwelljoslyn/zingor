"""Split a hoard into near-equal XP shares from the command line.

``uv run python manage.py split_treasure hoard.txt --shares 4``

The input file may be JSON, a Python dict literal, or the loosest form — one
``name: value`` per line::

    # cavern of the frog king
    gem of true seeing: 4,200
    platinum crown 3100
    healing potion: 400 xp

Repeated names are numbered rather than collapsed, so listing "gem" three
times gives you three gems.

Recipients who draw uneven shares are written ``name:shares``::

    --names 'Alix,Bront:2,Cwen:1/2'

Pass ``-o/--outfile`` to save the split instead of printing it.
"""

from __future__ import annotations

import ast
import json
from fractions import Fraction
from math import gcd, lcm
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from characters.treasure import split_treasure, split_treasure_by_share


class Command(BaseCommand):
    help = "Divide a file of treasure names and XP values into near-equal shares."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "file",
            type=Path,
            help="Hoard file: JSON, a Python dict literal, or 'name: value' lines.",
        )
        parser.add_argument(
            "-n",
            "--shares",
            type=int,
            help="How many equal shares to cut. Inferred from --names when omitted.",
        )
        parser.add_argument(
            "--names",
            help=(
                "Comma-separated recipients, e.g. 'Alix,Bront,Cwen'. Append"
                + " ':shares' to anyone drawing an uneven share, e.g. 'Cwen:1/2'."
            ),
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit the split as JSON instead of a table.",
        )
        parser.add_argument(
            "-o",
            "--outfile",
            type=Path,
            help="Write the split to this path instead of printing it.",
        )

    def handle(self, *args, **options) -> None:
        items = _load_hoard(options["file"])
        shares = _recipients(options["names"], options["shares"])
        if options["names"]:
            split = split_treasure_by_share(shares, items)
        else:
            split = dict(zip(shares, split_treasure(len(shares), items), strict=True))
        if options["as_json"]:
            lines = [(json.dumps(_as_payload(split, shares), indent=2), False)]
        else:
            lines = _table(split, shares, items)
        outfile = options["outfile"]
        if outfile is None:
            for text, heading in lines:
                self.stdout.write(self.style.SUCCESS(text) if heading else text)
            return
        _save(outfile, options["file"], [text for text, _ in lines])
        self.stdout.write(
            self.style.SUCCESS(f"Wrote a {len(split)}-way split to {outfile}.")
        )


def _table(
    split: dict[str, dict[str, int]],
    shares: dict[str, int],
    items: dict[str, int],
) -> list[tuple[str, bool]]:
    """Render the split as (line, is_heading) pairs.

    Headings are flagged rather than styled here so the same lines can go to a
    terminal with colour or to a file without escape codes in it.
    """
    total = sum(items.values())
    drawn = sum(shares.values())
    uneven = len(set(shares.values())) > 1
    width = max((len(f"{value:,}") for value in items.values()), default=0)
    lines = [
        (
            f"{total:,} XP across {len(items)} items"
            + f" -> {drawn} shares of about {total / drawn:,.0f} XP each",
            False,
        )
    ]
    for name, share in split.items():
        subtotal = sum(share.values())
        fair = total * Fraction(shares[name], drawn)
        count = shares[name]
        note = f" ({count} share{'' if count == 1 else 's'})" if uneven else ""
        lines.append(("", False))
        lines.append(
            (
                f"{name}{note}: {subtotal:,} XP"
                + f"  ({float(subtotal - fair):+,.0f} vs fair)",
                True,
            )
        )
        lines += [
            (f"  {value:>{width},}  {item}", False) for item, value in share.items()
        ]
        if not share:
            lines.append(("  (nothing)", False))
    lines.append(("", False))
    # With uneven shares only XP *per share* is comparable across recipients.
    per_share = [
        Fraction(sum(split[name].values()), count) for name, count in shares.items()
    ]
    gap = float(max(per_share) - min(per_share))
    suffix = " per share" if uneven else ""
    lines.append((f"Spread between richest and poorest: {gap:,.0f} XP{suffix}", False))
    return lines


def _save(outfile: Path, source: Path, lines: list[str]) -> None:
    """Write the rendered split out, refusing to clobber the hoard file itself."""
    if outfile.resolve() == source.resolve():
        raise CommandError(f"--outfile {outfile} is the hoard file; pick another path.")
    try:
        outfile.write_text("\n".join(lines) + "\n")
    except OSError as exc:
        raise CommandError(f"could not write {outfile}: {exc}") from exc


def _as_payload(
    split: dict[str, dict[str, int]], shares: dict[str, int]
) -> list[dict[str, object]]:
    return [
        {
            "share": name,
            "shares_drawn": shares[name],
            "xp": sum(items.values()),
            "items": items,
        }
        for name, items in split.items()
    ]


def _recipients(raw: str | None, shares: int | None) -> dict[str, int]:
    """Build the recipient -> shares-drawn mapping from --names and/or --shares."""
    if not raw:
        if shares is None:
            raise CommandError("give --shares, or --names to divide among.")
        if shares < 1:
            raise CommandError("--shares must be at least 1.")
        return {f"Share {i + 1}": 1 for i in range(shares)}
    drawn: dict[str, Fraction] = {}
    for entry in raw.split(","):
        name, sep, count = entry.strip().rpartition(":")
        if not sep:
            name, count = count, "1"
        name, count = name.strip(), count.strip()
        if not name:
            raise CommandError(f"--names has an empty entry: {entry!r}.")
        if name in drawn:
            raise CommandError(f"--names lists {name!r} twice.")
        drawn[name] = _as_share_count(name, count)
    if shares is not None and shares != len(drawn):
        raise CommandError(f"--shares is {shares} but {len(drawn)} names were given.")
    return _whole_shares(drawn)


def _as_share_count(name: str, count: str) -> Fraction:
    """Read one recipient's share count, which may be '2', '0.5' or '1/2'."""
    try:
        share = Fraction(count)
    except (ValueError, ZeroDivisionError):
        raise CommandError(
            f"--names gives {name!r} an unreadable share {count!r}."
        ) from None
    if share <= 0:
        raise CommandError(f"--names gives {name!r} a share of {count!r}.")
    return share


def _whole_shares(drawn: dict[str, Fraction]) -> dict[str, int]:
    """Rescale fractional shares to the smallest whole numbers in that ratio.

    Half shares are only ever compared against each other, so 1 and 1/2 mean
    the same division as 2 and 1 — and the core splitter wants integers.
    """
    scale = lcm(*(share.denominator for share in drawn.values()))
    counts = {name: int(share * scale) for name, share in drawn.items()}
    return {name: count // gcd(*counts.values()) for name, count in counts.items()}


def _load_hoard(path: Path) -> dict[str, int]:
    """Read a hoard file in whichever of the three supported formats it is in."""
    try:
        text = path.read_text()
    except OSError as exc:
        raise CommandError(f"could not read {path}: {exc}") from exc
    if not text.strip():
        raise CommandError(f"{path} is empty.")
    for parse in (json.loads, ast.literal_eval):
        try:
            data = parse(text)
        except (ValueError, SyntaxError):
            continue
        return _as_hoard(data, path)
    return _parse_lines(text, path)


def _as_hoard(data: object, path: Path) -> dict[str, int]:
    """Validate a parsed JSON/literal payload as a name -> XP mapping."""
    if not isinstance(data, dict):
        raise CommandError(f"{path} holds a {type(data).__name__}, not a dict.")
    hoard: dict[str, int] = {}
    for name, value in data.items():
        if not isinstance(name, str):
            raise CommandError(f"{path}: item name {name!r} is not a string.")
        hoard[name] = _as_xp(value, path, name)
    return hoard


def _parse_lines(text: str, path: Path) -> dict[str, int]:
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
            raise CommandError(f"{path} line {number}: no name before the value.")
        hoard[_unique(name, hoard)] = _as_xp(value.strip(), path, name)
    if not hoard:
        raise CommandError(f"{path} has no items in it.")
    return hoard


def _unique(name: str, hoard: dict[str, int]) -> str:
    """Number a repeated name so a hoard can hold three separate gems."""
    if name not in hoard:
        return name
    copy = 2
    while f"{name} ({copy})" in hoard:
        copy += 1
    return f"{name} ({copy})"


def _as_xp(value: object, path: Path, name: str) -> int:
    """Coerce one XP value, tolerating '4,200' and a trailing 'xp'."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise CommandError(f"{path}: {name!r} has a non-numeric value {value!r}.")
    if isinstance(value, str):
        cleaned = value.strip().lower().removesuffix("xp").strip().replace(",", "")
        try:
            value = int(cleaned)
        except ValueError:
            raise CommandError(
                f"{path}: {name!r} has a non-numeric value {value!r}."
            ) from None
    if value < 0:
        raise CommandError(f"{path}: {name!r} has a negative value {value!r}.")
    return value
