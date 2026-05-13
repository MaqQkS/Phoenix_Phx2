"""Stage 16A error type and closed-set L01-L22 / R01-R08 / B01 error codes.

Per Step 0 locked remediation #2, L15 and L16 (predicate.direction /
predicate.policy_surface) are intentionally dropped: Stage 15 already trims
the predicate to 5 keys, so those checks have nothing to verify. The closed
L-code set therefore enumerates L01-L14 and L17-L22 only.
"""

from __future__ import annotations

from typing import Mapping


# ---------------------------------------------------------------------------
# Load-time (Stage 15 input) codes
# ---------------------------------------------------------------------------

L_CODES: tuple[str, ...] = (
    "L01",  # --stage15-run-path missing / not a directory
    "L02",  # required Stage 15 files missing
    "L03",  # manifest.json not valid JSON
    "L04",  # manifest.approval_status not APPROVED_DRAFT_WRITTEN
    "L05",  # manifest.stage15_schema_version wrong
    "L06",  # draft hash does not match manifest.output_files entry
    "L07",  # manifest missing required lineage fields
    "L08",  # manifest safety surface diverges from EXPECTED_STAGE15_SAFETY_SURFACE
    "L09",  # approved_observe_only_policy_draft.json not valid JSON
    "L10",  # draft.schema_version wrong
    "L11",  # draft safety surface diverges from EXPECTED_STAGE15_DRAFT_SAFETY_SURFACE
    "L12",  # draft.rules is not a list
    "L13",  # rule missing required field
    "L14",  # rule predicate keys not exactly the 5 required keys
    # L15, L16 dropped per Step 0 locked remediation #2.
    "L17",  # rule predicate.tier_scope not in ALLOWED_TIER_SCOPES
    "L18",  # rule predicate.filter_label not in ALLOWED_FILTER_LABELS
    "L19",  # duplicate rule_id in draft.rules
    "L20",  # duplicate predicate 5-tuple in draft.rules
    "L21",  # --output-dir exists and is not empty
    "L22",  # git_commit unobtainable from current PHX2 working tree
)


# ---------------------------------------------------------------------------
# Runtime-load (Stage 16A own artifact) codes
# ---------------------------------------------------------------------------

R_CODES: tuple[str, ...] = (
    "R01",  # runtime policy file missing or invalid JSON
    "R02",  # schema_version not observe_only_runtime_policy_v0
    "R03",  # safety_surface diverges from EXPECTED_RUNTIME_SAFETY_SURFACE (exact)
    "R04",  # policy_hash does not match computed canonical hash of body
    "R05",  # lineage block missing one or more required non-empty hex fields
    "R06",  # rule has wrong predicate shape or unsafe intended_action
    "R07",  # rule predicate tier_scope or filter_label not in allowed set
    "R08",  # duplicate rule_id or duplicate predicate 5-tuple
)


# ---------------------------------------------------------------------------
# Build-time defensive codes
# ---------------------------------------------------------------------------

B_CODES: tuple[str, ...] = (
    "B01",  # builder produced an artifact whose safety surface drifted from expected runtime surface
)


# ---------------------------------------------------------------------------
# Closed-set membership helper
# ---------------------------------------------------------------------------

ALL_CODES: frozenset[str] = frozenset(L_CODES) | frozenset(R_CODES) | frozenset(B_CODES)


# ---------------------------------------------------------------------------
# Per-code message templates
# ---------------------------------------------------------------------------

MESSAGE_TEMPLATES: Mapping[str, str] = {
    "L01": "Stage 15 run path is missing or is not a directory",
    "L02": "Stage 15 run directory is missing required files (manifest.json, approved_observe_only_policy_draft.json)",
    "L03": "Stage 15 manifest.json is not valid JSON",
    "L04": "Stage 15 manifest.approval_status is not 'APPROVED_DRAFT_WRITTEN'",
    "L05": "Stage 15 manifest.stage15_schema_version is not 'stage15_manifest_v0'",
    "L06": "Stage 15 approved_observe_only_policy_draft.json hash does not match manifest.output_files entry",
    "L07": "Stage 15 manifest is missing one or more required lineage fields (Stage 14/13/12 hashes, operator review hash, reviewer)",
    "L08": "Stage 15 manifest safety surface does not match the expected Stage 15 surface",
    "L09": "Stage 15 approved_observe_only_policy_draft.json is not valid JSON",
    "L10": "Stage 15 draft.schema_version is not 'stage15_approval_draft_v0'",
    "L11": "Stage 15 draft safety surface does not match the expected Stage 15 draft surface",
    "L12": "Stage 15 draft.rules is not a list",
    "L13": "Stage 15 draft rule is missing one or more required fields (rule_id, predicate, intended_action_if_wired, hard_block_allowed, operator_decision, source_stage14_rule_hash)",
    "L14": "Stage 15 draft rule predicate keys are not exactly (tier_scope, filter_name, filter_version, filter_label, threshold_version)",
    "L17": "Stage 15 draft rule predicate.tier_scope is not in {'T1', 'T2', 'T3'}",
    "L18": "Stage 15 draft rule predicate.filter_label is not in the live-schema set ('NORMAL', 'ELEVATED', 'SUSPICIOUS', 'SCAM_LIKELY', 'UNKNOWN')",
    "L19": "Stage 15 draft contains duplicate rule_id values",
    "L20": "Stage 15 draft contains two rules with the same predicate 5-tuple (tier_scope, filter_name, filter_version, filter_label, threshold_version)",
    "L21": "Stage 16A --output-dir exists and is not empty",
    "L22": "Stage 16A could not obtain git_commit from the current PHX2 working tree",
    "R01": "Observe-only runtime policy file is missing or not valid JSON",
    "R02": "Observe-only runtime policy schema_version is not 'observe_only_runtime_policy_v0'",
    "R03": "Observe-only runtime policy safety_surface does not exactly match the expected runtime surface",
    "R04": "Observe-only runtime policy policy_hash does not match the computed canonical hash of the body",
    "R05": "Observe-only runtime policy lineage block is missing one or more required non-empty hex fields",
    "R06": "Observe-only runtime policy rule has the wrong predicate shape, a missing required field, or an unsafe intended_action",
    "R07": "Observe-only runtime policy rule predicate tier_scope or filter_label is not in the allowed set",
    "R08": "Observe-only runtime policy contains duplicate rule_id values or duplicate predicate 5-tuples",
    "B01": "Stage 16A builder produced an artifact whose safety_surface drifted from EXPECTED_RUNTIME_SAFETY_SURFACE",
}


# ---------------------------------------------------------------------------
# Exception type
# ---------------------------------------------------------------------------


class Stage16AError(Exception):
    """Raised on any Stage 16A validation, load, or defensive build error.

    Carries a closed-set code (L01-L22, R01-R08, or B01). Callers (including
    the CLI three-tier exit dispatcher) match on ``.code`` rather than
    inspecting the message string.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in ALL_CODES:
            raise ValueError(
                f"Stage16AError code {code!r} is not in the closed set"
            )
        self.code = code
        self.detail = detail
        template = MESSAGE_TEMPLATES[code]
        if detail:
            message = f"[{code}] {template}: {detail}"
        else:
            message = f"[{code}] {template}"
        super().__init__(message)
