"""Offline tests for benchmark converters, corpus limiting and JSONL I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from contam.data.benchmarks import BENCHMARKS, arc_item, gsm8k_item, load_benchmark, mmlu_item
from contam.data.corpus import limit_documents
from contam.data.jsonl import read_jsonl, write_jsonl


def test_gsm8k_converter() -> None:
    item = gsm8k_item({"question": "Q?", "answer": "work #### 4"}, 7, "test")
    assert item.item_id == "gsm8k:test:7"
    assert item.question == "Q?"
    assert item.choices == ()
    assert item.answer == "work #### 4"


def test_arc_converter_uses_row_id_and_choice_text() -> None:
    row = {
        "id": "Mercury_1",
        "question": "Which?",
        "choices": {"text": ["one", "two"], "label": ["A", "B"]},
        "answerKey": "B",
    }
    item = arc_item(row, 0, "test")
    assert item.item_id == "arc_challenge:test:Mercury_1"
    assert item.choices == ("one", "two")
    assert item.answer == "B"


def test_mmlu_converter_maps_answer_index_to_letter() -> None:
    row = {"question": "Q?", "choices": ["w", "x", "y", "z"], "answer": 2}
    assert mmlu_item(row, 3, "test").answer == "C"


def test_mmlu_converter_rejects_out_of_range_answer() -> None:
    with pytest.raises(ValueError, match="out of range"):
        mmlu_item({"question": "Q?", "choices": ["w", "x"], "answer": 5}, 0, "test")


def test_unknown_benchmark_name_is_rejected_before_any_network_access() -> None:
    with pytest.raises(ValueError, match="unknown benchmark"):
        load_benchmark("not-a-benchmark")


def test_registry_contains_the_three_planned_benchmarks() -> None:
    assert set(BENCHMARKS) == {"gsm8k", "arc_challenge", "mmlu"}


def test_limit_documents_by_count() -> None:
    rows = [{"id": str(i), "text": "t"} for i in range(10)]
    assert len(list(limit_documents(rows, max_docs=3))) == 3


def test_limit_documents_by_token_budget_stops_after_budget_is_reached() -> None:
    rows = [{"id": str(i), "text": "t", "token_count": 100} for i in range(10)]
    assert [doc_id for doc_id, _ in limit_documents(rows, max_tokens=250)] == ["0", "1", "2"]


def test_limit_documents_assigns_positional_ids_when_missing() -> None:
    assert next(iter(limit_documents([{"text": "t"}]))) == ("row-0", "t")


def test_jsonl_round_trip_preserves_unicode(tmp_path: Path) -> None:
    path = tmp_path / "data.jsonl"
    records = [{"id": "1", "text": "caf\u00e9 \u4f60\u597d"}, {"id": "2", "text": "plain"}]
    assert write_jsonl(path, records) == 2
    assert list(read_jsonl(path)) == records


def test_jsonl_reports_file_and_line_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ok": 1}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.jsonl:2"):
        list(read_jsonl(path))
