"""Tests for near-duplicate item detection (``contam.dupes``), D-045."""

from __future__ import annotations

import pytest

from contam.dupes import find_near_duplicates, jaccard, shingle_set
from contam.items import BenchmarkItem, View
from contam.synthetic import synthetic_items

BASE = synthetic_items(30, seed=8)


def _clone(item: BenchmarkItem, new_id: str, question: str | None = None) -> BenchmarkItem:
    return BenchmarkItem(
        item_id=new_id,
        benchmark=item.benchmark,
        split=item.split,
        question=question or item.question,
        choices=item.choices,
    )


def test_exact_and_near_duplicates_are_found_and_unrelated_items_are_not() -> None:
    original = BASE[0]
    words = original.question.split()
    changed_last_word = " ".join([*words[:-1], "different"])
    copy = _clone(original, "copy", original.question.upper())
    near = _clone(original, "near", changed_last_word)
    items = [*BASE, copy, near]
    pairs = find_near_duplicates(items, jaccard_threshold=0.7)
    found = {(p.id_a, p.id_b): p.jaccard for p in pairs}
    assert found[("synthetic:0", "copy")] == 1.0
    assert found[("synthetic:0", "near")] >= 0.7
    assert all("synthetic:0" in key or "copy" in key or "near" in key for key in found)


def test_pairs_are_unique_and_sorted_by_similarity() -> None:
    items = [*BASE[:5], _clone(BASE[0], "copy")]
    pairs = find_near_duplicates(items, jaccard_threshold=0.5)
    assert [p.jaccard for p in pairs] == sorted((p.jaccard for p in pairs), reverse=True)
    assert len({(p.id_a, p.id_b) for p in pairs}) == len(pairs)


def test_cross_split_search_finds_the_overlap() -> None:
    train = [_clone(BASE[3], "train:1")]
    test = [BASE[3], BASE[4]]
    pairs = find_near_duplicates(test, train, jaccard_threshold=0.9)
    assert [(p.id_a, p.id_b) for p in pairs] == [("synthetic:3", "train:1")]


def test_nothing_is_reported_for_unrelated_items() -> None:
    assert find_near_duplicates(BASE, jaccard_threshold=0.5) == []


def test_jaccard_and_shingle_set() -> None:
    a = shingle_set(BASE[0], 3, View.QUESTION)
    assert jaccard(a, a) == 1.0
    assert jaccard(a, frozenset()) == 0.0
    assert jaccard(frozenset(), frozenset()) == 0.0


@pytest.mark.parametrize("bad", [0.0, 1.5, -1.0])
def test_invalid_threshold_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="jaccard_threshold"):
        find_near_duplicates(BASE, jaccard_threshold=bad)
