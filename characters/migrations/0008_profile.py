import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_profiles_for_existing_users(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Profile = apps.get_model("characters", "Profile")
    for user in User.objects.all():
        Profile.objects.get_or_create(user=user, defaults={"email_confirmed": False})


def remove_all_profiles(apps, schema_editor):
    Profile = apps.get_model("characters", "Profile")
    Profile.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("characters", "0007_item_container_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="Profile",
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
                ("email_confirmed", models.BooleanField(default=False)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            create_profiles_for_existing_users,
            remove_all_profiles,
        ),
    ]
