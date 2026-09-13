"""Tests for the trade table: price rounding, workbook parsing, and the importer (#9)."""

from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from openpyxl import Workbook

from characters.models import Market, Price, PriceList, TradeGood, Vendor
from characters.trade import (
    TradeTableError,
    import_trade_table,
    listed_price,
    parse_trade_table,
    purchase_cost,
)
from characters.units import D, u

BUDAPEST = (
    Path(__file__).resolve().parents[1] / "spreadsheets" / "price-table-budapest.xlsx"
)

HEADINGS = ("vendor", "item", "description", "price", "coin", "weight", "unit")


def write_table(path: Path, blocks: dict[str, list[tuple]], titles=None) -> Path:
    """Write a workbook in the sheet's layout: column A blank, the sort key in
    column B, three header rows per vendor, then that vendor's rows."""
    titles = titles or {}
    book = Workbook()
    sheet = book.active
    for vendor, rows in blocks.items():
        sheet.append((None, f"{vendor}-aaa"))
        sheet.append((None, f"{vendor}-aab", None, titles.get(vendor)))
        sheet.append((None, f"{vendor}-aac") + HEADINGS)
        for row in rows:
            sheet.append((None, f"{vendor}-{row[1]}") + tuple(row))
    book.save(path)
    return path


LIMESTONE = (
    "mason",
    "cut limestone block",
    "pale and matte",
    20.613,
    "s.p.",
    163,
    "lb.",
)
CALFSKIN_PIECE = ("tanner", "calfskin", None, 7.323, "s.p.", 5.0138, "oz.")
CALFSKIN_HIDE = ("tanner", "calfskin", None, 4.941, "g.p.", 6, "lb.")
WAGE = ("mason", "journeyfolk", "daily wage", 12.54, "s.p.", None, None)


class RoundingTests(SimpleTestCase):
    def test_listed_price_is_the_nearest_quarter_coin(self):
        self.assertEqual(listed_price(D("20.613")), D("20.5"))
        self.assertEqual(listed_price(D("12.226")), D("12.25"))
        self.assertEqual(listed_price(D("4.4167")), D("4.5"))
        self.assertEqual(listed_price(D("0.235")), D("0.25"))
        self.assertEqual(listed_price(D("7")), D("7"))

    def test_listed_price_ties_round_up(self):
        self.assertEqual(listed_price(D("0.125")), D("0.25"))

    def test_one_unit_rounds_the_fraction_up(self):
        self.assertEqual(purchase_cost(D("20.613")), D(21))

    def test_quarters_collapse_across_units(self):
        """Two at 20 2/4 s.p. are 41 s.p. exactly; three leave a half to round up."""
        self.assertEqual(purchase_cost(D("20.613"), 2), D(41))
        self.assertEqual(purchase_cost(D("20.613"), 3), D(62))

    def test_whole_prices_are_charged_as_written(self):
        self.assertEqual(purchase_cost(D("7.1"), 4), D(28))

    def test_large_prices_keep_every_digit(self):
        """A galleon is 15,497 g.p.; nothing may clip that to 1.550E+4."""
        self.assertEqual(purchase_cost(D("15497.881")), D(15498))
        self.assertEqual(purchase_cost(D("15497.881"), 10), D(154980))


