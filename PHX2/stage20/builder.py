"""Stage 20.2 candidate + decision sequence builder.

Pure functions over already-validated Stage 19 ledger rows. The
caller is required to have invoked ``validate_inputs`` and to have
confirmed ``ValidationResult.ok`` before passing rows here -- this
module relies on the closed-set guarantees ``validate_inputs``
enforces (review_label in LABEL_TO_STATE_MAPPING_V0, ledger_row_id
non-empty, etc.) and only repeats the cheapest defense-in-depth
checks.

Module is import-isolation safe: imports only from stdlib and
``PHX2.stage20`` siblings.

Operator-locked policies enforced here:

  * tier_hint contract (v0): every candidate gets ``tier_hint = ""``.
    No derivation source exists in the ledger; W2003 stays
    deferred.

  * Closed-set mapping invariant: ``validate_inputs`` rejects
    unknown review_labels via E2005, so by the time
    ``build_candidate`` sees the winning row the label MUST be in
    ``LABEL_TO_STATE_MAPPING_V0``. If the assumption is violated
    (defense in depth), the builder raises ``ValueError`` rather
    than silently mapping the row to PREVIEW_EXCLUDED.

  * Decision-state population (operator Phase B constraint #4):
    - input_state  := previous step's output_state, or "" on the
                      first step.
    - output_state := decision_step_state on that step.
    The 4-step chain therefore cascades input_state
    ""  ->  "passed"  ->  "passed"  ->  "passed", and
    output_state "passed", "passed", "passed", "terminal".

  * Reason-code mapping (operator-defaulted, per-state in v0):
        PREVIEW_ELIGIBLE       -> LABEL_MAPPED_FROM_OPERATOR_REVIEW
        PREVIEW_OBSERVE_ONLY   -> WATCHLIST_OBSERVE_ONLY
        PREVIEW_NEEDS_MORE_DATA-> INSUFFICIENT_EVIDENCE
        PREVIEW_EXCLUDED       -> OPERATOR_EXCLUDED
    The constant ``REASON_CODE_DISPATCH_SAFETY_DISABLED`` stays
    unused at candidate level (it is a run-level signal carried
    on the manifest). ``REASON_CODE_FILTER_OBSERVE_ONLY_PASSTHROUGH``
    is Stage 20.3 territory and is not used here.

Alias-pair population (operator Phase B constraints #2 / #3):

  * PreviewCandidate.eligibility_state and PreviewCandidate.preview_state
    are populated with the identical ``PreviewEligibilityState`` value
    string.
  * DecisionStep.step_index / step_name / is_terminating are
    populated with the same values as decision_step_index /
    decision_step_name / decision_step_terminating respectively.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence

from PHX2.stage20.clock import Clock
from PHX2.stage20.constants import (
    LABEL_TO_STATE_MAPPING_V0,
    MAPPING_VERSION,
    PreviewEligibilityState,
    REASON_CODE_INSUFFICIENT_EVIDENCE,
    REASON_CODE_LABEL_MAPPED,
    REASON_CODE_OPERATOR_EXCLUDED,
    REASON_CODE_WATCHLIST_OBSERVE_ONLY,
    SAFE_FOR_LIVE_DISPATCH,
    STAGE19_LEDGER_TIMESTAMP_FORMAT,
    STAGE20_MINOR_VERSION,
    STAGE20_VERSION,
    STALENESS_THRESHOLD_DAYS,
    DECISION_STEP_NAMES_4,
    EligibilityErrorCode,
)
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.ids import derive_candidate_id, derive_decision_id
from PHX2.stage20.models import (
    DecisionStep,
    PreviewCandidate,
    RunWarnings,
)


# Per-state reason_code mapping. LOCKED at Stage 20.2 per operator
# Phase B approval. Closed-set: every value in
# PreviewEligibilityState appears exactly once on the left and
# selects exactly one REASON_CODE_* constant on the right. Any
# future change to this mapping requires a STAGE20_VERSION or
# STAGE20_MINOR_VERSION bump.
#
#   PREVIEW_ELIGIBLE         -> LABEL_MAPPED_FROM_OPERATOR_REVIEW
#   PREVIEW_OBSERVE_ONLY     -> WATCHLIST_OBSERVE_ONLY
#   PREVIEW_NEEDS_MORE_DATA  -> INSUFFICIENT_EVIDENCE
#   PREVIEW_EXCLUDED         -> OPERATOR_EXCLUDED
#
# ``REASON_CODE_DISPATCH_SAFETY_DISABLED`` is intentionally unused
# at candidate level -- it is a run-level signal carried on the
# manifest. ``REASON_CODE_FILTER_OBSERVE_ONLY_PASSTHROUGH`` is
# Stage 20.3 filter-scaffolding territory and is not used here.
_REASON_CODE_FOR_STATE: Mapping[str, str] = {
    PreviewEligibilityState.PREVIEW_ELIGIBLE.value:
        REASON_CODE_LABEL_MAPPED,
    PreviewEligibilityState.PREVIEW_OBSERVE_ONLY.value:
        REASON_CODE_WATCHLIST_OBSERVE_ONLY,
    PreviewEligibilityState.PREVIEW_NEEDS_MORE_DATA.value:
        REASON_CODE_INSUFFICIENT_EVIDENCE,
    PreviewEligibilityState.PREVIEW_EXCLUDED.value:
        REASON_CODE_OPERATOR_EXCLUDED,
}


# Slice key: (stage18_run_id, policy_hash, rule_id, window_seconds).
SliceKey = tuple[str, str, str, str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_ledger_timestamp(ts: str) -> Optional[datetime]:
    """Return a tz-aware UTC datetime or None on parse failure.

    Local mirror of ``input_validators._parse_ledger_timestamp``;
    duplicated here so the builder does not depend on a private
    helper of the locked validators module.
    """

    try:
        parsed = datetime.strptime(ts, STAGE19_LEDGER_TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _compute_review_age_days(review_timestamp_utc: str, clock: Clock) -> int:
    """Return integer days from clock.now() to parsed timestamp.

    Returns ``-1`` on parse failure (a malformed cell on the
    Stage 19 side). The builder never raises on a malformed
    timestamp -- the row is preserved but flagged with
    ``review_age_days = -1`` and ``review_stale = False``.
    """

    parsed = _parse_ledger_timestamp(review_timestamp_utc)
    if parsed is None:
        return -1
    delta = clock.now() - parsed
    return delta.days


def _slice_key_for_row(row: Mapping[str, str]) -> SliceKey:
    return (
        row.get("stage18_run_id", ""),
        row.get("policy_hash", ""),
        row.get("rule_id", ""),
        row.get("window_seconds", ""),
    )


def _map_label_to_state(review_label: str) -> str:
    """Map a Stage 19 review_label to a PreviewEligibilityState value.

    Raises ValueError if the label is not in
    ``LABEL_TO_STATE_MAPPING_V0`` -- a closed-set invariant
    violation that ``validate_inputs`` should have caught via
    E2005 upstream of the builder.
    """

    state = LABEL_TO_STATE_MAPPING_V0.get(review_label)
    if state is None:
        raise ValueError(
            "builder: review_label not in LABEL_TO_STATE_MAPPING_V0: "
            f"{review_label!r}. validate_inputs should have rejected "
            f"this row via E2005 before reaching the builder."
        )
    return state.value


def _safe_int(value: object, default: int = 0) -> int:
    """Best-effort int coercion for ledger CSV string cells.

    Returns ``default`` on TypeError / ValueError / empty string.
    Stage 19 emits well-formed numerics, but the builder defends
    against malformed cells (a Stage 19 contract violation) rather
    than crashing the run.
    """

    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Slice resolution + winning-row selection
# ---------------------------------------------------------------------------


def resolve_slices(
    ledger_rows: Sequence[Mapping[str, str]],
) -> dict[SliceKey, list[dict[str, str]]]:
    """Group ledger rows by slice key (preserving input order within).

    The slice key is the 4-tuple
    ``(stage18_run_id, policy_hash, rule_id, window_seconds)``.
    Rows are stored in the order encountered for each slice; the
    caller relies on ``select_winning_row`` for deterministic
    intra-slice selection rather than depending on input order.
    """

    grouped: dict[SliceKey, list[dict[str, str]]] = {}
    for row in ledger_rows:
        key = _slice_key_for_row(row)
        grouped.setdefault(key, []).append(dict(row))
    return grouped


def select_winning_row(
    rows: Sequence[Mapping[str, str]],
) -> Mapping[str, str]:
    """Pick the row with the highest review_sequence.

    Tie-breaker (locked): highest ``ledger_row_id`` by string
    comparison. ``ledger_row_id`` is treated as an opaque string
    -- if Stage 19 ever emits integer ids, string comparison is
    still well-defined and deterministic.

    Raises ValueError on an empty sequence.
    """

    if not rows:
        raise ValueError("select_winning_row: empty row sequence")

    def _sort_key(r: Mapping[str, str]) -> tuple[int, str]:
        return (
            _safe_int(r.get("review_sequence", "0")),
            r.get("ledger_row_id", "") or "",
        )

    return max(rows, key=_sort_key)


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------


def build_candidate(
    winning_row: Mapping[str, str],
    slice_rows: Sequence[Mapping[str, str]],
    *,
    clock: Clock,
    stage20_run_id: str,
) -> PreviewCandidate:
    """Build a single PreviewCandidate from a slice's winning row.

    Args:
        winning_row: the row chosen by ``select_winning_row``.
        slice_rows: every ledger row in the slice (used to compute
            ``multiple_operators_for_slice``).
        clock: injectable clock for ``review_age_days``.
        stage20_run_id: the per-run identifier produced upstream.

    Closed-set invariant: raises ValueError if ``winning_row``'s
    ``review_label`` is not in ``LABEL_TO_STATE_MAPPING_V0``.

    Both ``eligibility_state`` (20.1) and ``preview_state`` (20.2
    alias) are populated with the same value string per operator
    Phase B constraint #2.
    """

    review_label = winning_row.get("review_label", "")
    state_value = _map_label_to_state(review_label)
    reason_code = _REASON_CODE_FOR_STATE[state_value]

    source_ledger_row_id = winning_row.get("ledger_row_id", "")
    stage19_run_id = winning_row.get("stage19_run_id", "")

    candidate_id = derive_candidate_id(
        stage19_run_id=stage19_run_id,
        source_ledger_row_id=source_ledger_row_id,
        stage20_version=STAGE20_VERSION,
        stage20_minor_version=STAGE20_MINOR_VERSION,
    )

    review_timestamp_utc = winning_row.get("review_timestamp_utc", "")
    review_age_days = _compute_review_age_days(
        review_timestamp_utc, clock
    )
    review_stale = review_age_days > STALENESS_THRESHOLD_DAYS

    distinct_operators = {
        r.get("operator_id", "")
        for r in slice_rows
        if r.get("operator_id", "")
    }
    multiple_operators_for_slice = len(distinct_operators) >= 2

    review_sequence = _safe_int(winning_row.get("review_sequence", "0"))
    window_seconds = _safe_int(winning_row.get("window_seconds", "0"))

    return PreviewCandidate(
        # 20.1 fields
        candidate_id=candidate_id,
        stage18_run_id=winning_row.get("stage18_run_id", ""),
        stage19_run_id=stage19_run_id,
        policy_hash=winning_row.get("policy_hash", ""),
        rule_id=winning_row.get("rule_id", ""),
        window_seconds=window_seconds,
        operator_id=winning_row.get("operator_id", ""),
        review_sequence=review_sequence,
        review_label=review_label,
        review_timestamp_utc=review_timestamp_utc,
        eligibility_state=state_value,
        stage18_classification=winning_row.get("stage18_classification", ""),
        stage17_label_preserved=winning_row.get("stage17_label_preserved", ""),
        safe_for_live_dispatch=SAFE_FOR_LIVE_DISPATCH,
        tier_hint="",
        reason_code=reason_code,
        # 20.2 additive
        stage20_run_id=stage20_run_id,
        source_ledger_row_id=source_ledger_row_id,
        mapping_version=MAPPING_VERSION,
        review_age_days=review_age_days,
        review_stale=review_stale,
        multiple_operators_for_slice=multiple_operators_for_slice,
        notes="",
        # 20.2 alias (operator constraint #2)
        preview_state=state_value,
    )


# ---------------------------------------------------------------------------
# Decision sequence construction (4-step chain)
# ---------------------------------------------------------------------------


def build_decision_sequence(
    candidate: PreviewCandidate,
    *,
    stage20_run_id: str,
) -> list[DecisionStep]:
    """Build the 4-step decision audit trail for a candidate.

    Chain (locked): slice_resolved, mapping_applied,
    staleness_evaluated, terminal. The terminal step carries
    ``decision_outcome = candidate.preview_state``,
    ``decision_step_state = "terminal"``,
    ``is_terminating = True`` (paired with
    ``decision_step_terminating = True`` per operator
    constraint #3).

    State cascade (operator constraint #4):
      step_index 0: input_state="",       output_state="passed"
      step_index 1: input_state="passed", output_state="passed"
      step_index 2: input_state="passed", output_state="passed"
      step_index 3: input_state="passed", output_state="terminal"
    """

    chain = DECISION_STEP_NAMES_4
    steps: list[DecisionStep] = []
    last_output_state = ""

    for step_index, step_name in enumerate(chain):
        is_terminal = step_name == "terminal"
        if is_terminal:
            decision_step_state = "terminal"
            decision_outcome = candidate.preview_state
        else:
            decision_step_state = "passed"
            decision_outcome = ""

        input_state = last_output_state
        output_state = decision_step_state

        decision_id = derive_decision_id(
            candidate_id=candidate.candidate_id,
            decision_step_index=step_index,
            decision_step_name=step_name,
            stage20_version=STAGE20_VERSION,
            stage20_minor_version=STAGE20_MINOR_VERSION,
        )

        steps.append(DecisionStep(
            # 20.1 fields
            candidate_id=candidate.candidate_id,
            step_index=step_index,
            step_name=step_name,
            input_state=input_state,
            output_state=output_state,
            is_terminating=is_terminal,
            reason_code=candidate.reason_code,
            # 20.2 additive
            decision_id=decision_id,
            stage20_run_id=stage20_run_id,
            decision_step_state=decision_step_state,
            decision_outcome=decision_outcome,
            evidence_code="",
            evidence_detail="",
            # 20.2 alias (operator constraint #3)
            decision_step_index=step_index,
            decision_step_name=step_name,
            decision_step_terminating=is_terminal,
        ))
        last_output_state = output_state

    return steps


# ---------------------------------------------------------------------------
# Aggregate orchestrator
# ---------------------------------------------------------------------------


def build_all_candidates(
    validation_result,  # ValidationResult duck-typed
    ledger_rows: Sequence[Mapping[str, str]],
    *,
    clock: Clock,
    stage20_run_id: str,
    stage19_run_id: str,
) -> tuple[list[PreviewCandidate], list[DecisionStep], RunWarnings]:
    """Build the full candidate + decision lists plus a RunWarnings.

    Args:
        validation_result: ValidationResult from validate_inputs.
            Not consumed for content here; passed through so the
            signature mirrors the locked contract documented at
            Phase B. Upstream warnings are surfaced separately via
            ``surface_upstream_warnings``.
        ledger_rows: every Stage 19 ledger row read in.
        clock: injectable clock.
        stage20_run_id: the per-run id.
        stage19_run_id: the declared Stage 19 run id; informational
            here (the authoritative value lives on each ledger row
            and is read from the winning row at candidate-build
            time).

    Returns:
        (candidates, decisions, run_warnings)
        run_warnings carries W2002 (based on PREVIEW_ELIGIBLE
        count) and W2006 (count of review_stale candidates).
        W2007 stays False here -- prior-manifest drift is
        evaluated separately via ``compute_local_warnings``.

    The orchestrator does NOT call the E-code validators
    (validate_candidate_id_uniqueness, validate_decision_sequences).
    Phase C's runner calls them after this function returns; this
    keeps the builder pure and the validators independently
    testable.
    """

    del validation_result  # signature reservation; not consumed here
    del stage19_run_id     # signature reservation; not consumed here

    slices = resolve_slices(ledger_rows)

    candidates: list[PreviewCandidate] = []
    for _key, rows in slices.items():
        winning = select_winning_row(rows)
        candidates.append(build_candidate(
            winning,
            rows,
            clock=clock,
            stage20_run_id=stage20_run_id,
        ))

    decisions: list[DecisionStep] = []
    for candidate in candidates:
        decisions.extend(build_decision_sequence(
            candidate, stage20_run_id=stage20_run_id,
        ))

    eligible_value = PreviewEligibilityState.PREVIEW_ELIGIBLE.value
    eligible_count = sum(
        1 for c in candidates if c.preview_state == eligible_value
    )
    w2002 = eligible_count == 0
    w2006_count = sum(1 for c in candidates if c.review_stale)

    return candidates, decisions, RunWarnings(
        w2002_preview_eligible_count_zero=w2002,
        w2006_candidate_review_stale_count=w2006_count,
        w2007_eligibility_mapping_drift_detected=False,
    )


# ---------------------------------------------------------------------------
# Warning composition (local + upstream surfacing)
# ---------------------------------------------------------------------------


def compute_local_warnings(
    candidates: Sequence[PreviewCandidate],
    *,
    prior_manifest_label_mapping: Optional[Mapping[str, str]] = None,
    prior_manifest_mapping_version: Optional[str] = None,
) -> dict[str, object]:
    """Compute the 3 locally-detected manifest warning entries.

    W2002 fires when ``preview_eligible_count == 0``.
    W2006 reports the count of candidates with ``review_stale=True``.
    W2007 fires only when a prior manifest's ``mapping_version`` or
    ``label_mapping`` differs from the current run's.

    Returns:
        {
          "W2002_preview_eligible_count_zero": bool,
          "W2006_candidate_review_stale_count": int,
          "W2007_eligibility_mapping_drift_detected": bool,
        }
    """

    eligible_value = PreviewEligibilityState.PREVIEW_ELIGIBLE.value
    eligible_count = sum(
        1 for c in candidates if c.preview_state == eligible_value
    )
    w2002 = eligible_count == 0
    w2006_count = sum(1 for c in candidates if c.review_stale)

    if (
        prior_manifest_label_mapping is None
        and prior_manifest_mapping_version is None
    ):
        w2007 = False
    else:
        version_differs = (
            prior_manifest_mapping_version is not None
            and prior_manifest_mapping_version != MAPPING_VERSION
        )
        # str-Enum values of LABEL_TO_STATE_MAPPING_V0 compare equal
        # to their .value strings (PreviewEligibilityState extends
        # str), so a plain-string prior mapping compares cleanly
        # against the current MappingProxyType.
        mapping_differs = (
            prior_manifest_label_mapping is not None
            and dict(prior_manifest_label_mapping)
            != dict(LABEL_TO_STATE_MAPPING_V0)
        )
        w2007 = version_differs or mapping_differs

    return {
        "W2002_preview_eligible_count_zero": w2002,
        "W2006_candidate_review_stale_count": w2006_count,
        "W2007_eligibility_mapping_drift_detected": w2007,
    }


def surface_upstream_warnings(validation_result) -> dict[str, object]:
    """Project upstream W2001/W2004/W2005 from ValidationResult.warnings.

    Stage 20.1's input_validators emits each upstream warning at
    most ONCE per run (single-occurrence at run level, not
    per-slice). The count-style keys therefore range over
    ``{0, 1}`` in normal operation but use a full ``.count()``
    formula so any future 20.1 emission-semantics change (e.g.
    per-slice W2004) is automatically reflected here without a
    code change in 20.2.

    Returns:
        {
          "W2001_run_median_staleness_exceeded": bool,
          "W2004_multiple_operators_per_review_slice_count": int,
          "W2005_stage18_evidence_missing_for_review_count": int,
        }
    """

    warnings = tuple(validation_result.warnings)
    return {
        "W2001_run_median_staleness_exceeded":
            "W2001" in warnings,
        "W2004_multiple_operators_per_review_slice_count":
            warnings.count("W2004"),
        "W2005_stage18_evidence_missing_for_review_count":
            warnings.count("W2005"),
    }


def assemble_manifest_warnings_dict(
    validation_result,
    candidates: Sequence[PreviewCandidate],
    *,
    prior_manifest_label_mapping: Optional[Mapping[str, str]] = None,
    prior_manifest_mapping_version: Optional[str] = None,
) -> dict[str, object]:
    """Build the 7-key ``manifest.warnings`` dict.

    Combines upstream surfacing + local detection + the always-zero
    W2003 stub (no tier_hint source in v0).
    """

    upstream = surface_upstream_warnings(validation_result)
    local = compute_local_warnings(
        candidates,
        prior_manifest_label_mapping=prior_manifest_label_mapping,
        prior_manifest_mapping_version=prior_manifest_mapping_version,
    )
    return {
        **upstream,
        **local,
        "W2003_tier_hint_missing_count": 0,
    }


# ---------------------------------------------------------------------------
# E-code validators
# ---------------------------------------------------------------------------


def validate_candidate_id_uniqueness(
    candidates: Sequence[PreviewCandidate],
) -> None:
    """Raise Stage20ValidationError(E2011) on duplicate candidate_id."""

    seen: set[str] = set()
    for c in candidates:
        if c.candidate_id in seen:
            raise Stage20ValidationError(
                EligibilityErrorCode.E2011,
                detail=f"candidate_id={c.candidate_id}",
            )
        seen.add(c.candidate_id)


def validate_decision_sequences(
    decisions: Sequence[DecisionStep],
    candidates: Sequence[PreviewCandidate],
) -> None:
    """Run E2015 / E2016 / E2017 detectors across the decision list.

    E2015 -- decision_step_index collision within a candidate.
    E2016 -- != 1 terminating decision row per candidate.
    E2017 -- terminating row's decision_outcome != candidate.preview_state.

    Codex remediation: iterates over the ``candidates`` list rather
    than ``by_candidate.items()`` so a candidate with ZERO decision
    rows still trips E2016 (otherwise such a candidate is silently
    skipped because no entry exists in the by-candidate map).
    """

    by_candidate: dict[str, list[DecisionStep]] = {}
    for d in decisions:
        by_candidate.setdefault(d.candidate_id, []).append(d)

    for candidate in candidates:
        cand_id = candidate.candidate_id
        steps = by_candidate.get(cand_id, [])

        # E2015 -- index collision within candidate.
        seen_indices: set[int] = set()
        for s in steps:
            if s.step_index in seen_indices:
                raise Stage20ValidationError(
                    EligibilityErrorCode.E2015,
                    detail=(
                        f"candidate_id={cand_id} duplicate "
                        f"decision_step_index={s.step_index}"
                    ),
                )
            seen_indices.add(s.step_index)

        # E2016 -- exactly one terminating row.
        terminating = [s for s in steps if s.is_terminating]
        if len(terminating) != 1:
            raise Stage20ValidationError(
                EligibilityErrorCode.E2016,
                detail=(
                    f"candidate_id={cand_id} has "
                    f"{len(terminating)} terminating decision "
                    f"rows; expected exactly 1"
                ),
            )

        # E2017 -- terminating row's outcome matches candidate.preview_state.
        term = terminating[0]
        if term.decision_outcome != candidate.preview_state:
            raise Stage20ValidationError(
                EligibilityErrorCode.E2017,
                detail=(
                    f"candidate_id={cand_id} terminating "
                    f"decision_outcome={term.decision_outcome!r} "
                    f"!= candidate.preview_state={candidate.preview_state!r}"
                ),
            )


__all__ = [
    "SliceKey",
    "assemble_manifest_warnings_dict",
    "build_all_candidates",
    "build_candidate",
    "build_decision_sequence",
    "compute_local_warnings",
    "resolve_slices",
    "select_winning_row",
    "surface_upstream_warnings",
    "validate_candidate_id_uniqueness",
    "validate_decision_sequences",
]
