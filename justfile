# To accept extra args for a recipe, add {{args}} at the end.
# But just attempts to interpolate those itself, so you'd need double-quoting, e.g. `just test "'-k some_regex'"`.
# The positional-arguments setting below is global to the justfile and allows extra arguments without interpoloation.
# With that, you still need the *args parameter on the recipe, and $@ (or $1, etc.) on its shell command.
set positional-arguments

default: docs fix format

fix:
    uv run ruff check --fix

format:
    uv run ruff format

docs:
    uv run python -m sphinx -T -b html docs docs/_build/html

autodocs:
    uv run --with sphinx-autobuild sphinx-autobuild docs docs/_build/html

# Args go straight through to pytest: `just test --lf`, `just test -k 'not slow'`.
test *args:
    uv run pytest -n 6 "$@"
