"""The Phase 4 experiment: tune on dev, freeze, report on test (DECISIONS.md, D-011).

Order of operations (the order is the point):
  1. Split items and background documents into dev and test, deterministically.
  2. Plant corrupted dev items in dev background; sweep n, thresholds and views on that corpus.
  3. Choose the operating point on dev data ONLY, and write it to disk (frozen).
  4. Only then build the test corpus and evaluate the frozen point on it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from contam.corrupt import DEFAULT_SPECS, CorruptionSpec
from contam.evaluate import (
    EvalSummary,
    OperatingPoint,
    SweepRow,
    evaluate_at,
    rows_from_summary,
    run_sweep,
    save_operating_point,
    select_operating_point,
    summary_to_dict,
    write_rows_csv,
)
from contam.inject import Document, build_planted_corpus, verify_plants, write_manifest
from contam.items import BenchmarkItem, View
from contam.manifest import build_run_manifest
from contam.split import split_documents, split_items


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    ns: tuple[int, ...] = (5, 8, 13)
    stop_ks: tuple[int | None, ...] = (None,)
    partials: tuple[float, ...] = (0.3, 0.5, 0.7)
    near_duplicates: tuple[float, ...] = (0.8, 0.9)
    primary_view: View = View.QUESTION_CHOICES
    dev_fraction: float = 0.5
    items_per_spec: int = 100
    n_controls: int = 500
    max_control_fpr_upper: float = 0.05
    max_host_chars: int = 4000
    seed: int = 0
    specs: tuple[CorruptionSpec, ...] = DEFAULT_SPECS
    test_sweep: bool = True
    window_slacks: tuple[float | None, ...] = (None,)


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    out_dir: Path
    operating_point: OperatingPoint
    test_summary: EvalSummary
    dev_rows: list[SweepRow]
    n_dev_items: int
    n_test_items: int


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(text + "\n", encoding="utf-8")


def run_experiment(
    items: Sequence[BenchmarkItem],
    background: Sequence[Document],
    config: ExperimentConfig,
    out_dir: str | Path,
    *,
    make_plots: bool = True,
    extra_manifest: dict[str, Any] | None = None,
) -> ExperimentResult:
    """Run the full dev -> freeze -> test experiment and write every artifact to ``out_dir``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    dev_items, test_items = split_items(items, config.dev_fraction, config.seed)
    dev_background, test_background = split_documents(background, config.dev_fraction, config.seed)
    if not dev_items or not test_items:
        raise ValueError(
            f"split produced {len(dev_items)} dev and {len(test_items)} test items; "
            "provide more items"
        )
    if not dev_background or not test_background:
        raise ValueError("split left no background documents on one side; provide more documents")

    corpus_args: dict[str, Any] = {
        "specs": config.specs,
        "items_per_spec": config.items_per_spec,
        "n_controls": config.n_controls,
        "seed": config.seed,
        "max_host_chars": config.max_host_chars,
    }

    # ---- 2. dev: plant, verify the ground truth itself, sweep
    dev_corpus = build_planted_corpus(dev_items, dev_background, **corpus_args)
    problems = verify_plants(dev_corpus)
    if problems:
        raise RuntimeError(f"dev ground truth is inconsistent: {problems[:3]}")
    dev_rows = run_sweep(
        items,
        dev_corpus,
        ns=config.ns,
        stop_ks=config.stop_ks,
        partials=config.partials,
        near_duplicates=config.near_duplicates,
        window_slacks=config.window_slacks,
    )
    write_rows_csv(out / "dev_sweep.csv", dev_rows)
    write_manifest(out / "dev_manifest.jsonl", dev_corpus)

    # ---- 3. choose on dev only, then freeze to disk BEFORE the test corpus exists
    point = select_operating_point(
        dev_rows, view=config.primary_view, max_control_fpr_upper=config.max_control_fpr_upper
    )
    save_operating_point(
        out / "operating_point.json",
        point,
        context={
            "selected_on": "dev",
            "seed": config.seed,
            "max_control_fpr_upper": config.max_control_fpr_upper,
            "n_dev_items": len(dev_items),
            "n_dev_plants": len(dev_corpus.plants),
        },
    )

    # ---- 4. test: evaluate the frozen point (and, for sensitivity reporting, the whole grid)
    test_corpus = build_planted_corpus(test_items, test_background, **corpus_args)
    problems = verify_plants(test_corpus)
    if problems:
        raise RuntimeError(f"test ground truth is inconsistent: {problems[:3]}")
    summary = evaluate_at(items, test_corpus, point)
    test_rows = rows_from_summary(
        summary,
        n=point.n,
        stop_ngram_k=point.stop_ngram_k,
        view=View(point.view),
        window_slack=point.window_slack,
    )
    write_rows_csv(out / "test_conditions.csv", test_rows)
    _write_json(out / "test_summary.json", summary_to_dict(summary))
    write_manifest(out / "test_manifest.jsonl", test_corpus)
    if config.test_sweep:
        write_rows_csv(
            out / "test_sweep.csv",
            run_sweep(
                items,
                test_corpus,
                ns=config.ns,
                stop_ks=config.stop_ks,
                partials=config.partials,
                near_duplicates=config.near_duplicates,
                window_slacks=config.window_slacks,
            ),
        )

    _write_json(
        out / "run_manifest.json",
        build_run_manifest(asdict(config), {"n_items": len(items), **(extra_manifest or {})}),
    )

    if make_plots:
        from contam.plots import plot_condition_recall, plot_edit_rate_curves

        plot_edit_rate_curves(
            dev_rows,
            out / "dev_recall_vs_edit_rate.png",
            view=point.view,
            partial=point.partial,
            near_duplicate=point.near_duplicate,
            window_slack=point.window_slack,
        )
        plot_condition_recall(
            test_rows,
            out / "test_recall_by_condition.png",
            title=(
                f"Test recall at the frozen point (n={point.n}, "
                f"{point.partial}/{point.near_duplicate})"
            ),
        )

    return ExperimentResult(out, point, summary, dev_rows, len(dev_items), len(test_items))
