"""Tests for the Zingor microformats (ZMF) parser."""

from pathlib import Path

from django.test import SimpleTestCase

from characters.microformats import parse_sheet

LEXENT_HTML = (Path(__file__).parent / "data" / "lexent.html").read_text()


class ParseLexentFixtureTests(SimpleTestCase):
    """The parser drops height/weight/id but keeps level (see issue #65)."""

    def setUp(self):
        self.sheet = parse_sheet(LEXENT_HTML)

    def test_level_is_still_parsed(self):
        self.assertEqual(self.sheet.character.level, 5)

    def test_height_and_weight_are_not_parsed(self):
        self.assertIsNone(self.sheet.character.height)
        self.assertIsNone(self.sheet.character.weight)

    def test_character_id_is_not_parsed(self):
        """A parsed sheet never carries a pk from the wiki's zingor-character-id."""
        self.assertIsNone(self.sheet.character.pk)

    def test_scalar_fields_are_parsed(self):
        self.assertEqual(self.sheet.character.name, "Lexent Povarov")
        self.assertEqual(self.sheet.character.xp, 13414)
        self.assertEqual(self.sheet.character.strength, 14)
        self.assertEqual(self.sheet.character.current_hp, 12)

    def test_sage_studies_are_parsed(self):
        self.assertEqual(len(self.sheet.sage_studies), 5)

    def test_spells_lacking_a_level_are_skipped_with_warnings(self):
        """Lexent's page carries no zingor-spell-level, so each spell (level is
        a required subfield) is skipped rather than invented."""
        self.assertEqual(len(self.sheet.spells), 0)
        self.assertTrue(any("spell" in w and "level" in w for w in self.sheet.warnings))


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
