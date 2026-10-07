"""Compare detectors on the same planted corpus (D-041, D-044).

Every method sees identical documents and is judged with the same recall definition and the
same verification threshold, so the comparison is fair. The threshold here is fixed by the
caller; it is NOT tuned on this corpus, so run it on a held-out test split.
"""

from __future__ import annotations

import csv
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from contam.evaluate import Scores, score_corpus, summarize
from contam.exact import ExactIndex, Hit, Level, Thresholds
from contam.fuzzy import FuzzyIndex
from contam.inject import PlantedCorpus
from contam.items import BenchmarkItem, View


@dataclass(frozen=True, slots=True)
class CompareRow:
    method: str
    spec: str
    kind: str
    intensity: float | None
    planted: int
    detected: int
    recall: float
    recall_low: float
    recall_high: float
    control_docs: int
    control_flagged: int
    control_fpr_high: float
    seconds: float


def compare_methods(
    items: Sequence[BenchmarkItem],
    corpus: PlantedCorpus,
    *,
    exact_ns: Sequence[int] = (2, 3, 5),
    fuzzy_ks: Sequence[int] = (3,),
    windowed: Sequence[tuple[int, float]] = (),
    threshold: float = 0.3,
    view: View = View.QUESTION,
    num_perm: int = 64,
    bands: int = 32,
    seed: int = 0,
) -> list[CompareRow]:
    """Recall by corruption condition for exact n-gram containment and fuzzy MinHash matching."""
    thresholds = Thresholds(partial=threshold, near_duplicate=max(0.8, threshold))
    rows: list[CompareRow] = []

    def add(method: str, scores: Scores, indexed: frozenset[str], seconds: float) -> None:
        summary = summarize(corpus, scores, thresholds, indexed)
        rows.extend(
            CompareRow(
                method=method,
                spec=c.spec,
                kind=c.kind,
                intensity=c.intensity,
                planted=c.planted,
                detected=c.detected,
                recall=c.recall,
                recall_low=c.recall_low,
                recall_high=c.recall_high,
                control_docs=summary.control_docs,
                control_flagged=summary.control_flagged,
                control_fpr_high=summary.control_fpr_high,
                seconds=seconds,
            )
            for c in summary.conditions
        )

    for n in exact_ns:
        start = time.perf_counter()
        index = ExactIndex.build(items, view=view, n=n)
        scores = score_corpus(index, corpus)
        add(f"exact n={n}", scores, index.indexed_item_ids, time.perf_counter() - start)

    for n, slack in windowed:
        start = time.perf_counter()
        index = ExactIndex.build(items, view=view, n=n)
        scores = score_corpus(index, corpus, slack)
        add(f"win n={n}", scores, index.indexed_item_ids, time.perf_counter() - start)

    for k in fuzzy_ks:
        start = time.perf_counter()
        fuzzy = FuzzyIndex.build(items, view=view, k=k, num_perm=num_perm, bands=bands, seed=seed)
        fuzzy_scores: Scores = {
            (hit.doc_id, hit.item_id): Hit(
                item_id=hit.item_id,
                doc_id=hit.doc_id,
                level=Level.PARTIAL,
                containment=hit.containment,
                matched_ngrams=hit.matched_shingles,
                total_ngrams=hit.total_shingles,
                ngram_size=k,
                exact=False,
                short=False,
            )
            for hit in fuzzy.scan_corpus(corpus.documents, threshold)
        }
        add(f"fuzzy k={k}", fuzzy_scores, fuzzy.indexed_item_ids, time.perf_counter() - start)
    return rows


def write_compare_csv(path: str | Path, rows: Iterable[CompareRow]) -> int:
    names = [f.name for f in fields(CompareRow)]
    count = 0
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
            count += 1
    return count
