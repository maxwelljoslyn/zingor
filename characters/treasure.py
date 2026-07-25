"""Divide indivisible treasure into approximately equal XP shares.

No model imports — takes primitives, returns values.

This is multiway number partitioning (the cousin of bin packing where the
number of bins is fixed and you minimise the spread rather than the count).
Exact optimisation is NP-hard, so we use longest-processing-time-first to get
a good starting split and then hill-climb with moves, swaps and two-for-one
trades until no exchange between two shares can bring the totals closer.
"""

import heapq
from fractions import Fraction


def split_treasure(shares: int, items: dict[str, int]) -> list[dict[str, int]]:
    """Divide `items` among `shares` equal recipients so XP totals are near-equal.

    `items` maps a treasure's name to its XP value. No item is ever split, so
    the shares will rarely be exactly equal — chunky items (a single gem worth
    more than a fair share) put a hard floor on how close they can get.

    Returns a list of `shares` dicts, each a name -> XP subset of `items`,
    ordered from the most valuable share to the least. Some shares come back
    empty when there are fewer items than recipients.
    """
    if shares < 1:
        raise ValueError("shares must be at least 1")
    buckets = _partition([1] * shares, items)
    buckets.sort(key=lambda names: (-sum(items[n] for n in names), names))
    return [_as_share(names, items) for names in buckets]


def split_treasure_by_share(
    shares: dict[str, int], items: dict[str, int]
) -> dict[str, dict[str, int]]:
    """Divide `items` among named recipients drawing different numbers of shares.

    `shares` maps each recipient to how many shares they draw, so a henchman on
    a half share is written as everyone else on 2 and the henchman on 1. The aim
    is to equalise XP *per share* rather than XP per person.

    Returns a dict of recipient -> their items, in the order `shares` names them.
    """
    if not shares:
        raise ValueError("shares must name at least one recipient")
    if any(count < 1 for count in shares.values()):
        raise ValueError("every recipient must draw at least one share")
    buckets = _partition(list(shares.values()), items)
    return {
        name: _as_share(names, items)
        for name, names in zip(shares, buckets, strict=True)
    }


def share_spread(split: list[dict[str, int]] | dict[str, dict[str, int]]) -> int:
    """XP gap between the richest and poorest share of a split.

    Accepts either return shape. Meaningful when every recipient draws the same
    number of shares; with uneven shares, compare XP per share instead.
    """
    shares = split.values() if isinstance(split, dict) else split
    totals = [sum(share.values()) for share in shares]
    return max(totals) - min(totals)


def _partition(weights: list[int], items: dict[str, int]) -> list[list[str]]:
    """Assign every item to one of len(weights) shares, then balance the result."""
    entries = sorted(items.items(), key=lambda kv: (-kv[1], kv[0]))
    buckets = _longest_first(weights, entries)
    _balance(buckets, weights, items)
    return buckets


def _as_share(names: list[str], items: dict[str, int]) -> dict[str, int]:
    """One share as a name -> XP dict, most valuable item first."""
    return {name: items[name] for name in sorted(names, key=lambda n: (-items[n], n))}


def _longest_first(
    weights: list[int], entries: list[tuple[str, int]]
) -> list[list[str]]:
    """Greedily hand each item, largest first, to the least-loaded share so far.

    "Least loaded" is XP already held per share drawn, so a recipient on two
    shares is fed twice as fast as one on a single share.
    """
    buckets: list[list[str]] = [[] for _ in weights]
    heap = [(Fraction(0), i) for i in range(len(weights))]
    heapq.heapify(heap)
    for name, value in entries:
        load, i = heapq.heappop(heap)
        buckets[i].append(name)
        heapq.heappush(heap, (load + Fraction(value, weights[i]), i))
    return buckets


def _balance(
    buckets: list[list[str]], weights: list[int], values: dict[str, int]
) -> None:
    """Hill-climb the greedy split in place, minimising the sum of t^2/w per share.

    Minimising that sum is equivalent to minimising the variance of XP per
    share, and it gives a cheap exact test for whether an exchange helps. Each
    accepted exchange strictly lowers the cost, which cannot fall forever, so
    this terminates.
    """
    totals = [sum(values[name] for name in names) for names in buckets]
    pairs = [(a, b) for a in range(len(buckets)) for b in range(len(buckets)) if a != b]
    improved = True
    while improved:
        improved = False
        for a, b in pairs:
            while _exchange(buckets, totals, weights, values, a, b):
                improved = True


def _exchange(
    buckets: list[list[str]],
    totals: list[int],
    weights: list[int],
    values: dict[str, int],
    a: int,
    b: int,
) -> bool:
    """Make the single best-improving trade between shares a and b, if any.

    Considers handing one or two of a's items to b in return for at most one of
    b's, which covers plain moves, one-for-one swaps and two-for-one trades. The
    two-for-one case is what rescues splits where greedy has stranded a share
    holding one lump that no single item can trade against.
    """
    given = [(x,) for x in buckets[a]]
    given += [(x, y) for i, x in enumerate(buckets[a]) for y in buckets[a][i + 1 :]]
    taken: list[tuple[str, ...]] = [()] + [(y,) for y in buckets[b]]
    best: tuple[int, tuple[str, ...], tuple[str, ...]] | None = None
    for out in given:
        for back in taken:
            delta = sum(values[n] for n in out) - sum(values[n] for n in back)
            gain = _gain(delta, totals, weights, a, b)
            if gain < 0 and (best is None or gain < best[0]):
                best = (gain, out, back)
    if best is None:
        return False
    _, out, back = best
    delta = sum(values[n] for n in out) - sum(values[n] for n in back)
    for name in out:
        buckets[a].remove(name)
        buckets[b].append(name)
    for name in back:
        buckets[b].remove(name)
        buckets[a].append(name)
    totals[a] -= delta
    totals[b] += delta
    return True


def _gain(delta: int, totals: list[int], weights: list[int], a: int, b: int) -> int:
    """How much moving a net `delta` XP from share a to share b changes the cost.

    The real change in sum(t^2/w) is this scaled down by wa*wb, which is
    positive and so cannot flip the sign; working in the scaled integer keeps
    the comparison exact.
    """
    shift = totals[b] * weights[a] - totals[a] * weights[b]
    return delta * (delta * (weights[a] + weights[b]) + 2 * shift)
