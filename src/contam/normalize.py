"""Text normalization: the single canonical form used for all matching.

Every n-gram, hash and overlap score in this project is computed on the output
of :func:`normalize`, so a mistake here silently corrupts every result. That is
why this module is specified and tested *before* it is implemented.
"""

from __future__ import annotations


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

    The result must be idempotent: ``normalize(normalize(x)) == normalize(x)``.

    Raises:
        TypeError: if ``text`` is not a ``str``.
    """
    raise NotImplementedError("Roadmap phase 2: implement per the contract above.")