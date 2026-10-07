"""Measure the detector against planted ground truth (D-012, D-014, D-037 to D-040).

Method: scan the planted corpus ONCE with a floor threshold so that every (document, item)
overlap is recorded with its containment score and exact-match flag (D-040). Any threshold
setting can then be evaluated afterwards without rescanning, which makes threshold sweeps
cheap and guarantees every setting sees identical data.

Definitions:
  * A plant is *detected* if the detector reports its (document, item) pair at or above the
    thresholds. Plants whose item was never indexed (too short, all template n-grams) are
    excluded from recall and counted separately as ``unindexed`` (D-038).
  * A control document is *flagged* if any item is reported in it. Controls are real or
    synthetic background text, so on real corpora a flag may be genuine contamination: the
    control flag rate is an UPPER BOUND on the false-positive rate (D-037).
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from contam.exact import ExactIndex, Hit, Level, Thresholds
from contam.inject import PlantedCorpus
from contam.items import BenchmarkItem, View
from contam.stats import wilson_interval

# Record every overlap, however small; thresholds are applied afterwards.
SCAN_FLOOR = Thresholds(partial=1e-9, near_duplicate=1e-9)

Scores = dict[tuple[str, str], Hit]  # (doc_id, item_id) -> hit


@dataclass(frozen=True, slots=True)
class ConditionResult:
    """Recall for one corruption condition."""

    spec: str
    kind: str
    intensity: float | None
    planted: int
    detected: int
    exact: int
    recall: float
    recall_low: float
    recall_high: float
    mean_containment: float


@dataclass(frozen=True, slots=True)
class EvalSummary:
    thresholds: Thresholds
    conditions: tuple[ConditionResult, ...]
    unindexed: int
    control_docs: int
    control_flagged: int
    control_fpr: float
    control_fpr_low: float
    control_fpr_high: float
    foreign_hits: int  # hits in planted documents for an item other than the planted one

    @property
    def macro_recall(self) -> float:
        """Mean recall over conditions, each condition weighted equally."""
        scored = [c.recall for c in self.conditions if c.planted > 0]
        return sum(scored) / len(scored) if scored else 0.0


def score_corpus(
    index: ExactIndex, corpus: PlantedCorpus, window_slack: float | None = None
) -> Scores:
    """Scan every document once at the floor threshold (optionally window-localized)."""
    return {
        (hit.doc_id, hit.item_id): hit
        for hit in index.scan_corpus(corpus.documents, SCAN_FLOOR, window_slack=window_slack)
    }


def summarize(
    corpus: PlantedCorpus,
    scores: Scores,
    thresholds: Thresholds,
    indexed_ids: frozenset[str],
) -> EvalSummary:
    """Apply ``thresholds`` to pre-computed ``scores`` and tally recall and false positives."""
    planted_item_by_doc = {plant.doc_id: plant.item_id for plant in corpus.plants}
    control_ids = set(corpus.control_doc_ids)

    tallies: dict[str, list[Any]] = {}  # spec -> [kind, intensity, n, detected, exact, sum_c]
    unindexed = 0
    for plant in corpus.plants:
        if plant.item_id not in indexed_ids:
            unindexed += 1
            continue
        tally = tallies.setdefault(plant.spec, [plant.kind, plant.intensity, 0, 0, 0, 0.0])
        tally[2] += 1
        hit = scores.get((plant.doc_id, plant.item_id))
        if hit is None:
            continue
        level = thresholds.classify(hit.containment, exact=hit.exact)
        tally[3] += level is not Level.NONE
        tally[4] += level is Level.EXACT
        tally[5] += hit.containment

    conditions: list[ConditionResult] = []
    for spec, (kind, intensity, planted, detected, exact, total_containment) in tallies.items():
        low, high = wilson_interval(detected, planted)
        conditions.append(
            ConditionResult(
                spec=spec,
                kind=kind,
                intensity=intensity,
                planted=planted,
                detected=detected,
                exact=exact,
                recall=detected / planted,
                recall_low=low,
                recall_high=high,
                mean_containment=total_containment / planted,
            )
        )

    flagged_controls: set[str] = set()
    foreign = 0
    for (doc_id, item_id), hit in scores.items():
        if thresholds.classify(hit.containment, exact=hit.exact) is Level.NONE:
            continue
        if doc_id in control_ids:
            flagged_controls.add(doc_id)
        elif planted_item_by_doc.get(doc_id) != item_id:
            foreign += 1

    n_controls = len(control_ids)
    fpr_low, fpr_high = wilson_interval(len(flagged_controls), n_controls)
    return EvalSummary(
        thresholds=thresholds,
        conditions=tuple(conditions),
        unindexed=unindexed,
        control_docs=n_controls,
        control_flagged=len(flagged_controls),
        control_fpr=len(flagged_controls) / n_controls if n_controls else 0.0,
        control_fpr_low=fpr_low,
        control_fpr_high=fpr_high,
        foreign_hits=foreign,
    )


# --------------------------------------------------------------------------- sweeps
@dataclass(frozen=True, slots=True)
class SweepRow:
    """One (settings x condition) result; the flat shape written to CSV."""

    n: int
    stop_ngram_k: int | None
    view: str
    partial: float
    near_duplicate: float
    spec: str
    kind: str
    intensity: float | None
    planted: int
    detected: int
    exact: int
    recall: float
    recall_low: float
    recall_high: float
    mean_containment: float
    control_docs: int
    control_flagged: int
    control_fpr: float
    control_fpr_low: float
    control_fpr_high: float
    foreign_hits: int
    unindexed: int
    window_slack: float | None = None


def rows_from_summary(
    summary: EvalSummary,
    *,
    n: int,
    stop_ngram_k: int | None,
    view: View,
    window_slack: float | None = None,
) -> list[SweepRow]:
    return [
        SweepRow(
            n=n,
            stop_ngram_k=stop_ngram_k,
            view=str(view),
            partial=summary.thresholds.partial,
            near_duplicate=summary.thresholds.near_duplicate,
            spec=c.spec,
            kind=c.kind,
            intensity=c.intensity,
            planted=c.planted,
            detected=c.detected,
            exact=c.exact,
            recall=c.recall,
            recall_low=c.recall_low,
            recall_high=c.recall_high,
            mean_containment=c.mean_containment,
            control_docs=summary.control_docs,
            control_flagged=summary.control_flagged,
            control_fpr=summary.control_fpr,
            control_fpr_low=summary.control_fpr_low,
            control_fpr_high=summary.control_fpr_high,
            foreign_hits=summary.foreign_hits,
            unindexed=summary.unindexed,
            window_slack=window_slack,
        )
        for c in summary.conditions
    ]


def run_sweep(
    items: Sequence[BenchmarkItem],
    corpus: PlantedCorpus,
    *,
    ns: Sequence[int] = (5, 8, 13),
    stop_ks: Sequence[int | None] = (None,),
    views: Sequence[View] = (View.QUESTION_CHOICES, View.QUESTION),
    partials: Sequence[float] = (0.3, 0.5, 0.7),
    near_duplicates: Sequence[float] = (0.8, 0.9),
    window_slacks: Sequence[float | None] = (None,),
) -> list[SweepRow]:
    """Evaluate every combination of n, stop filter, view, window and thresholds.

    The index is built from ``items`` (the whole benchmark), exactly as a real scan would.
    ``None`` in ``window_slacks`` means whole-document containment.
    """
    rows: list[SweepRow] = []
    for view in views:
        for stop_k in stop_ks:
            for n in ns:
                index = ExactIndex.build(items, view=view, n=n, stop_ngram_k=stop_k)
                indexed = index.indexed_item_ids
                for slack in window_slacks:
                    scores = score_corpus(index, corpus, slack)
                    for partial in partials:
                        for near in near_duplicates:
                            if partial > near:
                                continue
                            summary = summarize(corpus, scores, Thresholds(partial, near), indexed)
                            rows.extend(
                                rows_from_summary(
                                    summary, n=n, stop_ngram_k=stop_k, view=view, window_slack=slack
                                )
                            )
    return rows


# --------------------------------------------------------------------------- operating point
@dataclass(frozen=True, slots=True)
class OperatingPoint:
    """The settings chosen on dev data and then frozen (D-011, D-039)."""

    n: int
    stop_ngram_k: int | None
    view: str
    partial: float
    near_duplicate: float
    macro_recall: float
    control_fpr_upper: float
    window_slack: float | None = None


def select_operating_point(
    rows: Iterable[SweepRow], *, view: View, max_control_fpr_upper: float = 0.05
) -> OperatingPoint:
    """Pick the settings with the best macro recall whose control false-positive rate is bounded.

    Rule (D-039): among settings in ``view`` whose Wilson UPPER bound on the control
    flag rate is at most ``max_control_fpr_upper``, maximize macro recall (every corruption
    condition counts equally). Ties prefer stricter thresholds, then larger n, then no
    stop-n-gram filter.

    Raises:
        ValueError: if no setting satisfies the false-positive bound.
    """
    groups: dict[tuple[int, int | None, str, float, float, float | None], list[SweepRow]] = {}
    for row in rows:
        if row.view != str(view):
            continue
        key = (row.n, row.stop_ngram_k, row.view, row.partial, row.near_duplicate, row.window_slack)
        groups.setdefault(key, []).append(row)

    candidates: list[tuple[tuple[float, float, float, int, bool, bool], OperatingPoint]] = []
    for (n, stop_k, view_name, partial, near, slack), group in groups.items():
        upper = group[0].control_fpr_high
        scored = [row.recall for row in group if row.planted > 0]
        if upper > max_control_fpr_upper or not scored:
            continue
        macro = sum(scored) / len(scored)
        point = OperatingPoint(n, stop_k, view_name, partial, near, macro, upper, slack)
        rank = (round(macro, 12), partial, near, n, stop_k is None, slack is None)
        candidates.append((rank, point))
    if not candidates:
        raise ValueError(
            "no setting keeps the control false-positive upper bound at or below "
            f"{max_control_fpr_upper}; use more control documents or relax the bound"
        )
    return max(candidates, key=lambda candidate: candidate[0])[1]


def evaluate_at(
    items: Sequence[BenchmarkItem], corpus: PlantedCorpus, point: OperatingPoint
) -> EvalSummary:
    """Evaluate one frozen operating point on a (test) corpus."""
    index = ExactIndex.build(
        items, view=View(point.view), n=point.n, stop_ngram_k=point.stop_ngram_k
    )
    scores = score_corpus(index, corpus, point.window_slack)
    thresholds = Thresholds(point.partial, point.near_duplicate)
    return summarize(corpus, scores, thresholds, index.indexed_item_ids)


# --------------------------------------------------------------------------- output files
def write_rows_csv(path: str | Path, rows: Iterable[SweepRow]) -> int:
    """Write sweep rows to CSV (UTF-8, LF line endings). Returns the number of rows."""
    names = [f.name for f in fields(SweepRow)]
    count = 0
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
            count += 1
    return count


def save_operating_point(
    path: str | Path, point: OperatingPoint, context: dict[str, Any] | None = None
) -> None:
    """Freeze the operating point (and how it was chosen) to JSON before the test run."""
    payload = {"operating_point": asdict(point), "context": context or {}}
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_operating_point(path: str | Path) -> OperatingPoint:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return OperatingPoint(**payload["operating_point"])


def summary_to_dict(summary: EvalSummary) -> dict[str, Any]:
    return {
        "thresholds": asdict(summary.thresholds),
        "macro_recall": summary.macro_recall,
        "unindexed": summary.unindexed,
        "control_docs": summary.control_docs,
        "control_flagged": summary.control_flagged,
        "control_fpr": summary.control_fpr,
        "control_fpr_low": summary.control_fpr_low,
        "control_fpr_high": summary.control_fpr_high,
        "foreign_hits": summary.foreign_hits,
        "conditions": [asdict(condition) for condition in summary.conditions],
    }
