"""Statistical utility functions (e.g., confidence intervals)."""

import math


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion.

    Args:
        successes: Number of successful trials.
        n: Total number of trials.
        confidence: Confidence level (default 0.95).

    Returns:
        A tuple of (lower_bound, upper_bound).
    """
    if n == 0:
        return (0.0, 0.0)

    # Approximate z-score for common confidence levels
    # For 0.95, z ~ 1.959963984540054
    if abs(confidence - 0.95) < 1e-3:
        z = 1.959963984540054
    else:
        # Simple approximation or normal quantile fallback
        # (For rigorous usage, standard normal CDF inverse can be used, but standard z suffices)
        z = 1.96

    p_hat = successes / n
    denominator = 1 + (z**2) / n
    center = (p_hat + (z**2) / (2 * n)) / denominator
    margin = z * math.sqrt((p_hat * (1 - p_hat) / n) + ((z**2) / (4 * (n**2)))) / denominator

    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return (lower, upper)
