"""Merge exact-duplicate item rows into single rows with a summed quantity.

Before quantity existed (#74), "28 torches" was 28 identical rows. Rows merge
only when every player-visible attribute matches; containers and any row that
holds contents keep their identity, since contents point at one specific row.
"""

import json

from django.db import migrations


def _group_key(item) -> tuple:
    """Identity of a mergeable item: every field except pk/quantity/created_at."""
    return (
        item.owner_id,
        item.name,
        str(item.weight),
        str(item.unit),
        item.container_id,
        item.is_carried,
        item.is_worn,
        str(item.capacity),
        json.dumps(item.props, sort_keys=True),
    )


def consolidate_duplicates(apps, schema_editor) -> None:
    """Collapse groups of identical non-container rows into one stacked row."""
    Item = apps.get_model("characters", "Item")
    holding_contents = set(
        Item.objects.exclude(container=None).values_list("container_id", flat=True)
    )
    groups: dict[tuple, list] = {}
    for item in Item.objects.filter(is_container=False).order_by("pk"):
        if item.pk in holding_contents:
            continue
        groups.setdefault(_group_key(item), []).append(item)
    for rows in groups.values():
        if len(rows) < 2:
            continue
        keeper, *dupes = rows
        keeper.quantity = sum(row.quantity for row in rows)
        keeper.save(update_fields=["quantity"])
        Item.objects.filter(pk__in=[row.pk for row in dupes]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0014_item_quantity"),
    ]

    operations = [
        migrations.RunPython(consolidate_duplicates, migrations.RunPython.noop),
    ]
