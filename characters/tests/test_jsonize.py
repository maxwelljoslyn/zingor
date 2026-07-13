"""Tests for the custom JSON encoder/decoder (jsonize) and modifier types.

These exercise the round-trip contract: anything ``my_encoder`` writes,
``my_decoder`` must read back into an equal Python object.
"""

from django.test import SimpleTestCase

from characters.jsonize import (
    MyEncoder,
    json_obj_to_python,
    my_decoder,
    my_encoder,
)
from characters.types import AbilityModifier, ActionPointModifier, WeightModifier
from characters.units import D, u


class RoundTripTests(SimpleTestCase):
    def _round_trip(self, obj):
        return my_decoder(my_encoder(obj))

    def test_ability_modifier_round_trips(self):
        mod = AbilityModifier(value=2, source="Bull's Strength", target="strength")
        self.assertEqual(self._round_trip(mod), mod)

    def test_action_point_modifier_round_trips(self):
        mod = ActionPointModifier(value=3, source="Haste")
        self.assertEqual(self._round_trip(mod), mod)

    def test_weight_modifier_round_trips(self):
        mod = WeightModifier(value=D(5) * u.lb, source="Encumbered")
        restored = self._round_trip(mod)
        self.assertEqual(restored.target, "weight")
        self.assertEqual(restored.source, "Encumbered")
        self.assertEqual(restored.value, D(5) * u.lb)

    def test_quantity_round_trips(self):
        qty = D(3) * u.lb
        restored = self._round_trip(qty)
        self.assertEqual(restored, qty)

    def test_modifier_nested_in_container_round_trips(self):
        """Modifiers survive being nested inside a list/dict payload."""
        payload = {"mods": [AbilityModifier(value=-1, source="Curse", target="wisdom")]}
        restored = self._round_trip(payload)
        self.assertEqual(restored["mods"][0].target, "wisdom")
        self.assertEqual(restored["mods"][0].value, -1)


class EncoderTests(SimpleTestCase):
    def test_decimal_encodes_as_number(self):
        self.assertEqual(my_encoder(D("2.5")), "2.5")

    def test_set_encodes_as_list(self):
        # A set has no guaranteed order, so decode and compare as a set.
        decoded = set(my_decoder(my_encoder({1, 2, 3})))
        self.assertEqual(decoded, {1, 2, 3})

    def test_unsupported_type_raises(self):
        with self.assertRaises(TypeError):
            MyEncoder().default(object())


class DecoderTests(SimpleTestCase):
    def test_plain_dict_passes_through_untouched(self):
        """A dict that matches no known shape is returned as-is."""
        d = {"hello": "world"}
        self.assertEqual(json_obj_to_python(d), d)

    def test_decoder_parses_floats_as_decimal(self):
        """my_decoder wires parse_float=D so numbers land as Decimal, not float."""
        restored = my_decoder('{"n": 2.5}')
        self.assertIsInstance(restored["n"], D)
        self.assertEqual(restored["n"], D("2.5"))
