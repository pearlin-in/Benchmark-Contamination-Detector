"""Tests for the corruption generators (contam.corrupt), D-013."""

from __future__ import annotations

import re
import unicodedata

import pytest
from contam.corrupt import (
    DEFAULT_SPECS,
    Corruption,
    CorruptionSpec,
    apply_corruption,
    render,
)
from contam.synthetic import make_rng

from contam.items import BenchmarkItem
from contam.normalize import normalize

MCQ = BenchmarkItem(
    item_id="c:1",
    benchmark="t",
    split="test",
    question="Maya's class has 24 students and 3 teachers, which is well-known!",
    choices=("red", "green", "blue", "gold"),
    answer="A",
)

PLAIN = BenchmarkItem(
    item_id="c:2",
    benchmark="t",
    split="test",
    question="One two three four five six seven eight nine ten",
)


def _apply(item: BenchmarkItem, kind: Corruption, intensity: float | None = None, seed: int = 0):
    spec = CorruptionSpec(kind, intensity)
    return apply_corruption(item, spec, make_rng(seed, spec.label, item.item_id))


def test_verbatim_is_the_plain_rendering() -> None:
    assert _apply(MCQ, Corruption.VERBATIM) == render(MCQ)
    assert render(MCQ).splitlines()[1:] == ["red", "green", "blue", "gold"]


def test_same_seed_gives_the_same_text_and_different_seeds_differ() -> None:
    first = _apply(MCQ, Corruption.WORD_SUBSTITUTE, 0.5, seed=1)
    assert first == _apply(MCQ, Corruption.WORD_SUBSTITUTE, 0.5, seed=1)
    assert first != _apply(MCQ, Corruption.WORD_SUBSTITUTE, 0.5, seed=2)


def test_format_noise_is_erased_by_normalization() -> None:
    for seed in range(20):
        noisy = _apply(MCQ, Corruption.FORMAT_NOISE, seed=seed)
        assert noisy is not None
        assert normalize(noisy) == normalize(render(MCQ))


def test_punct_delete_removes_every_punctuation_mark() -> None:
    result = _apply(MCQ, Corruption.PUNCT_DELETE)
    assert result is not None
    assert not any(unicodedata.category(ch).startswith("P") for ch in result)
    assert "wellknown" in result
    assert "Mayas" in result


def test_punct_delete_does_not_apply_without_punctuation() -> None:
    assert _apply(PLAIN, Corruption.PUNCT_DELETE) is None


def test_choice_shuffle_keeps_the_same_choices_in_a_different_order() -> None:
    result = _apply(MCQ, Corruption.CHOICE_SHUFFLE)
    assert result is not None
    lines = result.splitlines()
    assert lines[0] == MCQ.question
    assert sorted(lines[1:]) == sorted(MCQ.choices)
    assert tuple(lines[1:]) != MCQ.choices


@pytest.mark.parametrize(
    "kind", [Corruption.CHOICE_SHUFFLE, Corruption.LABELLED_DOT, Corruption.LABELLED_PAREN]
)
def test_choice_corruptions_do_not_apply_to_items_without_choices(kind: Corruption) -> None:
    assert _apply(PLAIN, kind) is None


def test_labelled_formats() -> None:
    dot = _apply(MCQ, Corruption.LABELLED_DOT)
    paren = _apply(MCQ, Corruption.LABELLED_PAREN)
    assert dot is not None
    assert paren is not None
    assert dot.splitlines()[1:] == ["A. red", "B. green", "C. blue", "D. gold"]
    assert paren.splitlines()[1:] == ["(A) red", "(B) green", "(C) blue", "(D) gold"]


def test_number_change_changes_numbers_and_nothing_else() -> None:
    result = _apply(MCQ, Corruption.NUMBER_CHANGE)
    assert result is not None
    assert re.sub(r"\d+", "#", result) == re.sub(r"\d+", "#", render(MCQ))
    assert re.findall(r"\d+", result) != re.findall(r"\d+", render(MCQ))


def test_number_change_does_not_apply_without_numbers() -> None:
    assert _apply(PLAIN, Corruption.NUMBER_CHANGE) is None


def test_word_delete_with_rate_zero_is_the_identity() -> None:
    assert _apply(PLAIN, Corruption.WORD_DELETE, 0.0) == render(PLAIN)


def test_word_delete_with_rate_one_keeps_exactly_one_word() -> None:
    result = _apply(PLAIN, Corruption.WORD_DELETE, 1.0)
    assert result is not None
    assert result.split() == ["One"]


def test_word_delete_removes_roughly_the_requested_share() -> None:
    long_item = BenchmarkItem(
        item_id="c:3", benchmark="t", split="test", question=" ".join(["word"] * 400)
    )
    result = _apply(long_item, Corruption.WORD_DELETE, 0.25)
    assert result is not None
    assert 250 <= len(result.split()) <= 350


def test_word_substitute_preserves_the_word_count() -> None:
    result = _apply(PLAIN, Corruption.WORD_SUBSTITUTE, 1.0)
    assert result is not None
    assert len(result.split()) == len(render(PLAIN).split())
    assert not set(result.split()) & set(render(PLAIN).split())


def test_truncate_keeps_a_prefix() -> None:
    result = _apply(PLAIN, Corruption.TRUNCATE, 0.6)
    assert result == "One two three four five six"


def test_truncate_keeps_at_least_one_word() -> None:
    assert _apply(PLAIN, Corruption.TRUNCATE, 0.0) == "One"


def test_html_wrap_contains_the_full_item_text() -> None:
    result = _apply(MCQ, Corruption.HTML_WRAP)
    assert result is not None
    assert render(MCQ) in result
    assert "<" in result


def test_html_split_inserts_the_requested_number_of_breaks() -> None:
    result = _apply(PLAIN, Corruption.HTML_SPLIT, 3)
    assert result is not None
    assert result.count("<br />") == 3
    assert result.replace("\n<br />\n", " ").split() == render(PLAIN).split()


def test_html_split_does_not_apply_to_single_word_items() -> None:
    single = BenchmarkItem(item_id="c:4", benchmark="t", split="test", question="Word")
    assert _apply(single, Corruption.HTML_SPLIT, 1) is None


def test_every_default_spec_applies_to_a_rich_item() -> None:
    for spec in DEFAULT_SPECS:
        assert apply_corruption(MCQ, spec, make_rng(0, spec.label)) is not None, spec.label


def test_default_spec_labels_are_unique() -> None:
    labels = [spec.label for spec in DEFAULT_SPECS]
    assert len(labels) == len(set(labels))


@pytest.mark.parametrize(
    ("kind", "intensity"),
    [
        (Corruption.WORD_DELETE, None),
        (Corruption.TRUNCATE, None),
        (Corruption.WORD_DELETE, 1.5),
        (Corruption.HTML_SPLIT, 0.5),
        (Corruption.HTML_SPLIT, 2.5),
    ],
)
def test_invalid_specs_are_rejected(kind: Corruption, intensity: float | None) -> None:
    with pytest.raises(ValueError, match=r"intensity|requires"):
        CorruptionSpec(kind, intensity)


def test_spec_labels() -> None:
    assert CorruptionSpec(Corruption.VERBATIM).label == "verbatim"
    assert CorruptionSpec(Corruption.WORD_DELETE, 0.1).label == "word_delete@0.1"
    assert CorruptionSpec(Corruption.HTML_SPLIT, 3).label == "html_split@3"
