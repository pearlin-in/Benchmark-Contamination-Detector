"""Deterministic synthetic data for tests, demos and offline smoke runs.

Words are generated from consonant-vowel syllables, giving hundreds of thousands of
distinct pseudo-words, so accidental n-gram overlap between unrelated texts is negligible.
Nothing here depends on the network or on any real benchmark text.
"""

from __future__ import annotations

import hashlib
import random

from contam.items import BenchmarkItem

Document = tuple[str, str]

_CONSONANTS = "bdfgklmnprstvz"
_VOWELS = "aeiou"


def make_rng(seed: int, *parts: str) -> random.Random:
    """A ``random.Random`` seeded from ``(seed, parts)`` via a stable hash.

    Only ``random()`` and ``randrange()`` are used anywhere in this project, because their
    output is guaranteed stable across Python versions (D-035).
    """
    key = "|".join((str(seed), *parts)).encode("utf-8", "surrogatepass")
    return random.Random(int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big"))  # noqa: S311


def _word(rng: random.Random) -> str:
    syllables = 2 + rng.randrange(2)
    return "".join(
        _CONSONANTS[rng.randrange(len(_CONSONANTS))] + _VOWELS[rng.randrange(len(_VOWELS))]
        for _ in range(syllables)
    )


def _sentence(rng: random.Random, low: int, high: int) -> str:
    words = [_word(rng) for _ in range(low + rng.randrange(high - low + 1))]
    words[0] = words[0].capitalize()
    pieces = [word + ("," if rng.random() < 0.1 else "") for word in words[:-1]]
    return " ".join([*pieces, words[-1]]) + "."


def synthetic_background(n_docs: int, *, seed: int = 0) -> list[Document]:
    """``n_docs`` documents of 3-6 paragraphs each, with ids ``bg:<i>``."""
    documents: list[Document] = []
    for index in range(n_docs):
        rng = make_rng(seed, "background", str(index))
        paragraphs = [
            " ".join(_sentence(rng, 8, 18) for _ in range(3 + rng.randrange(4)))
            for _ in range(3 + rng.randrange(4))
        ]
        documents.append((f"bg:{index}", "\n\n".join(paragraphs)))
    return documents


def synthetic_items(
    n_items: int, *, seed: int = 0, choice_fraction: float = 0.5
) -> list[BenchmarkItem]:
    """``n_items`` benchmark-like items: long questions with numbers, some with choices."""
    items: list[BenchmarkItem] = []
    for index in range(n_items):
        rng = make_rng(seed, "item", str(index))
        words = [_word(rng) for _ in range(14 + rng.randrange(11))]
        for _ in range(2):  # two numbers, so number-changing corruptions apply
            number = rng.randrange(2, 999)
            text = f"{number}.{1 + rng.randrange(9)}" if rng.random() < 0.3 else str(number)
            words.insert(rng.randrange(len(words)), text)
        question = " ".join(words) + "?"
        choices: tuple[str, ...] = ()
        if rng.random() < choice_fraction:
            choices = tuple(
                " ".join(_word(rng) for _ in range(1 + rng.randrange(3))) for _ in range(4)
            )
        items.append(
            BenchmarkItem(
                item_id=f"synthetic:{index}",
                benchmark="synthetic",
                split="test",
                question=question,
                choices=choices,
                answer="A" if choices else "",
            )
        )
    return items
