"""Turn a scan folder into the headline table (D-052): item-level contamination rates.

Counts are over benchmark *items*, not hits: an item is counted once, at its strongest level.
Rates are lower bounds for the full corpus, because only a slice was scanned and only
copy-like overlap is detected. They say nothing about any particular model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contam.data.jsonl import read_jsonl
from contam.stats import wilson_interval

_LEVEL_RANK = {"PARTIAL": 1, "NEAR_DUPLICATE": 2, "EXACT": 3}


@dataclass(frozen=True, slots=True)
class BenchmarkRow:
    benchmark: str
    items: int
    indexed: int
    partial_or_more: int
    near_or_more: int
    exact: int

    def interval(self, count: int) -> tuple[float, float]:
        return wilson_interval(count, self.indexed)


@dataclass(frozen=True, slots=True)
class ScanReport:
    rows: list[BenchmarkRow]
    docs: int
    tokens: int
    hits: int
    finished: bool
    top_hits: list[dict[str, Any]]
    skipped: int


def build_report(scan_dir: str | Path, top: int = 10) -> ScanReport:
    folder = Path(scan_dir)
    meta = json.loads((folder / "scan_meta.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((folder / "checkpoint.json").read_text(encoding="utf-8"))
    strongest: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    for record in read_jsonl(folder / "hits.jsonl"):
        records.append(record)
        rank = _LEVEL_RANK[record["level"]]
        strongest[record["item_id"]] = max(strongest.get(record["item_id"], 0), rank)

    rows: list[BenchmarkRow] = []
    for benchmark, total in meta["items_by_benchmark"].items():
        ranks = [r for item_id, r in strongest.items() if item_id.split(":", 1)[0] == benchmark]
        rows.append(
            BenchmarkRow(
                benchmark=benchmark,
                items=int(total),
                indexed=int(meta["indexed_by_benchmark"].get(benchmark, 0)),
                partial_or_more=len(ranks),
                near_or_more=sum(r >= 2 for r in ranks),
                exact=sum(r >= 3 for r in ranks),
            )
        )
    records.sort(key=lambda r: (-_LEVEL_RANK[r["level"]], -r["containment"], r["item_id"]))
    return ScanReport(
        rows=rows,
        docs=int(checkpoint["docs_done"]),
        tokens=int(checkpoint["tokens_done"]),
        hits=int(checkpoint["hits_written"]),
        finished=bool(checkpoint["finished"]),
        top_hits=records[:top],
        skipped=len(meta["skipped"]),
    )


def format_report(report: ScanReport) -> str:
    status = "finished" if report.finished else "PARTIAL (scan not finished)"
    lines = [
        f"scan {status}: {report.docs:,} documents, {report.tokens:,} tokens, {report.hits:,} hits",
        "items flagged (at least one hit); 95% Wilson interval over indexed items",
        f"{'benchmark':16}{'items':>7}{'indexed':>9}"
        f"{'>= partial':>24}{'>= near-dup':>20}{'exact':>7}",
    ]
    for row in report.rows:
        low, high = row.interval(row.partial_or_more)
        partial = f"{row.partial_or_more} [{100 * low:.2f}%, {100 * high:.2f}%]"
        near_low, near_high = row.interval(row.near_or_more)
        near = f"{row.near_or_more} [{100 * near_low:.2f}%, {100 * near_high:.2f}%]"
        lines.append(
            f"{row.benchmark:16}{row.items:>7}{row.indexed:>9}{partial:>24}{near:>20}{row.exact:>7}"
        )
    lines.append(f"items skipped (too short or template-only): {report.skipped}")
    lines.append("These are lower bounds for a corpus SLICE and say nothing about any model.")
    for hit in report.top_hits:
        lines.append(
            f"{hit['level']:15} {hit['containment']:.2f}  {hit['item_id']}  in  {hit['doc_id']}"
        )
        if hit.get("snippet"):
            lines.append(f"      {hit['snippet'][:110]!r}")
    return "\n".join(lines)
