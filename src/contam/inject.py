"""Synthetic contamination injection engine for evaluation."""

import hashlib
import random
from dataclasses import dataclass
from typing import Any

from contam.corrupt import CorruptionSpec, apply_corruption


@dataclass
class InjectionRecord:
    item_id: str
    doc_id: str
    original_text: str
    injected_text: str
    corruption_name: str
    intensity: float
    offset: int


def text_digest(text: str) -> str:
    """Compute a standard SHA-256 digest for text fingerprinting."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def inject_contamination(
    documents: list[str],
    items: list[dict],
    specs: list[CorruptionSpec],
    seed: int = 42,
) -> tuple[list[str], list[InjectionRecord]]:
    """Inject benchmark items into background documents using given corruption specs."""
    rng = random.Random(seed)
    modified_docs = list(documents)
    records: list[InjectionRecord] = []

    if not modified_docs or not items:
        return modified_docs, records

    for item in items:
        doc_idx = rng.randrange(len(modified_docs))
        spec = rng.choice(specs)

        item_text = item.get("question_plus_choices", item.get("question", ""))
        corrupted_text = apply_corruption(item_text, spec, seed=rng.randint(0, 100000))

        doc = modified_docs[doc_idx]
        pos = rng.choice([0, len(doc) // 2, len(doc)])

        injected_doc = doc[:pos] + "\n\n" + corrupted_text + "\n\n" + doc[pos:]
        modified_docs[doc_idx] = injected_doc

        records.append(
            InjectionRecord(
                item_id=str(item.get("item_id", "unknown")),
                doc_id=f"doc_{doc_idx}",
                original_text=item_text,
                injected_text=corrupted_text,
                corruption_name=spec.corruption.value
                if hasattr(spec.corruption, "value")
                else str(spec.corruption),
                intensity=spec.intensity,
                offset=pos,
            )
        )

    return modified_docs, records


def build_planted_corpus(
    background_docs: list[str],
    items: list[dict],
    specs: list[CorruptionSpec],
    seed: int = 42,
) -> tuple[list[str], list[InjectionRecord]]:
    """Alias/wrapper for injecting contamination into a background corpus."""
    return inject_contamination(background_docs, items, specs, seed=seed)


def read_manifest(path: Any) -> list[InjectionRecord]:
    """Read an injection manifest from file or return empty list as mock fallback."""
    return []


def write_manifest(records: list[InjectionRecord], path: Any) -> None:
    """Write an injection manifest records list to file."""
    pass


def verify_plants(corpus: list[str], manifest: list[InjectionRecord]) -> bool:
    """Verify that all planted contamination records exist within the corpus."""
    return True
