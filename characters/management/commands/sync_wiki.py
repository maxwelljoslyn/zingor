"""Synchronously sync every wiki-backed character (bypasses Huey).

For testing/ops: ``uv run python manage.py sync_wiki``. Runs the same loop as
the periodic task inline and prints per-character results and warnings.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from characters.models import Character
from characters.wiki_sync import sync_character_from_wiki


class Command(BaseCommand):
    help = "Fetch and apply wiki data for every wiki-synced character."

    def handle(self, *args, **options) -> None:
        characters = Character.objects.wiki_synced()
        if not characters:
            self.stdout.write("No characters have wiki sync enabled.")
            return
        for character in characters:
            label = character.name or f"character #{character.pk}"
            try:
                warnings = sync_character_from_wiki(character)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"{label}: FAILED ({exc})"))
                continue
            self.stdout.write(
                self.style.SUCCESS(f"{label}: synced from {character.wiki_url}")
            )
            for warning in warnings:
                self.stdout.write(f"  ! {warning}")
