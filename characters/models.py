"""Models for the characters app."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .fields import PintField
from .jsonize import my_decoder, my_encoder
from .units import D, u


class Character(models.Model):
    """A player character. Wide table with nullable columns so the sheet can start empty."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="characters",
    )
    name = models.CharField(max_length=200, default="", blank=True)

    # Identity
    race = models.CharField(max_length=100, null=True, blank=True)
    sex = models.CharField(max_length=20, null=True, blank=True)
    char_class = models.CharField(max_length=100, null=True, blank=True)
    level = models.IntegerField(null=True, blank=True)
    xp = models.IntegerField(null=True, blank=True)

    # Ability scores (base values, before modifiers)
    strength = models.IntegerField(null=True, blank=True)
    percentile_strength = models.IntegerField(null=True, blank=True)
    dexterity = models.IntegerField(null=True, blank=True)
    constitution = models.IntegerField(null=True, blank=True)
    intelligence = models.IntegerField(null=True, blank=True)
    wisdom = models.IntegerField(null=True, blank=True)
    charisma = models.IntegerField(null=True, blank=True)

    # Physical
    height = PintField(null=True, blank=True)
    weight = PintField(null=True, blank=True)

    # HP
    current_hp = models.IntegerField(null=True, blank=True)

    # Money
    gp = PintField(default="0 gp")
    sp = PintField(default="0 sp")
    cp = PintField(default="0 cp")

    # Encumbrance tuning
    encumbrance_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.0")
    )

    # Freeform
    notes = models.TextField(blank=True, default="")
    background = models.TextField(blank=True, default="")
    appearance = models.TextField(blank=True, default="")

    # Sage knowledge
    chosen_field = models.CharField(max_length=200, null=True, blank=True, default=None)
    chosen_study = models.CharField(max_length=200, null=True, blank=True, default=None)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name or f"Character #{self.pk}"

    # --- Ability score helpers ---

    ABILITY_NAMES = [
        "strength",
        "dexterity",
        "constitution",
        "intelligence",
        "wisdom",
        "charisma",
    ]

    def current_ability_score(self, ability, context=None):
        """Base score + sum of active Condition modifiers targeting that ability.

        context: if provided, include conditions with matching scope alongside
        unscoped conditions. If None, only unscoped conditions are included.
        """
        base = getattr(self, ability)
        if base is None:
            return None
        qs = self.conditions.filter(
            modifier_type="ability", target=ability, is_active=True
        )
        if context is not None:
            qs = qs.filter(
                models.Q(scope__isnull=True)
                | models.Q(scope="")
                | models.Q(scope=context)
            )
        else:
            qs = qs.filter(models.Q(scope__isnull=True) | models.Q(scope=""))
        mods = qs.aggregate(total=models.Sum("value"))["total"]
        return base + (mods or 0)

    def current_strength_and_percentile(self, context=None):
        """Effective (strength, percentile) after applying modifiers.

        Uses the AD&D rule: at the 18 boundary, each +1 modifier becomes
        +10% percentile instead of +1 score.
        """
        from . import rules

        base = self.strength
        if base is None:
            return None, None
        qs = self.conditions.filter(
            modifier_type="ability", target="strength", is_active=True
        )
        if context is not None:
            qs = qs.filter(
                models.Q(scope__isnull=True)
                | models.Q(scope="")
                | models.Q(scope=context)
            )
        else:
            qs = qs.filter(models.Q(scope__isnull=True) | models.Q(scope=""))
        modifier_sum = qs.aggregate(total=models.Sum("value"))["total"] or 0
        return rules.effective_strength(base, self.percentile_strength, modifier_sum)

    # --- HP ---

    @property
    def maximum_hp(self):
        """Calculate max HP from hit dice. Delegates to rules module."""
        from . import rules

        hit_dice = list(self.hit_dice.values("level", "die_type", "roll", "con_bonus"))
        if not hit_dice:
            return None
        return rules.maximum_hp(hit_dice, self.char_class)

    # --- Money ---

    @property
    def money(self):
        """Total money in copper pieces."""
        gp = self.gp or D(0) * u.gp
        sp = self.sp or D(0) * u.sp
        cp = self.cp or D(0) * u.cp
        return gp + sp + cp

    @property
    def weight_of_money(self):
        """Weight of all coins carried."""
        from . import rules

        gp = self.gp or D(0) * u.gp
        sp = self.sp or D(0) * u.sp
        cp = self.cp or D(0) * u.cp
        return rules.weight_of_money(gp, sp, cp)

    # --- Encumbrance ---

    @property
    def weight_of_carried_items(self):
        """Weight of carried inventory items, excluding coins."""
        total = D(0) * u.lb
        for item in self.inventory.filter(is_carried=True, container__isnull=True):
            total += item.total_weight
        return total

    @property
    def current_encumbrance(self):
        """Total weight of carried items + money."""
        return self.weight_of_carried_items + self.weight_of_money

    @property
    def max_encumbrance(self):
        """Maximum encumbrance based on strength and body weight."""
        from . import rules

        if self.strength is not None and self.weight:
            eff_str, eff_pct = self.current_strength_and_percentile(
                context="encumbrance"
            )
            return rules.maximum_encumbrance(
                eff_str or 0,
                eff_pct,
                D(self.weight.magnitude),
                self.encumbrance_multiplier,
            )
        return None

    @property
    def percent_encumbered(self):
        max_enc = self.max_encumbrance
        if max_enc is None or max_enc.magnitude == 0:
            return None
        return (self.current_encumbrance / max_enc) * 100

    BASE_AP = 5

    @property
    def current_action_points(self):
        """Current AP after encumbrance penalties."""
        from . import rules

        max_enc = self.max_encumbrance
        return rules.action_points(self.current_encumbrance, max_enc, self.BASE_AP)

    @property
    def ap_tiers(self):
        """List of (weight_threshold, ap_value) for each encumbrance tier.

        Returns None if max encumbrance is unknown.
        """
        max_enc = self.max_encumbrance
        if max_enc is None:
            return None
        num_tiers = self.BASE_AP
        # max_enc is a pint Quantity; extract plain float so arithmetic produces plain numbers
        max_enc_val = float(max_enc.magnitude)
        tier_size = max_enc_val / num_tiers
        # at each tier boundary, character loses one AP
        return [(tier_size * i, self.BASE_AP - i) for i in range(1, num_tiers)]

    # --- Undo/Redo ---

    def can_undo(self):
        return self.actions.filter(is_undone=False).exists()

    def undo(self):
        from .action_handlers import get_handler

        action = self.actions.filter(is_undone=False).order_by("-timestamp").first()
        if action is None:
            return False
        handler = get_handler(action.action_type)
        handler.apply_reverse(action)
        action.is_undone = True
        action.save(update_fields=["is_undone"])
        return True

    def can_redo(self):
        return self.actions.filter(is_undone=True).exists()

    def redo(self):
        from .action_handlers import get_handler

        action = self.actions.filter(is_undone=True).order_by("timestamp").first()
        if action is None:
            return False
        handler = get_handler(action.action_type)
        handler.apply_forward(action)
        action.is_undone = False
        action.save(update_fields=["is_undone"])
        return True


