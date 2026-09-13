"""The site header fits on one row: small nav buttons, folded into a menu when narrow."""

import re
from pathlib import Path

from django.test import TestCase


class SiteHeaderTemplateTests(TestCase):
    """The header markup that the one-row layout and the narrow-screen menu rely on."""

    def setUp(self) -> None:
        self.html = self.client.get("/login/").content.decode()

    def test_nav_is_a_popover_opened_by_the_menu_button(self) -> None:
        self.assertRegex(self.html, r'<button[^>]*popovertarget="site-nav"[^>]*>Menu<')
        self.assertRegex(self.html, r'<nav[^>]*id="site-nav"[^>]*popover')

    def test_nav_buttons_are_small(self) -> None:
        docs = re.search(r"<a[^>]*>Docs</a>", self.html).group(0)
        self.assertIn("btn-small", docs)


class ButtonStyleTests(TestCase):
    """.btn looks the same whether it's on a link or a button."""

    def test_button_rule_sets_its_own_line_height(self) -> None:
        # Left to inherit, a link button takes the page's line-height and a <button>
        # the browser's "normal", so side by side the link button stands taller.
        stylesheet = (
            Path(__file__).resolve().parents[1] / "static" / "characters" / "styles.css"
        ).read_text()
        rule = re.search(r"button, \.btn \{([^}]*)\}", stylesheet)
        self.assertIsNotNone(rule)
        self.assertRegex(rule.group(1), r"line-height:\s*[\d.]+;")
