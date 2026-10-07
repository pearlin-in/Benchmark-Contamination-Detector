"""Tests for the exact n-gram containment detector (``contam.exact``)."""

from __future__ import annotations

import pytest

from contam.exact import (
    GPT3_STYLE_THRESHOLDS,
    ExactIndex,
    Level,
    ScanStats,
    Thresholds,
    best_window,
    gpt3_style_ngram_size,
)
from contam.items import BenchmarkItem, View

ARC_LIKE = BenchmarkItem(
    item_id="arc:1",
    benchmark="arc",
    split="test",
    question="Which tool would a scientist use to measure the mass of a rock?",
    choices=("a balance", "a ruler", "a thermometer", "a beaker"),
    answer="A",
)
MATH = BenchmarkItem(
    item_id="math:1",
    benchmark="math",
    split="test",
    question=(
        "Maya buys 7 notebooks at 3 dollars each and pays with a 50 dollar bill. "
        "How much change does she get?"
    ),
)
SHORT = BenchmarkItem(item_id="short:1", benchmark="s", split="test", question="What is 5 + 7?")
TOO_SHORT = BenchmarkItem(item_id="tiny:1", benchmark="s", split="test", question="Hi there")


def _item(item_id: str, question: str) -> BenchmarkItem:
    return BenchmarkItem(item_id=item_id, benchmark="t", split="test", question=question)


# ----------------------------------------------------------------------------- exact matches
def test_verbatim_item_inside_a_longer_document_is_exact() -> None:
    index = ExactIndex.build([MATH], n=5)
    doc = f"Homework help. Problem 3: {MATH.question} Show your work. Thanks!"
    (hit,) = index.scan_document("d1", doc)
    assert hit.level is Level.EXACT
    assert hit.exact
    assert hit.containment == 1.0
    assert hit.item_id == "math:1"
    assert hit.doc_id == "d1"


def test_formatting_noise_does_not_prevent_an_exact_match() -> None:
    index = ExactIndex.build([MATH], n=5)
    noisy = "  " + MATH.question.upper().replace(" ", "\u00a0\u00a0") + "\r\n"
    (hit,) = index.scan_document("d1", noisy)
    assert hit.level is Level.EXACT


def test_unrelated_document_has_no_hits() -> None:
    index = ExactIndex.build([MATH, ARC_LIKE], n=5)
    assert index.scan_document("d1", "A recipe for lemon cake with butter and sugar.") == []


def test_empty_document_has_no_hits() -> None:
    assert ExactIndex.build([MATH], n=5).scan_document("d1", "") == []


def test_question_plus_choices_view_matches_when_choices_follow_the_question() -> None:
    index = ExactIndex.build([ARC_LIKE], view=View.QUESTION_CHOICES, n=5)
    doc = ARC_LIKE.question + "\n" + "\n".join(ARC_LIKE.choices)
    (hit,) = index.scan_document("d1", doc)
    assert hit.level is Level.EXACT


def test_question_plus_choices_exactness_fails_when_options_are_labelled() -> None:
    # Real web pages write "A. a balance B. a ruler ...". The labels break contiguity, so the
    # item is no longer EXACT in this view, but containment stays high. A known, documented
    # limitation (D-002): the question-only view is the robust one for exact matching.
    index = ExactIndex.build([ARC_LIKE], view=View.QUESTION_CHOICES, n=3)
    labelled = ARC_LIKE.question + " A. a balance B. a ruler C. a thermometer D. a beaker"
    (hit,) = index.scan_document("d1", labelled)
    assert not hit.exact
    assert hit.containment > 0.5


# ----------------------------------------------------------------------------- partial matches
def test_half_of_an_item_is_a_partial_hit() -> None:
    item = _item("p:1", "one two three four five six seven eight nine ten")
    index = ExactIndex.build([item], n=3)  # 8 windows
    (hit,) = index.scan_document("d1", "one two three four five six")  # 4 windows
    assert hit.level is Level.PARTIAL
    assert hit.matched_ngrams == 4
    assert hit.total_ngrams == 8
    assert hit.containment == 0.5


def test_one_changed_final_word_is_a_near_duplicate_not_exact() -> None:
    item = _item("n:1", "one two three four five six seven eight nine ten")
    index = ExactIndex.build([item], n=3)
    (hit,) = index.scan_document("d1", "one two three four five six seven eight nine ELEVEN")
    assert hit.level is Level.NEAR_DUPLICATE
    assert not hit.exact
    assert hit.containment == 7 / 8


