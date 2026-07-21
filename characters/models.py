"""Models for the characters app."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .fields import PintField
from .units import D, u


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    email_confirmed = models.BooleanField(default=False)
    # Blank means "use the username"; see the `display_name` template filter.
    display_name = models.CharField(max_length=150, blank=True, default="")

    def __str__(self):
        return f"{self.user.username} profile"


class LayoutOrder(models.Model):
    """One user's position for a single key within an ordering scope.

    A *scope* is an independently-orderable list on the character sheet: a section
    key like "abilities" for that section's rows (and, later, "sections" for the
    section order itself). The full order for a (user, scope) is its rows sorted
    by `position`. This is a per-user display preference, applied whenever the
    user views any character sheet.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="layout_orders",
    )
    scope = models.CharField(max_length=50)
    key = models.CharField(max_length=50)
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "scope", "key"], name="uniq_layout_user_scope_key"
            )
        ]

    def __str__(self):
        return f"{self.user.username} {self.scope}: {self.key}@{self.position}"


class CharacterQuerySet(models.QuerySet):
    def active(self):
        """Only characters the player has not marked inactive (dead, retired, …)."""
        return self.filter(is_active=True)

    def wiki_synced(self):
        """Characters whose data should be pulled from their Adventure wiki page."""
        return (
            self.filter(sync_from_wiki=True)
            .exclude(wiki_url__isnull=True)
            .exclude(wiki_url="")
        )


class Character(models.Model):
    """A player character. Wide table with nullable columns so the sheet can start empty."""

    objects = CharacterQuerySet.as_manager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="characters",
    )
    name = models.CharField(max_length=200, default="", blank=True)

    # What role this character plays in the party. Primary characters and their
    # henchmen are the party proper; followers, hirelings, and pets are the
    # supporting cast. Used to split the homepage roster.
    KIND_CHOICES = [
        ("primary", "Primary"),
        ("hench", "Henchman"),
        ("follower", "Follower"),
        ("hireling", "Hireling"),
        ("pet", "Pet"),
    ]
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="primary")

    # Active status. Players mark a character inactive when it dies, retires, etc.;
    # inactive characters drop out of the active party views but are not deleted.
    is_active = models.BooleanField(default=True)

    # Identity
    race = models.CharField(max_length=100, null=True, blank=True)
    sex = models.CharField(max_length=20, null=True, blank=True)
    char_class = models.CharField(max_length=100, null=True, blank=True)
    level = models.IntegerField(null=True, blank=True)
    xp = models.IntegerField(null=True, blank=True)

    # Link to the character's page on the Adventure wiki, surfaced on the sheet.
    wiki_url = models.URLField(null=True, blank=True)
    # When True (and wiki_url is set), the periodic job treats the wiki page as
    # the source of truth and overwrites synced fields/spells/studies each run.
    sync_from_wiki = models.BooleanField(default=False)

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

    # Combat. Stored, not derived: computing AC from worn armor/shields would
    # have to model padding-underneath rules, degraded armor, spell effects,
    # etc. (see issue #39), so the player just records the final number.
    armor_class = models.IntegerField(null=True, blank=True)

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

    @staticmethod
    def _height_to_feet_inches(height):
        """Split a height Quantity into (feet, inches) integers/Decimals.

        Inches are returned as an int when whole, else as a Decimal.
        """
        total = height.to(u.inch).magnitude
        feet = int(total // 12)
        rem = total - feet * 12
        inches = int(rem) if rem == int(rem) else rem
        return feet, inches

    @property
    def height_display(self):
        """Human-readable height, e.g. `5' 7"` (None if unset)."""
        h = self.height
        if h is None:
            return None
        feet, inches = self._height_to_feet_inches(h)
        if inches:
            return f"{feet}' {inches}\""
        return f"{feet}'"

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
        bonus_hp = sum(b.amount for b in self.bonus_hit_points.all())
        if not hit_dice and not bonus_hp:
            return None
        return rules.maximum_hp(hit_dice, self.char_class, bonus_hp=bonus_hp)

    # --- Money ---
    # Coins live in the inventory as money items (Item.currency), so wealth is
    # derived by summing stacks wherever they are — carried, stashed, or nested.

    def _coin_total(self, currency):
        """Total coins of one currency across all money items, as a Quantity."""
        total = self.inventory.filter(currency=currency).aggregate(
            total=models.Sum("quantity")
        )["total"]
        return D(total or 0) * getattr(u, currency)

    @property
    def gp(self):
        return self._coin_total("gp")

    @property
    def sp(self):
        return self._coin_total("sp")

    @property
    def cp(self):
        return self._coin_total("cp")

    @property
    def money(self):
        """Total money across all currencies (convertible, e.g. .to(u.cp))."""
        return self.gp + self.sp + self.cp

    # --- Encumbrance ---

    @property
    def weight_of_carried_items(self):
        """Weight of carried inventory items, coins included."""
        total = D(0) * u.lb
        # Iterate .all() and filter in Python so a primed inventory prefetch
        # cache is reused; a queryset .filter() bypasses the cache and, via the
        # carried_weight recursion below, re-queries every container (N+1). When
        # the cache is not primed this is one query for all items (see
        # views._stitch_container_tree / _sheet_context).
        for item in self.inventory.all():
            if item.is_carried and item.container_id is None:
                total += item.carried_weight
        return total

    @property
    def current_encumbrance(self):
        """Total weight of everything carried."""
        return self.weight_of_carried_items

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


class BonusHitPoints(models.Model):
    """Arbitrary additional hit points beyond hit dice, with a note explaining
    their source (e.g. a soldier at arms whose HP exceeds bodymass but falls
    short of a full additional hit die).
    """

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="bonus_hit_points"
    )
    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    note = models.CharField(max_length=200)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"+{self.amount} ({self.note})"


