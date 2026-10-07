"""Tests for the checkpointed scanner and the report (``contam.scan``, ``contam.report``)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from contam.corrupt import Corruption, CorruptionSpec
from contam.data.jsonl import read_jsonl
from contam.inject import build_planted_corpus
from contam.items import View
from contam.report import build_report, format_report
from contam.scan import ScanConfig, ScanError, run_scan
from contam.synthetic import synthetic_background, synthetic_items

ITEMS = synthetic_items(30, seed=12)
CORPUS = build_planted_corpus(
    ITEMS,
    synthetic_background(30, seed=12),
    (CorruptionSpec(Corruption.VERBATIM), CorruptionSpec(Corruption.WORD_DELETE, 0.1)),
    items_per_spec=8,
    n_controls=20,
    seed=12,
)
DOCS = CORPUS.documents
CONFIG = ScanConfig(
    n=3, view=View.QUESTION, partial=0.5, near_duplicate=0.9, batch_docs=7, source="test"
)


def _hits(folder: Path) -> list[dict[str, object]]:
    return list(read_jsonl(folder / "hits.jsonl"))


def _crashing(after: int):  # type: ignore[no-untyped-def]
    def factory():  # type: ignore[no-untyped-def]
        for index, document in enumerate(DOCS):
            if index == after:
                raise RuntimeError("simulated crash")
            yield document

    return factory


def test_every_verbatim_plant_is_found_and_no_control_is_flagged(tmp_path: Path) -> None:
    result = run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path)
    found = {(hit["doc_id"], hit["item_id"]) for hit in _hits(tmp_path)}
    verbatim = {(p.doc_id, p.item_id) for p in CORPUS.plants if p.spec == "verbatim"}
    assert verbatim <= found
    assert not {doc for doc, _ in found} & set(CORPUS.control_doc_ids)
    assert result.docs == len(DOCS)
    assert result.hits == len(_hits(tmp_path))
    assert result.finished


def test_hits_carry_a_short_snippet_of_the_matching_text(tmp_path: Path) -> None:
    run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path)
    for hit in _hits(tmp_path):
        assert 0 < len(str(hit["snippet"])) <= 200


def test_an_existing_scan_needs_resume_or_overwrite(tmp_path: Path) -> None:
    run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path)
    with pytest.raises(ScanError, match="checkpoint exists"):
        run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path)


def test_resuming_a_finished_scan_changes_nothing(tmp_path: Path) -> None:
    first = run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path)
    before = (tmp_path / "hits.jsonl").read_bytes()
    again = run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path, resume=True)
    assert again.docs == first.docs
    assert (tmp_path / "hits.jsonl").read_bytes() == before


def test_overwrite_reproduces_the_same_output(tmp_path: Path) -> None:
    run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path)
    before = (tmp_path / "hits.jsonl").read_bytes()
    run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path, overwrite=True)
    assert (tmp_path / "hits.jsonl").read_bytes() == before


def test_crash_and_resume_gives_byte_identical_output(tmp_path: Path) -> None:
    crashed, clean = tmp_path / "crashed", tmp_path / "clean"
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_scan(ITEMS, _crashing(25), CONFIG, crashed)
    checkpoint = json.loads((crashed / "checkpoint.json").read_text(encoding="utf-8"))
    assert 0 < checkpoint["docs_done"] < len(DOCS)
    assert not checkpoint["finished"]
    resumed = run_scan(ITEMS, lambda: DOCS, CONFIG, crashed, resume=True)
    run_scan(ITEMS, lambda: DOCS, CONFIG, clean)
    assert resumed.resumed_from_docs == checkpoint["docs_done"]
    assert (crashed / "hits.jsonl").read_bytes() == (clean / "hits.jsonl").read_bytes()


def test_resume_discards_a_half_written_tail(tmp_path: Path) -> None:
    crashed, clean = tmp_path / "crashed", tmp_path / "clean"
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_scan(ITEMS, _crashing(25), CONFIG, crashed)
    with (crashed / "hits.jsonl").open("ab") as handle:
        handle.write(b'{"half written batch": tr')
    run_scan(ITEMS, lambda: DOCS, CONFIG, crashed, resume=True)
    run_scan(ITEMS, lambda: DOCS, CONFIG, clean)
    assert (crashed / "hits.jsonl").read_bytes() == (clean / "hits.jsonl").read_bytes()


def test_resume_refuses_different_settings(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_scan(ITEMS, _crashing(25), CONFIG, tmp_path)
    with pytest.raises(ScanError, match="different settings"):
        run_scan(ITEMS, lambda: DOCS, replace(CONFIG, n=4), tmp_path, resume=True)


def test_modified_hits_file_is_detected(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_scan(ITEMS, _crashing(25), CONFIG, tmp_path)
    (tmp_path / "hits.jsonl").write_bytes(b"")
    with pytest.raises(ScanError, match="shorter than the checkpoint"):
        run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path, resume=True)


def test_malformed_documents_are_counted_not_fatal(tmp_path: Path) -> None:
    docs = [("bad", None), *DOCS[:10]]
    result = run_scan(ITEMS, lambda: docs, CONFIG, tmp_path)
    assert result.malformed == 1
    assert result.docs == 11


def test_two_workers_give_the_same_output_as_one(tmp_path: Path) -> None:
    run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path / "one")
    run_scan(ITEMS, lambda: DOCS, replace(CONFIG, workers=2), tmp_path / "two")
    assert (tmp_path / "one" / "hits.jsonl").read_bytes() == (
        tmp_path / "two" / "hits.jsonl"
    ).read_bytes()


def test_invalid_settings_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="batch_docs and workers"):
        run_scan(ITEMS, lambda: DOCS, replace(CONFIG, batch_docs=0), tmp_path)


def test_report_counts_items_once_at_their_strongest_level(tmp_path: Path) -> None:
    run_scan(ITEMS, lambda: DOCS, CONFIG, tmp_path)
    report = build_report(tmp_path)
    (row,) = report.rows
    assert row.benchmark == "synthetic"
    assert row.items == 30
    assert row.exact >= 8
    assert row.exact <= row.near_or_more <= row.partial_or_more <= row.indexed
    text = format_report(report)
    assert "synthetic" in text
    assert "lower bounds" in text
