from django.contrib import admin

from .models import Character, Condition, HitDie, Item, SageStudyPoints, Spell

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


class SageStudyPointsInline(admin.TabularInline):
    model = SageStudyPoints
    extra = 0


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
        SageStudyPointsInline,
    ]
