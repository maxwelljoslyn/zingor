"""Introspection tests that scan the source tree for known anti-patterns.

These are best-effort guards: they shell out to ripgrep (preferred) or
plain grep, and skip cleanly if neither tool is available. They catch
regressions that unit tests can't easily reach — for example a template
wiring an auto-committing input to a focus-dependent event.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_GLOBS = ("*.py", "*.js", "*.html")
# Directories grep would otherwise descend into; ripgrep already skips these
# via .gitignore / hidden-dir rules.
EXCLUDE_DIRS = (".git", ".venv", "node_modules", "staticfiles", "__pycache__")
# This test file is skipped from its own scan: it necessarily spells out the
# patterns it hunts for, so scanning it would always self-match.
THIS_FILE = Path(__file__).name
# Blur-based triggers: an htmx `hx-trigger="blur"`, an inline `onblur=` handler,
# or a JS `addEventListener("blur", ...)`. Wiring an auto-committing control to
# blur reintroduces issue #121 — number-spinner edits never fire blur unless the
# field was focused first, so the change is silently dropped. Prefer `change`.
BLUR_PATTERN = r"""hx-trigger\s*=\s*["'][^"']*\bblur\b|onblur\b|addEventListener\(\s*["']blur["']"""


def _ripgrep_cmd() -> list[str] | None:
    rg = shutil.which("rg")
    if rg is None:
        return None
    cmd = [rg, "--no-heading", "-n", "-e", BLUR_PATTERN]
    for glob in SOURCE_GLOBS:
        cmd += ["-g", glob]
    cmd += ["-g", "!" + THIS_FILE, str(REPO_ROOT)]
    return cmd


def _grep_cmd() -> list[str] | None:
    grep = shutil.which("grep")
    if grep is None:
        return None
    cmd = [grep, "-rnE", BLUR_PATTERN]
    cmd += ["--include=" + glob for glob in SOURCE_GLOBS]
    cmd += ["--exclude-dir=" + d for d in EXCLUDE_DIRS]
    cmd += ["--exclude=" + THIS_FILE, str(REPO_ROOT)]
    return cmd


def test_no_blur_triggers() -> None:
    """No source file should wire behavior to the blur event (see issue #121)."""
    cmd = _ripgrep_cmd() or _grep_cmd()
    if cmd is None:
        pytest.skip("neither rg nor grep is available")
    result = subprocess.run(cmd, capture_output=True, text=True)
    # rg/grep exit 0 when matches are found, 1 when there are none, and >=2 on
    # a real error (bad pattern, unreadable path); only the last is inconclusive.
    if result.returncode >= 2:
        pytest.skip(
            cmd[0]
            + " failed (exit "
            + str(result.returncode)
            + "): "
            + result.stderr.strip()
        )
    assert result.returncode == 1, (
        "Found blur trigger(s); use the `change` event instead (issue #121):\n"
        + result.stdout
    )
