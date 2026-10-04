"""Metamorphic property tests for the exact detector.

These encode what must be true for ANY input, instead of hand-picked examples:
an item copied into a document is always found exactly, wherever it sits, and a
document that shares no words with the benchmark is never flagged.
"""

from __future__ import annotations

import string

import pytest
from hypothesis import given
from hypothesis import strategies as st

from contam.exact import ExactIndex, Level, Thresholds
from contam.items import BenchmarkItem

pytestmark = pytest.mark.property

# Item words use letters a-m; unrelated-document words use letters n-z, so they can
# never share a token.
ITEM_WORD = st.text(alphabet=string.ascii_lowercase[:13], min_size=2, max_size=8)
OTHER_WORD = st.text(alphabet=string.ascii_lowercase[13:], min_size=2, max_size=8)


def _build(words: list[str], n: int) -> ExactIndex:
    item = BenchmarkItem(item_id="x", benchmark="p", split="test", question=" ".join(words))
    return ExactIndex.build([item], n=n)


@given(
    words=st.lists(ITEM_WORD, min_size=4, max_size=25),
    prefix=st.lists(ITEM_WORD, max_size=15),
    suffix=st.lists(ITEM_WORD, max_size=15),
)
def test_an_embedded_item_is_always_found_exactly(
    words: list[str], prefix: list[str], suffix: list[str]
) -> None:
    index = _build(words, n=4)
    document = " ".join([*prefix, *words, *suffix])
    hits = index.scan_document("d", document)
    assert [(hit.level, hit.containment) for hit in hits] == [(Level.EXACT, 1.0)]


@given(
    words=st.lists(ITEM_WORD, min_size=4, max_size=25),
    document=st.lists(OTHER_WORD, max_size=40),
)
def test_a_document_sharing_no_tokens_is_never_flagged(
    words: list[str], document: list[str]
) -> None:
    index = _build(words, n=4)
    assert index.scan_document("d", " ".join(document)) == []


@given(words=st.lists(ITEM_WORD, min_size=4, max_size=25))
def test_containment_is_always_between_zero_and_one(words: list[str]) -> None:
    index = _build(words, n=3)
    for hit in index.scan_document("d", " ".join(words[: len(words) // 2 + 2])):
        assert 0.0 < hit.containment <= 1.0


# A tiny vocabulary forces heavy token reuse, so overlaps (and repeated n-grams) are common.
SMALL_WORD = st.text(alphabet="ab", min_size=1, max_size=2)


def _grams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


@given(
    item=st.lists(SMALL_WORD, min_size=4, max_size=10),
    document=st.lists(SMALL_WORD, max_size=30),
)
def test_containment_matches_a_brute_force_oracle(item: list[str], document: list[str]) -> None:
    """Differential test: the indexed, hashed detector must agree with plain Python sets."""
    n = 3
    expected_items = _grams(item, n)
    expected = len(expected_items & _grams(document, n)) / len(expected_items)
    index = _build(item, n=n)
    hits = index.scan_document("d", " ".join(document), Thresholds(partial=1e-9))
    if expected == 0:
        assert hits == []
    else:
        assert len(hits) == 1
        assert abs(hits[0].containment - expected) < 1e-12
