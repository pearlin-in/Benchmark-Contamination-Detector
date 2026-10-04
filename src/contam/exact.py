"""M1: exact n-gram containment detector (DECISIONS.md, D-005, D-007 to D-009).

Architecture (D-007): hold the *small* side (benchmark n-grams) in memory and stream the
*large* side (corpus) once. No corpus index is ever built.

Core quantity (SCOPE.md, section 3): for benchmark item ``i`` and document ``d``

    containment(i, d) = |ngrams(i) & ngrams(d)| / |ngrams(i)|        (distinct n-grams)

Contamination levels are assigned from containment plus a verified contiguous match.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import IntEnum

from contam.items import BenchmarkItem, View
from contam.ngrams import ngram_hashes
from contam.normalize import normalize
from contam.tokenizer import tokenize


class Level(IntEnum):
    """Contamination level (SCOPE.md, section 3). Higher means stronger overlap."""

    NONE = 0
    PARTIAL = 1
    NEAR_DUPLICATE = 2
    EXACT = 3


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Containment cut-offs for levels L1 and L2 (tuned on dev data only, D-011)."""

    partial: float = 0.5
    near_duplicate: float = 0.8

    def __post_init__(self) -> None:
        if not 0.0 < self.partial <= self.near_duplicate <= 1.0:
            raise ValueError(
                "thresholds must satisfy 0 < partial <= near_duplicate <= 1, "
                f"got partial={self.partial}, near_duplicate={self.near_duplicate}"
            )

    def classify(self, containment: float, *, exact: bool) -> Level:
        if exact:
            return Level.EXACT
        if containment >= self.near_duplicate:
            return Level.NEAR_DUPLICATE
        if containment >= self.partial:
            return Level.PARTIAL
        return Level.NONE


# "Any single shared n-gram flags the item", the GPT-3-style reference rule (SCOPE.md, section 3).
GPT3_STYLE_THRESHOLDS = Thresholds(partial=1e-9, near_duplicate=0.8)


@dataclass(frozen=True, slots=True)
class Hit:
    """One (benchmark item, corpus document) overlap above threshold."""

    item_id: str
    doc_id: str
    level: Level
    containment: float
    matched_ngrams: int
    total_ngrams: int
    ngram_size: int
    exact: bool
    short: bool


@dataclass(frozen=True, slots=True)
class SkippedItem:
    """An item that could not be indexed, and why (reported, never silently dropped)."""

    item_id: str
    reason: str  # "too_short" or "all_stop_ngrams"


@dataclass(slots=True)
class ScanStats:
    """Counters filled in by :meth:`ExactIndex.scan_corpus`."""

    documents: int = 0
    tokens: int = 0
    hits: int = 0
    malformed: int = 0


@dataclass(frozen=True, slots=True)
class _Entry:
    """One unique normalized item text; identical items share an entry (D-029)."""

    item_ids: tuple[str, ...]
    needle: str  # " tok tok tok " with padding, for token-boundary-safe substring checks
    ngram_size: int
    total: int  # distinct non-stop n-grams: the containment denominator
    short: bool  # fewer tokens than the configured n


def gpt3_style_ngram_size(token_lengths: Sequence[int], cap: int = 13) -> int:
    """N used by the GPT-3 contamination analysis: 5th-percentile item length, capped.

    Uses the nearest-rank percentile definition. Never less than 1.
    """
    if not token_lengths:
        raise ValueError("token_lengths must not be empty")
    ordered = sorted(token_lengths)
    rank = max(math.ceil(0.05 * len(ordered)), 1)
    return max(1, min(cap, ordered[rank - 1]))


def item_token_lengths(items: Iterable[BenchmarkItem], view: View) -> list[int]:
    """Token count of each item under ``view`` (used to choose n and report short items)."""
    return [len(tokenize(normalize(item.text(view)))) for item in items]


