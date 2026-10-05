"""Corruptions that turn a benchmark item into the kind of imperfect copy found on the web.

Each corruption takes an item and returns the text to plant in a document, or ``None`` when
it does not apply (for example, shuffling the choices of an item that has none). They are
the ground truth generators for the evaluation harness (DECISIONS.md, D-013).

All randomness comes from a ``random.Random`` passed in by the caller, and only ``random()``
and ``randrange()`` are used (D-035), so the same seed gives the same text on every machine
and every Python version.

Synthetic edits are mechanical. They do not model natural paraphrase, which this project
explicitly does not detect (SCOPE.md, non-goals).
"""

from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from contam.items import BenchmarkItem

_SPLIT_WS = re.compile(r"(\s+)")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

FILLER_WORDS: tuple[str, ...] = (
    "about", "after", "again", "also", "because", "before", "being", "between", "both", "could",
    "each", "every", "first", "found", "great", "have", "here", "into", "just", "know",
    "large", "later", "little", "many", "might", "most", "much", "never", "other", "over",
    "people", "place", "right", "same", "small", "some", "still", "such", "take", "than",
    "their", "there", "these", "think", "those", "three", "through", "under", "until", "very",
    "water", "where", "which", "while", "with", "would", "write", "years", "young", "yours",
)  # fmt: skip

_NOISY_SPACES = (" ", "  ", "\t", "\u00a0", "\n", " \u00a0")
_TRAILING_PUNCTUATION = (",", ";", ":", "!", "?", '"', "'", ")")
_HTML_TEMPLATES = (
    '<div class="entry">\n<nav>Home | Courses | Contact</nav>\n<p>{text}</p>\n'
    "<footer>Posted by admin. All rights reserved.</footer>\n</div>",
    "<article><h2>Practice problem</h2>\n<p>{text}</p>\n<p>Share this page</p></article>",
    '<html><body>\n<div id="content">{text}</div>\n<div id="ads">Sponsored links</div>\n'
    "</body></html>",
)


class Corruption(StrEnum):
    VERBATIM = "verbatim"
    FORMAT_NOISE = "format_noise"
    PUNCT_DELETE = "punct_delete"
    CHOICE_SHUFFLE = "choice_shuffle"
    LABELLED_DOT = "labelled_dot"
    LABELLED_PAREN = "labelled_paren"
    NUMBER_CHANGE = "number_change"
    WORD_DELETE = "word_delete"
    WORD_SUBSTITUTE = "word_substitute"
    TRUNCATE = "truncate"
    HTML_WRAP = "html_wrap"
    HTML_SPLIT = "html_split"


_NEEDS_INTENSITY = frozenset(
    {
        Corruption.WORD_DELETE,
        Corruption.WORD_SUBSTITUTE,
        Corruption.TRUNCATE,
        Corruption.HTML_SPLIT,
    }
)


@dataclass(frozen=True, slots=True)
class CorruptionSpec:
    """One experimental condition: a corruption kind plus its intensity, if it has one.

    Intensity means: the fraction of words edited (``word_delete``, ``word_substitute``),
    the fraction of the item *kept* (``truncate``), the fraction of numbers changed
    (``number_change``, default 1.0), or the number of break markers (``html_split``).
    """

    kind: Corruption
    intensity: float | None = None

    def __post_init__(self) -> None:
        if self.kind in _NEEDS_INTENSITY and self.intensity is None:
            raise ValueError(f"{self.kind} requires an intensity")
        if self.intensity is None:
            return
        if self.kind is Corruption.HTML_SPLIT:
            if self.intensity < 1 or self.intensity != int(self.intensity):
                raise ValueError("html_split intensity must be a whole number >= 1")
        elif not 0.0 <= self.intensity <= 1.0:
            raise ValueError(f"{self.kind} intensity must be in [0, 1], got {self.intensity}")

    @property
    def label(self) -> str:
        """Stable identifier such as ``word_delete@0.1`` used in ids, files and plots."""
        if self.intensity is None:
            return str(self.kind)
        return f"{self.kind}@{self.intensity:g}"


