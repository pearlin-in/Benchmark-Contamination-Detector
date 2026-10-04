"""Property-based tests for rolling n-gram hashing."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from contam.ngrams import ngram_hash, ngram_hashes

pytestmark = pytest.mark.property

TOKENS = st.lists(st.text(min_size=1, max_size=6), max_size=40)


@given(tokens=TOKENS, n=st.integers(min_value=1, max_value=8))
def test_rolling_hash_equals_direct_hash_of_every_window(tokens: list[str], n: int) -> None:
    expected = [ngram_hash(tokens[i : i + n]) for i in range(max(0, len(tokens) - n + 1))]
    assert ngram_hashes(tokens, n) == expected


@given(tokens=TOKENS, n=st.integers(min_value=1, max_value=8))
def test_window_count_is_len_minus_n_plus_one(tokens: list[str], n: int) -> None:
    assert len(ngram_hashes(tokens, n)) == max(0, len(tokens) - n + 1)
