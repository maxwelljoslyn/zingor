# Zingor Project Guidelines

## Codebase map
Zingor is a Django app for tracking D&D party/character data (Alexis Smolensk's campaign rules). Single app `characters/`; project settings in `zingor/`; SQLite db; tests in `characters/tests/`.

Key modules in `characters/`:
- `models.py` — `Character`, `Item`, `Spell`, `Condition`, `HitDie`, `SageStudyPoints`. Items nest via `container` FK; quantities/weights use pint units (`units.py`, `fields.py`).
- `views.py` — all views. Generic HTMX field editing: `edit_field`/`update_field` for Character fields (typed via `FIELD_TYPES`/`INTEGER_FIELDS`/`PINT_FIELDS`), `edit_item_field`/`update_item_field` for items. `update_field` maps a field back to its section via `SECTION_FOR_FIELD` and returns that section partial, appending `hx-swap-oob` re-renders of other sections that depend on the changed field (see `_render_section`). Cross-section dependencies live in the `oob` list inside `update_field`.
- `rules.py` — pure game-rule functions/tables (THAC0, derived stats); builds the `derived` dict used by templates.
- `sage.py` — static `sage_studies` catalogue (study → fields), rank thresholds/logic.
- `layout.py` — single registry of user-reorderable scopes/keys/default order (see Drag-to-reorder below).
- `wiki_links.py` / `wiki_export.py` — build `wiki.alexissmolensk.com` URLs for spells/studies/fields; export character data.
- `microformats.py` — "Zingor microformats" (ZMF) parser for scraping character data from the Adventure wiki (`adventure.alexissmolensk.com`).
- `auth_emails.py`, `templates/registration/` — self-serve registration with email confirmation.

Templates: `templates/characters/` — `base.html`, `character_list.html` (whole-party view incl. all-items table), `character_sheet.html` composed of `partials/` per section (`identity`, `abilities`, `hp`, `inventory`/`item_row`, `spells`, `sage`, `conditions`, `notes`, …). Each section partial's outermost element has `id="section-<name>"` (the htmx swap target). One stylesheet: `static/characters/styles.css`, themed via CSS custom properties (light/dark).

## Package Management
- Always use `uv` for dependency management, installing packages, running scripts, etc.
- Never use pip, poetry, or other package managers.

## Git and GitHub
- Never include `Co-Authored-By` trailers in commit messages.
- When a commit relates to a GitHub issue, reference it in the commit message body (never the headline): use `Refs #X` if the commit touches the issue, or `Closes #X` if it resolves it. Put these references on their own line, separated by a single blank line from any other body text.
- Always use `gh issue view <id> --json title,body,comments` instead of bare `gh issue view <id>`. The default output hits a deprecated "Projects (classic)" API and errors out.
- GitHub issues are sometimes submitted by end users — always the case when the issue has the `user-feedback` label. Don't rely on such issues as accurate summaries of the problem or as specs for human or LLM development unless the developer (maintainer) has responded or clarified in comments or edits.

## Commands
- **Run all tests**: `uv run pytest -n auto`
- **Run single test**: `uv run pytest tests/path/to/test_file.py::test_function_name -n auto`
- **Run tests with output**: `uv run pytest -v -n auto`
- Don't use `cat` needlessly. Prefer `head` to `cat | head`; prefer `tail` to `cat | tail`
- Always run tests in a Haiku 4.6 subagent.

## Code Style
- **Types**: Use type annotations for function parameters and return values
- **Documentation**: Descriptive docstrings for functions and classes
- Never use Python implicit string concatenation; use `+` or, for a sequence of strings, call `list()` then `join()`
- Avoid excessive blank lines in Python code. Use them only where required syntactically. In particular, don't put a blank line and then an explanatory comment; just write the comment.
- Django template comments (`{# ... #}`) must fit on **one line**. Django only recognizes the single-line form; a `{# #}` wrapped across lines is not a comment and gets rendered literally into the page. Write several consecutive one-line comments instead of wrapping.
- HTMX is used in this codebase for frontend=>backend reactivity to user input.

## Frontend markup & CSS

### Never target HTML `id`s with CSS
An element's three jobs are kept on three separate hooks, so they can change independently:
- `class="..."` — styling only.
- `id="..."` — an htmx swap target only (e.g. `#section-inventory` is referenced by `hx-target`/`hx-swap="outerHTML"`, and a section partial re-renders itself into that id).
- `data-*` — stable, semantic identity for JS/behavior (drag-reorder keys, etc.).

Do **not** write CSS selectors against `#section-*`, `#item-*`, `#field-*`, or any other htmx-target id. Style via classes and `data-*` attributes instead. **Why:** the id is load-bearing for the htmx contract; styling against it entangles appearance with the swap target, so a change to one silently breaks the other. Keeping CSS off ids means markup can be re-targeted or restyled without the two concerns colliding. (If you find a rule like `#section-sage tbody tr {...}`, that's the anti-pattern — move it to a class such as `.data-table`.)

### Reusable structural classes
Prefer the shared vocabulary over page-specific rules: `.sheet-row` (+ `--between`, `--grab`) for flex list rows, `.striped` on a list container for zebra rows, `.kv-table` / `.data-table` for tables (`.group-striped` to zebra-stripe by `<tbody>` group instead of by row), `.subsection` for a titled block within a section, `.section-head` for a heading row that keeps its full-width underline while holding a control (e.g. a Reorder toggle).

### Drag-to-reorder uses `data-*`, not ids
Per-user reordering (sections, ability rows, notes blocks) is driven entirely by `data-*` attributes so the JS never depends on htmx ids or on the semantic class names:
- The orderable item carries its stable key: `data-section="<key>"` on each section, `data-row="<key>"` / `data-subsection="<key>"` on reorderable rows. **Why:** this key is decoupled from `id="section-<key>"` — the id can stay an htmx target while the `data-section` key is what gets persisted and reordered.
- The container declares how the generic Sortable driver finds its items: `data-sortable="<scope>"`, `data-sortable-item="<attr>"` (items are `[data-<attr>]`, the key read from `dataset[attr]`), and optional `data-sortable-handle="<sel>"` (omit it to make the whole item the grip, as ability rows and notes blocks do; use it — e.g. `h2` — when the item is full of interactive content, as sections do).
- The toggle button uses `data-reorder-toggle="<scope>"` with `data-label-off` / `data-label-on`.
- On drop the new key order is `POST`ed to `/layout/order/<scope>/`; `characters/layout.py` is the single registry of valid scopes, keys, and default order. Add a new orderable axis there, not by special-casing the view or JS.