DEFAULT_SPECS: tuple[CorruptionSpec, ...] = (
    CorruptionSpec(Corruption.VERBATIM),
    CorruptionSpec(Corruption.FORMAT_NOISE),
    CorruptionSpec(Corruption.PUNCT_DELETE),
    *(CorruptionSpec(Corruption.WORD_DELETE, rate) for rate in (0.05, 0.10, 0.20, 0.30)),
    *(CorruptionSpec(Corruption.WORD_SUBSTITUTE, rate) for rate in (0.05, 0.10, 0.20, 0.30)),
    CorruptionSpec(Corruption.TRUNCATE, 0.8),
    CorruptionSpec(Corruption.TRUNCATE, 0.6),
    CorruptionSpec(Corruption.NUMBER_CHANGE),
    CorruptionSpec(Corruption.CHOICE_SHUFFLE),
    CorruptionSpec(Corruption.LABELLED_DOT),
    CorruptionSpec(Corruption.LABELLED_PAREN),
    CorruptionSpec(Corruption.HTML_WRAP),
    CorruptionSpec(Corruption.HTML_SPLIT, 1),
    CorruptionSpec(Corruption.HTML_SPLIT, 3),
)


# --------------------------------------------------------------------------- helpers
def render(item: BenchmarkItem) -> str:
    """The natural plain-text rendering of an item: question, then one choice per line."""
    return "\n".join((item.question, *item.choices))


def _is_word(token: str) -> bool:
    return token != "" and not token.isspace()


def _shuffled(rng: random.Random, values: list[int]) -> list[int]:
    """Fisher-Yates shuffle using only ``randrange`` (stable across Python versions)."""
    result = list(values)
    for i in range(len(result) - 1, 0, -1):
        j = rng.randrange(i + 1)
        result[i], result[j] = result[j], result[i]
    return result


def _different_filler(original: str, rng: random.Random) -> str:
    for _ in range(10):
        candidate = FILLER_WORDS[rng.randrange(len(FILLER_WORDS))]
        if candidate != original.lower():
            return candidate
    return FILLER_WORDS[0]


def _different_number(raw: str, rng: random.Random) -> str:
    characters = list(raw)
    positions = [i for i, character in enumerate(characters) if character.isdigit()]
    for i in positions:
        characters[i] = str(rng.randrange(10))
    changed = "".join(characters)
    if changed == raw:  # extremely unlikely, but the corruption must really change the number
        last = positions[-1]
        characters[last] = str((int(characters[last]) + 1) % 10)
        changed = "".join(characters)
    return changed


# --------------------------------------------------------------------------- corruptions
def _verbatim(item: BenchmarkItem, _: float | None, __: random.Random) -> str | None:
    return render(item)


def _format_noise(item: BenchmarkItem, _: float | None, rng: random.Random) -> str | None:
    """Random casing, odd whitespace and stray punctuation after words.

    Normalization is designed to erase exactly these differences, so a correct pipeline must
    recall this condition at 100%. A lower number is a bug, not a result.
    """
    mode = rng.randrange(3)
    pieces: list[str] = []
    for token in _SPLIT_WS.split(render(item)):
        if token == "":
            continue
        if token.isspace():
            pieces.append(token if "\n" in token else _NOISY_SPACES[rng.randrange(6)])
            continue
        word = token.upper() if mode == 0 else token.lower() if mode == 1 else token.title()
        if rng.random() < 0.15:
            word += _TRAILING_PUNCTUATION[rng.randrange(len(_TRAILING_PUNCTUATION))]
        pieces.append(word)
    return "".join(pieces)


def _punct_delete(item: BenchmarkItem, _: float | None, __: random.Random) -> str | None:
    """Delete (not space out) every punctuation mark: ``well-known`` becomes ``wellknown``."""
    text = render(item)
    stripped = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P"))
    return stripped if stripped != text else None


def _choice_shuffle(item: BenchmarkItem, _: float | None, rng: random.Random) -> str | None:
    original = list(item.choices)
    if len(original) < 2:
        return None
    for _attempt in range(20):
        order = _shuffled(rng, list(range(len(original))))
        shuffled = [original[i] for i in order]
        if shuffled != original:
            return "\n".join((item.question, *shuffled))
    return None


def _labelled(item: BenchmarkItem, template: str) -> str | None:
    if not item.choices:
        return None
    lines = [
        template.format(letter=chr(ord("A") + i), text=choice)
        for i, choice in enumerate(item.choices)
    ]
    return "\n".join((item.question, *lines))


def _labelled_dot(item: BenchmarkItem, _: float | None, __: random.Random) -> str | None:
    return _labelled(item, "{letter}. {text}")


def _labelled_paren(item: BenchmarkItem, _: float | None, __: random.Random) -> str | None:
    return _labelled(item, "({letter}) {text}")


