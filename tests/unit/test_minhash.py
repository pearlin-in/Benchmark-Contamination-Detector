"""Tests for MinHash and LSH banding (``contam.minhash``), D-042 and D-043."""

from __future__ import annotations

import math

import pytest

from contam.minhash import (
    LshIndex,
    MinHasher,
    best_banding,
    candidate_probability,
    estimate_jaccard,
    lsh_threshold,
    merge_min,
)
from contam.ngrams import token_hash
from contam.synthetic import make_rng


def _elements(tag: str, count: int) -> set[int]:
    return {token_hash(f"{tag}:{i}") for i in range(count)}


def _pair_with_jaccard(similarity: float, size: int, tag: str) -> tuple[set[int], set[int]]:
    shared = round(2 * size * similarity / (1 + similarity))
    common = _elements(f"{tag}:common", shared)
    only_a = _elements(f"{tag}:a", size - shared)
    only_b = _elements(f"{tag}:b", size - shared)
    return common | only_a, common | only_b


def test_same_seed_gives_identical_signatures_and_different_seeds_differ() -> None:
    elements = _elements("x", 30)
    assert MinHasher(32, seed=1).signature(elements) == MinHasher(32, seed=1).signature(elements)
    assert MinHasher(32, seed=1).signature(elements) != MinHasher(32, seed=2).signature(elements)


@pytest.mark.parametrize("similarity", [0.25, 0.5, 0.8])
def test_estimate_is_close_to_true_jaccard(similarity: float) -> None:
    first, second = _pair_with_jaccard(similarity, 200, f"j{similarity}")
    true = len(first & second) / len(first | second)
    hasher = MinHasher(128, seed=0)
    estimate = estimate_jaccard(hasher.signature(first), hasher.signature(second))
    assert abs(estimate - true) <= 4 * math.sqrt(true * (1 - true) / 128)


def test_identical_sets_estimate_one_and_disjoint_sets_near_zero() -> None:
    hasher = MinHasher(128, seed=0)
    a, b = _elements("a", 100), _elements("b", 100)
    assert estimate_jaccard(hasher.signature(a), hasher.signature(a)) == 1.0
    assert estimate_jaccard(hasher.signature(a), hasher.signature(b)) < 0.05


def test_merging_signatures_gives_the_signature_of_the_union() -> None:
    hasher = MinHasher(32, seed=3)
    a, b = _elements("a", 20), _elements("b", 20)
    merged = merge_min([hasher.signature(a), hasher.signature(b)])
    assert merged == hasher.signature(a | b)


def test_merge_min_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="zero vectors"):
        merge_min([])


def test_estimate_requires_equal_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        estimate_jaccard((1, 2), (1,))


def test_theoretical_s_curve_values() -> None:
    assert candidate_probability(0.5, 32, 4) == pytest.approx(0.8735, abs=1e-3)
    assert candidate_probability(0.0, 32, 4) == 0.0
    assert candidate_probability(1.0, 32, 4) == 1.0
    assert lsh_threshold(32, 4) == pytest.approx(0.4204, abs=1e-3)


def test_best_banding_picks_the_steepest_point_at_or_below_the_threshold() -> None:
    assert best_banding(0.5, 128) == (32, 4)
    bands, rows = best_banding(0.7, 128)
    assert bands * rows == 128
    assert lsh_threshold(bands, rows) <= 0.7


def test_lsh_returns_the_identical_signature_and_not_an_unrelated_one() -> None:
    hasher = MinHasher(32, seed=0)
    index = LshIndex(bands=8, rows=4)
    index.add(7, hasher.signature(_elements("a", 40)))
    assert index.query(hasher.signature(_elements("a", 40))) == {7}
    assert index.query(hasher.signature(_elements("zzz", 40))) == set()


def test_lsh_rejects_a_signature_of_the_wrong_length() -> None:
    with pytest.raises(ValueError, match="signature length"):
        LshIndex(bands=4, rows=4).add(0, (1, 2, 3))


@pytest.mark.parametrize("similarity", [0.2, 0.5, 0.8])
def test_empirical_s_curve_matches_theory(similarity: float) -> None:
    hasher = MinHasher(64, seed=1)
    bands, rows = 16, 4
    trials = 80
    found = 0
    for trial in range(trials):
        first, second = _pair_with_jaccard(similarity, 60, f"t{similarity}:{trial}")
        index = LshIndex(bands, rows)
        index.add(0, hasher.signature(first))
        found += 0 in index.query(hasher.signature(second))
    assert abs(found / trials - candidate_probability(similarity, bands, rows)) < 0.17


def test_make_rng_is_stable() -> None:
    assert make_rng(1, "a").randrange(10**9) == make_rng(1, "a").randrange(10**9)