class ParseTests(SimpleTestCase):
    def test_reads_rows_and_vendor_titles(self):
        path = write_table(
            Path(self.tmp) / "t.xlsx",
            {"mason": [LIMESTONE, WAGE]},
            titles={"mason": "Mason"},
        )
        table = parse_trade_table(path)
        self.assertEqual(table.vendors, {"mason": "Mason"})
        self.assertEqual(table.problems, [])
        self.assertEqual(
            [r.item for r in table.rows], ["cut limestone block", "journeyfolk"]
        )
        block = table.rows[0]
        self.assertEqual(block.row, 4)
        self.assertEqual(block.description, "pale and matte")
        self.assertEqual(block.price, D("20.613"))
        self.assertEqual(block.coin, "sp")
        self.assertEqual(block.weight, D(163) * u.lb)
        self.assertIsNone(table.rows[1].weight)

    def test_vendor_names_are_lowercased(self):
        """The sheet has one block headed "Furrier" beside "furrier"."""
        path = write_table(
            Path(self.tmp) / "t.xlsx",
            {"Furrier": [("Furrier", "wrap", None, 1.0, "g.p.", 1, "lb.")]},
        )
        self.assertEqual(parse_trade_table(path).rows[0].vendor, "furrier")

    def test_weight_units_are_normalised(self):
        rows = [
            ("shipbuilder", "cog", None, 4912.6, "g.p.", 43.254, "tons"),
            ("shipbuilder", "dray", None, 193.7, "g.p.", 1.167, "ton"),
            ("shipbuilder", "sapphire", None, 860.3, "g.p.", 0.843, "dwt."),
            ("shipbuilder", "castanets", None, 5.0, "s.p.", 1, "composite"),
        ]
        table = parse_trade_table(
            write_table(Path(self.tmp) / "t.xlsx", {"shipbuilder": rows})
        )
        weights = [r.weight for r in table.rows]
        self.assertEqual(weights[0], D("43.254") * u.ton)
        self.assertEqual(weights[1], D("1.167") * u.ton)
        self.assertEqual(weights[2], D("0.843") * u.dwt)
        self.assertIsNone(weights[3])
        self.assertEqual(table.problems, [])

    def test_unreadable_cells_are_reported_and_skipped(self):
        rows = [
            ("church", "holy water", "4 fl. oz. vial", "#REF!", "#REF!", 10.675, "lb."),
            ("church", "candle", None, 1.0, "florins", 1, "lb."),
            ("church", "bell", None, 50.0, "g.p.", 200, "stone"),
            LIMESTONE,
        ]
        table = parse_trade_table(
            write_table(Path(self.tmp) / "t.xlsx", {"church": rows})
        )
        self.assertEqual([r.item for r in table.rows], ["bell", "cut limestone block"])
        self.assertIsNone(table.rows[0].weight)
        self.assertEqual(len(table.problems), 3)
        self.assertIn("row 4 (church: holy water): price is '#REF!'", table.problems[0])
        self.assertIn("unknown coin 'florins'", table.problems[1])
        self.assertIn("unknown weight unit 'stone'", table.problems[2])

    def test_goods_differing_only_in_weight_are_distinct(self):
        table = parse_trade_table(
            write_table(
                Path(self.tmp) / "t.xlsx", {"tanner": [CALFSKIN_PIECE, CALFSKIN_HIDE]}
            )
        )
        self.assertEqual(len(table.rows), 2)
        self.assertNotEqual(table.rows[0].key, table.rows[1].key)

    def test_exact_repeats_are_folded(self):
        table = parse_trade_table(
            write_table(Path(self.tmp) / "t.xlsx", {"mason": [LIMESTONE, LIMESTONE]})
        )
        self.assertEqual(len(table.rows), 1)
        self.assertEqual(table.collapsed, 1)
        self.assertEqual(table.problems, [])

    def test_repeat_at_another_price_keeps_the_first_and_reports(self):
        dearer = LIMESTONE[:3] + (25.0,) + LIMESTONE[4:]
        table = parse_trade_table(
            write_table(Path(self.tmp) / "t.xlsx", {"mason": [LIMESTONE, dearer]})
        )
        self.assertEqual(len(table.rows), 1)
        self.assertEqual(table.rows[0].price, D("20.613"))
        self.assertEqual(
            table.problems,
            [
                "row 5 (mason: cut limestone block) repeats row 4 at a different price; kept the earlier row"
            ],
        )

    def test_not_a_workbook(self):
        path = Path(self.tmp) / "t.xlsx"
        path.write_text("nope")
        with self.assertRaises(TradeTableError):
            parse_trade_table(path)

    def setUp(self):
        import tempfile

        self._dir = tempfile.TemporaryDirectory()
        self.tmp = self._dir.name
        self.addCleanup(self._dir.cleanup)


