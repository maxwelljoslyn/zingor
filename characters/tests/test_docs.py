"""Guards that the end-user docs stay reachable and in step with the code.

Docs are prose, so these are deliberately shallow: they check that a page is
wired into the table of contents (an unlisted page builds but nothing links to
it), and that the layout page still names every orderable key. If a section or
row is renamed in `characters/layout.py`, the second test fails and points at
the paragraph that has gone stale.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from characters import layout
from characters.models import Character
from characters.views import NOTES_FIELDS

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"
LAYOUT_PAGE = DOCS_DIR / "layout-customization.md"


def _toctree_entries() -> set[str]:
    """The document names listed in the toctree of `docs/index.md`."""
    index = (DOCS_DIR / "index.md").read_text()
    block = re.search(r"```\{toctree\}(.*?)```", index, re.DOTALL)
    assert block is not None, "docs/index.md has no toctree"
    return {
        line.strip()
        for line in block.group(1).splitlines()
        if line.strip() and not line.strip().startswith(":")
    }


class TocTreeTests(SimpleTestCase):
    def test_every_page_is_listed(self) -> None:
        pages = {path.stem for path in DOCS_DIR.glob("*.md") if path.name != "index.md"}
        self.assertEqual(pages - _toctree_entries(), set())


class LayoutPageTests(SimpleTestCase):
    def test_documents_every_orderable_key(self) -> None:
        text = LAYOUT_PAGE.read_text().lower()
        names = (
            [title for _, title, _ in layout.SECTIONS]
            + list(Character.ABILITY_NAMES)
            + list(NOTES_FIELDS.values())
        )
        missing = [name for name in names if name.lower() not in text]
        self.assertEqual(missing, [])
