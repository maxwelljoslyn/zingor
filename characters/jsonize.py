"""Custom JSON encoder/decoder for Pint Quantities, Decimals, and modifier types."""

from decimal import Decimal
from functools import partial
from json import JSONEncoder, dumps, loads

from .types import AbilityModifier, ActionPointModifier, WeightModifier
from .units import D, Quantity, u


class MyEncoder(JSONEncoder):
    """Custom JSON encoder for D&D types.

    Don't use this directly. Use my_encoder for symmetry with my_decoder.
    """

    def default(self, obj):
        if isinstance(obj, AbilityModifier):
            return {
                "type": "AbilityModifier",
                "target": obj.target,
                "value": obj.value,
                "source": obj.source,
            }
        elif isinstance(obj, WeightModifier):
            return {
                "type": "WeightModifier",
                "target": obj.target,
                "value": obj.value,
                "source": obj.source,
            }
        elif isinstance(obj, ActionPointModifier):
            return {
                "type": "ActionPointModifier",
                "value": obj.value,
                "source": obj.source,
            }
        elif isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, Quantity):
            return {"magnitude": str(obj.magnitude), "units": str(obj.units)}
        elif isinstance(obj, Decimal):
            return float(obj)
        else:
            return JSONEncoder.default(self, obj)


my_encoder = partial(dumps, cls=MyEncoder, ensure_ascii=False)


def json_obj_to_python(d: dict[str, str]):
    if "type" in d and d["type"] == "AbilityModifier":
        return AbilityModifier(
            target=d["target"],
            value=d["value"],
            source=d["source"],
        )
    elif "type" in d and d["type"] == "ActionPointModifier":
        return ActionPointModifier(
            value=d["value"],
            source=d["source"],
        )
    elif "type" in d and d["type"] == "WeightModifier":
        return WeightModifier(
            target=d["target"],
            value=d["value"],
            source=d["source"],
        )
    elif "magnitude" in d and "units" in d:
        base = u(f"{d['magnitude']} {d['units']}")
        return D(base.magnitude) * base.units
    return d


my_decoder = partial(loads, object_hook=json_obj_to_python, parse_float=D)
