"""Stage 20 typed model shapes (NamedTuple).

20.1 declares shape only -- no construction logic, no behavior
beyond what NamedTuple provides natively. 20.2 and 20.3 will
build instances of these models from validated Stage 18 +
Stage 19 inputs.

Following the locked prior-stage typing convention (Stage 18
Stage17InputBundle, Stage 19 LedgerRow / SummaryRow / etc., all
NamedTuple).
"""

from __future__ import annotations

from PHX2.stage20.models.decision_step import DecisionStep
from PHX2.stage20.models.filter_result import FilterResult
from PHX2.stage20.models.preview_candidate import PreviewCandidate
from PHX2.stage20.models.run_manifest import RunManifest


__all__ = [
    "DecisionStep",
    "FilterResult",
    "PreviewCandidate",
    "RunManifest",
]
