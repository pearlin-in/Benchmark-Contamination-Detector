"""Text normalization: the single canonical form used for all matching.

Every n-gram, hash and overlap score in this project is computed on the output
of :func:`normalize`, so a mistake here silently corrupts every result. That is
why this module is specified and tested *before* it was implemented.
"""

from __future__ import annotations

import sys
import unicodedata
from functools import cache


@cache
def _translation_tables() -> tuple[dict[int, None], dict[int, str]]:
    """Build (delete, to_space) tables for ``str.translate`` once, on first use.

    ``str.translate`` runs in C, so this is far faster on gigabytes of web text than
    testing each character's Unicode category in a Python loop. Building the tables
    scans every code point (a fraction of a second) and is cached.
    """
    delete: dict[int, None] = {}
    to_space: dict[int, str] = {}
    for codepoint in range(sys.maxunicode + 1):
        category = unicodedata.category(chr(codepoint))
        if category == "Cf":
            delete[codepoint] = None
        elif category.startswith("P"):
            to_space[codepoint] = " "
    return delete, to_space


def normalize(text: str) -> str:
    """Return the canonical form of ``text``.

    Contract (see ``docs/DECISIONS.md``, D-003; tests in ``tests/unit/test_normalize.py``):

    1. Reject anything that is not a ``str`` with ``TypeError``.
    2. Delete invisible format characters (Unicode category ``Cf``): zero-width
       space/joiner, byte-order mark, soft hyphen, and similar.
    3. Apply Unicode NFKC normalization (folds full-width forms, ligatures,
       superscripts, non-breaking spaces, and composes accents).
    4. Lowercase. Note that lowercasing can produce text that is no longer
       NFKC-stable, so NFKC must be applied again afterwards.
    5. Replace every punctuation character (Unicode category ``P*``) with a space.
       Symbols (category ``S*``: ``+``, ``=``, ``$``) and digits are kept.
    6. Collapse every run of whitespace to a single space and strip both ends.

    The result is idempotent: ``normalize(normalize(x)) == normalize(x)``.

    Raises:
        TypeError: if ``text`` is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(f"normalize() expects str, got {type(text).__name__}")
    delete, to_space = _translation_tables()
    text = text.translate(delete)
    text = unicodedata.normalize("NFKC", text).lower()
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(to_space)
    return " ".join(text.split())
