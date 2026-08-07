"""Guard that DEPLOYMENT.md keeps up with the settings it documents.

Deployment config is spread across ``zingor/settings.py`` and ``.env.example``,
and an undocumented setting is invisible to whoever next sets up a server. These
tests scan both sources and require every environment variable they mention to
appear in DEPLOYMENT.md, so adding a setting without documenting it fails CI.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_DOC = REPO_ROOT / "DEPLOYMENT.md"
SETTINGS = REPO_ROOT / "zingor" / "settings.py"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
# Matches both shapes settings.py uses to read config: os.environ["NAME"] for
# required values and os.environ.get("NAME", ...) for optional ones.
ENV_READ_PATTERN = re.compile(
    r"""os\.environ(?:\.get)?[\[(]\s*["']([A-Z][A-Z0-9_]*)["']"""
)


def settings_env_vars() -> set[str]:
    """Every environment variable name ``zingor/settings.py`` reads."""
    return set(ENV_READ_PATTERN.findall(SETTINGS.read_text()))


def env_example_vars() -> set[str]:
    """Every variable named in ``.env.example``, ignoring blanks and comments."""
    names = set()
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            names.add(line.split("=", 1)[0].strip())
    return names


def test_deployment_doc_exists() -> None:
    """The deployment doc is what the other tests here scan; it must be present."""
    assert DEPLOYMENT_DOC.is_file()


def test_settings_env_vars_are_documented() -> None:
    """Every setting read from the environment is named in DEPLOYMENT.md."""
    doc = DEPLOYMENT_DOC.read_text()
    found = settings_env_vars()
    # Sanity check on the regex itself: SECRET_KEY is the one variable
    # settings.py cannot start without, so an empty scan means a broken pattern.
    assert "SECRET_KEY" in found
    undocumented = sorted(name for name in found if name not in doc)
    assert not undocumented, f"undocumented in DEPLOYMENT.md: {undocumented}"


def test_env_example_vars_are_documented() -> None:
    """Every variable in .env.example is named in DEPLOYMENT.md."""
    doc = DEPLOYMENT_DOC.read_text()
    undocumented = sorted(name for name in env_example_vars() if name not in doc)
    assert not undocumented, f"undocumented in DEPLOYMENT.md: {undocumented}"
