"""Tests for stable n-gram hashing (DECISIONS.md, D-006)."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from contam.ngrams import MODULUS, ngram_hash, ngram_hashes, token_hash

SENTENCE = ["the", "cat", "sat", "on", "the", "mat"]


def test_token_hash_golden_values() -> None:
    # Pinned on purpose: these must be identical on every OS and Python version.
    # If this fails, hashing changed and every stored result is invalid.
    assert token_hash("hello") == 555892909868921986
    assert token_hash("world") == 1743389483813212945


def test_token_hash_is_within_modulus() -> None:
    assert 0 <= token_hash("anything") < MODULUS


def test_token_hash_survives_lone_surrogates() -> None:
    assert isinstance(token_hash("\ud800"), int)


def test_ngram_hashes_golden_values() -> None:
    assert ngram_hashes(SENTENCE, 3) == [
        971498812578316532,
        639619269198277324,
        173413958549216393,
        936932918611407685,
    ]


def test_window_count_matches_formula() -> None:
    assert len(ngram_hashes(SENTENCE, 3)) == len(SENTENCE) - 3 + 1


def test_rolling_hash_matches_direct_definition() -> None:
    rolled = ngram_hashes(SENTENCE, 3)
    direct = [ngram_hash(SENTENCE[i : i + 3]) for i in range(len(SENTENCE) - 2)]
    assert rolled == direct


def test_repeated_ngram_has_identical_hash() -> None:
    hashes = ngram_hashes(["a", "b", "a", "b", "a", "b"], 2)
    assert hashes[0] == hashes[2] == hashes[4]
    assert hashes[1] == hashes[3]


def test_hash_is_order_sensitive() -> None:
    assert ngram_hash(["a", "b"]) != ngram_hash(["b", "a"])


def test_empty_when_fewer_tokens_than_n() -> None:
    assert ngram_hashes(["a", "b"], 3) == []
    assert ngram_hashes([], 1) == []


def test_exactly_n_tokens_gives_one_window() -> None:
    assert len(ngram_hashes(["a", "b", "c"], 3)) == 1


@pytest.mark.parametrize("bad_n", [0, -1])
def test_rejects_non_positive_n(bad_n: int) -> None:
    with pytest.raises(ValueError, match="n must be >= 1"):
        ngram_hashes(SENTENCE, bad_n)


def _hash_in_subprocess(hash_seed: str) -> str:
    code = "from contam.ngrams import ngram_hashes; print(ngram_hashes(['a','b','c','d'], 2))"
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    )
    return result.stdout.strip()


def test_hashes_are_identical_across_processes_with_different_hash_seeds() -> None:
    # Python's built-in hash() would differ between these two runs; ours must not.
    assert _hash_in_subprocess("1") == _hash_in_subprocess("2")
