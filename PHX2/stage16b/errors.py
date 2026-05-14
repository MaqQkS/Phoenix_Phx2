"""Stage 16B closed-set error codes (M01-M08) and exception type used by the observer CLI, migration check, and repository surfaces."""

from __future__ import annotations

from typing import Mapping


# ---------------------------------------------------------------------------
# Stage 16B closed-set M codes
# ---------------------------------------------------------------------------
#
# Each code identifies a distinct failure surface. The CLI's locked
# exit-code class (0/2/3/4/5) maps to M-codes as follows:
#
#   exit 3 (load / schema validation):
#     M01 -- observe_only_policy_evaluations table absent
#     M02 -- alert_decisions table absent
#     M03 -- filter_evaluations table absent
#     M04 -- runtime policy load failed (Stage 16A R-codes surface here)
#     M07 -- invalid CLI argument (semantic, not argparse-defaulted)
#     M08 -- --limit must be a non-negative integer
#
#   exit 4 (runtime observer error):
#     M05 -- assembler decision not found
#     M06 -- repository insert failed

M_CODES: tuple[str, ...] = (
    "M01",  # observe_only_policy_evaluations table not present
    "M02",  # alert_decisions table not present
    "M03",  # filter_evaluations table not present
    "M04",  # runtime policy load failed
    "M05",  # assembler decision not found
    "M06",  # repository insert failed
    "M07",  # invalid CLI argument
    "M08",  # --limit must be non-negative integer
)


ALL_CODES: frozenset[str] = frozenset(M_CODES)


MESSAGE_TEMPLATES: Mapping[str, str] = {
    "M01": (
        "Stage 16B observe_only_policy_evaluations table is not present in "
        "the PHX2 database"
    ),
    "M02": (
        "Stage 16B requires the alert_decisions table, which is not present "
        "in the PHX2 database"
    ),
    "M03": (
        "Stage 16B requires the filter_evaluations table, which is not "
        "present in the PHX2 database"
    ),
    "M04": (
        "Stage 16B failed to load the Stage 16A observe-only runtime policy"
    ),
    "M05": (
        "Stage 16B decision-context assembler could not find the requested "
        "alert_decision_id"
    ),
    "M06": (
        "Stage 16B repository insert into observe_only_policy_evaluations "
        "failed"
    ),
    "M07": "Stage 16B received an invalid CLI argument",
    "M08": "Stage 16B --limit must be a non-negative integer",
}


class Stage16BError(Exception):
    """Raised on any Stage 16B closed-set error condition.

    Carries an M01-M08 code; callers (CLI exit-code dispatcher, tests)
    match on ``.code`` rather than inspecting the message string.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in ALL_CODES:
            raise ValueError(
                f"Stage16BError code {code!r} is not in the closed set"
            )
        self.code = code
        self.detail = detail
        template = MESSAGE_TEMPLATES[code]
        if detail:
            message = f"[{code}] {template}: {detail}"
        else:
            message = f"[{code}] {template}"
        super().__init__(message)
