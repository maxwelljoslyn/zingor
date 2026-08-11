"""Tests for parsing a hoard out of text.

The management command's tests cover the same formats through the CLI; these
pin the parser itself, which the web splitter reaches without a file in hand.
"""

import pytest

from characters.hoard import HoardError, parse_hoard


def test_reads_the_loose_line_format():
    hoard = parse_hoard("gem of true seeing: 4,200\nplatinum crown 3100\n")
    assert hoard == {"gem of true seeing": 4200, "platinum crown": 3100}


def test_reads_json_and_dict_literals():
    assert parse_hoard('{"gem": 4200}') == {"gem": 4200}
    assert parse_hoard("{'gem': 4200}") == {"gem": 4200}


def test_a_trailing_xp_unit_is_dropped():
    assert parse_hoard("handbell 50 xp\n") == {"handbell": 50}


def test_repeated_names_become_separate_items():
    hoard = parse_hoard("potion: 400\npotion: 400\npotion: 400\n")
    assert hoard == {"potion": 400, "potion (2)": 400, "potion (3)": 400}


def test_comments_and_blank_lines_are_skipped():
    assert parse_hoard("# frog king\n\ngem: 10\n") == {"gem": 10}


def test_a_hash_inside_a_name_is_not_a_comment():
    assert parse_hoard("potion #2: 400\n") == {"potion #2": 400}


def test_zero_valued_items_are_kept():
    """A worthless item still has to go to somebody."""
    assert parse_hoard("rusted helm: 0\n") == {"rusted helm": 0}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("gem: lots\n", "non-numeric"),
        ("gem: -5\n", "negative"),
        ("gem\n", "no name before the value"),
        ("[1, 2, 3]\n", "not a dict"),
        ('{"4": "x"}', "non-numeric"),
        ("{4: 200}", "not a string"),
        ("   \n", "is empty"),
        ("#\n", "no items in it"),
        ("{}", "no items in it"),
    ],
)
def test_unreadable_hoards_are_rejected(text: str, message: str):
    with pytest.raises(HoardError, match=message):
        parse_hoard(text)


def test_the_error_names_no_source():
    """Callers prefix their own source, so the parser must not guess at one."""
    with pytest.raises(HoardError) as caught:
        parse_hoard("gem\nlamp\n")
    assert str(caught.value).startswith("line 1:")
