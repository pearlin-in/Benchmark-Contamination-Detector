"""Compare a relabelled sample against the original labels (inter-pass agreement).

python scripts\\agreement.py results\\labels.csv results\\relabel.csv
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


def load(path: str) -> dict[tuple[str, str], str]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return {(r["item_id"], r["doc_id"]): r["label"] for r in csv.DictReader(handle)}


def main() -> None:
    first, second = load(sys.argv[1]), load(sys.argv[2])
    pairs = [(first[key], second[key]) for key in second if key in first and second[key]]
    if not pairs:
        sys.exit("no relabelled rows found")
    agree = sum(a == b for a, b in pairs)
    print(f"{len(pairs)} rows compared, {agree} agree ({100 * agree / len(pairs):.0f}%)")
    count_a, count_b = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(count_a[k] * count_b[k] for k in count_a) / len(pairs) ** 2
    kappa = (agree / len(pairs) - expected) / (1 - expected) if expected < 1 else 1.0
    print(f"Cohen's kappa: {kappa:.2f}")
    for (a, b), n in sorted(Counter(pairs).items(), key=lambda kv: -kv[1]):
        marker = "" if a == b else "   <-- disagreement"
        print(f"  first={a:20} second={b:20} {n}{marker}")


if __name__ == "__main__":
    main()
