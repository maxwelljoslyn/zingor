"""Convert each character's gp/sp/cp columns into carried money items (#71).

Coins become inventory rows so players can stash them in containers or leave
them behind; encumbrance then follows from ordinary carried-item weight.
Fractional amounts (prod held 13.75 sp) cascade exactly into smaller coins at
the campaign rates (1 gp = 16 sp, 1 sp = 12 cp): 13.75 sp -> 13 sp + 9 cp.
Any remainder below one copper is discarded — there is no smaller coin — and
the cascade is printed so the deploy log shows exactly what changed.
"""

from decimal import Decimal, localcontext

from django.db import migrations

CURRENCY_NAMES = {"gp": "gold pieces", "sp": "silver pieces", "cp": "copper pieces"}

# Exchange rates; must match characters/units.txt.
GP_TO_SP = 16
SP_TO_CP = 12


def whole_coins(gp: Decimal, sp: Decimal, cp: Decimal) -> dict[str, int]:
    """Decompose possibly-fractional coin amounts into whole coins.

    Fractions cascade into the next-smaller denomination; any remainder below
    one copper is discarded (no smaller coin exists). Negative amounts raise
    ValueError so nobody's wealth goes further wrong.
    """
    # The app's global Decimal precision is 4 significant digits; cascade
    # arithmetic on large purses needs more, so use a local context.
    with localcontext() as ctx:
        ctx.prec = 28
        if gp < 0 or sp < 0 or cp < 0:
            raise ValueError(f"negative coin amount: {gp} gp, {sp} sp, {cp} cp")
        gp_whole = int(gp)
        sp = sp + (gp - gp_whole) * GP_TO_SP
        sp_whole = int(sp)
        cp = cp + (sp - sp_whole) * SP_TO_CP
        cp_whole = int(cp)
    return {"gp": gp_whole, "sp": sp_whole, "cp": cp_whole}


def coins_to_items(apps, schema_editor) -> None:
    Character = apps.get_model("characters", "Character")
    Item = apps.get_model("characters", "Item")
    for character in Character.objects.all():
        amounts = {}
        for currency in CURRENCY_NAMES:
            quantity = getattr(character, currency)
            amounts[currency] = (
                quantity.magnitude if quantity is not None else Decimal(0)
            )
        try:
            counts = whole_coins(amounts["gp"], amounts["sp"], amounts["cp"])
        except ValueError as exc:
            raise ValueError(f"character {character.pk}: {exc}") from exc
        if any(counts[c] != amounts[c] for c in CURRENCY_NAMES):
            print(
                f"character {character.pk}: cascaded "
                + f"{amounts['gp']} gp, {amounts['sp']} sp, {amounts['cp']} cp -> "
                + f"{counts['gp']} gp, {counts['sp']} sp, {counts['cp']} cp"
            )
        for currency, name in CURRENCY_NAMES.items():
            if counts[currency] < 1:
                continue
            Item.objects.create(
                owner=character,
                name=name,
                weight=None,
                currency=currency,
                quantity=counts[currency],
            )


def items_to_coins(apps, schema_editor) -> None:
    """Reverse: sum money items back into the character columns."""
    Character = apps.get_model("characters", "Character")
    Item = apps.get_model("characters", "Item")
    for character in Character.objects.all():
        for currency in CURRENCY_NAMES:
            total = sum(
                item.quantity
                for item in Item.objects.filter(owner=character, currency=currency)
            )
            setattr(character, currency, f"{total} {currency}")
        character.save()
    Item.objects.exclude(currency=None).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0016_item_currency"),
    ]

    operations = [
        migrations.RunPython(coins_to_items, items_to_coins),
    ]
