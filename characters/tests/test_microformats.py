"""Tests for the Zingor microformats (ZMF) parser."""

from django.test import SimpleTestCase

from characters.microformats import ParsedSheet, parse_sheet, render_sheet
from characters.models import Spell
from characters.units import D, u


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

    def test_unparseable_money_is_warned_not_stored(self):
        sheet = parse_sheet('<span class="zingor-gp">lots</span>')
        self.assertEqual(sheet.money, {})
        self.assertEqual(len(sheet.warnings), 1)


class ParseScalarTests(SimpleTestCase):
    def test_string_and_int_scalars_map_to_character_columns(self):
        html = list(
            [
                '<span class="zingor-name">Zoltan</span>',
                '<span class="zingor-class">fighter</span>',
                '<span class="zingor-strength">17</span>',
                '<span class="zingor-level">3</span>',
            ]
        )
        sheet = parse_sheet("".join(html))
        self.assertEqual(sheet.character.name, "Zoltan")
        self.assertEqual(sheet.character.char_class, "fighter")
        self.assertEqual(sheet.character.strength, 17)
        self.assertEqual(sheet.character.level, 3)
        self.assertEqual(sheet.warnings, [])

    def test_int_scalar_strips_thousands_separators(self):
        sheet = parse_sheet('<span class="zingor-xp">1,250</span>')
        self.assertEqual(sheet.character.xp, 1250)

    def test_weight_scalar_becomes_pounds(self):
        sheet = parse_sheet('<span class="zingor-weight">75 Lbs.</span>')
        self.assertEqual(sheet.character.weight, D(75) * u.lb)

    def test_height_scalar_becomes_inches(self):
        html = '<span class="zingor-height">5\'7"</span>'
        sheet = parse_sheet(html)
        self.assertEqual(sheet.character.height, D(67) * u.inch)

    def test_height_feet_only_defaults_inches_to_zero(self):
        sheet = parse_sheet('<span class="zingor-height">6\'</span>')
        self.assertEqual(sheet.character.height, D(72) * u.inch)

    def test_bad_int_is_warned_and_field_left_unset(self):
        sheet = parse_sheet('<span class="zingor-strength">very strong</span>')
        self.assertIsNone(sheet.character.strength)
        self.assertEqual(len(sheet.warnings), 1)
        self.assertIn("strength", sheet.warnings[0])

    def test_bad_height_is_warned(self):
        sheet = parse_sheet('<span class="zingor-height">tall</span>')
        self.assertIsNone(sheet.character.height)
        self.assertEqual(len(sheet.warnings), 1)

    def test_duplicate_scalar_warns_and_uses_first(self):
        html = list(
            [
                '<span class="zingor-strength">17</span>',
                '<span class="zingor-strength">9</span>',
            ]
        )
        sheet = parse_sheet("".join(html))
        self.assertEqual(sheet.character.strength, 17)
        self.assertEqual(len(sheet.warnings), 1)
        self.assertIn("2 elements", sheet.warnings[0])


class ParseRecordTests(SimpleTestCase):
    def test_spell_record_parsed(self):
        html = list(
            [
                '<div class="zingor-spell">',
                '<span class="zingor-spell-name">Fireball</span>',
                '<span class="zingor-spell-level">3</span>',
                '<span class="zingor-spell-memorized">X</span>',
                "</div>",
            ]
        )
        sheet = parse_sheet("".join(html))
        self.assertEqual(len(sheet.spells), 1)
        spell = sheet.spells[0]
        self.assertEqual(spell.name, "Fireball")
        self.assertEqual(spell.level, 3)
        self.assertTrue(spell.is_memorized)

    def test_optional_subfield_absent_is_fine(self):
        html = list(
            [
                '<div class="zingor-spell">',
                '<span class="zingor-spell-name">Light</span>',
                '<span class="zingor-spell-level">1</span>',
                "</div>",
            ]
        )
        sheet = parse_sheet("".join(html))
        self.assertEqual(len(sheet.spells), 1)
        self.assertEqual(sheet.spells[0].name, "Light")
        self.assertEqual(sheet.warnings, [])
        # Absent optional subfield leaves the model's own default in place.
        default = Spell._meta.get_field("is_memorized").default
        self.assertEqual(sheet.spells[0].is_memorized, default)

    def test_sage_study_record_parsed(self):
        html = list(
            [
                '<tr class="zingor-sage-study">',
                '<td class="zingor-sage-study-name">Forgery</td>',
                '<td class="zingor-sage-study-points">27</td>',
                "</tr>",
            ]
        )
        sheet = parse_sheet("".join(html))
        self.assertEqual(len(sheet.sage_studies), 1)
        self.assertEqual(sheet.sage_studies[0].study, "Forgery")
        self.assertEqual(sheet.sage_studies[0].points, 27)

    def test_missing_required_subfield_skips_record_with_warning(self):
        html = list(
            [
                '<div class="zingor-spell">',
                '<span class="zingor-spell-level">2</span>',
                "</div>",
            ]
        )
        sheet = parse_sheet("".join(html))
        self.assertEqual(sheet.spells, [])
        self.assertEqual(len(sheet.warnings), 1)
        self.assertIn("missing required", sheet.warnings[0])

    def test_uncoercible_subfield_skips_record_with_warning(self):
        html = list(
            [
                '<div class="zingor-spell">',
                '<span class="zingor-spell-name">Bad</span>',
                '<span class="zingor-spell-level">not-a-level</span>',
                "</div>",
            ]
        )
        sheet = parse_sheet("".join(html))
        self.assertEqual(sheet.spells, [])
        self.assertEqual(len(sheet.warnings), 1)
        self.assertIn("could not parse", sheet.warnings[0])


class RenderSheetTests(SimpleTestCase):
    def test_render_lists_fields_records_money_and_warnings(self):
        sheet = parse_sheet(
            "".join(
                list(
                    [
                        '<span class="zingor-name">Zoltan</span>',
                        '<span class="zingor-strength">17</span>',
                        '<span class="zingor-gp">670</span>',
                        '<div class="zingor-spell">',
                        '<span class="zingor-spell-name">Fireball</span>',
                        '<span class="zingor-spell-level">3</span>',
                        "</div>",
                        '<tr class="zingor-sage-study">',
                        '<td class="zingor-sage-study-name">Forgery</td>',
                        '<td class="zingor-sage-study-points">27</td>',
                        "</tr>",
                    ]
                )
            )
        )
        out = render_sheet(sheet)
        self.assertIn("Zoltan", out)
        self.assertIn("Fireball", out)
        self.assertIn("Forgery", out)
        self.assertIn("gp", out)
        self.assertIn("=== Spells (1) ===", out)
        self.assertIn("=== Sage studies (1) ===", out)

    def test_render_empty_sheet_shows_none_placeholders(self):
        out = render_sheet(ParsedSheet(character=parse_sheet("").character))
        self.assertIn("(none)", out)
        self.assertIn("=== Warnings (0) ===", out)
