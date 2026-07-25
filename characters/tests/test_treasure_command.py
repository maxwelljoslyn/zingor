"""Tests for the split_treasure management command's file parsing and output."""

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

LINES = """
# cavern of the frog king
gem of true seeing: 4,200
platinum crown: 3100
healing potion: 400 xp
healing potion: 400
"""


def run(path: Path, *args: str) -> str:
    out = StringIO()
    call_command("split_treasure", str(path), *args, stdout=out)
    return out.getvalue()


def hoard_from(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def shares_from_json(output: str) -> list[dict]:
    return json.loads(output)


def test_reads_the_loose_line_format(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.txt", LINES)
    shares = shares_from_json(run(path, "-n", "2", "--json"))
    items = {name: xp for share in shares for name, xp in share["items"].items()}
    assert items["gem of true seeing"] == 4200
    assert items["platinum crown"] == 3100


def test_repeated_names_become_separate_items(tmp_path: Path):
    """Two healing potions are two items, not one that overwrote the other."""
    path = hoard_from(tmp_path, "hoard.txt", LINES)
    shares = shares_from_json(run(path, "-n", "2", "--json"))
    items = {name: xp for share in shares for name, xp in share["items"].items()}
    assert items["healing potion"] == 400
    assert items["healing potion (2)"] == 400


def test_comments_and_blank_lines_are_skipped(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.txt", LINES)
    shares = shares_from_json(run(path, "-n", "2", "--json"))
    assert sum(len(share["items"]) for share in shares) == 4


def test_hash_inside_a_name_is_not_a_comment(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.txt", "potion #2: 400\ngem: 400\n")
    shares = shares_from_json(run(path, "-n", "2", "--json"))
    names = [name for share in shares for name in share["items"]]
    assert "potion #2" in names


def test_reads_json(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200, "lamp": 120}')
    shares = shares_from_json(run(path, "-n", "2", "--json"))
    assert [share["items"] for share in shares] == [{"gem": 4200}, {"lamp": 120}]


def test_reads_a_python_dict_literal(tmp_path: Path):
    path = hoard_from(
        tmp_path, "hoard.py", "{\n    'gem': 4200,\n    'lamp': 120,\n}\n"
    )
    shares = shares_from_json(run(path, "-n", "2", "--json"))
    assert [share["items"] for share in shares] == [{"gem": 4200}, {"lamp": 120}]


def test_values_may_be_bare_space_separated(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.txt", "gem 4200\nlamp 120\n")
    shares = shares_from_json(run(path, "-n", "2", "--json"))
    assert [share["items"] for share in shares] == [{"gem": 4200}, {"lamp": 120}]


def test_values_may_carry_a_trailing_xp_unit(tmp_path: Path):
    """The campaign's own treasure lists are written 'handbell 50 xp'."""
    path = hoard_from(tmp_path, "hoard.txt", "handbell 50 xp\nalmondy topaz 100xp\n")
    shares = shares_from_json(run(path, "-n", "2", "--json"))
    items = {name: xp for share in shares for name, xp in share["items"].items()}
    assert items == {"handbell": 50, "almondy topaz": 100}


def test_names_label_the_shares(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200, "lamp": 120}')
    shares = shares_from_json(run(path, "--names", "Alix,Bront", "--json"))
    assert [share["share"] for share in shares] == ["Alix", "Bront"]


def test_share_count_is_inferred_from_names(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200, "lamp": 120}')
    assert len(shares_from_json(run(path, "--names", "Alix,Bront,Cwen", "--json"))) == 3


def test_table_output_shows_totals_and_spread(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200, "lamp": 120}')
    output = run(path, "--names", "Alix,Bront")
    assert "Alix: 4,200 XP" in output
    assert "Bront: 120 XP" in output
    assert "Spread between richest and poorest: 4,080 XP" in output


def test_empty_shares_are_shown_as_nothing(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200}')
    assert "(nothing)" in run(path, "-n", "3")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("gem: lots\n", "non-numeric"),
        ("gem: -5\n", "negative"),
        ("gem\n", "no name before the value"),
        ("[1, 2, 3]\n", "not a dict"),
        ("\n \n", "is empty"),
    ],
)
def test_unusable_files_are_rejected(tmp_path: Path, text: str, message: str):
    path = hoard_from(tmp_path, "hoard.txt", text)
    with pytest.raises(CommandError, match=message):
        run(path, "-n", "2")


def test_missing_file_is_rejected(tmp_path: Path):
    with pytest.raises(CommandError, match="could not read"):
        run(tmp_path / "nope.txt", "-n", "2")


def test_share_count_is_required(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200}')
    with pytest.raises(CommandError, match="give --shares"):
        run(path)


def test_names_must_match_an_explicit_share_count(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200}')
    with pytest.raises(CommandError, match="but 3 names were given"):
        run(path, "-n", "2", "--names", "Alix,Bront,Cwen")


def gems(tmp_path: Path, count: int, value: int = 100) -> Path:
    lines = "".join(f"gem{i}: {value}\n" for i in range(count))
    return hoard_from(tmp_path, "gems.txt", lines)


def test_a_recipient_can_draw_more_than_one_share(tmp_path: Path):
    shares = shares_from_json(
        run(gems(tmp_path, 9), "--names", "Alix,Bront:2", "--json")
    )
    drawn = {share["share"]: share["xp"] for share in shares}
    assert drawn == {"Alix": 300, "Bront": 600}


def test_fractional_shares_are_rescaled_to_whole_ones(tmp_path: Path):
    """'1,1,1/2' is the same division as '2,2,1' — and reports as such."""
    path = gems(tmp_path, 30, value=10)
    shares = shares_from_json(run(path, "--names", "Alix,Bront,Hench:1/2", "--json"))
    assert [(s["share"], s["shares_drawn"], s["xp"]) for s in shares] == [
        ("Alix", 2, 120),
        ("Bront", 2, 120),
        ("Hench", 1, 60),
    ]


def test_decimal_shares_work_too(tmp_path: Path):
    shares = shares_from_json(
        run(gems(tmp_path, 9), "--names", "Alix,Hench:0.5", "--json")
    )
    assert [(s["share"], s["shares_drawn"]) for s in shares] == [
        ("Alix", 2),
        ("Hench", 1),
    ]


def test_uneven_shares_are_labelled_and_compared_per_share(tmp_path: Path):
    output = run(gems(tmp_path, 9), "--names", "Alix,Bront:2")
    assert "Alix (1 share): 300 XP" in output
    assert "Bront (2 shares): 600 XP" in output
    assert "Spread between richest and poorest: 0 XP per share" in output


def test_even_shares_are_not_labelled_with_a_share_count(tmp_path: Path):
    output = run(gems(tmp_path, 9), "--names", "Alix,Bront,Cwen")
    assert "Alix: 300 XP" in output
    assert "shares)" not in output


@pytest.mark.parametrize("names", ["Alix,Bront:0", "Alix,Bront:-1", "Alix,Bront:many"])
def test_unusable_share_counts_are_rejected(tmp_path: Path, names: str):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200}')
    with pytest.raises(CommandError, match="Bront"):
        run(path, "--names", names)


def test_a_repeated_recipient_is_rejected(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200}')
    with pytest.raises(CommandError, match="lists 'Alix' twice"):
        run(path, "--names", "Alix,Alix")


def test_outfile_saves_the_table_and_confirms_on_stdout(tmp_path: Path):
    path = gems(tmp_path, 9)
    out = tmp_path / "split.txt"
    printed = run(path, "--names", "Alix,Bront,Cwen", "-o", str(out))
    assert "Alix: 300 XP" in out.read_text()
    assert f"Wrote a 3-way split to {out}." in printed
    # The table itself went to the file, not to the terminal.
    assert "Alix" not in printed


def test_outfile_content_matches_what_would_have_been_printed(tmp_path: Path):
    path = gems(tmp_path, 9)
    out = tmp_path / "split.txt"
    run(path, "--names", "Alix,Bront:2", "-o", str(out))
    assert out.read_text() == run(path, "--names", "Alix,Bront:2")


def test_outfile_saves_json_when_asked(tmp_path: Path):
    out = tmp_path / "split.json"
    run(gems(tmp_path, 9), "--names", "Alix,Bront:2", "--json", "-o", str(out))
    saved = json.loads(out.read_text())
    assert [(s["share"], s["xp"]) for s in saved] == [("Alix", 300), ("Bront", 600)]


def test_outfile_will_not_clobber_the_hoard_file(tmp_path: Path):
    path = gems(tmp_path, 9)
    with pytest.raises(CommandError, match="is the hoard file"):
        run(path, "-n", "3", "-o", str(path))
    assert path.read_text().startswith("gem0: 100")


def test_outfile_reports_a_path_it_cannot_write(tmp_path: Path):
    out = tmp_path / "nowhere" / "split.txt"
    with pytest.raises(CommandError, match="could not write"):
        run(gems(tmp_path, 9), "-n", "3", "-o", str(out))


def test_a_missing_recipient_name_is_rejected(tmp_path: Path):
    path = hoard_from(tmp_path, "hoard.json", '{"gem": 4200}')
    with pytest.raises(CommandError, match="empty entry"):
        run(path, "--names", "Alix,:2")
