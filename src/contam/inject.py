"""Planted-contamination corpora: the ground truth for validating the detector (D-012, D-036).

A real corpus has no labels, so recall cannot be measured on it. Instead we *create*
labels: take background documents, insert benchmark items (corrupted in known ways) at known
positions, and record exactly what was planted where. A perfect detector would find every
plant and nothing else.

Design rules:
  * One planted item per document, so every (document, item) pair is unambiguous.
  * Every record's randomness is derived from ``(seed, spec, item id)`` only. Adding a
    corruption spec or reordering items never changes any other record (D-035).
  * The manifest stores offsets, lengths and digests, never corpus or benchmark text (D-017).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contam.corrupt import DEFAULT_SPECS, CorruptionSpec, apply_corruption
from contam.data.jsonl import read_jsonl, write_jsonl
from contam.items import BenchmarkItem
from contam.synthetic import make_rng

Document = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Plant:
    """Ground-truth record: ``item_id`` was planted in ``doc_id`` under corruption ``spec``."""

    doc_id: str
    item_id: str
    spec: str  # e.g. "word_delete@0.1"
    kind: str
    intensity: float | None
    host_doc_id: str
    offset: int  # where the planted text starts inside the document
    length: int
    digest: str  # blake2b of the planted text, to verify a manifest without shipping text

    def to_record(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "item_id": self.item_id,
            "spec": self.spec,
            "kind": self.kind,
            "intensity": self.intensity,
            "host_doc_id": self.host_doc_id,
            "offset": self.offset,
            "length": self.length,
            "digest": self.digest,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Plant:
        intensity = record["intensity"]
        return cls(
            doc_id=str(record["doc_id"]),
            item_id=str(record["item_id"]),
            spec=str(record["spec"]),
            kind=str(record["kind"]),
            intensity=None if intensity is None else float(intensity),
            host_doc_id=str(record["host_doc_id"]),
            offset=int(record["offset"]),
            length=int(record["length"]),
            digest=str(record["digest"]),
        )


@dataclass(slots=True)
class PlantedCorpus:
    """Planted documents, untouched control documents, and the ground-truth manifest."""

    documents: list[Document]
    plants: list[Plant]
    control_doc_ids: list[str]
    seed: int
    shortfalls: dict[str, int] = field(default_factory=dict)  # spec -> plants actually made

    def text_of(self, doc_id: str) -> str:
        for candidate, text in self.documents:
            if candidate == doc_id:
                return text
        raise KeyError(doc_id)


def text_digest(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=8).hexdigest()


def _trim_host(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)
    return text[: cut if cut > 0 else max_chars]


def _insertion_points(host: str) -> list[int]:
    paragraph_starts = [match.end() for match in re.finditer(r"\n{2,}", host)]
    if paragraph_starts:
        return [0, *paragraph_starts, len(host)]
    return [0, *[match.start() for match in re.finditer(" ", host)], len(host)]


def _order_key(seed: int, spec_label: str, item_id: str) -> bytes:
    key = f"{seed}|order|{spec_label}|{item_id}".encode("utf-8", "surrogatepass")
    return hashlib.blake2b(key, digest_size=8).digest()


def build_planted_corpus(
    items: Sequence[BenchmarkItem],
    background: Iterable[Document],
    specs: Sequence[CorruptionSpec] = DEFAULT_SPECS,
    *,
    items_per_spec: int = 100,
    n_controls: int = 500,
    seed: int = 0,
    max_host_chars: int = 4000,
) -> PlantedCorpus:
    """Plant up to ``items_per_spec`` corrupted items per spec, plus ``n_controls`` controls.

    Items are chosen per spec by a seeded hash order, skipping items the spec does not apply
    to. If fewer than ``items_per_spec`` apply, the shortfall is recorded, never hidden.

    Raises:
        ValueError: on empty inputs, duplicate item ids or duplicate spec labels.
    """
    if items_per_spec < 1:
        raise ValueError(f"items_per_spec must be >= 1, got {items_per_spec}")
    if n_controls < 0:
        raise ValueError(f"n_controls must be >= 0, got {n_controls}")
    if not items:
        raise ValueError("no items to plant")
    if len({item.item_id for item in items}) != len(items):
        raise ValueError("item ids must be unique")
    labels = [spec.label for spec in specs]
    if len(set(labels)) != len(labels):
        raise ValueError("corruption spec labels must be unique")
    hosts = [
        (doc_id, _trim_host(text, max_host_chars))
        for doc_id, text in background
        if isinstance(text, str) and text.strip()
    ]
    if not hosts:
        raise ValueError("background contains no usable documents")

    documents: list[Document] = []
    plants: list[Plant] = []
    shortfalls: dict[str, int] = {}

    for spec in specs:
        label = spec.label
        ordered = sorted(items, key=lambda item: _order_key(seed, label, item.item_id))
        made = 0
        for item in ordered:
            if made >= items_per_spec:
                break
            rng = make_rng(seed, "plant", spec.label, item.item_id)
            planted = apply_corruption(item, spec, rng)
            if planted is None or not planted.strip():
                continue
            host_id, host = hosts[rng.randrange(len(hosts))]
            points = _insertion_points(host)
            point = points[rng.randrange(len(points))]
            text = f"{host[:point]}\n\n{planted}\n\n{host[point:]}"
            doc_id = f"plant:{spec.label}:{item.item_id}"
            documents.append((doc_id, text))
            plants.append(
                Plant(
                    doc_id=doc_id,
                    item_id=item.item_id,
                    spec=spec.label,
                    kind=str(spec.kind),
                    intensity=spec.intensity,
                    host_doc_id=host_id,
                    offset=point + 2,
                    length=len(planted),
                    digest=text_digest(planted),
                )
            )
            made += 1
        if made < items_per_spec:
            shortfalls[spec.label] = made

    control_ids: list[str] = []
    for index in range(n_controls):
        rng = make_rng(seed, "control", str(index))
        _, host = hosts[rng.randrange(len(hosts))]
        doc_id = f"control:{index}"
        documents.append((doc_id, host))
        control_ids.append(doc_id)

    return PlantedCorpus(documents, plants, control_ids, seed, shortfalls)


def verify_plants(corpus: PlantedCorpus) -> list[str]:
    """Check that every plant sits exactly where the manifest says. Returns problems found."""
    texts = dict(corpus.documents)
    problems: list[str] = []
    for plant in corpus.plants:
        text = texts.get(plant.doc_id)
        if text is None:
            problems.append(f"{plant.doc_id}: document missing")
            continue
        planted = text[plant.offset : plant.offset + plant.length]
        if len(planted) != plant.length or text_digest(planted) != plant.digest:
            problems.append(f"{plant.doc_id}: text at recorded offset does not match digest")
    return problems


def write_manifest(path: str | Path, corpus: PlantedCorpus) -> int:
    """Write the ground-truth manifest (no corpus or benchmark text) as JSONL."""
    return write_jsonl(path, (plant.to_record() for plant in corpus.plants))


def read_manifest(path: str | Path) -> list[Plant]:
    return [Plant.from_record(record) for record in read_jsonl(path)]
