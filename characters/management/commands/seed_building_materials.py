"""Create the building materials catalogue from the imported trade table.

``uv run python manage.py seed_building_materials``

Run it after ``import_trade_table``: every material points at a trade good,
and the command refuses to write anything while any of those goods is
missing. Materials already in the catalogue are left alone, so edits made in
the admin survive; ``--refresh`` overwrites them from the seed.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser

from characters.building_materials import CatalogueError, seed_catalogue


class Command(BaseCommand):
    help = "Create the building materials catalogue from the imported trade goods."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Overwrite materials already in the catalogue from the seed.",
        )

    def handle(self, *args, **options) -> None:
        try:
            report = seed_catalogue(refresh=options["refresh"])
        except CatalogueError as exc:
            lines = ["No materials written:"] + [f"  {p}" for p in exc.problems]
            raise CommandError("\n".join(lines)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(report.created)} materials created,"
                + f" {len(report.refreshed)} refreshed,"
                + f" {len(report.unchanged)} left as they were"
            )
        )
