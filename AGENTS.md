# Zingor Project Guidelines

## Package Management
- Always use `uv` for dependency management, installing packages, running scripts, etc.
- Never use pip, poetry, or other package managers.

## Git and GitHub
- Never include `Co-Authored-By` trailers in commit messages.
- When a commit relates to a GitHub issue, reference it in the commit message body (never the headline): use `Refs #X` if the commit touches the issue, or `Closes #X` if it resolves it. Put these references on their own line, separated by a single blank line from any other body text.
- Always use `gh issue view <id> --json title,body,comments` instead of bare `gh issue view <id>`. The default output hits a deprecated "Projects (classic)" API and errors out.

## Commands
- **Run all tests**: `uv run pytest -n auto`
- **Run single test**: `uv run pytest tests/path/to/test_file.py::test_function_name -n auto`
- **Run tests with output**: `uv run pytest -v -n auto`
- Don't use `cat` needlessly. Prefer `head` to `cat | head`; prefer `tail` to `cat | tail`

## Code Style
- **Types**: Use type annotations for function parameters and return values
- **Documentation**: Descriptive docstrings for functions and classes
- Never use Python implicit string concatenation; use `+` or, for a sequence of strings, call `list()` then `join()`
- Avoid excessive blank lines in Python code. Use them only where required syntactically. In particular, don't put a blank line and then an explanatory comment; just write the comment.
- HTMX is used in this codebase for frontend=>backend reactivity to user input.

## Frontend markup & CSS

### Never target HTML `id`s with CSS
An element's three jobs are kept on three separate hooks, so they can change independently:
- `class="..."` — styling only.
- `id="..."` — an htmx swap target only (e.g. `#section-inventory` is referenced by `hx-target`/`hx-swap="outerHTML"`, and a section partial re-renders itself into that id).
- `data-*` — stable, semantic identity for JS/behavior (drag-reorder keys, etc.).

Do **not** write CSS selectors against `#section-*`, `#item-*`, `#field-*`, or any other htmx-target id. Style via classes and `data-*` attributes instead. **Why:** the id is load-bearing for the htmx contract; styling against it entangles appearance with the swap target, so a change to one silently breaks the other. Keeping CSS off ids means markup can be re-targeted or restyled without the two concerns colliding. (If you find a rule like `#section-sage tbody tr {...}`, that's the anti-pattern — move it to a class such as `.data-table`.)

### Reusable structural classes
Prefer the shared vocabulary over page-specific rules: `.sheet-row` (+ `--between`, `--grab`) for flex list rows, `.striped` on a list container for zebra rows, `.kv-table` / `.data-table` for tables, `.subsection` for a titled block within a section, `.section-head` for a heading row that keeps its full-width underline while holding a control (e.g. a Reorder toggle).

### Drag-to-reorder uses `data-*`, not ids
Per-user reordering (sections, ability rows, notes blocks) is driven entirely by `data-*` attributes so the JS never depends on htmx ids or on the semantic class names:
- The orderable item carries its stable key: `data-section="<key>"` on each section, `data-row="<key>"` / `data-subsection="<key>"` on reorderable rows. **Why:** this key is decoupled from `id="section-<key>"` — the id can stay an htmx target while the `data-section` key is what gets persisted and reordered.
- The container declares how the generic Sortable driver finds its items: `data-sortable="<scope>"`, `data-sortable-item="<attr>"` (items are `[data-<attr>]`, the key read from `dataset[attr]`), and optional `data-sortable-handle="<sel>"` (omit it to make the whole item the grip, as ability rows and notes blocks do; use it — e.g. `h2` — when the item is full of interactive content, as sections do).
- The toggle button uses `data-reorder-toggle="<scope>"` with `data-label-off` / `data-label-on`.
- On drop the new key order is `POST`ed to `/layout/order/<scope>/`; `characters/layout.py` is the single registry of valid scopes, keys, and default order. Add a new orderable axis there, not by special-casing the view or JS.
