"""Compare scan folders from different corpora at item level, with intervals (RQ5, D-055).

    python scripts\\compare_scans.py --benchmark mmlu ^
        --scan edu=C:\\contam_scans\\edu_1b_mmlu --scan web=C:\\contam_scans\\web_1b_mmlu ^
        --labels edu=results\\labels.csv --labels web=results\\labels_web.csv

Counts are over benchmark items (an item counts once, at its strongest level). With --labels the
hand-labelled items are counted too (t = question text on a page, b = page quotes it). The
difference between the first two scans comes with a Newcombe 95% interval. Scans must use the
same settings and token budget for the comparison to mean anything.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

from contam.data.benchmarks import load_benchmark
from contam.exact import item_token_lengths
from contam.items import View
from contam.scan import read_hits
from contam.stats import wilson_interval

RANK = {"PARTIAL": 1, "NEAR_DUPLICATE": 2, "EXACT": 3}


@dataclass
class ScanSummary:
    name: str
    docs: int
    tokens: int
    hits: int
    best: dict[str, int]
    skipped: set[str]


def load_scan(name: str, folder: Path) -> ScanSummary:
    meta = json.loads((folder / "scan_meta.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((folder / "checkpoint.json").read_text(encoding="utf-8"))
    best: dict[str, int] = {}
    for hit in read_hits(folder):
        best[hit["item_id"]] = max(best.get(hit["item_id"], 0), RANK[hit["level"]])
    return ScanSummary(
        name=name,
        docs=int(checkpoint["docs_done"]),
        tokens=int(checkpoint["tokens_done"]),
        hits=int(checkpoint["hits_written"]),
        best=best,
        skipped={entry["item_id"] for entry in meta["skipped"]},
    )


def labelled_items(path: Path, benchmark: str) -> dict[str, set[str]]:
    """Items per label in a label_hits.py CSV, restricted to one benchmark."""
    found: dict[str, set[str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["label"] and row["item_id"].startswith(benchmark + ":"):
                found.setdefault(row["label"], set()).add(row["item_id"])
    return found


def newcombe(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """Difference of two proportions with Newcombe's hybrid-score 95% interval."""
    p1, p2 = k1 / n1, k2 / n2
    low1, high1 = wilson_interval(k1, n1)
    low2, high2 = wilson_interval(k2, n2)
    diff = p1 - p2
    lower = diff - math.sqrt((p1 - low1) ** 2 + (high2 - p2) ** 2)
    upper = diff + math.sqrt((high1 - p1) ** 2 + (p2 - low2) ** 2)
    return diff, lower, upper


def eligible_ids(
    benchmark: str, scan: ScanSummary, lengths: dict[str, int], minimum: int
) -> list[str]:
    return [
        item_id
        for item_id, length in lengths.items()
        if item_id.startswith(benchmark + ":") and item_id not in scan.skipped and length >= minimum
    ]


def pct(count: int, total: int) -> str:
    low, high = wilson_interval(count, total)
    return f"{count} ({100 * count / total:.2f}% [{100 * low:.2f}, {100 * high:.2f}])"


def compare(
    benchmark: str,
    scans: list[ScanSummary],
    lengths: dict[str, int],
    minimum: int,
    labels: dict[str, dict[str, set[str]]],
) -> list[str]:
    lines = [f"\n{benchmark}: items with >= {minimum} tokens, counted once at strongest level"]
    flagged: dict[str, dict[int, set[str]]] = {}
    sizes: dict[str, int] = {}
    for scan in scans:
        ids = eligible_ids(benchmark, scan, lengths, minimum)
        sizes[scan.name] = len(ids)
        flagged[scan.name] = {
            level: {i for i in ids if scan.best.get(i, 0) >= level} for level in (1, 2, 3)
        }
        per_million = 1e6 * scan.hits / max(scan.tokens, 1)
        lines.append(
            f"  {scan.name}: {scan.docs:,} docs, {scan.tokens:,} words, {scan.hits:,} hits "
            f"({per_million:.2f} per million words), {len(ids):,} eligible items"
        )
        for level, label in (
            (1, "partial or higher"),
            (2, "near-duplicate or higher"),
            (3, "exact"),
        ):
            lines.append(f"      {label:26}{pct(len(flagged[scan.name][level]), len(ids))}")
        verified = labels.get(scan.name, {})
        if verified:
            tru = len(verified.get("true_contamination", set()))
            tru_or_b = len(
                verified.get("true_contamination", set()) | verified.get("benign_discussion", set())
            )
            lines.append(f"      {'labelled t':26}{pct(tru, len(ids))}")
            lines.append(f"      {'labelled t or b':26}{pct(tru_or_b, len(ids))}")
    if len(scans) >= 2:
        a, b = scans[0], scans[1]
        lines.append(f"  difference ({a.name} minus {b.name}), percentage points, Newcombe 95%:")
        for level, label in (
            (1, "partial or higher"),
            (2, "near-duplicate or higher"),
            (3, "exact"),
        ):
            if sizes[a.name] and sizes[b.name]:
                diff, low, high = newcombe(
                    len(flagged[a.name][level]), sizes[a.name],
                    len(flagged[b.name][level]), sizes[b.name],
                )  # fmt: skip
                lines.append(
                    f"      {label:26}{100 * diff:+.2f} [{100 * low:+.2f}, {100 * high:+.2f}]"
                )
        for level, label in ((1, "partial or higher"), (2, "near-duplicate or higher")):
            both = flagged[a.name][level] & flagged[b.name][level]
            only_a = flagged[a.name][level] - flagged[b.name][level]
            only_b = flagged[b.name][level] - flagged[a.name][level]
            lines.append(
                f"  {label}: in both {len(both)}, only {a.name} {len(only_a)}, "
                f"only {b.name} {len(only_b)}"
            )
    return lines


def parse_pairs(values: list[str]) -> dict[str, Path]:
    pairs: dict[str, Path] = {}
    for value in values:
        name, _, path = value.partition("=")
        if not name or not path:
            raise SystemExit(f"expected NAME=PATH, got {value!r}")
        pairs[name] = Path(path)
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare scan folders at item level.")
    parser.add_argument("--scan", action="append", required=True, help="NAME=FOLDER (repeatable)")
    parser.add_argument("--labels", action="append", default=[], help="NAME=labels.csv")
    parser.add_argument("--benchmark", action="append", required=True)
    parser.add_argument("--view", choices=[v.value for v in View], default="question_choices")
    parser.add_argument("--min-tokens", type=int, default=0)
    args = parser.parse_args()

    scans = [load_scan(name, folder) for name, folder in parse_pairs(args.scan).items()]
    label_files = parse_pairs(args.labels)
    for benchmark in args.benchmark:
        items = load_benchmark(benchmark)
        lengths = dict(
            zip((i.item_id for i in items), item_token_lengths(items, View(args.view)), strict=True)
        )
        labels = {name: labelled_items(path, benchmark) for name, path in label_files.items()}
        print("\n".join(compare(benchmark, scans, lengths, args.min_tokens, labels)))


if __name__ == "__main__":
    main()
