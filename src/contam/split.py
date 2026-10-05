"""Deterministic dev/test splitting (DECISIONS.md, D-011 and D-034).

Thresholds are tuned on the dev half and reported on the test half. The split key is the
*normalized question text*, so duplicate questions always land on the same side. Splitting
by item id alone would let a duplicate leak from dev into test and inflate test results.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence

from contam.items import BenchmarkItem
from contam.normalize import normalize


def unit_interval(seed: int, key: str) -> float:
    """Stable pseudo-random number in [0, 1) derived from ``(seed, key)``.

    Independent of iteration order, platform and Python version, unlike shuffling.
    """
    digest = hashlib.blake2b(f"{seed}|{key}".encode("utf-8", "surrogatepass"), digest_size=8)
    return int.from_bytes(digest.digest(), "big") / 2**64


def _check_fraction(dev_fraction: float) -> None:
    if not 0.0 < dev_fraction < 1.0:
        raise ValueError(f"dev_fraction must be strictly between 0 and 1, got {dev_fraction}")


def split_items(
    items: Iterable[BenchmarkItem], dev_fraction: float = 0.5, seed: int = 0
) -> tuple[list[BenchmarkItem], list[BenchmarkItem]]:
    """Split items into (dev, test). Items with the same normalized question stay together."""
    _check_fraction(dev_fraction)
    dev: list[BenchmarkItem] = []
    test: list[BenchmarkItem] = []
    for item in items:
        key = normalize(item.question)
        (dev if unit_interval(seed, key) < dev_fraction else test).append(item)
    return dev, test


def split_documents(
    documents: Sequence[tuple[str, str]], dev_fraction: float = 0.5, seed: int = 0
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Split background documents by id, so dev and test never share host text."""
    _check_fraction(dev_fraction)
    dev: list[tuple[str, str]] = []
    test: list[tuple[str, str]] = []
    for doc_id, text in documents:
        (dev if unit_interval(seed, f"doc|{doc_id}") < dev_fraction else test).append(
            (doc_id, text)
        )
    return dev, test
