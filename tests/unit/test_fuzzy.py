"""Tests for windowed fuzzy matching and the detector comparison (D-041, D-044)."""

from __future__ import annotations

import pytest

from contam.compare import compare_methods
from contam.corrupt import Corruption, CorruptionSpec, apply_corruption
from contam.fuzzy import FuzzyIndex, window_size
from contam.inject import build_planted_corpus
from contam.items import BenchmarkItem
from contam.synthetic import make_rng, synthetic_background, synthetic_items

ITEMS = synthetic_items(40, seed=6)
BACKGROUND = synthetic_background(40, seed=6)
INDEX = FuzzyIndex.build(ITEMS, k=3)


def _doc_with(text: str) -> str:
    return BACKGROUND[0][1] + "\n\n" + text + "\n\n" + BACKGROUND[1][1]


def test_verbatim_item_inside_a_document_is_found_with_full_containment() -> None:
    item = ITEMS[0]
    hits = INDEX.scan_document("d", _doc_with(item.question))
    assert [(hit.item_id, hit.containment) for hit in hits] == [(item.item_id, 1.0)]


def test_a_lightly_edited_item_is_still_found() -> None:
    item = ITEMS[1]
    spec = CorruptionSpec(Corruption.WORD_DELETE, 0.1)
    edited = apply_corruption(item, spec, make_rng(0, "t"))
    assert edited is not None
    hits = INDEX.scan_document("d", _doc_with(edited))
    assert [hit.item_id for hit in hits] == [item.item_id]
    assert hits[0].containment >= 0.3


def test_unrelated_documents_produce_no_hits() -> None:
    for doc_id, text in BACKGROUND[:10]:
        assert INDEX.scan_document(doc_id, text) == []


def test_scan_corpus_skips_malformed_documents() -> None:
    docs: list[tuple[str, object]] = [("a", None), ("b", _doc_with(ITEMS[2].question))]
    assert [hit.doc_id for hit in INDEX.scan_corpus(docs)] == ["b"]


def test_short_items_are_skipped_and_reported() -> None:
    short = BenchmarkItem(item_id="s", benchmark="t", split="test", question="too short here")
    index = FuzzyIndex.build([short, ITEMS[0]], k=3)
    assert [(s.item_id, s.reason) for s in index.skipped] == [("s", "too_short")]
    assert index.indexed_item_ids == {ITEMS[0].item_id}


def test_window_sizes_follow_the_geometric_series() -> None:
    assert window_size(5) == 8
    assert window_size(9) == 11
    assert window_size(12) == 15
    assert 100 <= window_size(100) <= 130


def test_invalid_parameters_are_rejected() -> None:
    with pytest.raises(ValueError, match="k must be"):
        FuzzyIndex.build(ITEMS, k=0)
    with pytest.raises(ValueError, match="bands must divide"):
        FuzzyIndex.build(ITEMS, num_perm=64, bands=10)


def test_comparison_shows_that_smaller_n_recovers_heavily_edited_items() -> None:
    specs = (CorruptionSpec(Corruption.VERBATIM), CorruptionSpec(Corruption.WORD_DELETE, 0.3))
    corpus = build_planted_corpus(
        ITEMS, BACKGROUND, specs, items_per_spec=12, n_controls=15, seed=6
    )
    rows = compare_methods(ITEMS, corpus, exact_ns=(2, 5), fuzzy_ks=(2,))
    recall = {(row.method, row.spec): row.recall for row in rows}
    assert {row.method for row in rows} == {"exact n=2", "exact n=5", "fuzzy k=2"}
    for method in ("exact n=2", "exact n=5", "fuzzy k=2"):
        assert recall[(method, "verbatim")] == 1.0
    assert recall[("exact n=2", "word_delete@0.3")] > recall[("exact n=5", "word_delete@0.3")]
    assert all(row.control_flagged == 0 for row in rows)
