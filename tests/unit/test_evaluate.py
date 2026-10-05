"""Tests for evaluation against planted ground truth (``contam.evaluate``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from contam.corrupt import DEFAULT_SPECS, Corruption, CorruptionSpec
from contam.evaluate import (
    OperatingPoint,
    SweepRow,
    evaluate_at,
    load_operating_point,
    run_sweep,
    save_operating_point,
    score_corpus,
    select_operating_point,
    summarize,
    summary_to_dict,
    write_rows_csv,
)
from contam.exact import ExactIndex, Thresholds
from contam.inject import build_planted_corpus
from contam.items import BenchmarkItem, View
from contam.synthetic import synthetic_background, synthetic_items

ITEMS = synthetic_items(80, seed=11)
BACKGROUND = synthetic_background(120, seed=11)
CORPUS = build_planted_corpus(
    ITEMS, BACKGROUND, DEFAULT_SPECS, items_per_spec=15, n_controls=60, seed=11
)
INDEX = ExactIndex.build(ITEMS, view=View.QUESTION_CHOICES, n=5)
SCORES = score_corpus(INDEX, CORPUS)


def _summary(partial: float = 0.5, near: float = 0.8):  # type: ignore[no-untyped-def]
    return summarize(CORPUS, SCORES, Thresholds(partial, near), INDEX.indexed_item_ids)


def _by_spec(summary):  # type: ignore[no-untyped-def]
    return {condition.spec: condition for condition in summary.conditions}


# ----------------------------------------------------------------- ground-truth sanity checks
def test_verbatim_copies_are_always_found_and_always_exact() -> None:
    verbatim = _by_spec(_summary())["verbatim"]
    assert verbatim.recall == 1.0
    assert verbatim.exact == verbatim.planted


def test_formatting_noise_is_invisible_to_the_detector() -> None:
    noise = _by_spec(_summary())["format_noise"]
    assert noise.recall == 1.0
    assert noise.exact == noise.planted


def test_html_wrapping_does_not_hide_an_item() -> None:
    wrapped = _by_spec(_summary())["html_wrap"]
    assert wrapped.recall == 1.0


def test_reordered_choices_are_never_exact_but_still_detected() -> None:
    shuffled = _by_spec(_summary())["choice_shuffle"]
    assert shuffled.exact == 0
    assert shuffled.recall > 0.9


def test_recall_falls_as_more_words_are_deleted() -> None:
    by_spec = _by_spec(_summary())
    light = by_spec["word_delete@0.05"]
    heavy = by_spec["word_delete@0.3"]
    assert light.recall > heavy.recall
    assert light.mean_containment > heavy.mean_containment


def test_unrelated_control_documents_are_never_flagged() -> None:
    summary = _summary()
    assert summary.control_flagged == 0
    assert summary.control_docs == 60
    assert summary.control_fpr == 0.0
    assert 0.0 < summary.control_fpr_high < 0.1


def test_no_hits_for_items_that_were_not_planted() -> None:
    assert _summary().foreign_hits == 0


# ----------------------------------------------------------------- thresholds and bookkeeping
def test_stricter_thresholds_never_increase_recall() -> None:
    loose = _by_spec(_summary(0.3, 0.8))
    strict = _by_spec(_summary(0.7, 0.9))
    for spec, condition in strict.items():
        assert condition.recall <= loose[spec].recall


def test_macro_recall_is_the_mean_over_conditions() -> None:
    summary = _summary()
    expected = sum(c.recall for c in summary.conditions) / len(summary.conditions)
    assert summary.macro_recall == pytest.approx(expected)


def test_recall_intervals_contain_the_point_estimate() -> None:
    for condition in _summary().conditions:
        assert condition.recall_low <= condition.recall <= condition.recall_high


def test_plants_of_unindexed_items_are_excluded_and_counted() -> None:
    short = BenchmarkItem(item_id="short:1", benchmark="t", split="test", question="a b")
    corpus = build_planted_corpus(
        [short, *ITEMS[:20]],
        BACKGROUND,
        (CorruptionSpec(Corruption.VERBATIM),),
        items_per_spec=50,
        n_controls=5,
        seed=1,
    )
    index = ExactIndex.build([short, *ITEMS[:20]], n=5)
    summary = summarize(
        corpus,
        score_corpus(index, corpus),
        Thresholds(),
        index.indexed_item_ids,
    )
    assert summary.unindexed == 1
    assert summary.conditions[0].planted == 20


def test_a_foreign_item_found_in_a_planted_document_is_counted() -> None:
    # Index two items but plant only the first; a document containing both text blocks
    # must report the second as a foreign hit.
    first, second = ITEMS[0], ITEMS[1]
    corpus = build_planted_corpus(
        [first],
        BACKGROUND,
        (CorruptionSpec(Corruption.VERBATIM),),
        items_per_spec=1,
        n_controls=0,
        seed=2,
    )
    doc_id, text = corpus.documents[0]
    corpus.documents[0] = (doc_id, text + "\n\n" + second.question)
    index = ExactIndex.build([first, second], view=View.QUESTION, n=5)
    summary = summarize(corpus, score_corpus(index, corpus), Thresholds(), index.indexed_item_ids)
    assert summary.foreign_hits == 1


# ----------------------------------------------------------------- sweeps and selection
def test_sweep_produces_a_row_per_setting_and_condition() -> None:
    rows = run_sweep(
        ITEMS,
        CORPUS,
        ns=(5, 8),
        views=(View.QUESTION_CHOICES,),
        partials=(0.3, 0.5),
        near_duplicates=(0.8,),
    )
    assert len(rows) == 2 * 1 * 2 * 1 * len(DEFAULT_SPECS)
    assert {row.n for row in rows} == {5, 8}


def test_sweep_skips_threshold_pairs_where_partial_exceeds_near() -> None:
    rows = run_sweep(
        ITEMS,
        CORPUS,
        ns=(5,),
        views=(View.QUESTION,),
        partials=(0.9,),
        near_duplicates=(0.8,),
    )
    assert rows == []


def _row(
    n: int, partial: float, recall: float, fpr_high: float, view: str = "question_choices"
) -> SweepRow:
    return SweepRow(
        n=n,
        stop_ngram_k=None,
        view=view,
        partial=partial,
        near_duplicate=0.9,
        spec="verbatim",
        kind="verbatim",
        intensity=None,
        planted=10,
        detected=int(recall * 10),
        exact=0,
        recall=recall,
        recall_low=0.0,
        recall_high=1.0,
        mean_containment=recall,
        control_docs=100,
        control_flagged=0,
        control_fpr=0.0,
        control_fpr_low=0.0,
        control_fpr_high=fpr_high,
        foreign_hits=0,
        unindexed=0,
    )


def test_selection_maximizes_recall_within_the_false_positive_bound() -> None:
    rows = [_row(5, 0.3, 0.95, 0.20), _row(8, 0.5, 0.80, 0.01), _row(13, 0.7, 0.60, 0.01)]
    point = select_operating_point(rows, view=View.QUESTION_CHOICES, max_control_fpr_upper=0.05)
    assert (point.n, point.partial) == (8, 0.5)


def test_selection_breaks_ties_toward_stricter_thresholds_then_larger_n() -> None:
    rows = [_row(5, 0.3, 0.9, 0.01), _row(8, 0.3, 0.9, 0.01), _row(8, 0.5, 0.9, 0.01)]
    point = select_operating_point(rows, view=View.QUESTION_CHOICES)
    assert (point.n, point.partial) == (8, 0.5)


def test_selection_only_considers_the_requested_view() -> None:
    rows = [_row(5, 0.3, 0.99, 0.01, view="question"), _row(8, 0.5, 0.5, 0.01)]
    assert select_operating_point(rows, view=View.QUESTION_CHOICES).n == 8


def test_selection_fails_loudly_when_no_setting_is_safe_enough() -> None:
    with pytest.raises(ValueError, match="no setting keeps"):
        select_operating_point([_row(5, 0.3, 0.9, 0.5)], view=View.QUESTION_CHOICES)


def test_evaluate_at_matches_summarize_for_the_same_settings() -> None:
    point = OperatingPoint(5, None, "question_choices", 0.5, 0.8, 0.0, 0.0)
    assert evaluate_at(ITEMS, CORPUS, point).conditions == _summary(0.5, 0.8).conditions


# ----------------------------------------------------------------- files
def test_operating_point_round_trip(tmp_path: Path) -> None:
    point = OperatingPoint(8, 5, "question", 0.5, 0.9, 0.87, 0.02)
    path = tmp_path / "point.json"
    save_operating_point(path, point, context={"selected_on": "dev", "seed": 3})
    assert load_operating_point(path) == point


def test_csv_has_a_header_and_one_line_per_row(tmp_path: Path) -> None:
    rows = [_row(5, 0.3, 0.9, 0.01), _row(8, 0.5, 0.8, 0.01)]
    path = tmp_path / "rows.csv"
    assert write_rows_csv(path, rows) == 2
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("n,stop_ngram_k,view,partial")


def test_summary_dict_is_json_serializable() -> None:
    import json

    assert json.dumps(summary_to_dict(_summary()))
