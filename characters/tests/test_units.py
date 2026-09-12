"""Tests for the unit registry module: Decimal precision and display shortening."""

import decimal

from django.test import SimpleTestCase

from characters.units import D, display_magnitude, u


class DecimalContextTests(SimpleTestCase):
    def test_arithmetic_keeps_full_precision(self):
        """The module must not clip the thread's decimal context.

        It once set a global precision of 4 significant digits, which turned
        12,345 + 1 into 1.235E+4 anywhere in the app that added Decimals.
        """
        self.assertEqual(D(12345) + D(1), D(12346))
        self.assertEqual(decimal.getcontext().prec, decimal.DefaultContext.prec)

    def test_quantity_arithmetic_keeps_full_precision(self):
        total = D(12345) * u.lb + D(1) * u.lb
        self.assertEqual(total.magnitude, D(12346))


class DisplayMagnitudeTests(SimpleTestCase):
    def test_short_values_are_unchanged(self):
        self.assertEqual(display_magnitude(D("12.5")), "12.5")
        self.assertEqual(display_magnitude(D("0.1875")), "0.1875")
        self.assertEqual(display_magnitude(D(7)), "7")

    def test_long_fractions_round_to_four_significant_digits(self):
        self.assertEqual(display_magnitude(D("2.256215714285714")), "2.256")
        self.assertEqual(display_magnitude(D("0.04624457142857142")), "0.04624")

    def test_integer_digits_are_never_dropped(self):
        self.assertEqual(display_magnitude(D("12345.678")), "12346")
        self.assertEqual(display_magnitude(D("800000")), "800000")
        self.assertEqual(display_magnitude(D("1234.56")), "1235")

    def test_trailing_zeros_are_trimmed(self):
        self.assertEqual(display_magnitude(D("4.500")), "4.5")
        self.assertEqual(display_magnitude(D("4.000")), "4")

    def test_never_uses_exponent_notation(self):
        self.assertEqual(display_magnitude(D("1E+2")), "100")
        self.assertEqual(display_magnitude(D("1.5E+4")), "15000")

    def test_digits_argument(self):
        self.assertEqual(display_magnitude(D("2.256215"), digits=2), "2.3")
