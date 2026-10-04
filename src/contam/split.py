"""Data splitting utilities for train/test splits and document chunks."""

from typing import TypeVar

T = TypeVar("T")


def unit_interval(value: float) -> float:
    """Validate that a value falls within [0.0, 1.0]."""
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"Value {value} must be between 0.0 and 1.0 inclusive.")
    return value


def split_items(
    items: list[T], train_ratio: float = 0.8, seed: int = 42
) -> tuple[list[T], list[T]]:
    """Split a list of items deterministically into train and test sets."""
    import random

    unit_interval(train_ratio)
    shuffled = list(items)
    rng = random.Random(seed)
    rng.shuffle(shuffled)

    split_idx = int(len(shuffled) * train_ratio)
    return shuffled[:split_idx], shuffled[split_idx:]


def split_documents(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split a long document text into overlapping token/character chunks."""
    if not text:
        return []

    chunks = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end])
        if end == length:
            break
        start += chunk_size - overlap

    return chunks
