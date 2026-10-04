"""Tests for ``contam.tokenizer.tokenize`` (DECISIONS.md, D-004)."""

from __future__ import annotations

import pytest

from contam.normalize import normalize
from contam.tokenizer import tokenize

CASES = [
    pytest.param("", [], id="empty"),
    pytest.param("hello world", ["hello", "world"], id="two-words"),
    pytest.param("what is 12 + 30 =", ["what", "is", "12", "+", "30", "="], id="math-symbols"),
    pytest.param("12+30=42", ["12", "+", "30", "=", "42"], id="symbols-without-spaces"),
    pytest.param("cost $5", ["cost", "$", "5"], id="currency-is-its-own-token"),
    pytest.param("caf\u00e9 au lait", ["caf\u00e9", "au", "lait"], id="accents-stay-in-word"),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_tokenize(text: str, expected: list[str]) -> None:
    assert tokenize(text) == expected


def test_spacing_around_symbols_does_not_change_tokens() -> None:
    assert tokenize("12+30") == tokenize("12 + 30")


def test_normalize_then_tokenize_pipeline() -> None:
    assert tokenize(normalize("Maya's  50-dollar bill!")) == ["maya", "s", "50", "dollar", "bill"]
