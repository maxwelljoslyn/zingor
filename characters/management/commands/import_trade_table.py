"""Import one town's trade table workbook as a new price list.

``uv run python manage.py import_trade_table characters/spreadsheets/price-table-budapest.xlsx --market Budapest``

Every run adds a dated price list for the market and keeps the earlier ones.
Goods are matched to those already known by vendor, item and description, so
re-importing prices the same goods again rather than duplicating them. Cells
that cannot be read are reported and skipped, never guessed at.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from characters.trade import TradeTableError, import_trade_table


class Command(BaseCommand):
    help = "Record a trade table workbook as a new price list for a market."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("workbook", type=Path, help="The .xlsx trade table.")
        parser.add_argument(
            "--market",
            required=True,
            help="The town the prices are for, e.g. Budapest. Created if new.",
        )

    def handle(self, *args, **options) -> None:
        workbook: Path = options["workbook"]
        if not workbook.is_file():
            raise CommandError(f"{workbook} is not a file.")
        try:
            report = import_trade_table(workbook, options["market"])
        except TradeTableError as exc:
            raise CommandError(str(exc)) from exc
        price_list = report.price_list
        self.stdout.write(
            self.style.SUCCESS(
                f"{price_list.market.name}: recorded {report.prices} prices"
                + f" from {price_list.source} ({report.goods_created} new goods)"
            )
        )
        if report.collapsed:
            self.stdout.write(
                f"  {report.collapsed} repeated rows folded into their first"
            )
        if report.missing:
            self.stdout.write(
                f"  {report.missing} goods in the previous list are absent from this one"
            )
        for problem in report.problems:
            self.stdout.write(f"  ! {problem}")
