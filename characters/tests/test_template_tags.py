"""Tests for the character_tags template filters."""

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from characters.models import Profile
from characters.templatetags.character_tags import (
    ceildiv,
    display_name,
    floordiv,
    format_duration,
    format_modifier,
    format_pct,
)


class FormatModifierTests(SimpleTestCase):
    def test_none_is_em_dash(self):
        self.assertEqual(format_modifier(None), "—")

    def test_positive_gets_plus_sign(self):
        self.assertEqual(format_modifier(3), "+3")

    def test_zero_is_signed_plus(self):
        self.assertEqual(format_modifier(0), "+0")

    def test_negative_keeps_minus(self):
        self.assertEqual(format_modifier(-2), "-2")


class FormatPctTests(SimpleTestCase):
    def test_none_is_em_dash(self):
        self.assertEqual(format_pct(None), "—")

    def test_value_gets_percent_sign(self):
        self.assertEqual(format_pct(85), "85%")


class FloorDivTests(SimpleTestCase):
    def test_floor_division(self):
        self.assertEqual(floordiv(7, 4), 1)
        self.assertEqual(floordiv(8, 4), 2)

    def test_bad_input_returns_none(self):
        self.assertIsNone(floordiv("x", 4))
        self.assertIsNone(floordiv(5, 0))


class CeilDivTests(SimpleTestCase):
    def test_ceiling_division(self):
        self.assertEqual(ceildiv(5, 4), 2)
        self.assertEqual(ceildiv(8, 4), 2)

    def test_bad_input_returns_none(self):
        self.assertIsNone(ceildiv(None, 4))
        self.assertIsNone(ceildiv(5, 0))


class FormatDurationTests(SimpleTestCase):
    def test_minutes_only(self):
        self.assertEqual(format_duration(45), "45 min")

    def test_whole_hours_omit_minutes(self):
        self.assertEqual(format_duration(60), "1 hr")

    def test_hours_and_minutes(self):
        self.assertEqual(format_duration(90), "1 hr 30 min")

    def test_zero_shows_minutes(self):
        self.assertEqual(format_duration(0), "0 min")

    def test_bad_input_returns_none(self):
        self.assertIsNone(format_duration("soon"))


class DisplayNameFilterTests(TestCase):
    def test_falls_back_to_username_without_profile(self):
        user = User.objects.create_user(username="noprofile", password="x")
        self.assertEqual(display_name(user), "noprofile")

    def test_uses_display_name_when_set(self):
        user = User.objects.create_user(username="withname", password="x")
        Profile.objects.create(user=user, display_name="Maxwell of Zingor")
        self.assertEqual(display_name(user), "Maxwell of Zingor")

    def test_blank_display_name_falls_back_to_username(self):
        user = User.objects.create_user(username="blank", password="x")
        Profile.objects.create(user=user, display_name="")
        self.assertEqual(display_name(user), "blank")
