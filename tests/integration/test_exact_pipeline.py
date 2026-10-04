"""End-to-end test of the exact detector on small hand-made fixture files.

The expected results below were worked out by hand from the fixture text, so this test
checks the whole pipeline (JSONL loading, normalization, tokenization, hashing, indexing,
scanning, classification) against human-verified answers, not against the code's own output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contam.data.jsonl import read_jsonl
from contam.exact import ExactIndex, Hit, Level, ScanStats
from contam.items import BenchmarkItem, View

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

pytestmark = pytest.mark.integration


def _load_items() -> list[BenchmarkItem]:
    return [
        BenchmarkItem(
            item_id=row["item_id"],
            benchmark="mini",
            split="test",
            question=row["question"],
            choices=tuple(row["choices"]),
        )
        for row in read_jsonl(FIXTURES / "mini_benchmark.jsonl")
    ]


def _scan(n: int = 6) -> tuple[ExactIndex, dict[tuple[str, str], Hit], ScanStats]:
    index = ExactIndex.build(_load_items(), view=View.QUESTION, n=n, min_tokens=4)
    docs = [(row["id"], row["text"]) for row in read_jsonl(FIXTURES / "mini_corpus.jsonl")]
    stats = ScanStats()
    hits = {(hit.doc_id, hit.item_id): hit for hit in index.scan_corpus(docs, stats=stats)}
    return index, hits, stats


def test_tiny_item_is_skipped_and_reported() -> None:
    index, _, _ = _scan()
    assert [(s.item_id, s.reason) for s in index.skipped] == [("mini:tiny", "too_short")]


def test_verbatim_copy_in_a_forum_post_is_exact() -> None:
    _, hits, _ = _scan()
    assert hits[("doc-exact", "mini:math")].level is Level.EXACT


def test_heavily_reformatted_copy_is_still_exact_after_normalization() -> None:
    _, hits, _ = _scan()
    assert hits[("doc-noisy", "mini:math")].level is Level.EXACT


def test_reworded_ending_is_a_near_duplicate_and_not_exact() -> None:
    _, hits, _ = _scan()
    hit = hits[("doc-near", "mini:math")]
    assert hit.level is Level.NEAR_DUPLICATE
    assert not hit.exact
    assert hit.containment >= 0.8


def test_short_item_is_found_exactly_and_tagged_short() -> None:
    _, hits, _ = _scan()
    hit = hits[("doc-short", "mini:short")]
    assert hit.level is Level.EXACT
    assert hit.short


def test_clean_and_empty_documents_produce_no_hits() -> None:
    _, hits, _ = _scan()
    assert not [key for key in hits if key[0] in {"doc-clean", "doc-empty"}]


def test_clean_benchmark_item_is_never_flagged() -> None:
    _, hits, _ = _scan()
    assert not [key for key in hits if key[1] == "mini:clean"]


def test_every_document_was_scanned() -> None:
    _, _, stats = _scan()
    assert stats.documents == 7
    assert stats.malformed == 0
