default: fix format docs

fix:
    uv run ruff check --fix

format:
    uv run ruff format

docs:
    uv run python -m sphinx -T -b html docs docs/_build/html
