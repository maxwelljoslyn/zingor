"""The header stays put at the top of the viewport while the page scrolls.

The behaviour lives in CSS, so these read the stylesheet directly: they guard the
pieces that have to agree with one another — the header sticks, and everything
that positions itself against the viewport top allows for the room it takes.
"""

import re
from pathlib import Path

from django.test import TestCase

STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "characters"
STYLESHEET = (STATIC_DIR / "styles.css").read_text()
# Comments carry prose about the rules, including property names — drop them so a
# selector lookup can anchor on the end of the preceding rule.
UNCOMMENTED = re.sub(r"/\*.*?\*/", "", STYLESHEET, flags=re.DOTALL)


def declarations(selector: str) -> str:
    """Return the declaration block of the first rule with this exact selector."""
    match = re.search(
        r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", UNCOMMENTED
    )
    assert match is not None, f"no rule found for selector {selector!r}"
    return match.group(1)


class StickyHeaderStyleTests(TestCase):
    """The stylesheet rules that make the header stick and keep content clear of it."""

    def test_header_sticks_to_the_top_of_the_viewport(self) -> None:
        block = declarations("header")
        self.assertIn("position: sticky", block)
        self.assertIn("top: 0", block)
        self.assertIn("z-index", block)

    def test_header_stays_below_the_modal_layer(self) -> None:
        header_z = int(re.search(r"z-index:\s*(\d+)", declarations("header")).group(1))
        overlay_z = int(
            re.search(r"z-index:\s*(\d+)", declarations(".modal-overlay")).group(1)
        )
        self.assertLess(header_z, overlay_z)

    def test_in_page_jumps_clear_the_header(self) -> None:
        # Without this a jump to #section-<key> lands under the sticky header.
        self.assertIn("scroll-padding-top: var(--header-height)", declarations("html"))

    def test_sticky_sheet_rail_clears_the_header(self) -> None:
        block = declarations(".sheet-rail")
        for property_name in ("top", "max-height"):
            self.assertRegex(block, property_name + r":[^;]*var\(--header-height\)")

    def test_header_height_is_set_in_rem(self) -> None:
        # rem, so the offset scales with the user's font size along with the header.
        self.assertRegex(STYLESHEET, r"--header-height:\s*[\d.]+rem")