class ExactIndex:
    """In-memory n-gram index of a benchmark, scanned against documents.

    Build once with :meth:`build`, then call :meth:`scan_document` or :meth:`scan_corpus`.
    """

    def __init__(
        self,
        entries: list[_Entry],
        tables: dict[int, dict[int, tuple[int, ...]]],
        skipped: list[SkippedItem],
        *,
        n: int,
        view: View,
    ) -> None:
        self._entries = entries
        self._tables = tables
        self.skipped = skipped
        self.n = n
        self.view = view

    # ------------------------------------------------------------------ build
    @classmethod
    def build(
        cls,
        items: Iterable[BenchmarkItem],
        *,
        view: View = View.QUESTION_CHOICES,
        n: int = 8,
        stop_ngram_k: int | None = None,
        min_tokens: int | None = None,
    ) -> ExactIndex:
        """Index ``items`` for scanning.

        Args:
            view: which text of each item to search for (D-002).
            n: n-gram size (D-005).
            stop_ngram_k: if set, drop n-grams shared by at least this many *distinct* item
                texts, i.e. templates like "which of the following is" (D-008).
            min_tokens: items with fewer tokens are skipped and reported (D-009).
                Items with ``min_tokens <= length < n`` are matched as a whole (``short``).
                Defaults to ``min(4, n)``.
        """
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        if min_tokens is None:
            min_tokens = min(4, n)
        if not 1 <= min_tokens <= n:
            raise ValueError(f"min_tokens must satisfy 1 <= min_tokens <= n, got {min_tokens}")
        if stop_ngram_k is not None and stop_ngram_k < 2:
            raise ValueError(f"stop_ngram_k must be >= 2 (or None), got {stop_ngram_k}")

        skipped: list[SkippedItem] = []
        groups: dict[str, list[str]] = {}  # normalized text -> item ids
        token_lists: dict[str, list[str]] = {}
        for item in items:
            tokens = tokenize(normalize(item.text(view)))
            if len(tokens) < min_tokens:
                skipped.append(SkippedItem(item.item_id, "too_short"))
                continue
            key = " ".join(tokens)
            groups.setdefault(key, []).append(item.item_id)
            token_lists.setdefault(key, tokens)

        distinct: dict[str, tuple[int, set[int]]] = {}
        frequency: Counter[tuple[int, int]] = Counter()
        for key, tokens in token_lists.items():
            size = min(n, len(tokens))
            hashes = set(ngram_hashes(tokens, size))
            distinct[key] = (size, hashes)
            frequency.update((size, value) for value in hashes)

        stop: set[tuple[int, int]] = set()
        if stop_ngram_k is not None:
            stop = {pair for pair, count in frequency.items() if count >= stop_ngram_k}

        entries: list[_Entry] = []
        builders: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
        for key, ids in groups.items():
            size, hashes = distinct[key]
            kept = {value for value in hashes if (size, value) not in stop}
            if not kept:
                skipped.extend(SkippedItem(item_id, "all_stop_ngrams") for item_id in ids)
                continue
            entry_index = len(entries)
            entries.append(
                _Entry(
                    item_ids=tuple(ids),
                    needle=f" {key} ",
                    ngram_size=size,
                    total=len(kept),
                    short=len(token_lists[key]) < n,
                )
            )
            for value in kept:
                builders[size][value].append(entry_index)

        tables = {
            size: {value: tuple(indices) for value, indices in table.items()}
            for size, table in builders.items()
        }
        return cls(entries, tables, skipped, n=n, view=view)

    @classmethod
    def gpt3_style(
        cls, items: Sequence[BenchmarkItem], *, view: View = View.QUESTION_CHOICES, cap: int = 13
    ) -> ExactIndex:
        """Index built with the GPT-3 rule: adaptive N, short items matched whole."""
        n = gpt3_style_ngram_size(item_token_lengths(items, view), cap)
        return cls.build(items, view=view, n=n, min_tokens=1)

    # ------------------------------------------------------------------ introspection
    @property
    def indexed_items(self) -> int:
        """Number of benchmark items that can be detected (duplicates counted separately)."""
        return sum(len(entry.item_ids) for entry in self._entries)

    @property
    def ngram_sizes(self) -> tuple[int, ...]:
        return tuple(sorted(self._tables))

    @property
    def table_size(self) -> int:
        """Total number of distinct n-grams held in memory."""
        return sum(len(table) for table in self._tables.values())

    # ------------------------------------------------------------------ scanning
    def scan_document(
        self, doc_id: str, text: str, thresholds: Thresholds | None = None
    ) -> list[Hit]:
        """All benchmark items overlapping ``text`` at or above ``thresholds``."""
        tokens = tokenize(normalize(text))
        return self._scan_tokens(doc_id, tokens, thresholds or Thresholds())

    def scan_corpus(
        self,
        docs: Iterable[tuple[str, str]],
        thresholds: Thresholds | None = None,
        stats: ScanStats | None = None,
    ) -> Iterator[Hit]:
        """Stream ``(doc_id, text)`` pairs and yield hits; malformed documents are counted."""
        active = thresholds or Thresholds()
        for doc_id, text in docs:
            if not isinstance(text, str):
                if stats is not None:
                    stats.malformed += 1
                continue
            tokens = tokenize(normalize(text))
            hits = self._scan_tokens(doc_id, tokens, active)
            if stats is not None:
                stats.documents += 1
                stats.tokens += len(tokens)
                stats.hits += len(hits)
            yield from hits

    def _scan_tokens(self, doc_id: str, tokens: list[str], thresholds: Thresholds) -> list[Hit]:
        matched: dict[int, set[int]] = {}
        for size, table in self._tables.items():
            for value in ngram_hashes(tokens, size):
                entry_indices = table.get(value)
                if entry_indices is None:
                    continue
                for entry_index in entry_indices:
                    matched.setdefault(entry_index, set()).add(value)
        if not matched:
            return []

        haystack: str | None = None
        hits: list[Hit] = []
        for entry_index, values in matched.items():
            entry = self._entries[entry_index]
            containment = len(values) / entry.total
            exact = False
            if containment >= thresholds.near_duplicate:
                if haystack is None:
                    haystack = f" {' '.join(tokens)} "
                # Token-boundary-safe contiguous match: the only way to reach Level.EXACT.
                exact = entry.needle in haystack
            level = thresholds.classify(containment, exact=exact)
            if level is Level.NONE:
                continue
            hits.extend(
                Hit(
                    item_id=item_id,
                    doc_id=doc_id,
                    level=level,
                    containment=containment,
                    matched_ngrams=len(values),
                    total_ngrams=entry.total,
                    ngram_size=entry.ngram_size,
                    exact=exact,
                    short=entry.short,
                )
                for item_id in entry.item_ids
            )
        hits.sort(key=lambda hit: hit.item_id)
        return hits
