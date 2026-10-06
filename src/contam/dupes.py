"""Near-duplicate detection between benchmark items with MinHash + LSH (D-045).

The natural use of LSH: find similar items at scale without comparing every pair. Candidates
from LSH are verified with exact Jaccard similarity, so reported pairs are never estimates.
Use it within one benchmark split, or across splits (for example GSM8K train versus test).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from contam.items import BenchmarkItem, View
from contam.minhash import LshIndex, MinHasher, best_banding
from contam.ngrams import ngram_hashes
from contam.normalize import normalize
from contam.tokenizer import tokenize


@dataclass(frozen=True, slots=True)
class DuplicatePair:
    id_a: str
    id_b: str
    jaccard: float


def shingle_set(item: BenchmarkItem, k: int, view: View) -> frozenset[int]:
    """Distinct word k-shingle hashes of an item (shorter items use their full length)."""
    tokens = tokenize(normalize(item.text(view)))
    if not tokens:
        return frozenset()
    return frozenset(ngram_hashes(tokens, min(k, len(tokens))))


def jaccard(first: frozenset[int], second: frozenset[int]) -> float:
    union = len(first | second)
    return len(first & second) / union if union else 0.0


def find_near_duplicates(
    items_a: Sequence[BenchmarkItem],
    items_b: Sequence[BenchmarkItem] | None = None,
    *,
    k: int = 3,
    jaccard_threshold: float = 0.7,
    num_perm: int = 128,
    view: View = View.QUESTION,
    seed: int = 0,
) -> list[DuplicatePair]:
    """Pairs with verified Jaccard similarity at or above ``jaccard_threshold``.

    With only ``items_a``, finds pairs inside it. With ``items_b``, finds pairs between the
    two lists (items sharing an id are skipped).
    """
    if not 0.0 < jaccard_threshold <= 1.0:
        raise ValueError(f"jaccard_threshold must be in (0, 1], got {jaccard_threshold}")
    bands, rows = best_banding(jaccard_threshold, num_perm)
    hasher = MinHasher(num_perm, seed)
    right = items_a if items_b is None else items_b
    right_sets = [shingle_set(item, k, view) for item in right]
    left_sets = right_sets if items_b is None else [shingle_set(i, k, view) for i in items_a]

    lsh = LshIndex(bands, rows)
    for index, shingles in enumerate(right_sets):
        if shingles:
            lsh.add(index, hasher.signature(shingles))

    pairs: dict[tuple[str, str], float] = {}
    for i, (item, shingles) in enumerate(zip(items_a, left_sets, strict=True)):
        if not shingles:
            continue
        for j in lsh.query(hasher.signature(shingles)):
            if (items_b is None and j <= i) or item.item_id == right[j].item_id:
                continue
            value = jaccard(shingles, right_sets[j])
            if value >= jaccard_threshold:
                pairs[(item.item_id, right[j].item_id)] = value
    found = [DuplicatePair(a, b, value) for (a, b), value in pairs.items()]
    return sorted(found, key=lambda pair: (-pair.jaccard, pair.id_a, pair.id_b))
