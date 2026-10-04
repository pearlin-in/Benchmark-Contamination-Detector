"""Tests for planted-corpus construction and its manifest (contam.inject), D-036."""

from __future__ import annotations

from pathlib import Path

import pytest
from contam.corrupt import Corruption, CorruptionSpec
from contam.synthetic import synthetic_background, synthetic_items

from contam.inject import (
    build_planted_corpus,
    read_manifest,
    text_digest,
    verify_plants,
    write_manifest,
)
from contam.items import BenchmarkItem

ITEMS = synthetic_items(60, seed=5)
BACKGROUND = synthetic_background(40, seed=5)
SPECS = (
    CorruptionSpec(Corruption.VERBATIM),
    CorruptionSpec(Corruption.WORD_DELETE, 0.1),
    CorruptionSpec(Corruption.CHOICE_SHUFFLE),
)


def _build(**overrides):  # type: ignore[no-untyped-def]
    options = {"specs": SPECS, "items_per_spec": 10, "n_controls": 8, "seed": 5}
    options.update(overrides)
    return build_planted_corpus(ITEMS, BACKGROUND, **options)


def test_builds_the_requested_number_of_plants_and_controls() -> None:
    corpus = _build()
    assert len(corpus.plants) == 30
    assert len(corpus.control_doc_ids) == 8
    assert len(corpus.documents) == 38


def test_every_plant_is_exactly_where_the_manifest_says() -> None:
    assert verify_plants(_build()) == []


def test_verify_detects_a_tampered_document() -> None:
    corpus = _build()
    doc_id, text = corpus.documents[0]
    corpus.documents[0] = (doc_id, text.replace(text[corpus.plants[0].offset], "#", 1))
    assert verify_plants(corpus)


def test_construction_is_deterministic() -> None:
    assert _build().documents == _build().documents


def test_different_seeds_give_different_corpora() -> None:
    assert _build(seed=1).documents != _build(seed=2).documents


def test_adding_a_spec_does_not_change_other_records() -> None:
    small = _build(specs=SPECS[:1])
    larger = _build(specs=SPECS)
    first_spec_docs = [pair for pair in larger.documents if pair[0].startswith("plant:verbatim:")]
    assert [pair for pair in small.documents if pair[0].startswith("plant:")] == first_spec_docs


def test_documents_ids_are_unique() -> None:
    ids = [doc_id for doc_id, _ in _build().documents]
    assert len(ids) == len(set(ids))


def test_controls_are_unmodified_background_text() -> None:
    corpus = _build()
    background_texts = {text for _, text in BACKGROUND}
    for control_id in corpus.control_doc_ids:
        assert corpus.text_of(control_id) in background_texts


def test_planted_text_matches_the_corruption() -> None:
    corpus = _build(specs=SPECS[:1])
    items = {item.item_id: item for item in ITEMS}
    for plant in corpus.plants:
        expected = "\n".join((items[plant.item_id].question, *items[plant.item_id].choices))
        assert text_digest(expected) == plant.digest
        assert plant.length == len(expected)


def test_inapplicable_specs_produce_a_recorded_shortfall() -> None:
    no_choices = [
        BenchmarkItem(item_id=f"n:{i}", benchmark="t", split="test", question="a b c d e f g h")
        for i in range(5)
    ]
    corpus = build_planted_corpus(
        no_choices,
        BACKGROUND,
        (CorruptionSpec(Corruption.CHOICE_SHUFFLE),),
        items_per_spec=3,
        n_controls=0,
    )
    assert corpus.plants == []
    assert corpus.shortfalls == {"choice_shuffle": 0}


def test_fewer_applicable_items_than_requested_is_reported() -> None:
    corpus = _build(items_per_spec=1000)
    assert corpus.shortfalls["verbatim"] == len(ITEMS)


def test_manifest_round_trip(tmp_path: Path) -> None:
    corpus = _build()
    path = tmp_path / "manifest.jsonl"
    assert write_manifest(path, corpus) == len(corpus.plants)
    assert read_manifest(path) == corpus.plants


def test_manifest_contains_no_text(tmp_path: Path) -> None:
    corpus = _build()
    path = tmp_path / "manifest.jsonl"
    write_manifest(path, corpus)
    content = path.read_text(encoding="utf-8")
    assert ITEMS[0].question not in content


def test_synthetic_background_is_deterministic() -> None:
    assert synthetic_background(5, seed=9) == synthetic_background(5, seed=9)
    assert synthetic_background(5, seed=9) != synthetic_background(5, seed=10)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"items_per_spec": 0}, "items_per_spec"),
        ({"n_controls": -1}, "n_controls"),
    ],
)
def test_invalid_parameters_are_rejected(overrides: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _build(**overrides)


def test_empty_inputs_and_duplicates_are_rejected() -> None:
    with pytest.raises(ValueError, match="no items"):
        build_planted_corpus([], BACKGROUND)
    with pytest.raises(ValueError, match="no usable documents"):
        build_planted_corpus(ITEMS, [("x", "   ")])
    with pytest.raises(ValueError, match="unique"):
        build_planted_corpus([ITEMS[0], ITEMS[0]], BACKGROUND)
    with pytest.raises(ValueError, match="labels must be unique"):
        build_planted_corpus(ITEMS, BACKGROUND, (SPECS[0], SPECS[0]))
