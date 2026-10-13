import statistics

from contam.data.benchmarks import load_benchmark
from contam.exact import item_token_lengths
from contam.items import View

for name in ("arc_challenge", "gsm8k"):
    lengths = item_token_lengths(load_benchmark(name), View.QUESTION_CHOICES)
    print(
        name,
        "min",
        min(lengths),
        "median",
        statistics.median(lengths),
        "under 15 tokens:",
        sum(length < 15 for length in lengths),
    )
