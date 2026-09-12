"""Pint unit registry setup for D&D units."""

from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import TypeAlias

import pint


D = Decimal

u = pint.UnitRegistry(system="US", non_int_type=Decimal)
u.load_definitions(str(Path(__file__).parent / "units.txt"))
pint.set_application_registry(u)

Quantity: TypeAlias = u.Quantity

# The global decimal context is left at its default (28 digits). It used to be
# set to 4 significant digits here so that displayed weights stayed short, but
# that clipped every intermediate result app-wide: any total over 9,999 came
# out as, say, 1.235E+4, and the setting is thread-local, so it only ever held
# in the thread that imported this module. Shortening is a display concern and
# lives in display_magnitude below.
DISPLAY_DIGITS = 4


def display_magnitude(value: Decimal, digits: int = DISPLAY_DIGITS) -> str:
    """Format a magnitude for the page: at most `digits` significant digits.

    Integer digits are never dropped (12345.6 -> "12346", not "1.235E+4"),
    the result is never in exponent notation, and trailing zeros after the
    point are trimmed (4.500 -> "4.5"). Fractions shorter than the limit are
    shown as they are, so 0.1875 stays "0.1875".
    """
    value = Decimal(value)
    if not value.is_finite():
        return str(value)
    # adjusted() is the exponent of the leading digit: 12345 -> 4, 0.0123 -> -2.
    places = max(0, digits - (value.adjusted() + 1))
    rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    text = f"{rounded:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
