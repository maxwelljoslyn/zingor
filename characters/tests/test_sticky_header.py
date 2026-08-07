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
    def test_header_sticks_to_the_top_of_the_viewport(self):
        block = declarations("header")
        self.assertIn("position: sticky", block)
        self.assertIn("top: 0", block)
        self.assertIn("z-index", block)

    def test_header_stays_below_the_modal_layer(self):
        header_z = int(re.search(r"z-index:\s*(\d+)", declarations("header")).group(1))
        overlay_z = int(
            re.search(r"z-index:\s*(\d+)", declarations(".modal-overlay")).group(1)
        )
        self.assertLess(header_z, overlay_z)

    def test_in_page_jumps_clear_the_header(self):
        # Without this a jump to #section-<key> lands under the sticky header.
        self.assertIn("scroll-padding-top: var(--header-height)", declarations("html"))

    def test_sticky_table_of_contents_clears_the_header(self):
        block = declarations(".sheet-toc")
        self.assertIn("var(--header-height)", block)
        for property_name in ("top", "max-height"):
            self.assertIn(property_name, block)
            self.assertRegex(block, property_name + r":[^;]*var\(--header-height\)")

    def test_header_height_has_a_fallback_for_js_off(self):
        self.assertRegex(STYLESHEET, r"--header-height:\s*[\d.]+rem")


class StickyHeaderTemplateTests(TestCase):
    def test_pages_load_the_header_measurement_script(self):
        # sticky-header.js republishes --header-height with the measured height,
        # which the sheet's table of contents and scroll-padding both read.
        html = self.client.get("/login/").content.decode()
        # The hashed name manifest static storage serves, e.g. sticky-header.abc123.js.
        self.assertRegex(html, r"sticky-header(\.[0-9a-f]+)?\.js")