def test_overlap_below_the_partial_threshold_is_not_reported() -> None:
    item = _item("p:2", "one two three four five six seven eight nine ten")
    index = ExactIndex.build([item], n=3)
    assert index.scan_document("d1", "one two three four") == []  # 2 of 8 windows


def test_custom_thresholds_change_the_level() -> None:
    item = _item("p:3", "one two three four five six seven eight nine ten")
    index = ExactIndex.build([item], n=3)
    doc = "one two three four five six"  # containment 0.5
    strict = index.scan_document("d1", doc, Thresholds(partial=0.6, near_duplicate=0.9))
    assert strict == []


# ----------------------------------------------------------------------------- short items
def test_short_item_is_matched_as_a_whole_and_tagged() -> None:
    index = ExactIndex.build([SHORT], n=8, min_tokens=4)
    (hit,) = index.scan_document("d1", "Quick quiz: what is 5 + 7? Answer below.")
    assert hit.short
    assert hit.level is Level.EXACT
    assert hit.ngram_size == 5


def test_items_below_min_tokens_are_skipped_and_reported() -> None:
    index = ExactIndex.build([TOO_SHORT, MATH], n=5, min_tokens=4)
    assert [(s.item_id, s.reason) for s in index.skipped] == [("tiny:1", "too_short")]
    assert index.indexed_items == 1


def test_long_items_are_not_tagged_short() -> None:
    index = ExactIndex.build([MATH], n=5)
    (hit,) = index.scan_document("d1", MATH.question)
    assert not hit.short


# ----------------------------------------------------------------------------- stop n-grams
TEMPLATE_A = _item("a", "which of the following is a mammal bat whale")
TEMPLATE_B = _item("b", "which of the following is a metal iron copper")
TEMPLATE_DOC = "which of the following is a"


def test_shared_template_ngrams_cause_hits_without_stop_filtering() -> None:
    index = ExactIndex.build([TEMPLATE_A, TEMPLATE_B], n=3)
    assert {hit.item_id for hit in index.scan_document("d1", TEMPLATE_DOC)} == {"a", "b"}


def test_stop_ngram_filter_removes_template_only_matches() -> None:
    index = ExactIndex.build([TEMPLATE_A, TEMPLATE_B], n=3, stop_ngram_k=2)
    assert index.scan_document("d1", TEMPLATE_DOC) == []


def test_stop_ngram_filter_still_finds_genuine_items() -> None:
    index = ExactIndex.build([TEMPLATE_A, TEMPLATE_B], n=3, stop_ngram_k=2)
    (hit,) = index.scan_document("d1", "xx which of the following is a mammal bat whale yy")
    assert hit.item_id == "a"
    assert hit.level is Level.EXACT


def test_item_made_only_of_stop_ngrams_is_skipped_and_reported() -> None:
    twin = _item("twin", "which of the following is a mammal bat whale")  # same text as "a"
    other = _item("c", "which of the following is a mammal bat whale extra words here")
    index = ExactIndex.build([twin, other], n=3, stop_ngram_k=2)
    reasons = {s.item_id: s.reason for s in index.skipped}
    assert reasons == {"twin": "all_stop_ngrams"}


# ----------------------------------------------------------------------------- duplicates
def test_identical_items_share_one_entry_and_both_ids_are_reported() -> None:
    first = _item("dup:1", "the quick brown fox jumps over the lazy dog")
    second = _item("dup:2", "The quick brown fox jumps over the lazy dog!")
    index = ExactIndex.build([first, second], n=4)
    hits = index.scan_document("d1", "the quick brown fox jumps over the lazy dog")
    assert [hit.item_id for hit in hits] == ["dup:1", "dup:2"]
    assert index.indexed_items == 2


# ----------------------------------------------------------------------------- corpus scanning
def test_scan_corpus_streams_hits_and_fills_stats() -> None:
    index = ExactIndex.build([MATH], n=5)
    docs = [
        ("d1", "nothing relevant here at all"),
        ("d2", f"see this: {MATH.question}"),
        ("d3", None),
    ]
    stats = ScanStats()
    hits = list(index.scan_corpus(docs, stats=stats))
    assert [hit.doc_id for hit in hits] == ["d2"]
    assert stats.documents == 2
    assert stats.hits == 1
    assert stats.malformed == 1
    assert stats.tokens > 0


def test_scanning_is_deterministic() -> None:
    index = ExactIndex.build([MATH, ARC_LIKE], n=5)
    doc = MATH.question + " " + ARC_LIKE.question
    assert index.scan_document("d", doc) == index.scan_document("d", doc)


