import subprocess
import tomllib
from pathlib import Path

from django.conf import settings

REPO_DIR = Path(__file__).resolve().parent.parent


def _read_version() -> str:
    """Return the project version from pyproject.toml, or "unknown".

    Resolved once at import time so we don't re-read the file per request.
    """
    try:
        pyproject = tomllib.loads((REPO_DIR / "pyproject.toml").read_text())
        return pyproject["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "unknown"


def _read_git_commit() -> str:
    """Return the short commit hash of the running code, or "unknown".

    Resolved once at import time (app startup) so we don't shell out per request.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


GIT_COMMIT = _read_git_commit()
VERSION = _read_version()


def registration_enabled(request):
    """Expose REGISTRATION_ENABLED to templates so the Register link can be hidden."""
    return {"registration_enabled": settings.REGISTRATION_ENABLED}


def build_info(request):
    """Expose the running code's version and git commit hash for debugging."""
    return {"version": VERSION, "git_commit": GIT_COMMIT}
