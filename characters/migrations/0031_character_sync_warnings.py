"""Store the last external sync's warnings on the character.

The parser has always recorded what it refused to guess at, but the warnings
only reached the log. Keeping the latest run's list — and when it ran — on the
row lets the character sheet show them to the player who owns the page.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0030_canonical_sage_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="character",
            name="last_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="character",
            name="sync_warnings",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