def test_introspection_properties() -> None:
    index = ExactIndex.build([MATH, SHORT], n=8, min_tokens=4)
    assert index.ngram_sizes == (5, 8)
    assert index.table_size > 0
    assert index.n == 8


# ----------------------------------------------------------------------------- configuration
def test_thresholds_classify() -> None:
    thresholds = Thresholds(partial=0.5, near_duplicate=0.8)
    assert thresholds.classify(0.1, exact=False) is Level.NONE
    assert thresholds.classify(0.5, exact=False) is Level.PARTIAL
    assert thresholds.classify(0.8, exact=False) is Level.NEAR_DUPLICATE
    assert thresholds.classify(1.0, exact=True) is Level.EXACT


@pytest.mark.parametrize(
    ("partial", "near"), [(0.0, 0.8), (0.9, 0.8), (0.5, 1.5), (-0.1, 0.8)], ids=str
)
def test_invalid_thresholds_are_rejected(partial: float, near: float) -> None:
    with pytest.raises(ValueError, match="thresholds must satisfy"):
        Thresholds(partial=partial, near_duplicate=near)


def test_build_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="n must be >= 1"):
        ExactIndex.build([MATH], n=0)
    with pytest.raises(ValueError, match="min_tokens"):
        ExactIndex.build([MATH], n=3, min_tokens=5)
    with pytest.raises(ValueError, match="stop_ngram_k"):
        ExactIndex.build([MATH], n=3, stop_ngram_k=1)


# ----------------------------------------------------------------------------- GPT-3 style rule
def test_gpt3_style_n_is_the_fifth_percentile_capped_at_13() -> None:
    assert gpt3_style_ngram_size([20] * 95 + [3] * 5) == 3
    assert gpt3_style_ngram_size([50] * 100) == 13
    assert gpt3_style_ngram_size([1, 40, 40, 40]) == 1


def test_gpt3_style_n_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        gpt3_style_ngram_size([])


def test_gpt3_style_index_flags_any_single_shared_ngram() -> None:
    index = ExactIndex.gpt3_style([MATH])
    assert index.n == 13
    # Exactly one shared 13-token window (13 of the item's 21 tokens): 1 of 9 windows,
    # far below the 0.5 default threshold but enough under the GPT-3 rule.
    doc = "and pays with a 50 dollar bill how much change does she get"
    hits = index.scan_document("d1", doc, GPT3_STYLE_THRESHOLDS)
    assert len(hits) == 1
    assert hits[0].level is Level.PARTIAL
    assert hits[0].matched_ngrams == 1
    assert index.scan_document("d1", doc) == []  # the default thresholds do not flag it


# ----------------------------------------------------------------------------- windowed mode
def test_best_window_counts_distinct_ngrams_inside_the_span() -> None:
    positions = [(0, 1), (1, 2), (50, 3), (51, 4)]
    assert best_window(positions, 5) == (2, 0)
    assert best_window(positions, 100) == (4, 0)
    assert best_window([], 5) == (0, -1)


def test_repeated_ngrams_in_a_window_count_once() -> None:
    assert best_window([(0, 7), (1, 7), (2, 7)], 10)[0] == 1


def test_windowing_ignores_overlap_scattered_across_a_long_document() -> None:
    item = _item("w:1", "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima")
    index = ExactIndex.build([item], n=3)  # 10 trigrams
    filler = " ".join(f"zz{i}" for i in range(40))
    pieces = ["alpha bravo charlie", "delta echo foxtrot", "golf hotel india", "juliet kilo lima"]
    document = f" {filler} ".join(pieces)  # each fragment contributes one trigram
    whole = index.scan_document("d", document, Thresholds(partial=0.3))
    windowed = index.scan_document("d", document, Thresholds(partial=0.3), window_slack=1.5)
    assert [hit.containment for hit in whole] == [0.4]
    assert windowed == []


def test_windowing_does_not_change_a_verbatim_hit_and_reports_where_it_is() -> None:
    index = ExactIndex.build([MATH], n=5)
    document = "intro words before " + MATH.question + " and some words after"
    plain = index.scan_document("d", document)[0]
    windowed = index.scan_document("d", document, window_slack=1.5, snippet_chars=60)[0]
    assert windowed.level is Level.EXACT
    assert windowed.containment == plain.containment == 1.0
    assert windowed.window_start == 3
    assert windowed.snippet.startswith("maya buys 7 notebooks")
    assert len(windowed.snippet) <= 60
    assert plain.snippet == ""
