"""MinHash signatures and LSH banding, implemented from scratch (DECISIONS.md, D-042, D-043).

MinHash: apply many independent hash functions h_i(x) = (a_i * x + b_i) mod p (p = 2^61 - 1)
to every element of a set and keep the minimum per function. The probability that two sets
share the same minimum under one function equals their Jaccard similarity, so the fraction
of agreeing positions is an unbiased estimate with standard deviation sqrt(J (1 - J) / k).

LSH banding: cut a signature of k = bands * rows values into bands. Two sets become
candidates if ANY band matches exactly, which happens with probability
1 - (1 - s^rows)^bands at similarity s: an S-shaped curve that rises near (1 / bands)^(1 / rows).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from contam.ngrams import MODULUS
from contam.synthetic import make_rng

Signature = tuple[int, ...]


class MinHasher:
    """Deterministic family of ``num_perm`` hash functions (same seed, same signatures)."""

    def __init__(self, num_perm: int = 64, seed: int = 0) -> None:
        if num_perm < 1:
            raise ValueError(f"num_perm must be >= 1, got {num_perm}")
        rng = make_rng(seed, "minhash")
        self.num_perm = num_perm
        self._params = [
            (1 + rng.randrange(MODULUS - 1), rng.randrange(MODULUS)) for _ in range(num_perm)
        ]

    def vector(self, value: int) -> Signature:
        """The ``num_perm`` hash values of a single element."""
        return tuple((a * value + b) % MODULUS for a, b in self._params)

    def signature(self, values: Iterable[int]) -> Signature:
        """Signature of a set: the per-function minimum over all its elements."""
        minima = [MODULUS] * self.num_perm
        for value in values:
            for i, (a, b) in enumerate(self._params):
                hashed = (a * value + b) % MODULUS
                if hashed < minima[i]:
                    minima[i] = hashed
        return tuple(minima)


def merge_min(vectors: Sequence[Sequence[int]]) -> Signature:
    """Elementwise minimum, i.e. the signature of the union of the underlying sets."""
    if not vectors:
        raise ValueError("cannot merge zero vectors")
    return tuple(map(min, zip(*vectors, strict=True)))


def estimate_jaccard(first: Sequence[int], second: Sequence[int]) -> float:
    """Fraction of agreeing signature positions: the Jaccard estimate."""
    if len(first) != len(second):
        raise ValueError("signatures must have the same length")
    return sum(a == b for a, b in zip(first, second, strict=True)) / len(first)


def candidate_probability(similarity: float, bands: int, rows: int) -> float:
    """Theoretical chance that LSH proposes a pair with the given Jaccard similarity."""
    return 1.0 - (1.0 - similarity**rows) ** bands


def lsh_threshold(bands: int, rows: int) -> float:
    """Similarity near which the S-curve rises most steeply."""
    return float((1.0 / bands) ** (1.0 / rows))


def best_banding(threshold: float, num_perm: int) -> tuple[int, int]:
    """Choose (bands, rows) with bands * rows == num_perm for a target similarity.

    Prefers the steepest point at or below ``threshold`` (favouring recall; verification
    removes the extra candidates). If none is at or below it, uses the lowest available.
    """
    options = [
        (num_perm // rows, rows, lsh_threshold(num_perm // rows, rows))
        for rows in range(1, num_perm + 1)
        if num_perm % rows == 0
    ]
    below = [option for option in options if option[2] <= threshold]
    bands, rows, _ = max(below, key=lambda o: o[2]) if below else min(options, key=lambda o: o[2])
    return bands, rows


class LshIndex:
    """Banded hash tables mapping signature slices to integer keys."""

    def __init__(self, bands: int, rows: int) -> None:
        if bands < 1 or rows < 1:
            raise ValueError("bands and rows must be >= 1")
        self.bands = bands
        self.rows = rows
        self._tables: list[dict[Signature, list[int]]] = [{} for _ in range(bands)]

    def _slices(self, signature: Sequence[int]) -> list[Signature]:
        if len(signature) != self.bands * self.rows:
            raise ValueError(
                f"signature length {len(signature)} != bands * rows = {self.bands * self.rows}"
            )
        return [
            tuple(signature[band * self.rows : (band + 1) * self.rows])
            for band in range(self.bands)
        ]

    def add(self, key: int, signature: Sequence[int]) -> None:
        for table, piece in zip(self._tables, self._slices(signature), strict=True):
            table.setdefault(piece, []).append(key)

    def query(self, signature: Sequence[int]) -> set[int]:
        found: set[int] = set()
        for table, piece in zip(self._tables, self._slices(signature), strict=True):
            found.update(table.get(piece, ()))
        return found
