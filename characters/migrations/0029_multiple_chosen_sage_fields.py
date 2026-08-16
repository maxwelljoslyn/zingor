"""Turn the single chosen field/study into sets of chosen fields and studies.

Characters gain further fields and studies as they advance (issue #163), so
``Character.chosen_field`` / ``Character.chosen_study`` become a
``SageChosenField`` row per field and a ``chosen`` flag per study row.
"""

import django.db.models.deletion
from django.db import migrations, models


def forwards(apps, schema_editor):
    """Copy each character's single chosen field/study into the new shape."""
    Character = apps.get_model("characters", "Character")
    SageChosenField = apps.get_model("characters", "SageChosenField")
    SageStudyPoints = apps.get_model("characters", "SageStudyPoints")
    for character in Character.objects.exclude(
        chosen_field__isnull=True, chosen_study__isnull=True
    ):
        if character.chosen_field:
            SageChosenField.objects.get_or_create(
                character=character, field=character.chosen_field
            )
        if character.chosen_study:
            # The old column could name a study with no points row of its own;
            # give it one so the choice survives as a flag.
            row, _created = SageStudyPoints.objects.get_or_create(
                character=character,
                study=character.chosen_study,
                defaults={"points": 0},
            )
            row.chosen = True
            row.save(update_fields=["chosen"])


def backwards(apps, schema_editor):
    """Collapse the sets back to one field/study, keeping the first of each."""
    Character = apps.get_model("characters", "Character")
    for character in Character.objects.all():
        field = character.chosen_fields.order_by("field").first()
        study = character.sage_studies.filter(chosen=True).order_by("study").first()
        character.chosen_field = field.field if field else None
        character.chosen_study = study.study if study else None
        character.save(update_fields=["chosen_field", "chosen_study"])


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0028_character_picture"),
    ]

    operations = [
        migrations.CreateModel(
            name="SageChosenField",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("field", models.CharField(max_length=200)),
                (
                    "character",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chosen_fields",
                        to="characters.character",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Sage chosen fields",
                "ordering": ["field"],
                "unique_together": {("character", "field")},
            },
        ),
        migrations.AddField(
            model_name="sagestudypoints",
            name="chosen",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name="character",
            name="chosen_field",
        ),
        migrations.RemoveField(
            model_name="character",
            name="chosen_study",
        ),
    ]
