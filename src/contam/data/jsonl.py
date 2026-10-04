"""Minimal JSON Lines reader/writer. Always UTF-8, so behaviour is identical on Windows."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield one dict per non-empty line of a UTF-8 JSONL file."""
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON ({error.msg})") from error
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object per line")
            yield record


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> int:
    """Write records as UTF-8 JSONL and return how many were written."""
    count = 0
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count
