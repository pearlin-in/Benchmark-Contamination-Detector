import sys
from collections import Counter

from contam.data.benchmarks import load_benchmark
from contam.exact import item_token_lengths
from contam.items import View
from contam.scan import read_hits

items = [item for name in ("arc_challenge", "gsm8k") for item in load_benchmark(name)]
lengths = dict(
    zip(
        (item.item_id for item in items),
        item_token_lengths(items, View.QUESTION_CHOICES),
        strict=True,
    )
)
hits: Counter[str] = Counter()
distinct: dict[str, set[str]] = {"short": set(), "long": set()}
for folder in sys.argv[1:]:
    for hit in read_hits(folder):
        bucket = "short" if lengths[hit["item_id"]] < 15 else "long"
        hits[bucket] += 1
        distinct[bucket].add(hit["item_id"])
print("hits:", dict(hits))
print("distinct items hit:", {k: len(v) for k, v in distinct.items()})
print("short items in benchmark:", sum(v < 15 for v in lengths.values()), "of", len(lengths))
