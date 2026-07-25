"""Tests for splitting indivisible treasure into near-equal XP shares."""

import itertools
import random

import pytest

from characters.treasure import share_spread, split_treasure, split_treasure_by_share

HOARD = {
    "gem of true seeing": 4200,
    "platinum crown": 3100,
    "spellbook": 2000,
    "coin pile": 1500,
    "ivory idol": 1500,
    "silk tapestry": 900,
    "jade ring": 750,
    "silver mirror": 650,
    "healing potion": 400,
    "brass lamp": 120,
}


def _totals(split: list[dict[str, int]]) -> list[int]:
    return [sum(share.values()) for share in split]


def _best_possible_spread(shares: int, items: dict[str, int]) -> int:
    """Brute-force the smallest achievable spread. Only for tiny inputs."""
    names = list(items)
    best = None
    for assignment in itertools.product(range(shares), repeat=len(names)):
        totals = [0] * shares
        for name, index in zip(names, assignment):
            totals[index] += items[name]
        spread = max(totals) - min(totals)
        if best is None or spread < best:
            best = spread
    return best


def test_returns_one_dict_per_share():
    assert len(split_treasure(4, HOARD)) == 4


def test_every_item_appears_exactly_once_at_its_own_value():
    seen: dict[str, int] = {}
    for share in split_treasure(3, HOARD):
        for name, value in share.items():
            assert name not in seen, f"{name} handed out twice"
            seen[name] = value
    assert seen == HOARD


def test_shares_are_ordered_richest_first():
    totals = _totals(split_treasure(3, HOARD))
    assert totals == sorted(totals, reverse=True)


def test_evenly_divisible_hoard_splits_exactly():
    items = {f"gem{i}": 100 for i in range(9)}
    assert _totals(split_treasure(3, items)) == [300, 300, 300]


def test_one_share_keeps_the_whole_hoard():
    split = split_treasure(1, HOARD)
    assert len(split) == 1
    assert split[0] == HOARD


def test_more_shares_than_items_leaves_empty_shares():
    split = split_treasure(4, {"idol": 300, "ring": 200})
    assert _totals(split) == [300, 200, 0, 0]


def test_empty_hoard_gives_empty_shares():
    assert split_treasure(3, {}) == [{}, {}, {}]


def test_a_single_dominant_item_sets_the_floor():
    """One item worth more than a fair share cannot be beaten down any further."""
    items = {"crown": 1000, "a": 10, "b": 10, "c": 10}
    split = split_treasure(2, items)
    assert _totals(split) == [1000, 30]


def test_spread_beats_naive_round_robin():
    """Dealing items out in turn is the obvious wrong answer; we must do better."""
    naive = [0] * 3
    for index, value in enumerate(HOARD.values()):
        naive[index % 3] += value
    assert share_spread(split_treasure(3, HOARD)) < max(naive) - min(naive)


@pytest.mark.parametrize("shares", [2, 3, 4, 5])
def test_hoard_spread_stays_tight(shares: int):
    split = split_treasure(shares, HOARD)
    fair = sum(HOARD.values()) / shares
    biggest_item = max(HOARD.values())
    # No share can be off by more than the largest single item.
    assert all(abs(total - fair) <= biggest_item for total in _totals(split))


def test_matches_brute_force_on_small_random_hoards():
    """The hill-climb should land on (or very near) the true optimum."""
    rng = random.Random(1234)
    misses = 0
    for _ in range(60):
        shares = rng.randint(2, 3)
        items = {f"item{i}": rng.randint(1, 200) for i in range(rng.randint(1, 7))}
        got = share_spread(split_treasure(shares, items))
        best = _best_possible_spread(shares, items)
        assert got >= best
        misses += got > best
    assert misses <= 3


def test_result_is_deterministic():
    first = split_treasure(3, HOARD)
    shuffled = dict(random.Random(9).sample(list(HOARD.items()), len(HOARD)))
    assert split_treasure(3, shuffled) == first


def test_share_spread_reports_the_gap():
    assert share_spread([{"a": 500}, {"b": 300, "c": 100}]) == 100


@pytest.mark.parametrize("shares", [0, -1])
def test_nonsense_share_counts_are_rejected(shares: int):
    with pytest.raises(ValueError):
        split_treasure(shares, HOARD)


def test_by_share_keys_the_result_by_recipient():
    split = split_treasure_by_share({"Alix": 1, "Bront": 1, "Cwen": 1}, HOARD)
    assert list(split) == ["Alix", "Bront", "Cwen"]
    assert sum(sum(share.values()) for share in split.values()) == sum(HOARD.values())


def test_by_share_gives_a_double_share_twice_the_xp():
    items = {f"gem{i}": 100 for i in range(9)}
    split = split_treasure_by_share({"Alix": 1, "Bront": 2}, items)
    assert sum(split["Alix"].values()) == 300
    assert sum(split["Bront"].values()) == 600


def test_by_share_equalises_xp_per_share_not_per_person():
    """A henchman on a half share should draw about half of what a PC draws."""
    items = {f"gem{i}": 10 for i in range(30)}
    split = split_treasure_by_share({"Alix": 2, "Bront": 2, "Hench": 1}, items)
    assert sum(split["Alix"].values()) == 120
    assert sum(split["Bront"].values()) == 120
    assert sum(split["Hench"].values()) == 60


def test_by_share_matches_the_equal_split_when_all_shares_are_one():
    equal = sorted(sum(share.values()) for share in split_treasure(3, HOARD))
    by_name = split_treasure_by_share({"a": 1, "b": 1, "c": 1}, HOARD)
    assert sorted(sum(share.values()) for share in by_name.values()) == equal


def test_by_share_rejects_an_empty_roster():
    with pytest.raises(ValueError):
        split_treasure_by_share({}, HOARD)


def test_by_share_rejects_a_recipient_drawing_nothing():
    with pytest.raises(ValueError):
        split_treasure_by_share({"Alix": 1, "Bront": 0}, HOARD)


def test_share_spread_accepts_either_return_shape():
    assert share_spread({"Alix": {"a": 500}, "Bront": {"b": 300}}) == 200
