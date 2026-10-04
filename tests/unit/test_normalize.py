"""Contract tests for ``contam.normalize.normalize``, written before the code.

Run them now and they FAIL. That is the point: red first, then make them green.

Every expectation is a decision, not an accident. Cases tagged ``[D-003]`` are judgement
calls: if you change one, record why in ``docs/DECISIONS.md`` (entry D-003).
"""

from __future__ import annotations

from typing import Any

import pytest

from contam.normalize import normalize

# --------------------------------------------------------------------------- #
# Basic behaviour
# --------------------------------------------------------------------------- #
BASIC_CASES = [
    pytest.param("Hello WORLD", "hello world", id="lowercases"),
    pytest.param("  leading and trailing  ", "leading and trailing", id="strips-ends"),
    pytest.param("a   b", "a b", id="collapses-spaces"),
    pytest.param("a\n\tb\r\nc", "a b c", id="newlines-and-tabs-become-spaces"),
    pytest.param("", "", id="empty-string"),
    pytest.param("   \n\t ", "", id="whitespace-only"),
    pytest.param("!!! ... ???", "", id="punctuation-only"),
    pytest.param("Janet has 16 eggs.", "janet has 16 eggs", id="keeps-digits"),
]


@pytest.mark.parametrize(("raw", "expected"), BASIC_CASES)
def test_basic_behaviour(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


# --------------------------------------------------------------------------- #
# Punctuation and symbols  [D-003]
# --------------------------------------------------------------------------- #
PUNCTUATION_CASES = [
    pytest.param("well-known", "well known", id="hyphen-becomes-space"),
    pytest.param("a,b", "a b", id="comma-between-words-becomes-space"),
    pytest.param("don't", "don t", id="apostrophe-becomes-space"),
    pytest.param("\u201cHello,\u201d she said.", "hello she said", id="curly-quotes-removed"),
    pytest.param("1,000", "1 000", id="number-separator-becomes-space"),
    pytest.param("3.5", "3 5", id="decimal-point-becomes-space"),
    pytest.param("What is 12 + 30 = ?", "what is 12 + 30 =", id="math-symbols-kept"),
    pytest.param("Cost: $5", "cost $5", id="currency-symbol-kept"),
]


@pytest.mark.parametrize(("raw", "expected"), PUNCTUATION_CASES)
def test_punctuation_and_symbols(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_straight_and_curly_apostrophes_are_equivalent() -> None:
    assert normalize("don't") == normalize("don\u2019t")


# --------------------------------------------------------------------------- #
# Unicode handling
# --------------------------------------------------------------------------- #
UNICODE_CASES = [
    pytest.param("\uff21\uff22\uff23\uff11\uff12\uff13", "abc123", id="fullwidth-forms-fold"),
    pytest.param("\ufb01ne", "fine", id="ligature-expands"),
    pytest.param("x\u00b2", "x2", id="superscript-two-becomes-digit"),
    pytest.param("a\u00a0b", "a b", id="non-breaking-space-becomes-space"),
    pytest.param("a\u200bb\ufeffc", "abc", id="zero-width-and-bom-are-deleted"),
    pytest.param("co\u00adoperate", "cooperate", id="soft-hyphen-is-deleted"),
    pytest.param("wait\u2026", "wait", id="ellipsis-char-removed"),
    pytest.param("\u00dcn\u00efc\u00f6d\u00e9", "\u00fcn\u00efc\u00f6d\u00e9", id="accents-kept"),
    pytest.param("\u4f60\u597d\uff0c\u4e16\u754c", "\u4f60\u597d \u4e16\u754c", id="cjk-comma"),
]


@pytest.mark.parametrize(("raw", "expected"), UNICODE_CASES)
def test_unicode_handling(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_composed_and_decomposed_accents_are_equivalent() -> None:
    composed = "caf\u00e9"
    decomposed = "cafe\u0301"
    assert normalize(composed) == normalize(decomposed) == "caf\u00e9"


def test_line_ending_styles_are_equivalent() -> None:
    assert normalize("a\r\nb") == normalize("a\nb") == normalize("a b")


# --------------------------------------------------------------------------- #
# Realistic robustness: formatting noise must not change the result
# --------------------------------------------------------------------------- #
def test_formatting_noise_does_not_change_the_result() -> None:
    clean = "Janet's ducks lay 16 eggs per day."
    noisy = "  JANET\u2019S  ducks\u00a0lay 16 eggs\tper day.\r\n"
    assert normalize(noisy) == normalize(clean)


# --------------------------------------------------------------------------- #
# Invalid input
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [None, b"abc", 123, ["a"]], ids=["none", "bytes", "int", "list"])
def test_non_string_input_raises_type_error(bad: Any) -> None:
    with pytest.raises(TypeError):
        normalize(bad)
