"""Guards for the end-user documentation under docs/.

Sphinx builds the site from docs/index.md's toctree, so a page that isn't
listed there is unreachable, and a cross-link to a missing page is a dead
link. Neither shows up as a build error, hence these checks.

A page may opt out of the toctree with `orphan: true` in its front matter,
which is how Sphinx itself is told the omission is deliberate — that is the
marker for a page documenting a feature that isn't finished yet.
"""

import re
from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"
# Markdown inline links, e.g. [external sync](external-synchronization.md#anchor).
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# MyST front matter: a YAML block fenced by --- at the very top of the page.
FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
ORPHAN_RE = re.compile(r"^orphan:\s*true\s*$", re.MULTILINE | re.IGNORECASE)


def _doc_pages() -> list[Path]:
    """Every documentation page, index excluded (it does the including)."""
    return sorted(p for p in DOCS_ROOT.glob("*.md") if p.name != "index.md")


def _is_orphan(page: Path) -> bool:
    """Whether a page declares `orphan: true`, opting out of the toctree."""
    front_matter = FRONT_MATTER_RE.match(page.read_text())
    return (
        front_matter is not None and ORPHAN_RE.search(front_matter.group(1)) is not None
    )


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
    """A page missing from the toctree never appears in the built docs.

    Pages marked `orphan: true` are left out on purpose and exempt.
    """
    assert {p.stem for p in _doc_pages() if not _is_orphan(p)} == set(
        _toctree_entries()
    )


def test_no_orphan_page_is_in_the_toctree() -> None:
    """Sphinx warns about an orphan that turns out to be reachable after all."""
    orphans = {p.stem for p in _doc_pages() if _is_orphan(p)}
    assert orphans.isdisjoint(_toctree_entries())


def test_docs_cross_links_resolve() -> None:
    """Every relative link between docs pages points at a file that exists."""
    for page in _doc_pages() + [DOCS_ROOT / "index.md"]:
        for target in LINK_RE.findall(page.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            # Drop any fragment: only the file part names something on disk.
            path = DOCS_ROOT / target.split("#", 1)[0]
            assert path.exists(), f"{page.name} links to missing {target}"