class HitDie(models.Model):
    """A single hit die roll. Can be a level-up hit die or a bodymass hit die."""

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="hit_dice"
    )
    level = models.IntegerField(null=True, blank=True)  # null for bodymass dice
    die_type = models.CharField(max_length=10)  # "d4", "d6", "d8", "d10", "d12"
    roll = models.IntegerField()
    con_bonus = models.IntegerField(default=0)
    is_bodymass = models.BooleanField(default=False)

    class Meta:
        ordering = ["is_bodymass", "level"]

    def __str__(self):
        if self.is_bodymass:
            return f"Bodymass: {self.die_type} → {self.roll}"
        return f"Level {self.level}: {self.die_type} → {self.roll} (+{self.con_bonus})"


class Spell(models.Model):
    """A spell known by a character."""

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="spells"
    )
    name = models.CharField(max_length=200)
    level = models.IntegerField()

    class Meta:
        unique_together = ("character", "name")
        ordering = ["level", "name"]

    def __str__(self):
        return f"{self.name} (L{self.level})"


class Condition(models.Model):
    """An active condition or modifier on a character."""

    MODIFIER_TYPES = [
        ("ability", "Ability"),
        ("weight", "Weight"),
        ("action_point", "Action Point"),
    ]

    SCOPE_CHOICES = [
        ("encumbrance", "Encumbrance"),
    ]

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="conditions"
    )
    modifier_type = models.CharField(max_length=20, choices=MODIFIER_TYPES)
    target = models.CharField(max_length=50, null=True, blank=True)
    value = models.IntegerField()
    source = models.CharField(max_length=200)
    scope = models.CharField(
        max_length=50, choices=SCOPE_CHOICES, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.value >= 0 else ""
        target_str = f" to {self.target}" if self.target else ""
        return f"{sign}{self.value}{target_str} ({self.source})"


class Item(models.Model):
    """An item in a character's inventory."""

    owner = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="inventory"
    )
    name = models.CharField(max_length=200)
    weight = PintField(default="0 oz")
    unit = PintField(default="1 item")
    container = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="contents"
    )
    is_carried = models.BooleanField(default=True)
    is_worn = models.BooleanField(default=False)
    props = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def _get_weight_quantity(self):
        """Get weight as a Pint Quantity, handling string values."""
        w = self.weight
        if w is None:
            return D(0) * u.oz
        if isinstance(w, str):
            from .fields import PintField

            field = PintField()
            return field.to_python(w)
        return w

    @property
    def adjusted_weight(self):
        """Weight adjusted for percent_left (e.g. partially consumed items)."""
        w = self._get_weight_quantity()
        percent_left = self.props.get("percent_left") if self.props else None
        if percent_left is None:
            return w
        return w * (D("0.01") * D(str(percent_left)))

    @property
    def total_weight(self):
        """Weight including contents (recursive for containers)."""
        total = self.adjusted_weight
        for content in self.contents.all():
            total += content.total_weight.to(total.units)
        return total


