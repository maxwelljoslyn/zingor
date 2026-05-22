# Zingor Project Guidelines

## Package Management
- Always use `uv` for dependency management, installing packages, running scripts, etc.
- Never use pip, poetry, or other package managers.

## Git and GitHub
- Never include `Co-Authored-By` trailers in commit messages.
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
