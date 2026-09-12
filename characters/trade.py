"""The trade table: Alexis's per-town price spreadsheets (#9).

A workbook holds one sheet. Column B is a sort key of the form
``vendor-item``; columns C to I are vendor, item, description, price, coin,
weight and weight unit. Each vendor's block opens with three header rows
keyed ``<vendor>-aaa`` (blank), ``-aab`` (the vendor's display title, in
column D) and ``-aac`` (the column headings). Every town's workbook has the
same layout and, give or take an item, the same goods at different prices.

A price cell holds a long float (12.226270177996476), but the sheet formats
it as whole coins plus quarters, and that listed figure is what the rules
charge (see ``listed_price`` and ``purchase_cost``). The raw value is what
gets stored, so the rounding can change without a re-import.

``parse_trade_table`` reads a workbook into plain rows and never touches the
database; ``import_trade_table`` records those rows as a dated price list for
one market.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path

from django.db import transaction
from openpyxl import load_workbook

from .models import Market, Price, PriceList, TradeGood, Vendor
from .units import D, Quantity, u

# The sheet's coin abbreviations -> the unit names in units.txt.
COINS = {"g.p.": "gp", "s.p.": "sp", "c.p.": "cp"}
# The sheet's weight units -> pint unit names. "composite" (a set of parts
# weighed separately) and a blank unit mean the row carries no weight.
WEIGHT_UNITS = {"lb.": "lb", "oz.": "oz", "ton": "ton", "tons": "ton", "dwt.": "dwt"}
UNWEIGHED = {None, "", "composite"}
HEADER_KEY_RE = re.compile(r"-aa([abc])$")
QUARTER = Decimal("0.25")


class TradeTableError(Exception):
    """A workbook that cannot be read as a trade table."""


def listed_price(raw: Decimal) -> Decimal:
    """The price as the table shows it: rounded to the nearest quarter coin.

    Every price cell is formatted as whole coins plus quarters (Excel's
    ``# ?/4``), so a raw 20.613 s.p. is listed as 20 2/4 s.p.
    """
    quarters = (Decimal(raw) / QUARTER).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return quarters * QUARTER


def purchase_cost(raw: Decimal, quantity: int = 1) -> Decimal:
    """Whole coins charged for `quantity` units at a listed price.

    Quarters collapse across units and any remainder rounds up against the
    buyer: at 20 2/4 s.p. one costs 21, two cost 41, and three cost 62.
    """
    total = listed_price(raw) * quantity
    return total.to_integral_value(rounding=ROUND_CEILING)


@dataclass
class TradeRow:
    """One priced good as read from the sheet."""

    row: int
    vendor: str
    item: str
    description: str
    price: Decimal
    coin: str
    weight: Quantity | None

    @property
    def key(self) -> tuple[str, str, str, str]:
        """What identifies a good across imports.

        (vendor, item) alone repeats: two sizes of window frame differ only in
        description, and a calfskin by the piece and as a whole hide differ
        only in weight. Must match TradeGood.key.
        """
        return (
            self.vendor,
            self.item,
            self.description,
            "" if self.weight is None else str(self.weight),
        )


@dataclass
class ParsedTable:
    """The rows of one workbook, with everything that could not be read."""

    vendors: dict[str, str] = field(default_factory=dict)
    rows: list[TradeRow] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    # Rows repeating an earlier row exactly, folded into it.
    collapsed: int = 0


def parse_trade_table(path: Path) -> ParsedTable:
    """Read a trade table workbook into rows, reporting rather than raising on bad cells.

    Exact repeats of a row are folded into the first; a repeat that differs
    only in price is reported and the first kept.
    """
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise TradeTableError(f"cannot open {path}: {exc}") from exc
    sheet = workbook.worksheets[0]
    table = ParsedTable()
    seen: dict[tuple[str, str, str], TradeRow] = {}
    for number, cells in enumerate(sheet.iter_rows(values_only=True), 1):
        cells = tuple(cells) + (None,) * max(0, 9 - len(cells))
        key = cells[1]
        if key is None:
            continue
        header = HEADER_KEY_RE.search(str(key))
        if header:
            if header.group(1) == "b":
                vendor = str(key)[: header.start()].strip().lower()
                table.vendors[vendor] = str(cells[3] or "").strip()
            continue
        row = _parse_row(number, cells, table.problems)
        if row is None:
            continue
        earlier = seen.get(row.key)
        if earlier is None:
            seen[row.key] = row
            table.rows.append(row)
        elif (earlier.price, earlier.coin) == (row.price, row.coin):
            table.collapsed += 1
        else:
            table.problems.append(
                f"row {number} ({row.vendor}: {row.item}) repeats row {earlier.row}"
                + " at a different price; kept the earlier row"
            )
    return table


def _parse_row(number: int, cells: tuple, problems: list[str]) -> TradeRow | None:
    """One data row, or None (with the reason appended to `problems`)."""
    vendor, item, description, price, coin, weight, unit = cells[2:9]
    vendor = str(vendor or "").strip().lower()
    item = str(item or "").strip()
    if not vendor or not item:
        problems.append(f"row {number}: no vendor or item; skipped")
        return None
    label = f"row {number} ({vendor}: {item})"
    if not _is_number(price):
        problems.append(f"{label}: price is {price!r}, not a number; skipped")
        return None
    coin_code = COINS.get(str(coin).strip())
    if coin_code is None:
        problems.append(f"{label}: unknown coin {coin!r}; skipped")
        return None
    return TradeRow(
        row=number,
        vendor=vendor,
        item=item,
        description=str(description or "").strip(),
        price=D(str(price)),
        coin=coin_code,
        weight=_weight(label, weight, unit, problems),
    )


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _weight(label: str, weight, unit, problems: list[str]) -> Quantity | None:
    """The row's weight as a Quantity, or None when it has none.

    A weight with no unit, or a unit the table does not use, is reported and
    dropped rather than guessed at.
    """
    unit = None if unit is None else str(unit).strip()
    if unit in UNWEIGHED or weight is None:
        return None
    if not _is_number(weight):
        problems.append(f"{label}: weight is {weight!r}, not a number; dropped")
        return None
    unit_name = WEIGHT_UNITS.get(unit)
    if unit_name is None:
        problems.append(f"{label}: unknown weight unit {unit!r}; weight dropped")
        return None
    return D(str(weight)) * getattr(u, unit_name)


@dataclass
class ImportReport:
    """What one import did."""

    price_list: PriceList
    goods_created: int
    prices: int
    # Goods priced in the market's previous list but absent from this one.
    missing: int
    collapsed: int
    problems: list[str]


def import_trade_table(
    path: Path, market_name: str, *, source: str | None = None
) -> ImportReport:
    """Record a workbook as a new, dated price list for `market_name`.

    Vendors and goods are shared across imports and markets, matched by
    TradeRow.key; each import adds a PriceList and one Price per row.
    Earlier lists are kept.
    """
    table = parse_trade_table(path)
    if not table.rows:
        raise TradeTableError(f"no price rows found in {path}")
    with transaction.atomic():
        market, _ = Market.objects.get_or_create(name=market_name)
        previous = market.price_lists.first()
        vendors = _vendors(table)
        goods = {good.key: good for good in TradeGood.objects.select_related("vendor")}
        created = 0
        for row in table.rows:
            if row.key not in goods:
                goods[row.key] = TradeGood.objects.create(
                    vendor=vendors[row.vendor],
                    name=row.item,
                    description=row.description,
                    weight=row.weight,
                )
                created += 1
        price_list = PriceList.objects.create(
            market=market, source=source or Path(path).name
        )
        prices = Price.objects.bulk_create(
            Price(
                price_list=price_list,
                good=goods[row.key],
                amount=row.price,
                coin=row.coin,
            )
            for row in table.rows
        )
        priced = {goods[row.key].pk for row in table.rows}
        missing = 0
        if previous is not None:
            missing = previous.prices.exclude(good_id__in=priced).count()
    return ImportReport(
        price_list=price_list,
        goods_created=created,
        prices=len(prices),
        missing=missing,
        collapsed=table.collapsed,
        problems=table.problems,
    )


def _vendors(table: ParsedTable) -> dict[str, Vendor]:
    """The Vendor row for every vendor in the table, titles refreshed from it."""
    vendors = {}
    for name in sorted({row.vendor for row in table.rows}):
        vendor, _ = Vendor.objects.get_or_create(name=name)
        title = table.vendors.get(name, "")
        if title and vendor.title != title:
            vendor.title = title
            vendor.save(update_fields=["title"])
        vendors[name] = vendor
    return vendors
