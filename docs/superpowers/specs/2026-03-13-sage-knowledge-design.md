# Sage Knowledge Feature Design

**Date:** 2026-03-13
**Status:** Approved

## Overview

Add sage knowledge tracking to the character sheet. Each character has a chosen field, a chosen study, and a set of studies accumulating knowledge points. Status (amateur/authority/expert/sage) derived from points.

Reference: https://wiki.alexissmolensk.com/index.php/Knowledge_Points

---

## 1. Static Catalogue

New file `characters/sage.py`, content copied from `dnd/dnd/sage.py`.

### `sage_studies`
`{study_name: {"fields": [...], "alexis_name": ...}}`. `sage_studies` and `sage_fields` are kept in sync by construction: every study in `sage_fields[f]["studies"]` is a key in `sage_studies`, and vice versa.

### `sage_fields`
`{field_name: {"studies": [...], "alexis_name": ...}}`. Authoritative for validation.

### `RANK_THRESHOLDS`
```python
RANK_THRESHOLDS = [(100,"sage"),(60,"expert"),(30,"authority"),(10,"amateur"),(0,"unranked")]
```

### `rank_for_points(points: int) -> str`
Iterates top-to-bottom, returns first name where `points >= threshold`. 10→amateur, 9→unranked, 100→sage.

### `CLASS_FIELDS`
```python
CLASS_FIELDS = {
    "assassin": ["Animal Training (Assassin)", "Grace", "Mastery at Arms", "Skulduggery"],
    "bard": ["Architecture","Art World","Ceramics","Circus","Dance","Drama","Fine Art",
             "Gastronomy","Leatherwork","Literature","Metalwork","Music","Puppetry","Salon",
             "Textiles","Woodworking"],
    "cleric": ["Legends and Folklore","Power","The Church","Theology and Customs"],
    "druid": ["Animal Life","Earth and Sky","Plant Life"],
    "fighter": ["Animal Training","Leadership","Mastery at Arms","Training"],
    "illusionist": ["Civitas (Illusionist)","Humanities","Reality","Unreality"],
    "mage": ["Civitas (Mage)","Humanities","Black Magic","Science"],
    "monk": ["Way of the Heart","Way of the Spirit","Way of the Stick","Way of the Stone"],
    "paladin": ["Animal Training","Mastery at Arms","Leadership","Reverence"],
    "ranger": ["Animal Training","Mastery at Arms","Training","Wilderland"],
    "thief": ["Fraud","Skulduggery","Streetwisdom","Theft"],
}
```
All 11 playable classes are covered. Every field name in `CLASS_FIELDS` is guaranteed to exist in `sage_fields`. If `char_class` is not in `CLASS_FIELDS` (e.g. an NPC class), bulk-creation is silently skipped.

### Helper functions (copied as-is)
- `alexisify(text) -> str` — converts name to wiki canonical spelling
- `linkify_field(x) -> str` — HTML anchor to wiki field page
- `linkify_study(x) -> str` — HTML anchor to wiki study page
- `sort_sage_entries(entries: dict[str,int], sort_keys=None) -> list[dict]` — flattens `{name: points}` into list of `{name, points, rank, rank_order}` dicts. `sort_keys` is a list of strings (`"name"`, `"points"`, `"rank"`, prefix `-` for descending); default `None` → `["rank", "name"]` (best rank first, then alphabetical). `rank_order` is numeric: `{sage:0, expert:1, authority:2, amateur:3, unranked:4}` — lower = better, ascending sort puts sage first. Handles empty dict (returns `[]`). Template always calls with default `sort_keys`.
- `rank_studies(study_dict) -> dict` — copied but not directly used in this feature; included for completeness.

---

## 2. Data Model

### Changes to `Character`
```python
chosen_field = models.CharField(max_length=200, null=True, blank=True, default=None)
chosen_study = models.CharField(max_length=200, null=True, blank=True, default=None)
```
No data migration needed for existing rows.

