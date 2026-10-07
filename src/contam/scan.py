"""Phase 6: a checkpointed, multi-process scan of a corpus stream (D-047 to D-051).

Design:
  * The main process streams documents and cuts them into batches. A bounded number of
    batches are in flight in a ``spawn`` process pool (identical behaviour on Windows,
    macOS and Linux), so memory stays flat however large the corpus is.
  * Results are committed strictly in batch order, so the output file is byte-identical
    whether you use one worker or many.
  * After every committed batch the hits file is flushed and a checkpoint is written
    atomically. The checkpoint records how many documents are done and the exact byte size of
    the hits file, so a resumed run discards any half-written tail and never duplicates or
    loses a hit (exactly-once).
  * A fingerprint of every setting that affects results is stored in the checkpoint; a resume
    with different settings is refused.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, cast

from contam.data.jsonl import read_jsonl
from contam.exact import ExactIndex, Hit, ScanStats, Thresholds
from contam.items import BenchmarkItem, View

RawDocument = tuple[str, object]


class ScanError(Exception):
    """A scan cannot start or resume safely."""


@dataclass(frozen=True, slots=True)
class ScanConfig:
    n: int = 3
    view: View = View.QUESTION_CHOICES
    partial: float = 0.5
    near_duplicate: float = 0.9
    window_slack: float | None = 1.5
    stop_ngram_k: int | None = None
    min_tokens: int | None = None
    snippet_chars: int = 200
    batch_docs: int = 500
    workers: int = 1
    source: str = ""  # identifies the corpus slice; part of the resume fingerprint


@dataclass(frozen=True, slots=True)
class ScanResult:
    out_dir: Path
    docs: int
    tokens: int
    hits: int
    malformed: int
    seconds: float
    resumed_from_docs: int
    finished: bool


@dataclass(frozen=True, slots=True)
class _BatchResult:
    hits: list[Hit]
    batch_docs: int
    tokens: int
    malformed: int


# --------------------------------------------------------------------------- worker side
_WORKER: dict[str, Any] = {}


def _init_worker(items: Sequence[BenchmarkItem], config: ScanConfig) -> None:
    _WORKER["index"] = ExactIndex.build(
        items,
        view=config.view,
        n=config.n,
        stop_ngram_k=config.stop_ngram_k,
        min_tokens=config.min_tokens,
    )
    _WORKER["config"] = config


def _scan_batch(batch: list[RawDocument]) -> _BatchResult:
    index: ExactIndex = _WORKER["index"]
    config: ScanConfig = _WORKER["config"]
    stats = ScanStats()
    hits = list(
        index.scan_corpus(
            batch,
            Thresholds(config.partial, config.near_duplicate),
            stats,
            window_slack=config.window_slack,
            snippet_chars=config.snippet_chars,
        )
    )
    return cast(_BatchResult, _BatchResult(hits, len(batch), stats.tokens, stats.malformed))


# --------------------------------------------------------------------------- file helpers
def _hit_record(hit: Hit) -> dict[str, Any]:
    return {
        "item_id": hit.item_id,
        "doc_id": hit.doc_id,
        "level": hit.level.name,
        "containment": round(hit.containment, 4),
        "matched_ngrams": hit.matched_ngrams,
        "total_ngrams": hit.total_ngrams,
        "ngram_size": hit.ngram_size,
        "exact": hit.exact,
        "short": hit.short,
        "window_start": hit.window_start,
        "snippet": hit.snippet,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write via a temp file and ``os.replace``; retry because OneDrive/antivirus may lock."""
    temporary = path.with_name(path.name + ".tmp")
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary.write_text(text, encoding="utf-8", newline="\n")
    for attempt in range(8):
        try:
            os.replace(temporary, path)
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.25)
        else:
            return


def _fingerprint(items: Sequence[BenchmarkItem], config: ScanConfig) -> dict[str, Any]:
    digest = hashlib.blake2b(digest_size=16)
    for line in sorted(f"{item.item_id}\x00{item.text(config.view)}" for item in items):
        digest.update(line.encode("utf-8", "surrogatepass"))
    return {
        "items_digest": digest.hexdigest(),
        "n_items": len(items),
        "n": config.n,
        "view": str(config.view),
        "partial": config.partial,
        "near_duplicate": config.near_duplicate,
        "window_slack": config.window_slack,
        "stop_ngram_k": config.stop_ngram_k,
        "min_tokens": config.min_tokens,
        "snippet_chars": config.snippet_chars,
        "source": config.source,
    }


def _batched(documents: Iterable[RawDocument], size: int) -> Iterator[list[RawDocument]]:
    batch: list[RawDocument] = []
    for document in documents:
        batch.append(document)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def _benchmark_of(item_id: str) -> str:
    return item_id.split(":", 1)[0]


