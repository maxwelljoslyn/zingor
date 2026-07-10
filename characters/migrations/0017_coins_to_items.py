"""Convert each character's gp/sp/cp columns into carried money items (#71).

Coins become inventory rows so players can stash them in containers or leave
them behind; encumbrance then follows from ordinary carried-item weight. Every
amount in the wild is a whole number of coins; a fractional amount would lose
money silently, so it aborts the migration instead.
"""

from django.db import migrations

CURRENCY_NAMES = {"gp": "gold pieces", "sp": "silver pieces", "cp": "copper pieces"}


def coins_to_items(apps, schema_editor) -> None:
    Character = apps.get_model("characters", "Character")
    Item = apps.get_model("characters", "Item")
    for character in Character.objects.all():
        for currency, name in CURRENCY_NAMES.items():
            amount = getattr(character, currency)
            if amount is None:
                continue
            magnitude = amount.magnitude
            count = int(magnitude)
            if count != magnitude:
                raise ValueError(
                    f"character {character.pk} has fractional {currency}: {amount}"
                )
            if count < 1:
                continue
            Item.objects.create(
                owner=character,
                name=name,
                weight=None,
                currency=currency,
                quantity=count,
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
