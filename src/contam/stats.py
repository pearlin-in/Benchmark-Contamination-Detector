"""Small statistics helpers (DECISIONS.md, D-014)."""

from __future__ import annotations

import math


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion (95% by default).

    Unlike the textbook normal approximation, it behaves well for small samples and for
    proportions near 0 or 1, which is exactly where detector recall and false-positive
    rates live. With ``total == 0`` nothing is known, so the interval is (0, 1).

    Raises:
        ValueError: if the counts are inconsistent.
    """
    if total < 0 or successes < 0 or successes > total:
        raise ValueError(f"invalid counts: successes={successes}, total={total}")
    if total == 0:
        return 0.0, 1.0
    proportion = successes / total
    z_squared = z * z
    denominator = 1 + z_squared / total
    center = (proportion + z_squared / (2 * total)) / denominator
    half_width = (
        z * math.sqrt(proportion * (1 - proportion) / total + z_squared / (4 * total * total))
    ) / denominator
    # Exactly 0 or total successes pin one end of the interval; floating-point error must
    # not leave it a hair away from 0 or 1.
    low = 0.0 if successes == 0 else max(0.0, center - half_width)
    high = 1.0 if successes == total else min(1.0, center + half_width)
    return low, high
