from django.db import migrations, models

import characters.fields


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0006_sage"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="is_container",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="item",
            name="capacity",
            field=characters.fields.PintField(blank=True, null=True),
        ),
    ]
