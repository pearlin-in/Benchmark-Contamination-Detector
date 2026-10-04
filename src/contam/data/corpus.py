"""Streaming corpus access: documents are never stored on disk (DECISIONS.md, D-007, D-018)."""

from __future__ import annotations

import importlib
from collections.abc import Iterable, Iterator
from typing import Any

Document = tuple[str, str]  # (doc_id, text)


def limit_documents(
    rows: Iterable[dict[str, Any]],
    *,
    max_docs: int | None = None,
    max_tokens: int | None = None,
) -> Iterator[Document]:
    """Yield ``(doc_id, text)`` from raw rows until a document or token budget is reached.

    ``max_tokens`` uses each row's ``token_count`` field when present (FineWeb provides
    it). Rows with a missing ``id`` get a positional id so results stay traceable.
    """
    docs_seen = 0
    tokens_seen = 0
    for position, row in enumerate(rows):
        if max_docs is not None and docs_seen >= max_docs:
            return
        if max_tokens is not None and tokens_seen >= max_tokens:
            return
        yield str(row.get("id", f"row-{position}")), row.get("text", "")
        docs_seen += 1  # noqa: SIM113
        tokens_seen += int(row.get("token_count", 0) or 0)


def stream_documents(
    path: str = "HuggingFaceFW/fineweb",
    name: str = "sample-10BT",
    *,
    split: str = "train",
    max_docs: int | None = None,
    max_tokens: int | None = None,
    revision: str | None = None,
) -> Iterator[Document]:
    """Stream a Hugging Face corpus as ``(doc_id, text)`` pairs.

    Requires the ``data`` extra and internet access. Pass ``max_tokens`` to define a
    corpus slice tier (S ~ 1e8, M ~ 1e9 tokens).
    """
    datasets = importlib.import_module("datasets")
    stream = datasets.load_dataset(path, name, split=split, streaming=True, revision=revision)
    yield from limit_documents(stream, max_docs=max_docs, max_tokens=max_tokens)
