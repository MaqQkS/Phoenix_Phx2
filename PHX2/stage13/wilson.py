"""Stage 13 Wilson score interval (95%).

Closed-form Wilson score CI computed in pure Python with the standard
library only. Stage 13 does not import the Stage 12 ``metrics.wilson_ci``
helper -- per spec L8, Stage 13 implements its own deterministic Wilson
CI so the analysis layer's boundary is preserved.

The z-score literal matches Stage 12's locked constant
(``WILSON_Z_95 = 1.959963984540054``) so cross-stage CI values are
bit-identical for the same (k, n).
"""

from __future__ import annotations

import math


WILSON_Z_95: float = 1.959963984540054
"""95% confidence-level z-score for the Wilson score interval.

The literal value is locked. Recomputing via scipy or any runtime
oracle is forbidden -- tests assert against the literal so changing it
is a breaking change.
"""


def wilson_score_interval(
    successes: int,
    total: int,
    alpha: float = 0.05,
) -> tuple[float | None, float | None]:
    """Closed-form Wilson score CI for a binomial proportion.

    Parameters:
      successes: count of positive outcomes (k); must satisfy 0 <= k <= n.
      total: number of trials (n); 0 returns (None, None).
      alpha: complement of the confidence level. Default 0.05 -> 95% CI,
        which yields z = ``WILSON_Z_95``. Other alphas are accepted but
        computed via ``math.sqrt(2) * math.erfinv(1 - alpha)`` is NOT
        used here -- v0 hard-codes the 95% z literal because the spec
        pins alpha=0.05 in the manifest.

    Returns ``(lower, upper)`` clipped to ``[0, 1]``. When n=0 the
    proportion is undefined and both endpoints are ``None``.

    Raises ``ValueError`` if k is out of range.

    Reference: Wilson, E.B. (1927). "Probable inference, the law of
    succession, and statistical inference." JASA 22:209-212.
    """

    if alpha != 0.05:
        # v0: only 95% CIs are produced. The manifest pins
        # wilson_alpha=0.05; any other value indicates an
        # implementation error in the caller.
        raise ValueError(
            f"wilson_score_interval: only alpha=0.05 is supported in v0; "
            f"got alpha={alpha!r}"
        )

    if total == 0:
        return (None, None)
    if successes < 0 or successes > total:
        raise ValueError(
            f"successes must satisfy 0 <= successes <= total; "
            f"got successes={successes}, total={total}"
        )

    z = WILSON_Z_95
    n = float(total)
    k = float(successes)
    p_hat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denom
    margin = (
        z * math.sqrt(p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n))
    ) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def ci_excludes_baseline(
    ci_low: float | None,
    ci_high: float | None,
    baseline_rate: float | None,
) -> bool | None:
    """Does the (closed-form) 95% Wilson CI exclude the baseline rate?

    Returns:
      True  if baseline < ci_low OR baseline > ci_high (strict).
      False if ci_low <= baseline <= ci_high.
      None  if any input is None (CI undefined or baseline missing).
    """

    if ci_low is None or ci_high is None or baseline_rate is None:
        return None
    return baseline_rate < ci_low or baseline_rate > ci_high