def _number_change(item: BenchmarkItem, intensity: float | None, rng: random.Random) -> str | None:
    fraction = 1.0 if intensity is None else intensity
    text = render(item)
    matches = list(_NUMBER.finditer(text))
    if not matches:
        return None
    count = min(len(matches), max(1, round(fraction * len(matches))))
    chosen = set(_shuffled(rng, list(range(len(matches))))[:count])
    parts: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        parts.append(text[cursor : match.start()])
        parts.append(_different_number(match.group(), rng) if index in chosen else match.group())
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts)


def _edit_words(
    item: BenchmarkItem, rate: float | None, rng: random.Random, *, substitute: bool
) -> str | None:
    if rate is None:
        raise ValueError("word edits require an intensity")
    tokens = _SPLIT_WS.split(render(item))
    word_positions = [i for i, token in enumerate(tokens) if _is_word(token)]
    edited = list(tokens)
    kept = 0
    for position in word_positions:
        if rng.random() < rate:
            edited[position] = _different_filler(tokens[position], rng) if substitute else ""
        else:
            kept += 1
    if kept == 0 and word_positions and not substitute:
        edited[word_positions[0]] = tokens[word_positions[0]]  # never plant an empty text
    return "".join(edited)


def _word_delete(item: BenchmarkItem, rate: float | None, rng: random.Random) -> str | None:
    return _edit_words(item, rate, rng, substitute=False)


def _word_substitute(item: BenchmarkItem, rate: float | None, rng: random.Random) -> str | None:
    return _edit_words(item, rate, rng, substitute=True)


def _truncate(item: BenchmarkItem, keep: float | None, _: random.Random) -> str | None:
    if keep is None:
        raise ValueError("truncate requires an intensity")
    tokens = _SPLIT_WS.split(render(item))
    total_words = sum(1 for token in tokens if _is_word(token))
    if total_words == 0:
        return None
    limit = max(1, round(keep * total_words))
    kept: list[str] = []
    seen = 0
    for token in tokens:
        if _is_word(token):
            if seen == limit:
                break
            seen += 1
        kept.append(token)
    return "".join(kept).rstrip()


def _html_wrap(item: BenchmarkItem, _: float | None, rng: random.Random) -> str | None:
    template = _HTML_TEMPLATES[rng.randrange(len(_HTML_TEMPLATES))]
    return template.format(text=render(item))


def _html_split(item: BenchmarkItem, count: float | None, rng: random.Random) -> str | None:
    if count is None:
        raise ValueError("html_split requires an intensity")
    tokens = _SPLIT_WS.split(render(item))
    word_positions = [i for i, token in enumerate(tokens) if _is_word(token)]
    if len(word_positions) < 2:
        return None
    breaks = min(int(count), len(word_positions) - 1)
    # break before these words (never before the first one)
    candidates = list(range(1, len(word_positions)))
    chosen = {word_positions[i] for i in _shuffled(rng, candidates)[:breaks]}
    pieces: list[str] = []
    for position, token in enumerate(tokens):
        if position in chosen:
            pieces.append("\n<br />\n")
        pieces.append(token)
    return "".join(pieces)


_Handler = Callable[[BenchmarkItem, float | None, random.Random], str | None]

_HANDLERS: dict[Corruption, _Handler] = {
    Corruption.VERBATIM: _verbatim,
    Corruption.FORMAT_NOISE: _format_noise,
    Corruption.PUNCT_DELETE: _punct_delete,
    Corruption.CHOICE_SHUFFLE: _choice_shuffle,
    Corruption.LABELLED_DOT: _labelled_dot,
    Corruption.LABELLED_PAREN: _labelled_paren,
    Corruption.NUMBER_CHANGE: _number_change,
    Corruption.WORD_DELETE: _word_delete,
    Corruption.WORD_SUBSTITUTE: _word_substitute,
    Corruption.TRUNCATE: _truncate,
    Corruption.HTML_WRAP: _html_wrap,
    Corruption.HTML_SPLIT: _html_split,
}


def apply_corruption(item: BenchmarkItem, spec: CorruptionSpec, rng: random.Random) -> str | None:
    """The text to plant for ``item`` under ``spec``, or ``None`` if the spec does not apply."""
    return _HANDLERS[spec.kind](item, spec.intensity, rng)


def spec_labels(specs: Sequence[CorruptionSpec]) -> list[str]:
    return [spec.label for spec in specs]