### New model: `SageStudyPoints`
```python
from django.core.validators import MinValueValidator

class SageStudyPoints(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="sage_studies")
    study = models.CharField(max_length=200)
    points = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ("character", "study")
        ordering = ["study"]
```
Negative points are never valid and enforced via validator.

---

## 3. Character Sheet UI

New partial `characters/templates/characters/partials/sage.html`, included in `sheet_body.html`. The outermost element is `<div class="section" id="section-sage">` — matching the convention used for other sections (e.g. `id="section-identity"`). All HTMX swaps target this div.

### Context helper

All views that render `sage.html` call a shared helper. To avoid Django template dict subscript limitations (the standard template engine does not support `dict[variable_key]`), each entry in `sage_studies_sorted` is enriched with the row `pk` directly, so templates use dot notation:

```python
def _build_sage_context(character):
    from .sage import sage_fields, sage_studies, sort_sage_entries
    import json
    rows = {r.study: r for r in character.sage_studies.all()}
    sorted_entries = sort_sage_entries({study: row.points for study, row in rows.items()})
    for entry in sorted_entries:
        entry["pk"] = rows[entry["name"]].pk
    return {
        "character": character,
        "sage_studies_sorted": sorted_entries,  # each dict: {name, points, rank, rank_order, pk}
        "sage_fields": sage_fields,
        "sage_fields_json": json.dumps(sage_fields),
        "all_study_names": sorted(sage_studies.keys()),
    }
```

Template accesses pk as `{{ entry.pk }}` (dot notation). `sage_fields_json` is emitted via `<script>window.SAGE_FIELDS = {{ sage_fields_json|escapejs }};</script>` so the `onchange` JS handler can read it.

### Contents

**Chosen field / chosen study** — displayed as read-only text ("Not set" when null), wrapped in `<span id="sage-chosen-field">`. Clicking triggers `hx-get="/characters/<pk>/sage/chosen-field/form/"` with `hx-target="#sage-chosen-field"` `hx-swap="outerHTML"` — this replaces only the display span with a form snippet. The form snippet contains two `<select>` inputs (field and study), a submit button, and the `window.SAGE_FIELDS` script block. Field `<select>` has `onchange` JS that reads `window.SAGE_FIELDS` to repopulate the study `<select>`. The form POSTs to `chosen-field/` with `hx-post` `hx-target="#section-sage"` `hx-swap="outerHTML"` — on success the full sage section is replaced. This mirrors the existing `unknown_or_value` / `edit_field.html` pattern.

`chosen_field` is not validated against `CLASS_FIELDS` — any catalogue field may be chosen freely.

**Studies table** — rendered from `sage_studies_sorted` (each dict has `name`, `points`, `rank`, `rank_order`, `pk`). Columns: Study Name, Points, Status. Points cell: `<input name="points" value="{{ entry.points }}" hx-post="/characters/{{ character.pk }}/sage/study/{{ entry.pk }}/points/" hx-target="#section-sage" hx-swap="outerHTML" hx-trigger="blur">` — POST fires when the user clicks away from the input. Status = `entry.rank`.

**Add study form** — `<select>` from `all_study_names`. `hx-post` to `study/add/` `hx-target="#section-sage"` `hx-swap="outerHTML"`. Adding an already-tracked study: silent no-op, table re-renders unchanged.

**Null/empty states** — "Not set" when null. Empty table shows "No studies tracked yet".

### 400 error handling
`HttpResponse(message, status=400)`. HTMX does not swap content on non-2xx by default; no error display in partial needed.

---

## 4. Views & URLs

**Auth pattern (same as all existing views):** `@login_required`, `get_object_or_404(Character, pk=pk, user=request.user)`.

**URL configuration:** All four URL patterns are added to `characters/urls.py` under the prefix `characters/<int:pk>/sage/`. URL names:
- `sage_chosen_field_form` → `characters/<int:pk>/sage/chosen-field/form/`
- `sage_chosen_field` → `characters/<int:pk>/sage/chosen-field/`
- `sage_study_points` → `characters/<int:pk>/sage/study/<int:study_pk>/points/`
- `sage_study_add` → `characters/<int:pk>/sage/study/add/`

