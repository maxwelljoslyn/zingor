import subprocess
from pathlib import Path

from django.conf import settings


def _read_git_commit() -> str:
    """Return the short commit hash of the running code, or "unknown".

    Resolved once at import time (app startup) so we don't shell out per request.
    """
    repo_dir = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir,
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


def registration_enabled(request):
    """Expose REGISTRATION_ENABLED to templates so the Register link can be hidden."""
    return {"registration_enabled": settings.REGISTRATION_ENABLED}


def git_commit(request):
    """Expose the running code's git commit hash for debugging."""
    return {"git_commit": GIT_COMMIT}
