"""Huey periodic tasks. Auto-discovered from installed apps' ``tasks.py``."""

from __future__ import annotations

import logging

from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from .models import Character
from .wiki_sync import sync_character_from_wiki

logger = logging.getLogger(__name__)


@db_periodic_task(crontab(minute="*"))
def sync_wiki_characters() -> None:
    """Poll every wiki-synced character and update it from its page.

    Per-character try/except so one bad fetch can't abort the whole run.
    """
    for character in Character.objects.wiki_synced():
        try:
            warnings = sync_character_from_wiki(character)
            for warning in warnings:
                logger.warning("wiki-sync %s: %s", character.name, warning)
        except Exception:
            logger.exception("wiki-sync failed for character %s", character.pk)
