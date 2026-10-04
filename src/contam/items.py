"""The benchmark item schema shared by every loader and detector (roadmap 1.4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class View(StrEnum):
    """Which text of an item is searched for (DECISIONS.md, D-002)."""

    QUESTION = "question"
    QUESTION_CHOICES = "question_choices"


@dataclass(frozen=True, slots=True)
class BenchmarkItem:
    """One benchmark test item, independent of which dataset it came from."""

    item_id: str
    benchmark: str
    split: str
    question: str
    choices: tuple[str, ...] = ()
    answer: str = ""

    def text(self, view: View = View.QUESTION_CHOICES) -> str:
        """The text to search for under ``view``.

        Items without choices (e.g. GSM8K) have the same text in both views. Answers are
        never part of the searched text: they are too short to match meaningfully.
        """
        if view is View.QUESTION or not self.choices:
            return self.question
        return "\n".join((self.question, *self.choices))
