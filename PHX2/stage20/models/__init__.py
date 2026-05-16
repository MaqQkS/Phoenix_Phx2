"""Stage 20 typed model shapes (NamedTuple).

20.1 declared shape only -- no construction logic, no behavior
beyond what NamedTuple provides natively. 20.2 extends
PreviewCandidate and DecisionStep additively (no field renames)
and introduces RunWarnings for aggregated 20.2-local warning
state.

Following the locked prior-stage typing convention (Stage 18
Stage17InputBundle, Stage 19 LedgerRow / SummaryRow / etc., all
NamedTuple).
"""

from __future__ import annotations

from PHX2.stage20.models.decision_step import DecisionStep
from PHX2.stage20.models.filter_result import FilterResult
from PHX2.stage20.models.preview_candidate import PreviewCandidate
from PHX2.stage20.models.run_manifest import RunManifest
from PHX2.stage20.models.run_warnings import RunWarnings


__all__ = [
    "DecisionStep",
    "FilterResult",
    "PreviewCandidate",
    "RunManifest",
    "RunWarnings",
]
