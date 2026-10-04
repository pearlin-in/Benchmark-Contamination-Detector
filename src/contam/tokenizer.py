"""Word-level tokenization (DECISIONS.md, D-004).

Deliberately simple and model-independent: the output must be identical on every
machine and for every run. Input is expected to be the output of
:func:`contam.normalize.normalize`, where punctuation has already become spaces.
"""

from __future__ import annotations

import re

# A token is a run of word characters, or a single remaining symbol such as "+", "=" or "$".
# Splitting symbols off makes "12+30" and "12 + 30" tokenize identically.
_TOKEN_RE = re.compile(r"\w+|[^\w\s]")


def tokenize(text: str) -> list[str]:
    """Split normalized text into tokens.

    Limitation (documented, English-only scope): scripts that use combining marks
    outside ``\\w`` are split into more tokens than a linguist would. The output is still
    deterministic, which is what matching requires.
    """
    return _TOKEN_RE.findall(text)
