"""Build a self-contained HTML page for a SECOND annotator (D-012, D-056).

    python scripts\\make_annotation_pack.py --labels results\\labels.csv --labels results\\labels_q.csv ^
        --per-label t=20 --per-label p=15 --per-label b=10 --per-label c=10 --seed 7 ^
        --out annotation_pack.html --key annotation_key.csv

The page needs no Python and no internet: the second person opens it in a browser, labels each
row, and clicks "Download labels CSV". Your own labels are NOT in the page; they go to the key
file (keep it private). After the second annotator returns their CSV:

    python scripts\\agreement.py annotation_key.csv annotator2_labels.csv

The page contains benchmark question text: share it privately, never publish or commit it.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

from contam.data.benchmarks import load_benchmark

LABEL_NAMES = {
    "t": "true_contamination",
    "p": "shared_source_text",
    "c": "coincidental",
    "b": "benign_discussion",
}

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Labelling pack</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
.card { border: 1px solid #bbb; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
pre { white-space: pre-wrap; background: #f4f4f4; padding: .6rem; border-radius: 6px; }
label { display: block; margin: .25rem 0; }
#bar { position: sticky; top: 0; background: #fff; padding: .5rem 0; border-bottom: 1px solid #ccc; }
.rubric { background: #fffbe6; border: 1px solid #e6d98a; padding: .8rem 1rem; border-radius: 8px; }
</style></head><body>
<h1>Labelling pack</h1>
<div class="rubric">
<p>Each row shows a <b>benchmark question</b> and a short, lower-cased <b>excerpt from a web page</b>.
Decide how the page relates to the question. Judge only from what you see; if unsure, pick the
closest option. Your progress is saved in this browser.</p>
<ul>
<li><b>Contains the question (a copy):</b> the page presents this question (the question sentence,
with or without answer options or an answer), for example as a quiz or exam item.</li>
<li><b>Quotes only the same source passage:</b> the question quotes a text (a speech, a historical
passage), and the page contains that text but not the question itself.</li>
<li><b>Only a coincidental phrase overlap:</b> the page shares ordinary words or a common fact with
the question but is not about the question.</li>
<li><b>Quotes or discusses the question:</b> an article, forum post or explanation that quotes or
analyses this question.</li>
</ul></div>
<div id="bar"><span id="progress"></span>
<button id="download">Download labels CSV</button></div>
<div id="rows"></div>
<script>
const ROWS = __DATA__;
const LABELS = [
  ["true_contamination", "Contains the question (a copy)"],
  ["shared_source_text", "Quotes only the same source passage"],
  ["coincidental", "Only a coincidental phrase overlap"],
  ["benign_discussion", "Quotes or discusses the question"]
];
const KEY = "labelling-pack-v1";
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { state = {}; }
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
function progress() {
  const done = ROWS.filter(function (r) { return state[r.id]; }).length;
  document.getElementById("progress").textContent = done + " of " + ROWS.length + " labelled  ";
}
const container = document.getElementById("rows");
ROWS.forEach(function (row, index) {
  const card = document.createElement("div");
  card.className = "card";
  const head = document.createElement("h3");
  head.textContent = "Row " + (index + 1) + " of " + ROWS.length;
  const q = document.createElement("div");
  q.textContent = "Benchmark question:";
  const item = document.createElement("pre");
  item.textContent = row.item;
  const p = document.createElement("div");
  p.textContent = "Web page excerpt (normalized):";
  const excerpt = document.createElement("pre");
  excerpt.textContent = row.excerpt;
  card.append(head, q, item, p, excerpt);
  LABELS.forEach(function (pair) {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "r" + index;
    input.value = pair[0];
    input.checked = state[row.id] === pair[0];
    input.addEventListener("change", function () {
      state[row.id] = pair[0]; save(); progress();
    });
    label.append(input, " " + pair[1]);
    card.append(label);
  });
  container.append(card);
});
function cell(s) { return '"' + String(s).replace(/"/g, '""') + '"'; }
document.getElementById("download").addEventListener("click", function () {
  const lines = ["item_id,doc_id,label"];
  ROWS.forEach(function (r) {
    lines.push([cell(r.item_id), cell(r.doc_id), cell(state[r.id] || "")].join(","));
  });
  const blob = new Blob([lines.join("\\n") + "\\n"], { type: "text/csv" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "annotator2_labels.csv";
  link.click();
});
progress();
</script></body></html>
"""


def read_labelled(paths: list[Path]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = (row["item_id"], row["doc_id"])
                if row["label"] and key not in seen:
                    seen.add(key)
                    rows.append(row)
    return rows


def choose(
    rows: list[dict[str, str]], per_label: dict[str, int], seed: int
) -> list[dict[str, str]]:
    """Pick rows per first-annotator label, at most one row per item, then shuffle."""
    rng = random.Random(seed)
    chosen: list[dict[str, str]] = []
    used_items: set[str] = set()
    for short, count in per_label.items():
        pool = [r for r in rows if r["label"] == LABEL_NAMES[short]]
        rng.shuffle(pool)
        taken = 0
        for row in pool:
            if taken >= count:
                break
            if row["item_id"] in used_items:
                continue
            used_items.add(row["item_id"])
            chosen.append(row)
            taken += 1
    rng.shuffle(chosen)
    return chosen


def render(rows: list[dict[str, str]], texts: dict[str, str]) -> str:
    data: list[dict[str, Any]] = [
        {
            "id": f"{row['item_id']}|{row['doc_id']}",
            "item_id": row["item_id"],
            "doc_id": row["doc_id"],
            "item": texts[row["item_id"]],
            "excerpt": row["snippet"],
        }
        for row in rows
    ]
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return PAGE.replace("__DATA__", payload)


def parse_per_label(values: list[str]) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for value in values:
        key, _, count = value.partition("=")
        if key not in LABEL_NAMES or not count.isdigit():
            raise SystemExit(
                f"--per-label expects one of {sorted(LABEL_NAMES)}=COUNT, got {value!r}"
            )
        parsed[key] = int(count)
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a labelling pack for a second annotator.")
    parser.add_argument("--labels", type=Path, action="append", required=True)
    parser.add_argument("--per-label", action="append", default=[])
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("annotation_pack.html"))
    parser.add_argument("--key", type=Path, default=Path("annotation_key.csv"))
    args = parser.parse_args()

    per_label = parse_per_label(args.per_label) or {"t": 20, "p": 15, "b": 10, "c": 10}
    rows = choose(read_labelled(args.labels), per_label, args.seed)
    prefixes = sorted({row["item_id"].split(":", 1)[0] for row in rows})
    texts = {i.item_id: i.text() for name in prefixes for i in load_benchmark(name)}
    args.out.write_text(render(rows, texts), encoding="utf-8")
    with args.key.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["item_id", "doc_id", "label"])
        writer.writerows((r["item_id"], r["doc_id"], r["label"]) for r in rows)
    print(f"{len(rows)} rows -> {args.out}; your labels (keep private) -> {args.key}")


if __name__ == "__main__":
    main()
