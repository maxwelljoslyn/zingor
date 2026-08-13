"""Split a hoard into near-equal XP shares from the command line.

``uv run python manage.py split_treasure hoard.txt --shares 4``

The input file may be JSON, a Python dict literal, or the loosest form — one
``name: value`` per line::

    # cavern of the frog king
    gem of true seeing: 4,200
    platinum crown 3100
    healing potion: 400 xp

Repeated names are numbered rather than collapsed, so listing "gem" three
times gives you three gems: "gem (1 of 3)", "gem (2 of 3)", "gem (3 of 3)".

Recipients who draw uneven shares are written ``name:shares``::

    --names 'Alix,Bront:2,Cwen:1/2'

Pass ``-o/--outfile`` to save the split instead of printing it.
"""

from __future__ import annotations

import json
from fractions import Fraction
from math import gcd, lcm
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from characters.hoard import HoardError, parse_hoard
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
    """Read a hoard file, reporting anything unreadable in it against its path."""
    try:
        text = path.read_text()
    except OSError as exc:
        raise CommandError(f"could not read {path}: {exc}") from exc
    try:
        return parse_hoard(text)
    except HoardError as exc:
        raise CommandError(f"{path}: {exc}") from exc
