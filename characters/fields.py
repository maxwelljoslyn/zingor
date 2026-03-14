"""Custom Django model fields for Pint Quantities."""

from django.db import models

from .units import D, Quantity, u


class PintField(models.TextField):
    """Stores Pint Quantities as TEXT in the database.

    Converts between string representation and Pint Quantity with Decimal magnitude.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return None
        return self._to_quantity(value)

    def to_python(self, value):
        if value is None or value == "":
            return None
        if isinstance(value, Quantity):
            return value
        return self._to_quantity(value)

    def get_prep_value(self, value):
        if value is None:
            return None
        return str(value)

    def _to_quantity(self, value):
        """Convert a string to a Pint Quantity with Decimal magnitude."""
        if "deg" in str(value):
            amount, unit_str = str(value).split()
            amount = D(amount)
            return Quantity(amount, unit_str)
        else:
            base = u(str(value))
            return D(base.magnitude) * base.units
