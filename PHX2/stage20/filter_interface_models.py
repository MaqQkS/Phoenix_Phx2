"""
Stage 20.3 filter interface -- empty contract surface.

Lineage:
  Stage 20.1 (c576067): schema/model lock + input validators.
  Stage 20.2 (a60bbd4): preview candidate builder + artifact
                        writer + manifest assembler + runner.
  Stage 20.3 (this):    empty filter interface scaffolding.

Known limitations (v0):
  - Zero filters registered. Registry is an empty tuple.
  - Only OBSERVE_ONLY and DISABLED modes exist. SHADOW and
    BLOCKING are intentionally undefined.
  - Filter evaluation is not implemented. The result CSV is
    headers-only with zero data rows.
  - No live dispatch readiness. safe_for_live_dispatch is false.

Relationship to the 20.1-era FilterResult scaffold:
  PHX2/stage20/models/filter_result.py defined a FilterResult
  NamedTuple in Stage 20.1 with a different field shape (7
  fields including pass_through/reason_code/ordering_index).
  The Stage 20.3 design lock supersedes that shape with the
  10-field FilterEvaluationRow defined in this module. The
  20.1 FilterResult scaffold remains untouched and dormant; no
  Stage 20.3 production module imports it.

Phoenix1 departure notes:
  - No Phoenix1 filter code is imported, ported, or referenced.
  - PHX2 rebuilds the filter interface from scratch.
"""

from __future__ import annotations

import json as _json
from typing import NamedTuple

from PHX2.stage20.constants import (
    FILTER_INTERFACE_REGISTRY_COLUMNS,
    FILTER_INTERFACE_RESULTS_COLUMNS,
    FILTER_INTERFACE_VERSION,
    FILTER_MODE_VALUES_V0,
    FILTER_REGISTRY_CONTRACT_VERSION,
    FILTER_RESULT_CONTRACT_VERSION,
    EligibilityErrorCode,
)
from PHX2.stage20.errors import Stage20ValidationError


class FilterDefinition(NamedTuple):
    """One filter contract entry. Field order matches the CSV column order."""

    filter_id: str
    filter_name: str
    filter_version: str
    threshold_version: str
    mode: str
    contract_version: str


class FilterEvaluationRow(NamedTuple):
    """One per-candidate filter evaluation outcome.

    Field order matches FILTER_INTERFACE_RESULTS_COLUMNS so the CSV
    writer can iterate the tuple positionally.
    """

    candidate_id: str
    filter_id: str
    filter_name: str
    filter_version: str
    threshold_version: str
    mode: str
    evaluation_status: str
    observation_label: str
    observation_detail_json: str
    contract_version: str


REGISTRY_V0: tuple[FilterDefinition, ...] = ()


def _validate_filter_definition(fdef: FilterDefinition) -> None:
    """Raises Stage20ValidationError(E2028) on contract violation.

    Contract checks:
      - every field is a non-empty string
      - mode in FILTER_MODE_VALUES_V0
      - mode != "BLOCKING" (defense-in-depth; redundant with the
        FILTER_MODE_VALUES_V0 check above)
      - contract_version == FILTER_REGISTRY_CONTRACT_VERSION
    """

    for field_name, value in zip(fdef._fields, fdef):
        if not isinstance(value, str) or value == "":
            raise Stage20ValidationError(
                EligibilityErrorCode.E2028,
                detail=(
                    f"FilterDefinition.{field_name} must be a non-empty "
                    f"string; got {value!r}"
                ),
            )
    if fdef.mode not in FILTER_MODE_VALUES_V0:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2028,
            detail=(
                f"FilterDefinition.mode {fdef.mode!r} not in locked v0 "
                f"set {FILTER_MODE_VALUES_V0!r}"
            ),
        )
    if fdef.mode == "BLOCKING":
        raise Stage20ValidationError(
            EligibilityErrorCode.E2028,
            detail=(
                "FilterDefinition.mode 'BLOCKING' is not defined in v0"
            ),
        )
    if fdef.contract_version != FILTER_REGISTRY_CONTRACT_VERSION:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2028,
            detail=(
                f"FilterDefinition.contract_version "
                f"{fdef.contract_version!r} does not match locked "
                f"{FILTER_REGISTRY_CONTRACT_VERSION!r}"
            ),
        )


def _validate_filter_evaluation_row(row: FilterEvaluationRow) -> None:
    """Raises Stage20ValidationError(E2029) on contract violation.

    Contract checks:
      - every field is a string (observation_detail_json may be the
        string "{}" but must be a string type)
      - mode in FILTER_MODE_VALUES_V0
      - contract_version == FILTER_RESULT_CONTRACT_VERSION
      - observation_detail_json parses as a JSON dict via json.loads;
        not a list, not a scalar.
    """

    for field_name, value in zip(row._fields, row):
        if not isinstance(value, str):
            raise Stage20ValidationError(
                EligibilityErrorCode.E2029,
                detail=(
                    f"FilterEvaluationRow.{field_name} must be a string; "
                    f"got {type(value).__name__}"
                ),
            )
    if row.mode not in FILTER_MODE_VALUES_V0:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2029,
            detail=(
                f"FilterEvaluationRow.mode {row.mode!r} not in locked v0 "
                f"set {FILTER_MODE_VALUES_V0!r}"
            ),
        )
    if row.contract_version != FILTER_RESULT_CONTRACT_VERSION:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2029,
            detail=(
                f"FilterEvaluationRow.contract_version "
                f"{row.contract_version!r} does not match locked "
                f"{FILTER_RESULT_CONTRACT_VERSION!r}"
            ),
        )
    try:
        parsed = _json.loads(row.observation_detail_json)
    except (ValueError, TypeError) as exc:
        raise Stage20ValidationError(
            EligibilityErrorCode.E2029,
            detail=(
                "FilterEvaluationRow.observation_detail_json is not "
                f"valid JSON: {exc}"
            ),
        )
    if not isinstance(parsed, dict):
        raise Stage20ValidationError(
            EligibilityErrorCode.E2029,
            detail=(
                "FilterEvaluationRow.observation_detail_json must parse "
                f"as a JSON object; got {type(parsed).__name__}"
            ),
        )


def build_v0_registry() -> tuple[FilterDefinition, ...]:
    """Return the locked Stage 20.3 v0 filter registry.

    REGISTRY_V0 is an empty tuple in v0. Defense-in-depth: this
    function iterates REGISTRY_V0 and calls
    _validate_filter_definition on every entry. The loop is empty
    in v0; the structure prevents Stage 21+ from registering a
    filter without contract validation.
    """

    for fdef in REGISTRY_V0:
        _validate_filter_definition(fdef)
    return REGISTRY_V0


__all__ = [
    "FILTER_INTERFACE_REGISTRY_COLUMNS",
    "FILTER_INTERFACE_RESULTS_COLUMNS",
    "FILTER_INTERFACE_VERSION",
    "FILTER_MODE_VALUES_V0",
    "FILTER_REGISTRY_CONTRACT_VERSION",
    "FILTER_RESULT_CONTRACT_VERSION",
    "FilterDefinition",
    "FilterEvaluationRow",
    "REGISTRY_V0",
    "build_v0_registry",
]