class BudapestWorkbookTests(SimpleTestCase):
    """The checked-in Budapest table parses cleanly."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.table = parse_trade_table(BUDAPEST)

    def test_every_row_is_read(self):
        """1626 priced rows: 10 exact repeats fold into an earlier row, and the
        music tutor is listed twice at different rates with nothing else to
        tell the two apart, which is reported and the first kept."""
        self.assertEqual(len(self.table.rows), 1615)
        self.assertEqual(self.table.collapsed, 10)
        self.assertEqual(
            self.table.problems,
            [
                "row 371 (college: tutor of music) repeats row 370 at a different price; kept the earlier row"
            ],
        )

    def test_vendors(self):
        self.assertEqual(len({r.vendor for r in self.table.rows}), 83)
        self.assertEqual(self.table.vendors["abattoir"], "Abbatoir")

    def test_a_known_row(self):
        block = next(r for r in self.table.rows if r.item == "cut limestone block")
        self.assertEqual(block.vendor, "mason")
        self.assertEqual(listed_price(block.price), D("20.5"))
        self.assertEqual(block.weight, D(163) * u.lb)


class ImportTests(TestCase):
    def setUp(self):
        import tempfile

        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)
        self.path = write_table(
            self.tmp / "budapest.xlsx",
            {"mason": [LIMESTONE, WAGE], "tanner": [CALFSKIN_PIECE, CALFSKIN_HIDE]},
            titles={"mason": "Mason"},
        )

    def test_records_a_price_list(self):
        report = import_trade_table(self.path, "Budapest")
        market = Market.objects.get(name="Budapest")
        self.assertEqual(report.price_list.market, market)
        self.assertEqual(report.price_list.source, "budapest.xlsx")
        self.assertEqual(report.goods_created, 4)
        self.assertEqual(report.prices, 4)
        self.assertEqual(report.missing, 0)
        self.assertEqual(Vendor.objects.get(name="mason").title, "Mason")
        self.assertEqual(Vendor.objects.get(name="tanner").title, "")
        good = TradeGood.objects.get(name="cut limestone block")
        self.assertEqual(good.weight, D(163) * u.lb)
        price = good.current_price(market)
        self.assertEqual(price.amount, D("20.613"))
        self.assertEqual(price.coin, "sp")

    def test_price_arithmetic_is_in_the_listed_coin(self):
        import_trade_table(self.path, "Budapest")
        price = TradeGood.objects.get(name="cut limestone block").prices.get()
        self.assertEqual(price.listed, D("20.5") * u.sp)
        self.assertEqual(price.cost(), D(21) * u.sp)
        self.assertEqual(price.cost(3), D(62) * u.sp)
        self.assertEqual(price.cost(3).to(u.cp), D(744) * u.cp)

    def test_reimport_adds_a_list_and_reuses_the_goods(self):
        import_trade_table(self.path, "Budapest")
        dearer = LIMESTONE[:3] + (30.0,) + LIMESTONE[4:]
        newer = write_table(self.tmp / "newer.xlsx", {"mason": [dearer, WAGE]})
        report = import_trade_table(newer, "Budapest")
        self.assertEqual(report.goods_created, 0)
        self.assertEqual(report.missing, 2)
        self.assertEqual(TradeGood.objects.count(), 4)
        market = Market.objects.get(name="Budapest")
        self.assertEqual(PriceList.objects.filter(market=market).count(), 2)
        self.assertEqual(market.latest_price_list(), report.price_list)
        good = TradeGood.objects.get(name="cut limestone block")
        self.assertEqual(good.current_price(market).amount, D("30"))
        self.assertEqual(good.prices.count(), 2)
        hide = TradeGood.objects.get(name="calfskin", weight=D(6) * u.lb)
        self.assertIsNone(hide.current_price(market))

    def test_another_market_shares_the_goods(self):
        import_trade_table(self.path, "Budapest")
        report = import_trade_table(self.path, "Miskolc")
        self.assertEqual(report.goods_created, 0)
        self.assertEqual(Market.objects.count(), 2)
        self.assertEqual(Price.objects.count(), 8)

    def test_an_empty_table_is_refused(self):
        empty = write_table(self.tmp / "empty.xlsx", {"mason": []})
        with self.assertRaises(TradeTableError):
            import_trade_table(empty, "Budapest")
        self.assertEqual(Market.objects.count(), 0)

    def test_the_real_workbook_imports_and_reimports_without_new_goods(self):
        first = import_trade_table(BUDAPEST, "Budapest")
        self.assertEqual(first.prices, 1615)
        self.assertEqual(first.goods_created, 1615)
        again = import_trade_table(BUDAPEST, "Budapest")
        self.assertEqual(again.goods_created, 0)
        self.assertEqual(again.missing, 0)
        self.assertEqual(TradeGood.objects.count(), 1615)


class CommandTests(TestCase):
    def setUp(self):
        import tempfile

        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def run_command(self, *args) -> str:
        out = StringIO()
        call_command("import_trade_table", *args, stdout=out)
        return out.getvalue()

    def test_reports_what_it_did(self):
        bad = ("church", "holy water", None, "#REF!", "#REF!", 10.675, "lb.")
        path = write_table(
            self.tmp / "t.xlsx", {"mason": [LIMESTONE, LIMESTONE], "church": [bad]}
        )
        output = self.run_command(str(path), "--market", "Budapest")
        self.assertIn("Budapest: recorded 1 prices from t.xlsx (1 new goods)", output)
        self.assertIn("1 repeated rows folded", output)
        self.assertIn("! row 9 (church: holy water): price is '#REF!'", output)
        self.assertEqual(Price.objects.count(), 1)

    def test_missing_file(self):
        with self.assertRaises(CommandError):
            self.run_command(str(self.tmp / "none.xlsx"), "--market", "Budapest")

    def test_market_is_required(self):
        path = write_table(self.tmp / "t.xlsx", {"mason": [LIMESTONE]})
        with self.assertRaises(CommandError):
            self.run_command(str(path))
