"""PHX2 filters package.

Stage 10 introduces the filter substrate (Filter ABC, FilterContext)
and the first concrete filter (FeeGateFilter v1.0). Filters are
observe-only label/score producers consumed by
FilterEvaluationEngine; they never affect alert eligibility.
"""

from PHX2.filters.base import Filter, FilterContext
from PHX2.filters.fee_gate import FeeGateFilter

__all__ = [
    "FeeGateFilter",
    "Filter",
    "FilterContext",
]
