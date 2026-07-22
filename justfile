default: fix format docs

fix:
    uv run ruff check --fix

format:
    uv run ruff format

docs:
    uv run python -m sphinx -T -b html docs docs/_build/html

autodocs:
    uv run --with sphinx-autobuild sphinx-autobuild docs docs/_build/html
