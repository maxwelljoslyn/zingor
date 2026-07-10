"""Tests for the Zingor microformats (ZMF) parser."""

from django.test import SimpleTestCase

from characters.microformats import parse_sheet


class ParseMoneyTests(SimpleTestCase):
    def test_money_is_parsed_into_sheet_money(self):
        """Coins land on sheet.money, not on the (now money-less) Character."""
        html = (
            '<div><span class="zingor-name">Zoltan</span>'
            + '<span class="zingor-gp">670</span>'
            + '<span class="zingor-sp">224</span>'
            + '<span class="zingor-cp">227</span></div>'
        )
        sheet = parse_sheet(html)
        self.assertEqual(sheet.character.name, "Zoltan")
        self.assertEqual(sheet.money, {"gp": 670, "sp": 224, "cp": 227})
        self.assertEqual(sheet.warnings, [])

    def test_absent_money_leaves_sheet_money_empty(self):
        sheet = parse_sheet('<span class="zingor-name">Zoltan</span>')
        self.assertEqual(sheet.money, {})
