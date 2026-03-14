"""Modifier types for character conditions."""

from typing import Literal

from attrs import frozen

from .units import Quantity


@frozen
class Modifier:
    """Base class for all modifiers that can affect a character."""

    value: int
    source: str


@frozen
class AbilityModifier(Modifier):
    """A bonus or penalty added to a character's ability score."""

    target: Literal[
        "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"
    ]


@frozen
class WeightModifier(Modifier):
    """A modifier that affects a character's weight."""

    value: Quantity
    target: Literal["weight"] = "weight"


@frozen
class ActionPointModifier(Modifier):
    """A modifier that affects a character's action points."""
