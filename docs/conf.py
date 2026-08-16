import os
import sys
from pathlib import Path

# The repo root, so `characters.limits` is importable. That module imports
# nothing, so this needs neither the app's dependencies nor Django settings.
sys.path.insert(0, str(Path(__file__).parent.parent))

from characters.limits import (  # noqa: E402
    MAX_PICTURE_MB,
    MAX_PICTURE_PIXELS,
    MAX_SYNC_WARNINGS,
)

extensions = [
    "sphinx_rtd_theme",
    "myst_parser",
]

html_theme = "sphinx_rtd_theme"
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "/")
project = "Zingor"
author = "Maxwell Joslyn"
project_copyright = "%Y Maxwell Joslyn"

myst_enable_extensions = ["colon_fence", "substitution"]

# Limits the app enforces, so the prose can't drift from the code. Written in
# pages as {{ max_picture_mb }} and so on.
myst_substitutions = {
    "max_picture_mb": MAX_PICTURE_MB,
    "max_picture_pixels": MAX_PICTURE_PIXELS,
    "max_sync_warnings": MAX_SYNC_WARNINGS,
}