class Action(models.Model):
    """Records a mutation for undo/redo support."""

    character = models.ForeignKey(
        Character,
        on_delete=models.CASCADE,
        related_name="actions",
        null=True,
        blank=True,
    )
    action_type = models.CharField(max_length=50)
    forward_data = models.JSONField(
        default=dict,
        encoder=None,
    )
    reverse_data = models.JSONField(
        default=dict,
        encoder=None,
    )
    is_undone = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    group_id = models.CharField(max_length=100, null=True, blank=True)
    sequence = models.IntegerField(default=0)

    class Meta:
        ordering = ["timestamp", "sequence"]

    def __str__(self):
        status = " (undone)" if self.is_undone else ""
        return f"{self.action_type}{status}"

    @classmethod
    def record(cls, character, action_type, forward_data, reverse_data, **kwargs):
        """Create a new action, discarding any undone actions (branching history)."""
        character.actions.filter(is_undone=True).delete()
        return cls.objects.create(
            character=character,
            action_type=action_type,
            forward_data=forward_data,
            reverse_data=reverse_data,
            **kwargs,
        )


class SageStudyPoints(models.Model):
    """Knowledge point total for one study on a character."""

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="sage_studies"
    )
    study = models.CharField(max_length=200)
    points = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ("character", "study")
        ordering = ["study"]

    def __str__(self):
        return f"{self.study}: {self.points} pts"
