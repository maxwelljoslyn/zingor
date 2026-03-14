# Sage Knowledge Feature Design

**Date:** 2026-03-13
**Status:** Approved

## Overview

Add sage knowledge tracking to the character sheet. Each character has a chosen field, a chosen study within that field, and a set of studies across all their class's fields — each study accumulates knowledge points over time. Status (amateur/authority/expert/sage) is derived from point totals.

Reference: https://wiki.alexissmolensk.com/index.php/Knowledge_Points

---

## 1. Static Catalogue

A new file `characters/sage.py` is created by copying and adapting content from the existing `dnd/dnd/sage.py` in the related project. It contains:

- `sage_studies`: dict mapping study name → `{fields: [...]}` (with optional `alexis_name`)
- `sage_fields`: dict mapping field name → `{studies: [...]}` (with optional `alexis_name`)
- `RANK_THRESHOLDS`: list of `(min_points, rank_name)` tuples — `(100, "sage")`, `(60, "expert")`, `(30, "authority")`, `(10, "amateur")`, `(0, "unranked")`
- `rank_for_points(points) -> str`: derives rank from point total
- `CLASS_FIELDS`: dict mapping class name (e.g. `"fighter"`) to list of field names available to that class. If not already present in the dnd project's sage.py, the user will provide this mapping.
- Helper functions copied as-is: `alexisify`, `linkify_field`, `linkify_study`, `sort_sage_entries`, `rank_studies`

Status is always derived at render time from `points` — never stored.

---

## 2. Data Model

### Changes to `Character`

Two new nullable CharFields added to the existing `Character` model:

```python
chosen_field = models.CharField(max_length=200, null=True, blank=True)
chosen_study = models.CharField(max_length=200, null=True, blank=True)
```

### New model: `SageStudyPoints`

```python
class SageStudyPoints(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="sage_studies")
    study = models.CharField(max_length=200)
    points = models.IntegerField(default=0)

    class Meta:
        unique_together = ("character", "study")
        ordering = ["study"]
```

One row per study the character is tracking. Points are the running total — no per-level roll history is stored.

When a character's chosen field is first set, `SageStudyPoints` rows are bulk-created (points=0) for all studies across all fields available to the character's class.

---

## 3. Character Sheet UI

A new partial `characters/templates/characters/partials/sage.html` is added and included in `sheet_body.html`.

The partial contains:

- **Chosen field / chosen study**: Displayed as read-only text, inline-editable via HTMX (same pattern as other identity fields). Setting these for the first time triggers bulk-creation of study rows.
- **Studies table**: Columns are Study Name, Points, Status. Each Points cell is inline-editable (click → input → HTMX POST → re-render partial). Status is rendered from `rank_for_points(points)`.
- **Add study form**: A small form (dropdown from full catalogue or free text) to add a study row outside the class defaults. Submits via HTMX POST.

No full-page reloads. All interactions return the re-rendered `sage.html` partial.

---

## 4. Views & URLs

Three new HTMX endpoints added to `views.py` and `urls.py`:

### `POST /characters/<pk>/sage/chosen-field/`
- Updates `character.chosen_field` and `character.chosen_study`
- If this is the first assignment (no existing `SageStudyPoints` rows), bulk-creates rows for all studies in `CLASS_FIELDS[character.char_class]`
- Returns re-rendered `sage.html` partial

### `POST /characters/<pk>/sage/study/<study>/points/`
- Updates `points` on the matching `SageStudyPoints` row
- Creates the row if it doesn't exist (handles studies added outside class defaults)
- Returns re-rendered `sage.html` partial

### `POST /characters/<pk>/sage/study/add/`
- Creates a new `SageStudyPoints` row for an arbitrary study from the catalogue
- No-ops if the row already exists
- Returns re-rendered `sage.html` partial

All three hang off the existing character detail URL namespace.

---

## 5. Testing

- Unit tests in `test_rules.py` for `rank_for_points` with boundary values (9, 10, 29, 30, 59, 60, 99, 100)
- Model tests for `SageStudyPoints` uniqueness constraint
- View tests for each of the three endpoints: correct status codes, correct point updates, bulk-creation on first field assignment, re-rendered partial content
