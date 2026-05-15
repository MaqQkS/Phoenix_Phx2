"""Stage 20 FilterResult model shape (NamedTuple).

Shape declaration only -- defined here for 20.3 filter-interface
scaffolding. Real filter implementations land in Stage 22+; in
Stage 20 v0 every filter is OBSERVE_ONLY and passes the candidate
through unchanged.

Field provenance:

  * candidate_id    -- foreign key to PreviewCandidate.
  * filter_name     -- short identifier for the filter
                       (e.g. "evidence_present_v0").
  * filter_version  -- semver-ish version string the filter
                       carries; pinned per filter.
  * filter_mode     -- locked to "OBSERVE_ONLY" in v0; E2013
                       catches deviations in 20.3.
  * ordering_index  -- 0-based index within the filter chain;
                       each ordering_index is unique within a
                       Stage 20 run. E2014 catches collisions
                       in 20.3.
  * pass_through    -- True in v0 (the filter never gates).
  * reason_code     -- one of REASON_CODE_* from
                       PHX2.stage20.constants;
                       REASON_CODE_FILTER_OBSERVE_ONLY_PASSTHROUGH
                       is the v0 default.
"""

from __future__ import annotations

from typing import NamedTuple


class FilterResult(NamedTuple):
    """One filter outcome per PreviewCandidate (scaffolded for 20.3)."""

    candidate_id: str
    filter_name: str
    filter_version: str
    filter_mode: str
    ordering_index: int
    pass_through: bool
    reason_code: str


__all__ = ["FilterResult"]
