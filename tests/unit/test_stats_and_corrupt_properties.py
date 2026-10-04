"""Property-based tests for the statistics helper and the corruption generators."""

from __future__ import annotations

import string

import pytest
from contam.corrupt import DEFAULT_SPECS, Corruption, CorruptionSpec, apply_corruption, render
from contam.stats import wilson_interval
from contam.synthetic import make_rng
from hypothesis import given
from hypothesis import strategies as st

from contam.items import BenchmarkItem
from contam.normalize import normalize

pytestmark = pytest.mark.property

WORD = st.text(alphabet=string.ascii_letters + string.digits + "'-.,", min_size=1, max_size=8)


def _item(words: list[str], choices: list[str]) -> BenchmarkItem:
    return BenchmarkItem(
        item_id="p:1",
        benchmark="p",
        split="test",
        question=" ".join(words),
        choices=tuple(choices),
    )


@given(
    total=st.integers(min_value=1, max_value=500), data=st.integers(min_value=0, max_value=10**6)
)
def test_wilson_interval_is_ordered_and_inside_zero_one(total: int, data: int) -> None:
    successes = data % (total + 1)
    low, high = wilson_interval(successes, total)
    assert 0.0 <= low <= successes / total <= high <= 1.0


@given(
    words=st.lists(WORD, min_size=1, max_size=20),
    choices=st.lists(WORD, max_size=4),
    seed=st.integers(min_value=0, max_value=1000),
)
def test_format_noise_never_changes_the_normalized_text(
    words: list[str], choices: list[str], seed: int
) -> None:
    item = _item(words, choices)
    spec = CorruptionSpec(Corruption.FORMAT_NOISE)
    noisy = apply_corruption(item, spec, make_rng(seed, "n"))
    assert noisy is not None
    assert normalize(noisy) == normalize(render(item))


@given(
    words=st.lists(WORD, min_size=1, max_size=20),
    choices=st.lists(WORD, max_size=4),
    seed=st.integers(min_value=0, max_value=1000),
)
def test_no_default_corruption_ever_crashes_or_returns_blank_text(
    words: list[str], choices: list[str], seed: int
) -> None:
    item = _item(words, choices)
    for spec in DEFAULT_SPECS:
        result = apply_corruption(item, spec, make_rng(seed, spec.label))
        assert result is None or result.strip() != ""
