"""Keep only the hits of benchmark items with at least N tokens (DECISIONS.md, D-053, D-057).

    python scripts\\filter_scan_by_length.py C:\\contam_scans\\edu_1b_mmlu_q ^
        --benchmark mmlu --view question --min-tokens 12 --out C:\\contam_scans\\edu_1b_mmlu_q_ge12

Prints, for several minimum lengths, how many items are eligible and how many are flagged at
each level. With --out it also writes a filtered scan folder that works with label_hits.py
(--all) and 'contam report' (rates in that report are diluted, so use it for labelling only).
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from contam.data.benchmarks import load_benchmark
from contam.exact import item_token_lengths
from contam.items import View
from contam.scan import read_hits
from contam.stats import wilson_interval

RANK = {"PARTIAL": 1, "NEAR_DUPLICATE": 2, "EXACT": 3}


def strongest(hits: list[dict[str, Any]]) -> dict[str, int]:
    """Strongest level (1 to 3) reached by each item."""
    best: dict[str, int] = {}
    for hit in hits:
        best[hit["item_id"]] = max(best.get(hit["item_id"], 0), RANK[hit["level"]])
    return best


def table(
    lengths: dict[str, int], skipped: set[str], best: dict[str, int], minimums: list[int]
) -> list[str]:
    lines = [f"{'min tokens':>10}{'eligible':>10}{'>= partial':>26}{'>= near-dup':>24}{'exact':>7}"]
    for minimum in minimums:
        eligible = [i for i, n in lengths.items() if n >= minimum and i not in skipped]
        flagged = [best.get(i, 0) for i in eligible]
        cells = []
        for level in (1, 2):
            count = sum(r >= level for r in flagged)
            low, high = wilson_interval(count, len(eligible))
            cells.append(f"{count} [{100 * low:.2f}%, {100 * high:.2f}%]")
        exact = sum(r >= 3 for r in flagged)
        lines.append(f"{minimum:>10}{len(eligible):>10}{cells[0]:>26}{cells[1]:>24}{exact:>7}")
    return lines


def filter_hits(
    hits: list[dict[str, Any]], lengths: dict[str, int], minimum: int
) -> list[dict[str, Any]]:
    return [hit for hit in hits if lengths.get(hit["item_id"], 0) >= minimum]


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter a scan folder by item length.")
    parser.add_argument("scan", type=Path)
    parser.add_argument("--benchmark", default="mmlu")
    parser.add_argument("--view", choices=[v.value for v in View], default="question")
    parser.add_argument("--min-tokens", type=int, default=12)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    items = load_benchmark(args.benchmark)
    lengths = dict(
        zip(
            (item.item_id for item in items),
            item_token_lengths(items, View(args.view)),
            strict=True,
        )
    )
    meta = json.loads((args.scan / "scan_meta.json").read_text(encoding="utf-8"))
    skipped = {entry["item_id"] for entry in meta["skipped"]}
    hits = list(read_hits(args.scan))
    print(f"{len(hits):,} hits in {args.scan}")
    best = strongest(hits)
    minimums = sorted({3, 8, 12, 20, 30, args.min_tokens})
    print("\n".join(table(lengths, skipped, best, minimums)))

    if args.out is not None:
        kept = filter_hits(hits, lengths, args.min_tokens)
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "hits.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for hit in kept:
                handle.write(json.dumps(hit, ensure_ascii=False) + "\n")
        for name in ("scan_meta.json", "checkpoint.json"):
            shutil.copy(args.scan / name, args.out / name)
        print(f"\nwrote {len(kept):,} hits of items with >= {args.min_tokens} tokens to {args.out}")


if __name__ == "__main__":
    main()
