from django.apps import AppConfig
from django.db.backends.signals import connection_created


def set_sqlite_pragmas(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA cache_size=-64000;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA ignore_check_constraints=OFF;")


class CharactersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "characters"

    def ready(self):
        connection_created.connect(set_sqlite_pragmas)
