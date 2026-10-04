"""Stable n-gram hashing with an O(1)-per-window rolling hash (D-006, D-028).

Why not Python's built-in ``hash()``? It is salted per process, so the same text hashes
differently in every run and in every multiprocessing worker. Every hash here is
reproducible on any machine.

Design:
  1. Each token is hashed once with BLAKE2b (8 bytes) and reduced modulo a Mersenne prime.
  2. An n-gram hash is a polynomial over its token hashes (a Rabin-Karp style rolling hash):

         H(t_0 .. t_{n-1}) = sum_j  h(t_j) * BASE^(n-1-j)   (mod 2^61 - 1)

     so sliding the window by one token costs a constant number of multiplications.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from functools import lru_cache

MODULUS = (1 << 61) - 1  # Mersenne prime 2^61 - 1
# Fixed (not random) odd base: determinism across runs matters more than adversarial
# resistance for a measurement tool. Must stay < MODULUS.
BASE = 0x1D2F3A4B5C6D7E8


@lru_cache(maxsize=1 << 20)
def token_hash(token: str) -> int:
    """Stable 61-bit hash of a single token.

    ``surrogatepass`` keeps malformed web text (lone surrogates) from crashing the scan.
    """
    digest = hashlib.blake2b(token.encode("utf-8", "surrogatepass"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % MODULUS


def ngram_hash(tokens: Sequence[str]) -> int:
    """Hash of one token sequence (the slow, obviously-correct definition)."""
    value = 0
    for token in tokens:
        value = (value * BASE + token_hash(token)) % MODULUS
    return value


def ngram_hashes(tokens: Sequence[str], n: int) -> list[int]:
    """Hashes of every window of ``n`` consecutive tokens, in order.

    Returns an empty list when there are fewer than ``n`` tokens.

    Raises:
        ValueError: if ``n < 1``.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    count = len(tokens) - n + 1
    if count <= 0:
        return []
    token_hashes = [token_hash(token) for token in tokens]
    top = pow(BASE, n - 1, MODULUS)  # weight of the token leaving the window
    value = 0
    for item in token_hashes[:n]:
        value = (value * BASE + item) % MODULUS
    hashes = [value]
    for i in range(n, len(token_hashes)):
        value = ((value - token_hashes[i - n] * top) * BASE + token_hashes[i]) % MODULUS
        hashes.append(value)
    return hashes
