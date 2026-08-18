from django.contrib import admin

from .models import (
    Character,
    Condition,
    HitDie,
    InventionMaintenance,
    Item,
    SageAbilityPoints,
    SageChosenField,
    SageConcentration,
    SageStudyPoints,
    Spell,
)

# The "extra" field on Inline classes controls how many blank/empty forms Django shows for adding new related objects.
# With the default (3) the admin sees see 3 empty rows for hit dice, 3 for spells, etc. That clutter is unecessary in Zingor.
# Setting the value to 0 means only existing records are shown, with an "Add another" link if the admin wants to create one.


class HitDieInline(admin.TabularInline):
    model = HitDie
    extra = 0


class SpellInline(admin.TabularInline):
    model = Spell
    extra = 0


class ConditionInline(admin.TabularInline):
    model = Condition
    extra = 0


class ItemInline(admin.TabularInline):
    model = Item
    extra = 0


class SageChosenFieldInline(admin.TabularInline):
    model = SageChosenField
    extra = 0


class SageStudyPointsInline(admin.TabularInline):
    model = SageStudyPoints
    extra = 0


class SageAbilityPointsInline(admin.TabularInline):
    model = SageAbilityPoints
    extra = 0


class SageConcentrationInline(admin.TabularInline):
    model = SageConcentration
    extra = 0


class InventionMaintenanceInline(admin.TabularInline):
    model = InventionMaintenance
    extra = 0


# Concentrations and invention maintenance hang off a study rather than off
# the character, so they get their own admin page instead of riding along on
# CharacterAdmin's inlines.
@admin.register(SageStudyPoints)
class SageStudyPointsAdmin(admin.ModelAdmin):
    list_display = ["study", "character", "points", "chosen", "hidden"]
    list_filter = ["chosen", "hidden"]
    search_fields = ["study", "character__name"]
    inlines = [SageConcentrationInline, InventionMaintenanceInline]


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "race", "char_class", "level"]
    list_filter = ["char_class", "race"]
    search_fields = ["name", "user__username"]
    inlines = [
        HitDieInline,
        SpellInline,
        ConditionInline,
        ItemInline,
        SageChosenFieldInline,
        SageStudyPointsInline,
        SageAbilityPointsInline,
    ]
