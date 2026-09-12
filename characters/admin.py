from django.contrib import admin

from .models import (
    Building,
    Character,
    Condition,
    HitDie,
    InventionMaintenance,
    Item,
    Market,
    Parcel,
    Price,
    PriceList,
    SageAbilityPoints,
    SageChosenField,
    SageConcentration,
    SageStudyPoints,
    Spell,
    TradeGood,
    Vendor,
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


class BuildingInline(admin.TabularInline):
    model = Building
    extra = 0
    fields = ["name"]
    show_change_link = True


@admin.register(Parcel)
class ParcelAdmin(admin.ModelAdmin):
    list_display = ["name", "owner_names"]
    search_fields = ["name", "owners__name"]
    filter_horizontal = ["owners"]
    inlines = [BuildingInline]

    @admin.display(description="Owners")
    def owner_names(self, parcel):
        return ", ".join(str(owner) for owner in parcel.owners.all())


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ["name", "parcel", "owner_names"]
    list_filter = ["parcel"]
    search_fields = ["name", "owners__name"]
    filter_horizontal = ["owners"]

    @admin.display(description="Owners")
    def owner_names(self, building):
        return ", ".join(str(owner) for owner in building.owners.all())


# --- Trade table ---


@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = ["name", "latest_import"]

    @admin.display(description="Latest import")
    def latest_import(self, market):
        price_list = market.latest_price_list()
        return None if price_list is None else price_list.imported_at


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ["name", "title"]
    search_fields = ["name", "title"]


@admin.register(TradeGood)
class TradeGoodAdmin(admin.ModelAdmin):
    list_display = ["name", "vendor", "weight", "description"]
    list_filter = ["vendor"]
    search_fields = ["name", "description"]


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ["market", "imported_at", "source", "price_count"]
    list_filter = ["market"]

    @admin.display(description="Prices")
    def price_count(self, price_list):
        return price_list.prices.count()


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ["good", "price_list", "listed", "amount", "coin"]
    list_filter = ["price_list__market", "price_list", "coin"]
    search_fields = ["good__name", "good__description", "good__vendor__name"]
    raw_id_fields = ["good"]
    list_select_related = ["good", "good__vendor", "price_list", "price_list__market"]
