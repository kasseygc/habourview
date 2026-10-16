"""Small-cell suppression for the funder export.

Primary: any count from 1 to threshold-1 is shown as "<threshold".
Secondary (complementary): if a group's total is published and exactly one cell is hidden,
it could be recovered by subtraction, so the next-smallest non-zero cell is hidden too.
Rates are hidden whenever their numerator, or the denominator minus the numerator, is small.
"""

from __future__ import annotations

from axon.config import SMALL_CELL_THRESHOLD


def is_small(n: int, threshold: int = SMALL_CELL_THRESHOLD) -> bool:
    return 0 < n < threshold


def suppress_counts(counts: dict[str, int], threshold: int = SMALL_CELL_THRESHOLD) -> dict[str, str]:
    hidden = {k for k, v in counts.items() if is_small(v, threshold)}
    if len(hidden) == 1:
        candidates = sorted((v, k) for k, v in counts.items() if k not in hidden and v > 0)
        if candidates:
            hidden.add(candidates[0][1])
    return {k: (f"<{threshold}" if k in hidden and is_small(v, threshold) else "hidden" if k in hidden else str(v))
            for k, v in counts.items()}


def suppress_total(n: int, threshold: int = SMALL_CELL_THRESHOLD) -> str:
    return f"<{threshold}" if is_small(n, threshold) else str(n)


def rate_is_publishable(numerator: int, denominator: int, threshold: int = SMALL_CELL_THRESHOLD) -> bool:
    if denominator < threshold:
        return False
    return not (is_small(numerator, threshold) or is_small(denominator - numerator, threshold))
