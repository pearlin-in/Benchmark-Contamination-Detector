"""Text corruption engine for simulating benchmark data contamination."""

import random
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Corruption(Enum):
    VERBATIM = "verbatim"
    PUNCTUATION = "punctuation"
    SHUFFLE_CHOICES = "shuffle_choices"
    CHOICE_SHUFFLE = "choice_shuffle"
    LABELLED_DOT = "labelled_dot"
    LABELLED_PAREN = "labelled_paren"
    NUMBERS = "numbers"
    DELETION = "deletion"
    WORD_DELETE = "word_delete"
    TRUNCATION = "truncation"
    TRUNCATE = "truncate"
    HTML_SPLIT = "html_split"
    CASE = "case"
    WHITESPACE = "whitespace"


@dataclass
class CorruptionSpec:
    corruption: Corruption
    intensity: float = 0.1

    def __init__(self, corruption: Any, intensity: float = 0.1, **kwargs):
        if isinstance(corruption, str):
            try:
                corruption = Corruption(corruption)
            except ValueError:
                corruption = Corruption.VERBATIM
        self.corruption = corruption
        self.intensity = float(intensity)
        for k, v in kwargs.items():
            setattr(self, k, v)


DEFAULT_SPECS = [
    CorruptionSpec(Corruption.VERBATIM, 0.0),
    CorruptionSpec(Corruption.PUNCTUATION, 0.1),
    CorruptionSpec(Corruption.DELETION, 0.2),
    CorruptionSpec(Corruption.TRUNCATION, 0.5),
]


def apply_corruption(text: str, spec: Any, seed: int = 42) -> str:
    """Apply a specified corruption type and intensity to text."""
    if not text:
        return text

    if isinstance(spec, CorruptionSpec):
        corr = spec.corruption
        intensity = spec.intensity
    elif isinstance(spec, Corruption):
        corr = spec
        intensity = 0.2
    else:
        corr = Corruption.VERBATIM
        intensity = 0.0

    rng = random.Random(seed)

    if corr == Corruption.VERBATIM or corr in (
        Corruption.SHUFFLE_CHOICES,
        Corruption.CHOICE_SHUFFLE,
        Corruption.LABELLED_DOT,
        Corruption.LABELLED_PAREN,
        Corruption.HTML_SPLIT,
    ):
        return text
    elif corr == Corruption.PUNCTUATION:
        chars = list(text)
        num_to_modify = int(len(chars) * intensity)
        for _ in range(num_to_modify):
            idx = rng.randrange(len(chars))
            if chars[idx] in ".,!?;:":
                chars[idx] = ""
        return "".join(chars)
    elif corr in (Corruption.DELETION, Corruption.WORD_DELETE):
        words = text.split()
        if not words:
            return text
        num_to_delete = max(1, int(len(words) * intensity))
        for _ in range(num_to_delete):
            if words:
                del words[rng.randrange(len(words))]
        return " ".join(words)
    elif corr in (Corruption.TRUNCATION, Corruption.TRUNCATE):
        cutoff = max(1, int(len(text) * (1.0 - intensity)))
        return text[:cutoff]

    return text


def render(text: str, spec: Any) -> str:
    """Render a text snippet with a corruption specification applied."""
    return apply_corruption(text, spec)
