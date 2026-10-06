"""M2: windowed fuzzy matching with MinHash + LSH and exact verification (D-044).

Why windows: an item is a short passage inside a long document, so whole-document
signatures are too coarse. We slide windows about the item's length across the document.
A window's signature is the elementwise minimum of its shingles' hash vectors (each shingle
is hashed once per document). LSH proposes (window, item) candidates, and every candidate is
verified by exact containment of the item's shingles in the window, so reported
containment values are exact, never estimates.

Expectation (D-041): with word k-shingles, a fraction p of deleted words leaves about
(1 - p)^k of the shingles, so a small k tolerates heavier edits than the n=5 exact detector.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from contam.exact import SkippedItem
from contam.items import BenchmarkItem, View
from contam.minhash import LshIndex, MinHasher, Signature, merge_min
from contam.ngrams import ngram_hashes
from contam.normalize import normalize
from contam.tokenizer import tokenize


@dataclass(frozen=True, slots=True)
class FuzzyHit:
    item_id: str
    doc_id: str
    containment: float  # exact fraction of the item's shingles found in the best window
    matched_shingles: int
    total_shingles: int
    window_start: int  # shingle position where the best window begins


@dataclass(frozen=True, slots=True)
class _Entry:
    item_ids: tuple[str, ...]
    shingles: frozenset[int]
    window: int


def window_size(n_shingles: int, base: int = 8, ratio: float = 1.3) -> int:
    """Smallest size in the geometric series 8, 11, 15, ... that is >= ``n_shingles``.

    Bucketing keeps the number of distinct window sizes small, and a window is at most
    ``ratio`` times longer than the item.
    """
    size = base
    while size < n_shingles:
        size = max(size + 1, math.ceil(size * ratio))
    return size


class FuzzyIndex:
    """LSH index over benchmark items, scanned against documents with sliding windows."""

    def __init__(
        self,
        entries: list[_Entry],
        lsh: LshIndex,
        hasher: MinHasher,
        k: int,
        skipped: list[SkippedItem],
    ) -> None:
        self._entries = entries
        self._lsh = lsh
        self._hasher = hasher
        self.k = k
        self.skipped = skipped
        self._windows = tuple(sorted({entry.window for entry in entries}))
        self._all_shingles = frozenset().union(*(entry.shingles for entry in entries))
        self._cache: dict[int, Signature] = {}

    @classmethod
    def build(
        cls,
        items: Iterable[BenchmarkItem],
        *,
        view: View = View.QUESTION,
        k: int = 3,
        num_perm: int = 64,
        bands: int = 32,
        min_tokens: int = 8,
        seed: int = 0,
    ) -> FuzzyIndex:
        """Index ``items`` using word ``k``-shingles and ``bands`` x ``num_perm / bands`` LSH."""
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        if bands < 1 or num_perm % bands != 0:
            raise ValueError("bands must divide num_perm")
        hasher = MinHasher(num_perm, seed)
        skipped: list[SkippedItem] = []
        groups: dict[str, list[str]] = {}
        shingle_sets: dict[str, frozenset[int]] = {}
        for item in items:
            tokens = tokenize(normalize(item.text(view)))
            if len(tokens) < max(min_tokens, k + 1):
                skipped.append(SkippedItem(item.item_id, "too_short"))
                continue
            key = " ".join(tokens)
            groups.setdefault(key, []).append(item.item_id)
            if key not in shingle_sets:
                shingle_sets[key] = frozenset(ngram_hashes(tokens, k))
        lsh = LshIndex(bands, num_perm // bands)
        entries: list[_Entry] = []
        for key, ids in groups.items():
            shingles = shingle_sets[key]
            lsh.add(len(entries), hasher.signature(shingles))
            entries.append(_Entry(tuple(ids), shingles, window_size(len(shingles))))
        return cls(entries, lsh, hasher, k, skipped)

    @property
    def indexed_item_ids(self) -> frozenset[str]:
        return frozenset(item_id for entry in self._entries for item_id in entry.item_ids)

    def _vector(self, value: int) -> Signature:
        cached = self._cache.get(value)
        if cached is None:
            if len(self._cache) >= 200_000:
                self._cache.clear()
            cached = self._hasher.vector(value)
            self._cache[value] = cached
        return cached

    def scan_document(
        self, doc_id: str, text: str, min_containment: float = 0.3, min_shared: int = 3
    ) -> list[FuzzyHit]:
        """Items whose shingles are at least ``min_containment`` contained in some window."""
        shingles = ngram_hashes(tokenize(normalize(text)), self.k)
        if not shingles or len(self._all_shingles.intersection(shingles)) < min_shared:
            return []
        vectors = [self._vector(value) for value in shingles]
        best: dict[int, tuple[int, int]] = {}  # entry -> (matched shingles, window start)
        for window in self._windows:
            last = max(0, len(shingles) - window)
            starts = list(range(0, last + 1, max(1, window // 8)))
            if starts[-1] != last:
                starts.append(last)
            for start in starts:
                candidates = self._lsh.query(merge_min(vectors[start : start + window]))
                if not candidates:
                    continue
                window_set = set(shingles[start : start + window])
                for index in candidates:
                    entry = self._entries[index]
                    if entry.window != window:
                        continue
                    matched = len(entry.shingles & window_set)
                    if matched > best.get(index, (0, 0))[0]:
                        best[index] = (matched, start)
        hits: list[FuzzyHit] = []
        for index, (matched, start) in best.items():
            entry = self._entries[index]
            containment = matched / len(entry.shingles)
            if containment >= min_containment:
                hits.extend(
                    FuzzyHit(item_id, doc_id, containment, matched, len(entry.shingles), start)
                    for item_id in entry.item_ids
                )
        hits.sort(key=lambda hit: hit.item_id)
        return hits

    def scan_corpus(
        self, docs: Iterable[tuple[str, object]], min_containment: float = 0.3
    ) -> Iterator[FuzzyHit]:
        for doc_id, text in docs:
            if isinstance(text, str):
                yield from self.scan_document(doc_id, text, min_containment)
