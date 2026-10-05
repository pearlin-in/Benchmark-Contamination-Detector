"""Figures for the evaluation results. Requires the ``analysis`` extra (matplotlib)."""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from contam.evaluate import SweepRow


def _pyplot() -> Any:
    """Import matplotlib lazily with a non-interactive backend (works on any machine)."""
    try:
        matplotlib = importlib.import_module("matplotlib")
        matplotlib.use("Agg")
        return importlib.import_module("matplotlib.pyplot")
    except ImportError as error:
        raise ImportError(
            'matplotlib is required for plots: pip install -e ".[analysis]"'
        ) from error


def plot_edit_rate_curves(
    rows: Sequence[SweepRow],
    path: str | Path,
    *,
    view: str,
    partial: float,
    near_duplicate: float,
) -> None:
    """Recall versus the fraction of words edited, one line per n, with Wilson intervals."""
    plt = _pyplot()
    selected = [
        r
        for r in rows
        if r.view == view
        and r.partial == partial
        and r.near_duplicate == near_duplicate
        and r.stop_ngram_k is None
        and r.intensity is not None
    ]
    kinds = [
        kind for kind in ("word_delete", "word_substitute") if any(r.kind == kind for r in selected)
    ]
    panels = max(1, len(kinds))
    figure, axes = plt.subplots(1, panels, figsize=(5.5 * panels, 4), squeeze=False)
    for axis, kind in zip(axes[0], kinds, strict=False):
        for n in sorted({r.n for r in selected if r.kind == kind}):
            points = sorted(
                (r for r in selected if r.kind == kind and r.n == n),
                key=lambda r: r.intensity or 0.0,
            )
            x = [100 * (r.intensity or 0.0) for r in points]
            y = [r.recall for r in points]
            lower = [r.recall - r.recall_low for r in points]
            upper = [r.recall_high - r.recall for r in points]
            axis.errorbar(x, y, yerr=[lower, upper], marker="o", capsize=3, label=f"n = {n}")
        axis.set_title(kind.replace("_", " "))
        axis.set_xlabel("% of words edited")
        axis.set_ylabel("recall")
        axis.set_ylim(-0.02, 1.02)
        axis.grid(alpha=0.3)
        axis.legend()
    figure.suptitle(f"Recall vs. edit rate (view={view}, thresholds {partial}/{near_duplicate})")
    figure.tight_layout()
    figure.savefig(Path(path), dpi=150)
    plt.close(figure)


def plot_condition_recall(rows: Sequence[SweepRow], path: str | Path, *, title: str) -> None:
    """Horizontal bars of recall per corruption condition at ONE setting, with Wilson intervals."""
    plt = _pyplot()
    ordered = list(rows)
    figure, axis = plt.subplots(figsize=(7, 0.35 * len(ordered) + 1.5))
    positions = list(range(len(ordered)))
    recalls = [r.recall for r in ordered]
    lower = [r.recall - r.recall_low for r in ordered]
    upper = [r.recall_high - r.recall for r in ordered]
    axis.barh(positions, recalls, xerr=[lower, upper], capsize=2, color="#4C72B0")
    axis.set_yticks(positions)
    axis.set_yticklabels([r.spec for r in ordered])
    axis.invert_yaxis()
    axis.set_xlim(0, 1.02)
    axis.set_xlabel("recall (95% Wilson interval)")
    axis.set_title(title)
    axis.grid(axis="x", alpha=0.3)
    figure.tight_layout()
    figure.savefig(Path(path), dpi=150)
    plt.close(figure)
