"""Property-based tests for ``contam.normalize.normalize``.

Instead of hand-picking examples, Hypothesis generates thousands of strings (including
strange Unicode) and checks that universal rules always hold.

A heads-up: if ``test_is_idempotent`` fails with a strange character, that is a real
finding, not a flaky test. Lowercasing or removing characters can leave text that
NFKC would change again. Read the shrunk counterexample Hypothesis prints, and fix the
order of steps in ``normalize`` (see the contract in its docstring).
"""

from __future__ import annotations

import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st

from contam.normalize import normalize

pytestmark = pytest.mark.property


@given(st.text())
def test_is_idempotent(s: str) -> None:
    once = normalize(s)
    assert normalize(once) == once


@given(st.text())
def test_output_has_canonical_whitespace(s: str) -> None:
    out = normalize(s)
    assert out == " ".join(out.split())


@given(st.text())
def test_output_has_no_punctuation_or_format_characters(s: str) -> None:
    for ch in normalize(s):
        category = unicodedata.category(ch)
        assert not category.startswith("P"), f"punctuation {ch!r} survived"
        assert category != "Cf", f"format character {ch!r} survived"


@given(st.text())
def test_surrounding_whitespace_is_irrelevant(s: str) -> None:
    assert normalize(f"  \n{s}\t ") == normalize(s)
