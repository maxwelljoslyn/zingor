"""Writing to a building's design tree: commits and drafts (#197).

The editor sends whole documents. A commit is checked in full
(characters.design_document.problems) and appended as a child of the
version the player started from; a draft is stored unchecked, since it is
work in progress.

New rooms arrive with negative ids, chosen by the editor, because a room's
id is the pk of its Room row and that row should exist only once the room
is committed. The commit creates the rows and writes their pks into the
stored document, and hands back the mapping so the editor can do the same
to its working copy.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from .design_document import SCHEMA_VERSION, material_specs, problems
from .models import Design, DesignDraft, DesignVersion, Room


class DesignRejected(Exception):
    """A document or request that cannot be committed, with the reasons."""

    def __init__(self, found: list[str]):
        super().__init__("; ".join(found))
        self.problems = found


@dataclass
class CommitResult:
    """What a commit made."""

    version: DesignVersion
    # True when the parent already had a child: someone else committed from
    # the same starting point, so this commit branches rather than continues.
    sibling: bool
    # The editor's new-room ids (negative) -> the Room pks now standing for them.
    rooms: dict[int, int] = field(default_factory=dict)


def _version_of(design: Design, version_id: Any) -> DesignVersion | None:
    """The building's version `version_id`, None for no id; rejects anything else."""
    if version_id is None:
        return None
    version = None
    if isinstance(version_id, int) and not isinstance(version_id, bool):
        version = DesignVersion.objects.filter(
            pk=version_id, building_id=design.building_id
        ).first()
    if version is None:
        raise DesignRejected([f"version {version_id} is not part of this building"])
    return version


def _is_new_room_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value < 0


def commit(
    design: Design, document: Any, parent_id: Any, author, message: str = ""
) -> CommitResult:
    """Append `document` to the tree as a child of `parent_id` and make it the design's head.

    The head moves last-write-wins: two players committing from the same
    parent both succeed, as siblings, and the design shows whichever came
    second. The author's draft of the design is discarded.
    """
    with transaction.atomic():
        parent = _version_of(design, parent_id)
        building = design.building
        existing_rooms = set(building.rooms.values_list("pk", flat=True))
        new_room_ids = set()
        if isinstance(document, dict) and isinstance(document.get("rooms"), list):
            new_room_ids = {
                room.get("id")
                for room in document["rooms"]
                if isinstance(room, dict) and _is_new_room_id(room.get("id"))
            }
        found = problems(document, material_specs(), existing_rooms | new_room_ids)
        if found:
            raise DesignRejected(found)
        document = copy.deepcopy(document)
        mapping = {}
        for room in document.get("rooms") or []:
            name = room["name"].strip()
            if _is_new_room_id(room["id"]):
                created = Room.objects.create(building=building, name=name)
                mapping[room["id"]] = created.pk
                room["id"] = created.pk
            else:
                Room.objects.filter(pk=room["id"]).exclude(name=name).update(name=name)
        if parent is not None:
            sibling = parent.children.exists()
        else:
            sibling = DesignVersion.objects.filter(design=design).exists()
        version = DesignVersion.objects.create(
            building=building,
            parent=parent,
            design=design,
            author=author,
            message=message[:500],
            schema_version=SCHEMA_VERSION,
            document=document,
        )
        design.head = version
        design.save(update_fields=["head", "updated_at"])
        DesignDraft.objects.filter(design=design, user=author).delete()
    return CommitResult(version, sibling, mapping)


def save_draft(
    design: Design, user, document: Any, base_version_id: Any
) -> DesignDraft:
    """Store `user`'s work in progress on `design`, replacing any earlier draft.

    Only its shape is checked (a JSON object); its contents may be half drawn.
    """
    if not isinstance(document, dict):
        raise DesignRejected(["the design is not a JSON object"])
    base_version = _version_of(design, base_version_id)
    draft, _ = DesignDraft.objects.update_or_create(
        design=design,
        user=user,
        defaults={
            "base_version": base_version,
            "schema_version": SCHEMA_VERSION,
            "document": document,
        },
    )
    return draft