### `GET /characters/<int:pk>/sage/chosen-field/form/`
`@login_required`. Returns the template `characters/partials/sage_field_form.html`, pre-populated with current `chosen_field` and `chosen_study`. The outermost element of that template **must have `id="sage-chosen-field"`** so that the `outerHTML` swap of the display span is reversible (the form replaces the span, but the id is preserved so the POST response can still target `#section-sage`). Contains two `<select>` inputs, a submit button, and the `window.SAGE_FIELDS` script block.

### `POST /characters/<pk>/sage/chosen-field/`
`@login_required`, `@require_POST`.

1. Validate `chosen_field` in `sage_fields` → else `HttpResponse("Invalid field", status=400)`
2. Validate `chosen_study` in `sage_fields[chosen_field]["studies"]` → else `HttpResponse("Invalid study for field", status=400)`
3. Save both to character
4. `char_class = character.char_class` (existing lowercase field on Character, e.g. `"fighter"`). If `char_class` is in `CLASS_FIELDS`: iterate over **all** field names in `CLASS_FIELDS[char_class]` (not just the chosen_field) — for each field name, get `sage_fields[field_name]["studies"]` — flatten all study name lists together — deduplicate with `dict.fromkeys()` — then `SageStudyPoints.objects.bulk_create([SageStudyPoints(character=character, study=s, points=0) for s in deduped_studies], ignore_conflicts=True)`. Each new row starts at `points=0`. If `char_class` is not in `CLASS_FIELDS`, skip silently.
5. Return `render(request, "characters/partials/sage.html", _build_sage_context(character))`

Step 4 runs on every call; `ignore_conflicts=True` makes it idempotent.

### `POST /characters/<pk>/sage/study/<int:study_pk>/points/`
`@login_required`, `@require_POST`.

1. `get_object_or_404(SageStudyPoints, pk=study_pk, character=character)`
2. Parse `request.POST.get("points")`: if missing, non-integer, or < 0 → `HttpResponse("Points must be a non-negative integer", status=400)`
3. Update and save
4. Return `render(request, "characters/partials/sage.html", _build_sage_context(character))`

### `POST /characters/<pk>/sage/study/add/`
`@login_required`, `@require_POST`.

1. Validate `study` in `sage_studies` → else `HttpResponse("Unknown study", status=400)`
2. `SageStudyPoints.objects.get_or_create(character=character, study=study, defaults={"points": 0})`
3. Return `render(request, "characters/partials/sage.html", _build_sage_context(character))`

---

## 5. Testing

**Unit tests** (`test_sage.py`):
- `rank_for_points`: 0→unranked, 9→unranked, 10→amateur, 29→amateur, 30→authority, 59→authority, 60→expert, 99→expert, 100→sage
- `sort_sage_entries({})` returns `[]` without error

**Model tests**:
- Duplicate `(character, study)` → `IntegrityError`
- `points=-1` via `full_clean()` → `ValidationError`

**View tests for `chosen-field/`**:
- Valid field + study → `character.chosen_field` and `character.chosen_study` persisted, 200
- `chosen_field` not in catalogue → 400
- `chosen_study` not in field's studies → 400
- First call, fighter class → `SageStudyPoints` count equals sum of study counts across all fighter fields
- Re-post → existing points unchanged, count unchanged
- Unknown `char_class` → no rows created, 200

**View tests for `study/<pk>/points/`**:
- Valid → updated, 200
- `study_pk` belonging to different character → 404
- `points=-1` → 400; `points="abc"` → 400; `points` missing → 400

**View tests for `study/add/`**:
- Valid study → row created points=0, 200
- Duplicate study → idempotent, 200
- Unknown study → 400

**View tests for `chosen-field/form/`**:
- Unauthenticated → redirect to login
- Valid character with existing chosen_field → 200, response contains select with current value
- Wrong user's character pk → 404
