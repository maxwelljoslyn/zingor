# Inventory filtering, categories, and sortable tables

Implementation plan for the inventory-UX group of issues. Ordered by dependency:
categories underpin presets, presets and free-text search share one filter
endpoint, and the whole-party table is the first surface to get all three.

## Issues in this cluster

GitHub now models the filtering feature as a tree: **#27 is the parent**, with
**#31** and **#32** tracked as its sub-issues. #26 and #29 are separate open
issues in the same UX area.

| # | Title | Role | Notes |
|---|-------|------|-------|
| **#27** | Search/filter interface for whole-party inventory | **parent** | Full-width debounced input + HTMX endpoint; its own core is free-text name search. Sub-issues: #31, #32. |
| #32 | Item categories | sub-issue of #27 / foundation | One item ↔ many categories. Seed an initial set; make user-extensible later. Built first (presets and category-filtering depend on it). |
| #31 | Filter presets by name or category | sub-issue of #27 | Named, reusable filters (e.g. "Food", "Torches"). Depends on #32. |
| #30 | Way to designate a party shared resource | originating request, **kept open** | Joey's "see food/torches everyone shares" need. Maintainer is folding it into #27 via category presets (see cross-link comments on #27/#30); track it there, don't close yet. |
| #26 | Make inventories sortable | separate, partly shipped | Whole-party table already sorts client-side (`character_list.html`). Per-character inventory still needs it. |
| #29 | Consistent inventory UI (whole-party + per-character) | separate epic | Tracks the convergence of the above across both surfaces; not a discrete unit of work. |

## Current state (what exists today)

- **Whole-party table**: `character_list` view builds `all_items` (top-level items,
  `container__isnull=True`) and renders `character_list.html`, which sorts
  client-side via inline JS on Owner / Item / Weight columns.
- **Per-character inventory**: rendered by `partials/inventory.html` → `partials/item.html`;
  edited through the HTMX `item/<id>/edit-field/` + `update-field/` endpoints. No sort, no filter.
- **Item model** (`models.py`): `owner`, `name`, `weight`, `unit`, `container`,
  `is_container`, `capacity`, `is_carried`, `is_worn`, `props` (JSON). No category concept.
- URL namespace is `characters:`; HTMX partial-swap is the established pattern for reactive UI.

## Data model (#32)

Add a `Category` model and a many-to-many link to `Item`. ("One item has many
categories" and one category spans many items → M2M, despite the issue's loose
"one:many" wording.)

```
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)        # stable key for preset matching
    is_user_created = models.BooleanField(default=False)  # admin-seeded vs. user-added

class Item(models.Model):
    ...
    categories = models.ManyToManyField(Category, related_name="items", blank=True)
```

- Migration + a data migration to seed initial categories (food, torches/light,
  ammunition, containers, armor, weapons, tools, …). Final list TBD — see Open questions.
- Admin registration so the seeded set is editable now; defer end-user category
  creation to a later phase (#32 says "after it settles in").

## Phased implementation

### Phase 1 — Categories (#32)
- Model `Category` + `Item.categories` M2M; migration + seed data migration.
- Register `Category` in `admin.py`; inline category assignment on the `Item` admin.
- Surface categories read-only in `partials/item.html` (small tags/badges).
- Tests: model + M2M, seed migration applied, item renders its categories.

### Phase 2 — Whole-party filter + sort endpoint (#27; also reworks whole-party #26)
**Decision: sort and filter both run server-side.** One endpoint, one source of
truth, consistent with the HTMX-everywhere pattern and minimal JS. Accepts the
round-trip cost — the party table is small.
- New view `party_inventory_filter` (e.g. `GET character/inventory/filter/?q=&category=&sort=&dir=`)
  returning the table partial only.
- Extract the `all_items` table into `partials/party_inventory_table.html`
  shared by the full page and every filter/sort response.
- Filter logic: case-insensitive `name__icontains` for `q`; `categories__slug=` for category.
- Sort logic: `sort` ∈ {owner, item, weight}, `dir` ∈ {asc, desc}, applied via
  `queryset.order_by(...)`; weight sorts on a normalized unit (reuse `adjusted_weight_oz`).
  Default order = current owner/name.
- Template: full-width search input above the table, `hx-get` the endpoint,
  `hx-trigger="keyup changed delay:300ms, search"`, `hx-target` the table container.
  Column headers become `hx-get` links that pass `sort`/`dir` (and preserve the
  active `q`/`category`); the swapped partial renders the active-sort arrow itself.
- **Remove** the inline client-side sort `<script>` from `character_list.html`.
- Tests: filter by name, by category, empty result, combined q+category; sort each
  column asc/desc; sort + filter together preserve each other.

### Phase 3 — Filter presets (#31)
- A preset = a saved `{name, category-or-name-match}` filter. Start with
  category-backed presets (one preset per seeded category) rendered as quick
  buttons/chips above the filter input; each chip `hx-get`s the Phase 2 endpoint
  with its `category` slug.
- Optional later: name-substring presets (e.g. "torch") and user-saved presets.
- This is what closes the spirit of #30 (shared-resource visibility).
- Tests: preset chip issues the right filtered request; preset list reflects seeded categories.

### Phase 4 — Per-character sort + UI convergence (#26 / #29)
- Apply the same sortable-column treatment to `partials/inventory.html` that the
  whole-party table already has (Item, Weight at minimum).
- Align markup/styles/behaviors between the two inventory surfaces so sorting and
  (where it makes sense) filtering look and work the same. This is the bulk of #29.
- Close #26 once per-character sort lands; keep #29 open until both surfaces converge.

## Issue hygiene (already done / remaining)
- **Done**: #27 is the parent of sub-issues #31 and #32; the Cluster A umbrella
  #15 ("input constraints") is closed alongside #25/#35/#37.
- **#30**: kept open intentionally — it's the originating user request, tracked via
  #27's category presets (#31). Close it only when that ships, not before.
- **#29**: keep as the tracking epic; link Phases 1–4 to it.
- **#26**: note in the issue that whole-party sort already shipped; remaining scope
  is per-character (Phase 4).

## Open questions
1. **Initial category set** (#32): which seed categories, and their names/slugs?
   Needs the maintainer's list.
2. **Preset shape** (#31): category-only to start, or also name-substring presets in v1?
3. **User-created categories** (#32): in scope now (admin only) vs. deferred end-user UI.
