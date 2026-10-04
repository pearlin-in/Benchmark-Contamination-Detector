"""Tests for deterministic dev/test splitting (D-011, D-034)."""

from __future__ import annotations

import pytest
from contam.split import split_documents, split_items, unit_interval
from contam.synthetic import synthetic_items

from contam.items import BenchmarkItem


def _ids(items: list[BenchmarkItem]) -> set[str]:
    return {item.item_id for item in items}


def test_split_is_a_partition() -> None:
    items = synthetic_items(200, seed=1)
    dev, test = split_items(items, 0.5, seed=0)
    assert _ids(dev).isdisjoint(_ids(test))
    assert _ids(dev) | _ids(test) == _ids(items)


def test_split_is_deterministic() -> None:
    items = synthetic_items(100, seed=1)
    assert split_items(items, 0.5, seed=7) == split_items(items, 0.5, seed=7)


def test_split_does_not_depend_on_item_order() -> None:
    items = synthetic_items(100, seed=1)
    dev_a, _ = split_items(items, 0.5, seed=3)
    dev_b, _ = split_items(list(reversed(items)), 0.5, seed=3)
    assert _ids(dev_a) == _ids(dev_b)


def test_different_seeds_give_different_splits() -> None:
    items = synthetic_items(100, seed=1)
    assert _ids(split_items(items, 0.5, seed=1)[0]) != _ids(split_items(items, 0.5, seed=2)[0])


def test_split_fraction_is_roughly_respected() -> None:
    dev, test = split_items(synthetic_items(1000, seed=1), 0.3, seed=0)
    assert 240 <= len(dev) <= 360
    assert len(dev) + len(test) == 1000


def test_duplicate_questions_never_straddle_the_split() -> None:
    duplicates = [
        BenchmarkItem(item_id=f"dup:{i}", benchmark="t", split="test", question="Same Question?!")
        for i in range(20)
    ]
    dev, test = split_items(duplicates, 0.5, seed=0)
    assert not dev or not test


def test_documents_are_split_by_id() -> None:
    documents = [(f"doc:{i}", "text") for i in range(200)]
    dev, test = split_documents(documents, 0.5, seed=0)
    assert {d for d, _ in dev}.isdisjoint({d for d, _ in test})
    assert len(dev) + len(test) == 200


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.2, 1.5])
def test_invalid_fraction_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="dev_fraction"):
        split_items([], bad)


def test_unit_interval_is_stable_and_in_range() -> None:
    value = unit_interval(0, "abc")
    assert 0.0 <= value < 1.0
    assert value == unit_interval(0, "abc")
