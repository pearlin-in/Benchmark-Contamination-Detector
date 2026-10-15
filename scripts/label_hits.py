"""Hand-label scan hits in the terminal (DECISIONS.md, D-012).

The first run builds a sample and saves it; later runs resume where you stopped. Rows are
ordered strongest-first, so stopping early still covers the hits that matter most.

--all PATH      include every hit of that scan (repeatable)
--sampled PATH  include the top --top hits by containment plus --random random others

Labels:
  t  the page contains the test item itself (a copy)
  p  the page quotes the same SOURCE text the question quotes (e.g. a historical speech)
  c  only a coincidental phrase overlap
  b  an honest discussion or quote of the question
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path
from typing import Any

from contam.data.benchmarks import load_benchmark
from contam.scan import read_hits
from contam.stats import wilson_interval

FIELDS = ["stratum", "item_id", "doc_id", "level", "containment", "snippet", "label"]
LABELS = {
    "t": "true_contamination",
    "p": "shared_source_text",
    "c": "coincidental",
    "b": "benign_discussion",
}


def _ranked(folder: Path) -> list[dict[str, Any]]:
    return sorted(read_hits(folder), key=lambda h: (-h["containment"], h["item_id"], h["doc_id"]))


def build_sample(args: argparse.Namespace) -> None:
    chosen: list[tuple[str, dict[str, Any]]] = []
    for folder in args.all:
        chosen += [(folder.name, hit) for hit in _ranked(folder)]
    for folder in args.sampled:
        ranked = _ranked(folder)
        chosen += [(f"{folder.name}_top", hit) for hit in ranked[: args.top]]
        rest = ranked[args.top :]
        picked = random.Random(args.seed).sample(rest, min(args.random, len(rest)))
        chosen += [(f"{folder.name}_random", hit) for hit in picked]
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for stratum, hit in chosen:
            writer.writerow(
                {
                    "stratum": stratum,
                    "item_id": hit["item_id"],
                    "doc_id": hit["doc_id"],
                    "level": hit["level"],
                    "containment": hit["containment"],
                    "snippet": hit["snippet"],
                    "label": "",
                }
            )
    print(f"built a sample of {len(chosen)} hits in {args.out}")


def save(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, str]]) -> None:
    print("\nlabels so far")
    for stratum in dict.fromkeys(row["stratum"] for row in rows):
        labelled = [r["label"] for r in rows if r["stratum"] == stratum and r["label"]]
        counts = Counter(labelled)
        low, high = wilson_interval(counts["true_contamination"], len(labelled))
        interval = f"  true share 95% interval [{100 * low:.1f}%, {100 * high:.1f}%]"
        print(f"  {stratum:22} labelled {len(labelled):3}  {dict(counts)}", end="")
        print(interval if labelled else "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hand-label scan hits.")
    parser.add_argument("--all", type=Path, action="append", default=[])
    parser.add_argument("--sampled", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, default=Path("results/labels.csv"))
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--random", type=int, default=20)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    if not args.out.exists():
        if not args.all and not args.sampled:
            parser.error("give at least one --all or --sampled scan folder")
        build_sample(args)

    with args.out.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    needed = sorted({row["item_id"].split(":", 1)[0] for row in rows})
    items = {item.item_id: item for name in needed for item in load_benchmark(name)}
    todo = [row for row in rows if not row["label"]]
    print(f"{len(rows) - len(todo)} labelled, {len(todo)} to go.")
    print("t = true copy, p = shared source text, c = coincidental, b = benign discussion")
    print("s = skip, q = quit (progress is saved after every label)")
    for number, row in enumerate(todo, start=1):
        print("-" * 78)
        print(f"[{number}/{len(todo)}] {row['stratum']}  {row['level']}  {row['containment']}")
        print("BENCHMARK ITEM:", items[row["item_id"]].text()[:700].replace("\n", " | "))
        print("PAGE EXCERPT  :", row["snippet"])
        key = ""
        while key not in {*LABELS, "s", "q"}:
            key = input("label [t/p/c/b/s/q]: ").strip().lower()
        if key == "q":
            break
        if key != "s":
            row["label"] = LABELS[key]
            save(args.out, rows)
    summarize(rows)


if __name__ == "__main__":
    main()