class Spell(models.Model):
    """A spell known by a character."""

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="spells"
    )
    name = models.CharField(max_length=200)
    level = models.IntegerField()
    is_memorized = models.BooleanField(default=True)

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
    """An item in a character's inventory.

    A row with `currency` set is a stack of coins: its per-coin weight comes
    from the rules tables (never stored, hence weight must be NULL) and its
    quantity is the coin count.
    """

    CURRENCY_CHOICES = [
        ("gp", "gold pieces"),
        ("sp", "silver pieces"),
        ("cp", "copper pieces"),
    ]

    owner = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="inventory"
    )
    name = models.CharField(max_length=200)
    weight = PintField(default="0 oz", null=True, blank=True)
    currency = models.CharField(
        max_length=2, choices=CURRENCY_CHOICES, null=True, blank=True
    )
    unit = PintField(default="1 item")
    container = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="contents"
    )
    is_container = models.BooleanField(default=False)
    capacity = PintField(null=True, blank=True)
    is_carried = models.BooleanField(default=True)
    is_worn = models.BooleanField(default=False)
    quantity = models.IntegerField(default=1)
    props = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="item_quantity_gte_1",
            ),
            # Contents point at a single container row, so containers can't stack.
            models.CheckConstraint(
                condition=models.Q(is_container=False) | models.Q(quantity=1),
                name="item_container_quantity_1",
            ),
            # Coin weight is derived from the rules tables, so storing one is a bug;
            # and a coin stack can't hold other items.
            models.CheckConstraint(
                condition=models.Q(currency__isnull=True)
                | models.Q(weight__isnull=True, is_container=False),
                name="item_money_no_weight_no_container",
            ),
        ]

    def __str__(self):
        return self.name

    def _get_weight_quantity(self):
        """Per-unit weight as a Pint Quantity, handling string values.

        Money items derive their per-coin weight from the rules tables; their
        stored weight is NULL by constraint.
        """
        if self.currency:
            from . import rules

            return rules.coin_weight(self.currency)
        w = self.weight
        if w is None:
            return D(0) * u.oz
        if isinstance(w, str):
            from .fields import PintField

            field = PintField()
            return field.to_python(w)
        return w

    @property
    def unit_weight(self):
        """Public per-unit weight, e.g. for the "(X each)" note on stacks."""
        return self._get_weight_quantity()

    @property
    def adjusted_weight(self):
        """Stack weight: per-unit weight × quantity, scaled by percent_left."""
        w = self._get_weight_quantity() * self.quantity
        percent_left = self.props.get("percent_left") if self.props else None
        if percent_left is None:
            return w
        return w * (D("0.01") * D(str(percent_left)))

    @property
    def total_weight(self):
        """Physical weight including all contents (recursive for containers)."""
        total = self.adjusted_weight
        for content in self.contents.all():
            total += content.total_weight.to(total.units)
        return total

    @property
    def total_weight_oz(self) -> D:
        """Total weight converted to ounces, for uniform numeric comparison."""
        return self.total_weight.to(u.oz).magnitude

    @property
    def carried_weight(self):
        """Weight including contents, counting only carried items (recursive).

        Unlike total_weight, contents flagged is_carried=False are skipped, so
        nested items are treated consistently with top-level items when summing
        a character's encumbrance.
        """
        total = self.adjusted_weight
        # Filter carried contents in Python rather than with .contents.filter():
        # a queryset filter bypasses any primed prefetch cache, re-querying once
        # per container (N+1), whereas .all() is cache-served when contents were
        # prefetched (see views._stitch_container_tree).
        for content in self.contents.all():
            if content.is_carried:
                total += content.carried_weight.to(total.units)
        return total


class SageStudyPoints(models.Model):
    """Knowledge point total for one study on a character."""

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="sage_studies"
    )
    study = models.CharField(max_length=200)
    points = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    hidden = models.BooleanField(default=False)

    class Meta:
        unique_together = ("character", "study")
        ordering = ["study"]
        verbose_name_plural = "Sage study points"

    def __str__(self):
        return f"{self.study}: {self.points} pts"
