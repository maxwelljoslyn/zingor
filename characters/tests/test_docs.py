"""Guards for the end-user documentation under docs/.

Sphinx builds the site from docs/index.md's toctree, so a page that isn't
listed there is unreachable, and a cross-link to a missing page is a dead
link. Neither shows up as a build error, hence these checks.
"""

import re
from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"
# Markdown inline links, e.g. [external sync](external-synchronization.md#anchor).
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _doc_pages() -> list[Path]:
    """Every documentation page, index excluded (it does the including)."""
    return sorted(p for p in DOCS_ROOT.glob("*.md") if p.name != "index.md")


def _toctree_entries() -> list[str]:
    """Document names listed in index.md's toctree, in order."""
    text = (DOCS_ROOT / "index.md").read_text()
    block = re.search(r"```\{toctree\}\n(.*?)```", text, re.DOTALL)
    assert block is not None, "index.md has no toctree"
    entries = []
    for line in block.group(1).splitlines():
        line = line.strip()
        # Skip directives (":maxdepth: 2") and the blank line after them.
        if line and not line.startswith(":"):
            entries.append(line)
    return entries


def test_every_docs_page_is_in_the_toctree() -> None:
    """A page missing from the toctree never appears in the built docs."""
    assert {p.stem for p in _doc_pages()} == set(_toctree_entries())


def test_docs_cross_links_resolve() -> None:
    """Every relative link between docs pages points at a file that exists."""
    for page in _doc_pages() + [DOCS_ROOT / "index.md"]:
        for target in LINK_RE.findall(page.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            # Drop any fragment: only the file part names something on disk.
            path = DOCS_ROOT / target.split("#", 1)[0]
            assert path.exists(), f"{page.name} links to missing {target}"
