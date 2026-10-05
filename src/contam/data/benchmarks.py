"""Benchmark loaders: pure row converters (testable offline) plus thin Hugging Face wrappers.

Converters take one raw dataset row and return a :class:`~contam.items.BenchmarkItem`.
They contain all the logic worth testing and need no network. The loader functions only
fetch rows and call a converter.

Always pass ``revision`` (a dataset commit hash) for reproducible runs (DECISIONS.md, D-015).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contam.data.jsonl import read_jsonl
from contam.items import BenchmarkItem

_LETTERS = "ABCDEFGHIJ"


def gsm8k_item(row: Mapping[str, Any], index: int, split: str) -> BenchmarkItem:
    """Convert a row of ``openai/gsm8k`` (config ``main``)."""
    return BenchmarkItem(
        item_id=f"gsm8k:{split}:{index}",
        benchmark="gsm8k",
        split=split,
        question=str(row["question"]),
        answer=str(row["answer"]),
    )


def arc_item(row: Mapping[str, Any], index: int, split: str) -> BenchmarkItem:
    """Convert a row of ``allenai/ai2_arc`` (config ``ARC-Challenge``)."""
    choices = tuple(str(text) for text in row["choices"]["text"])
    return BenchmarkItem(
        item_id=f"arc_challenge:{split}:{row.get('id', index)}",
        benchmark="arc_challenge",
        split=split,
        question=str(row["question"]),
        choices=choices,
        answer=str(row["answerKey"]),
    )


def mmlu_item(row: Mapping[str, Any], index: int, split: str) -> BenchmarkItem:
    """Convert a row of ``cais/mmlu`` (config ``all``). ``answer`` is an index 0-3."""
    choices = tuple(str(text) for text in row["choices"])
    answer_index = int(row["answer"])
    if not 0 <= answer_index < len(choices):
        raise ValueError(f"MMLU row {index}: answer index {answer_index} out of range")
    return BenchmarkItem(
        item_id=f"mmlu:{split}:{index}",
        benchmark="mmlu",
        split=split,
        question=str(row["question"]),
        choices=choices,
        answer=_LETTERS[answer_index],
    )


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    hf_path: str
    hf_config: str
    convert: Callable[[Mapping[str, Any], int, str], BenchmarkItem]


BENCHMARKS: dict[str, BenchmarkSpec] = {
    "gsm8k": BenchmarkSpec("openai/gsm8k", "main", gsm8k_item),
    "arc_challenge": BenchmarkSpec("allenai/ai2_arc", "ARC-Challenge", arc_item),
    "mmlu": BenchmarkSpec("cais/mmlu", "all", mmlu_item),
}


def load_benchmark(
    name: str, split: str = "test", revision: str | None = None
) -> list[BenchmarkItem]:
    """Download one benchmark split and convert it to :class:`BenchmarkItem` objects.

    Requires the ``data`` extra (``pip install -e ".[data]"``) and internet access.
    """
    if name not in BENCHMARKS:
        raise ValueError(f"unknown benchmark {name!r}; choose from {sorted(BENCHMARKS)}")
    spec = BENCHMARKS[name]
    datasets = importlib.import_module("datasets")
    rows = datasets.load_dataset(spec.hf_path, spec.hf_config, split=split, revision=revision)
    return [spec.convert(row, index, split) for index, row in enumerate(rows)]


def load_items_jsonl(path: str | Path, benchmark: str | None = None) -> list[BenchmarkItem]:
    """Load items from a JSONL file with ``item_id`` and ``question`` (``choices`` optional).

    Handy for offline runs, test fixtures and custom benchmarks.
    """
    name = benchmark or Path(path).stem
    items: list[BenchmarkItem] = [
        BenchmarkItem(
            item_id=str(row["item_id"]),
            benchmark=str(row.get("benchmark", name)),
            split=str(row.get("split", "test")),
            question=str(row["question"]),
            choices=tuple(str(choice) for choice in row.get("choices", ())),
            answer=str(row.get("answer", "")),
        )
        for row in read_jsonl(path)
    ]
    return items