# --------------------------------------------------------------------------- the scan
def run_scan(
    items: Sequence[BenchmarkItem],
    documents: Callable[[], Iterable[RawDocument]],
    config: ScanConfig,
    out_dir: str | Path,
    *,
    resume: bool = False,
    overwrite: bool = False,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> ScanResult:
    """Scan ``documents()`` for ``items``, writing ``hits.jsonl`` and ``checkpoint.json``.

    ``documents`` is a factory so a resumed run can re-create the same stream and skip the
    documents already processed. It must yield the same documents in the same order.
    """
    if config.batch_docs < 1 or config.workers < 1:
        raise ValueError("batch_docs and workers must be >= 1")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    hits_path = out / "hits.jsonl"
    checkpoint_path = out / "checkpoint.json"
    meta_path = out / "scan_meta.json"
    fingerprint = _fingerprint(items, config)

    state: dict[str, Any] = {
        "docs_done": 0,
        "tokens_done": 0,
        "hits_bytes": 0,
        "hits_written": 0,
        "malformed": 0,
        "elapsed": 0.0,
        "finished": False,
    }
    has_checkpoint = checkpoint_path.exists()
    if overwrite:
        for stale in (hits_path, checkpoint_path):
            stale.unlink(missing_ok=True)
        has_checkpoint = False
    elif has_checkpoint and not resume:
        raise ScanError("a checkpoint exists in this folder; pass resume=True or overwrite=True")
    elif not has_checkpoint and hits_path.exists():
        raise ScanError("hits.jsonl exists without a checkpoint; pass overwrite=True")

    resumed_from = 0
    if has_checkpoint:
        saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if saved["fingerprint"] != fingerprint:
            raise ScanError("checkpoint was made with different settings; refusing to resume")
        state.update({key: saved[key] for key in state})
        resumed_from = int(state["docs_done"])
        size = hits_path.stat().st_size if hits_path.exists() else 0
        if size < state["hits_bytes"]:
            raise ScanError("hits.jsonl is shorter than the checkpoint says; it was modified")
        if size > state["hits_bytes"]:  # a crash left a half-written batch: discard it
            with hits_path.open("r+b") as handle:
                handle.truncate(state["hits_bytes"])

    def write_checkpoint() -> None:
        _atomic_write_json(checkpoint_path, {**state, "fingerprint": fingerprint})

    def result() -> ScanResult:
        return ScanResult(
            out,
            int(state["docs_done"]),
            int(state["tokens_done"]),
            int(state["hits_written"]),
            int(state["malformed"]),
            float(state["elapsed"]),
            resumed_from,
            bool(state["finished"]),
        )

    if state["finished"]:
        return result()

    index = ExactIndex.build(
        items,
        view=config.view,
        n=config.n,
        stop_ngram_k=config.stop_ngram_k,
        min_tokens=config.min_tokens,
    )
    meta = {
        "fingerprint": fingerprint,
        "items_by_benchmark": _count(_benchmark_of(item.item_id) for item in items),
        "indexed_by_benchmark": _count(_benchmark_of(i) for i in index.indexed_item_ids),
        "skipped": [{"item_id": s.item_id, "reason": s.reason} for s in index.skipped],
        "table_size": index.table_size,
    }
    _atomic_write_json(meta_path, meta)

    started = time.perf_counter()
    base_elapsed = float(state["elapsed"])
    handle = hits_path.open("ab")  # type: ignore[assignment]
    pool = None
    if config.workers > 1:
        context = multiprocessing.get_context("spawn")
        pool = context.Pool(config.workers, _init_worker, (list(items), config))
    else:
        _init_worker(items, config)

    pending: deque[Any] = deque()
    in_flight = max(1, config.workers * 2)

    def resolve(task: Any) -> _BatchResult:
        return task if pool is None else task.get()  # type: ignore[no-any-return]

    def commit(batch_result: _BatchResult) -> None:
        payload = "".join(
            json.dumps(_hit_record(hit), ensure_ascii=False) + "\n" for hit in batch_result.hits
        )
        handle.write(payload.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
        state["hits_bytes"] = hits_path.stat().st_size
        state["hits_written"] += len(batch_result.hits)
        state["docs_done"] += batch_result.batch_docs
        state["tokens_done"] += batch_result.tokens
        state["malformed"] += batch_result.malformed
        state["elapsed"] = base_elapsed + (time.perf_counter() - started)
        write_checkpoint()
        if progress is not None:
            progress(dict(state))

    try:
        stream = islice(documents(), int(state["docs_done"]), None)
        for batch in _batched(stream, config.batch_docs):
            task = pool.apply_async(_scan_batch, (batch,)) if pool else _scan_batch(batch)
            pending.append(task)
            while len(pending) >= in_flight:
                commit(resolve(pending.popleft()))
        while pending:
            commit(resolve(pending.popleft()))
        state["finished"] = True
        write_checkpoint()
    except BaseException:
        # Keep every batch that finished before the failure, in order, then re-raise.
        try:
            while pending:
                commit(resolve(pending.popleft()))
        except Exception:  # noqa: S110 - the original error is the one worth reporting
            pass
        raise
    finally:
        handle.close()
        if pool is not None:
            pool.terminate()
            pool.join()
    return result()


def _count(names: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def read_hits(scan_dir: str | Path) -> Iterator[dict[str, Any]]:
    """Yield the hit records of a finished or partial scan."""
    return read_jsonl(Path(scan_dir) / "hits.jsonl")
