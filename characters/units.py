"""Pint unit registry setup for D&D units."""

from decimal import Decimal, getcontext
from pathlib import Path
from typing import TypeAlias

import pint

getcontext().prec = 4

D = Decimal

u = pint.UnitRegistry(system="US", non_int_type=Decimal)
u.load_definitions(str(Path(__file__).parent / "units.txt"))
pint.set_application_registry(u)

Quantity: TypeAlias = u.Quantity
