"""Stage 26.5 observe-only policy candidate closed sets.

Stage 26.5 converts Stage 26.4 threshold candidate evidence into
deterministic observe-only **policy candidate** artifacts. The
output is review material -- not approved policy, not runtime
policy, not enforcement rules, not dispatch instructions. The
closed sets declared here pin that discipline at the vocabulary
layer:

  * ``POLICY_CANDIDATE_KINDS``        -- one kind per candidate
                                         derivation lane:
                                         primary-measured threshold
                                         evidence vs. coverage /
                                         observability / rejection
                                         caveats. Stage 26.5 NEVER
                                         invents a new caveat lane;
                                         every kind maps back to a
                                         Stage 26.4 evidence class.
  * ``POLICY_CANDIDATE_STATUSES``     -- per-candidate outcome state.
                                         ``OBSERVE_ONLY_CANDIDATE`` is
                                         the normal non-suppressed
                                         outcome; the ``BLOCKED_*``
                                         states record why a candidate
                                         must NOT advance.
  * ``POLICY_CANDIDATE_READINESSES``  -- per-candidate readiness for
                                         downstream operator review.
                                         ``READY_FOR_OPERATOR_REVIEW``
                                         simply means the candidate
                                         cleared the Stage 26.5
                                         provenance + safety-lock
                                         gates; it does NOT mean any
                                         policy is approved.
  * ``POLICY_CANDIDATE_ARTIFACT_KINDS`` -- closed set of artifact
                                           categories the deterministic
                                           writer emits.
  * ``STAGE26_POLICY_CANDIDATE_ERROR_CODES`` -- typed-error code
                                                 tokens, all prefixed
                                                 ``STG26_CAL_POLICY_CANDIDATE_``.

Stage 26.5 does NOT declare:

  * any operator review packet vocabulary -- Stage 26.6.
  * any approval-state / approval-actor vocabulary -- Stage 26.6.
  * any enforcement / dispatch tokens     -- Stage 29+ (never in 26).
  * any subscriber / public / private routing tokens -- Stage 29+.

Stage 26.5 imports nothing from ``PHX2.stage25`` directly. The
Stage 26.5 manifest self-entry sentinels mirror Stage 25's locked
convention but are declared in Stage 26.5 vocabulary so this module
remains free of Stage 25 imports.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 26.5 version axes
# ---------------------------------------------------------------------------


STAGE26_POLICY_CANDIDATE_VERSION: str = "stage26_policy_candidate_v0"


# Deterministic-ordering version. Bumping the deterministic ordering
# convention used by the builder (lexicographic sort on
# (cohort_key.values, candidate_kind)) requires bumping this axis so
# downstream consumers can pin the exact ordering they consumed.
STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION: str = (
    "stage26_policy_candidate_ordering_v0"
)


# Stage 26.5 artifact schema version. Bumping the on-disk row /
# summary / manifest JSON shape requires bumping this axis.
STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION: str = (
    "stage26_policy_candidate_artifact_v0"
)


# ---------------------------------------------------------------------------
# POLICY_CANDIDATE_KINDS -- locked candidate kinds
# ---------------------------------------------------------------------------


POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE: str = (
    "THRESHOLD_POLICY_CANDIDATE"
)
POLICY_CANDIDATE_KIND_COVERAGE_CAVEAT_POLICY_CANDIDATE: str = (
    "COVERAGE_CAVEAT_POLICY_CANDIDATE"
)
POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE: str = (
    "OBSERVABILITY_CAVEAT_POLICY_CANDIDATE"
)
POLICY_CANDIDATE_KIND_REJECTION_CAVEAT_POLICY_CANDIDATE: str = (
    "REJECTION_CAVEAT_POLICY_CANDIDATE"
)


POLICY_CANDIDATE_KINDS: tuple[str, ...] = (
    POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE,
    POLICY_CANDIDATE_KIND_COVERAGE_CAVEAT_POLICY_CANDIDATE,
    POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE,
    POLICY_CANDIDATE_KIND_REJECTION_CAVEAT_POLICY_CANDIDATE,
)


# ---------------------------------------------------------------------------
# POLICY_CANDIDATE_STATUSES -- per-candidate outcome states
# ---------------------------------------------------------------------------


POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE: str = (
    "OBSERVE_ONLY_CANDIDATE"
)
POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE: str = (
    "BLOCKED_INSUFFICIENT_EVIDENCE"
)
POLICY_CANDIDATE_STATUS_BLOCKED_INVALID_THRESHOLD: str = (
    "BLOCKED_INVALID_THRESHOLD"
)
POLICY_CANDIDATE_STATUS_BLOCKED_POLICY_LEAK: str = (
    "BLOCKED_POLICY_LEAK"
)
POLICY_CANDIDATE_STATUS_BLOCKED_RUNTIME_CONSUMABLE: str = (
    "BLOCKED_RUNTIME_CONSUMABLE"
)
POLICY_CANDIDATE_STATUS_BLOCKED_APPROVAL_LEAK: str = (
    "BLOCKED_APPROVAL_LEAK"
)


POLICY_CANDIDATE_STATUSES: tuple[str, ...] = (
    POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE,
    POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE,
    POLICY_CANDIDATE_STATUS_BLOCKED_INVALID_THRESHOLD,
    POLICY_CANDIDATE_STATUS_BLOCKED_POLICY_LEAK,
    POLICY_CANDIDATE_STATUS_BLOCKED_RUNTIME_CONSUMABLE,
    POLICY_CANDIDATE_STATUS_BLOCKED_APPROVAL_LEAK,
)


# ---------------------------------------------------------------------------
# POLICY_CANDIDATE_READINESSES -- readiness for operator review
# ---------------------------------------------------------------------------


POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW: str = (
    "READY_FOR_OPERATOR_REVIEW"
)
POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS: str = (
    "NEEDS_MORE_MEASURED_ROWS"
)
POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE: str = (
    "NEEDS_BETTER_COVERAGE"
)
POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW: str = (
    "NEEDS_SCOPE_REVIEW"
)
POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW: str = (
    "NEEDS_REJECTION_REVIEW"
)
POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW: str = (
    "INVALID_FOR_OPERATOR_REVIEW"
)


POLICY_CANDIDATE_READINESSES: tuple[str, ...] = (
    POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW,
    POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS,
    POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE,
    POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW,
    POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW,
    POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW,
)


# ---------------------------------------------------------------------------
# POLICY_CANDIDATE_ARTIFACT_KINDS -- artifact categories the writer emits
# ---------------------------------------------------------------------------


POLICY_CANDIDATE_ARTIFACT_KIND_ROWS: str = "POLICY_CANDIDATE_ROWS"
POLICY_CANDIDATE_ARTIFACT_KIND_SUMMARY: str = (
    "POLICY_CANDIDATE_SUMMARY"
)
POLICY_CANDIDATE_ARTIFACT_KIND_MANIFEST: str = (
    "POLICY_CANDIDATE_MANIFEST"
)


POLICY_CANDIDATE_ARTIFACT_KINDS: tuple[str, ...] = (
    POLICY_CANDIDATE_ARTIFACT_KIND_ROWS,
    POLICY_CANDIDATE_ARTIFACT_KIND_SUMMARY,
    POLICY_CANDIDATE_ARTIFACT_KIND_MANIFEST,
)


# ---------------------------------------------------------------------------
# Stage 26.5 artifact basenames (locked, observe-only filenames)
# ---------------------------------------------------------------------------


STAGE26_POLICY_CANDIDATE_ROWS_FILENAME: str = (
    "stage26_policy_candidates.jsonl"
)
STAGE26_POLICY_CANDIDATE_SUMMARY_FILENAME: str = (
    "stage26_policy_candidate_summary.json"
)
STAGE26_POLICY_CANDIDATE_MANIFEST_FILENAME: str = (
    "stage26_policy_candidate_manifest.json"
)


STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES: tuple[str, ...] = (
    STAGE26_POLICY_CANDIDATE_ROWS_FILENAME,
    STAGE26_POLICY_CANDIDATE_SUMMARY_FILENAME,
    STAGE26_POLICY_CANDIDATE_MANIFEST_FILENAME,
)


# ---------------------------------------------------------------------------
# Manifest self-entry sentinels (mirror Stage 25 convention, declared in
# Stage 26.5 vocabulary so this module does not import Stage 25)
# ---------------------------------------------------------------------------


# The self-entry sentinel must NOT look like a 64-char lowercase hex
# digest so downstream readers cannot mistake it for a real sha256.
STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_SHA256: str = (
    "stage26_policy_candidate_manifest_self_entry_sentinel"
)
STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT: int = -1
STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_ROW_COUNT: int = -1


# Stage 26.5 observe-only mode marker. Used in the writer's summary +
# manifest body so a downstream consumer can immediately distinguish a
# Stage 26.5 observe-only artifact from any future runtime artifact.
STAGE26_POLICY_CANDIDATE_OBSERVE_ONLY_MODE: str = (
    "stage26_policy_candidate_observe_only"
)


# Redaction-confirmed token, written into the manifest body after the
# writer's redaction sweep passes. Mirrors Stage 25's redaction
# discipline at the Stage 26.5 vocabulary layer.
STAGE26_POLICY_CANDIDATE_REDACTION_CONFIRMED_TOKEN: str = (
    "stage26_policy_candidate_redaction_confirmed"
)


# ---------------------------------------------------------------------------
# STAGE26_POLICY_CANDIDATE_ERROR_CODES -- typed-error code tokens
# ---------------------------------------------------------------------------


STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD: str = (
    "STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD"
)
STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK: str = (
    "STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK"
)
STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK: str = (
    "STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK"
)
STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK: str = (
    "STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK"
)
STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS: str = (
    "STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS"
)
STG26_CAL_POLICY_CANDIDATE_HASH_MISMATCH: str = (
    "STG26_CAL_POLICY_CANDIDATE_HASH_MISMATCH"
)
STG26_CAL_POLICY_CANDIDATE_MANIFEST_INVALID: str = (
    "STG26_CAL_POLICY_CANDIDATE_MANIFEST_INVALID"
)
STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED: str = (
    "STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED"
)
STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID: str = (
    "STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID"
)
STG26_CAL_POLICY_CANDIDATE_RUNTIME_FILENAME_LEAK: str = (
    "STG26_CAL_POLICY_CANDIDATE_RUNTIME_FILENAME_LEAK"
)
STG26_CAL_POLICY_CANDIDATE_MIXED_MANIFEST_HASH: str = (
    "STG26_CAL_POLICY_CANDIDATE_MIXED_MANIFEST_HASH"
)
STG26_CAL_POLICY_CANDIDATE_UNKNOWN_EVIDENCE_CLASS: str = (
    "STG26_CAL_POLICY_CANDIDATE_UNKNOWN_EVIDENCE_CLASS"
)


STAGE26_POLICY_CANDIDATE_ERROR_CODES: tuple[str, ...] = (
    STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD,
    STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK,
    STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK,
    STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK,
    STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS,
    STG26_CAL_POLICY_CANDIDATE_HASH_MISMATCH,
    STG26_CAL_POLICY_CANDIDATE_MANIFEST_INVALID,
    STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED,
    STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID,
    STG26_CAL_POLICY_CANDIDATE_RUNTIME_FILENAME_LEAK,
    STG26_CAL_POLICY_CANDIDATE_MIXED_MANIFEST_HASH,
    STG26_CAL_POLICY_CANDIDATE_UNKNOWN_EVIDENCE_CLASS,
)


# ---------------------------------------------------------------------------
# Default builder config
# ---------------------------------------------------------------------------


# Stage 26.5 by default emits every Stage 26.4 candidate (including
# the non-ready ones) so the operator review surface can see WHY a
# cohort did not clear. The minimum-ready-threshold-candidates knob
# is informational; the builder does not drop input candidates based
# on it, but the summary records it for downstream review traceability.
DEFAULT_MIN_READY_THRESHOLD_CANDIDATES: int = 0
DEFAULT_INCLUDE_NON_READY_CANDIDATES: bool = True


# ---------------------------------------------------------------------------
# Forbidden runtime-policy filename + marker fragments
# ---------------------------------------------------------------------------
#
# Stage 26.5 outputs MUST NOT carry any of these markers. The writer
# rejects an output basename / payload that contains a runtime-policy
# fragment so a future contributor cannot silently re-purpose the
# writer as a runtime policy emitter. The substrings are deliberately
# fragments (not exact filenames) so a clever rename does not slip
# past the scan.


STAGE26_POLICY_CANDIDATE_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS: tuple[
    str, ...
] = (
    "runtime_policy",
    "approved_policy",
    "enforcement_policy",
    "live_policy",
    "policy_dispatch",
    "subscriber_policy",
    "public_policy",
    "private_policy",
    "operator_review_packet",
    "approval_decision",
)


# ---------------------------------------------------------------------------
# Forbidden output-content substrings (redaction sweep)
# ---------------------------------------------------------------------------
#
# Stage 26.5 outputs MUST NOT carry secrets, env values, webhook URLs,
# API keys, RPC URLs, or tokens. The writer scans every serialized
# byte stream (rows JSONL + summary JSON + manifest JSON) for these
# fragments before promoting the artifact set.


STAGE26_POLICY_CANDIDATE_FORBIDDEN_OUTPUT_SUBSTRINGS: tuple[str, ...] = (
    # URL / webhook fragments. Each fragment is split so this source
    # file does not itself contain a literal URL prefix (the closure-
    # audit URL boundary check forbids it).
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
    # Common secret / credential field-name fragments.
    "api_key",
    "api-token",
    "api_secret",
    "secret_key",
    "private_key",
    "webhook_url",
    "auth_token",
    "bearer ",
    "bearer_token",
    "session_token",
    "access_token",
    "refresh_token",
    # Solana RPC / endpoint fragments commonly used by Phoenix.
    "rpc_url",
    "helius",
    "jupiter.ag",
    # Approval / enforcement leak fragments.
    "operator_approved=true",
    "operator_approved=True",
    "operator_approved=1",
    "runtime_consumable=true",
    "runtime_consumable=True",
    "runtime_consumable=1",
    "enforcement_enabled=true",
    "enforcement_enabled=True",
    "enforcement_enabled=1",
)


__all__ = [
    "DEFAULT_INCLUDE_NON_READY_CANDIDATES",
    "DEFAULT_MIN_READY_THRESHOLD_CANDIDATES",
    "POLICY_CANDIDATE_ARTIFACT_KINDS",
    "POLICY_CANDIDATE_ARTIFACT_KIND_MANIFEST",
    "POLICY_CANDIDATE_ARTIFACT_KIND_ROWS",
    "POLICY_CANDIDATE_ARTIFACT_KIND_SUMMARY",
    "POLICY_CANDIDATE_KINDS",
    "POLICY_CANDIDATE_KIND_COVERAGE_CAVEAT_POLICY_CANDIDATE",
    "POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE",
    "POLICY_CANDIDATE_KIND_REJECTION_CAVEAT_POLICY_CANDIDATE",
    "POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE",
    "POLICY_CANDIDATE_READINESSES",
    "POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW",
    "POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE",
    "POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS",
    "POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW",
    "POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW",
    "POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW",
    "POLICY_CANDIDATE_STATUSES",
    "POLICY_CANDIDATE_STATUS_BLOCKED_APPROVAL_LEAK",
    "POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE",
    "POLICY_CANDIDATE_STATUS_BLOCKED_INVALID_THRESHOLD",
    "POLICY_CANDIDATE_STATUS_BLOCKED_POLICY_LEAK",
    "POLICY_CANDIDATE_STATUS_BLOCKED_RUNTIME_CONSUMABLE",
    "POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE",
    "STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES",
    "STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION",
    "STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION",
    "STAGE26_POLICY_CANDIDATE_ERROR_CODES",
    "STAGE26_POLICY_CANDIDATE_FORBIDDEN_OUTPUT_SUBSTRINGS",
    "STAGE26_POLICY_CANDIDATE_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS",
    "STAGE26_POLICY_CANDIDATE_MANIFEST_FILENAME",
    "STAGE26_POLICY_CANDIDATE_OBSERVE_ONLY_MODE",
    "STAGE26_POLICY_CANDIDATE_REDACTION_CONFIRMED_TOKEN",
    "STAGE26_POLICY_CANDIDATE_ROWS_FILENAME",
    "STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT",
    "STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_ROW_COUNT",
    "STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_SHA256",
    "STAGE26_POLICY_CANDIDATE_SUMMARY_FILENAME",
    "STAGE26_POLICY_CANDIDATE_VERSION",
    "STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK",
    "STG26_CAL_POLICY_CANDIDATE_HASH_MISMATCH",
    "STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS",
    "STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD",
    "STG26_CAL_POLICY_CANDIDATE_MANIFEST_INVALID",
    "STG26_CAL_POLICY_CANDIDATE_MIXED_MANIFEST_HASH",
    "STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID",
    "STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK",
    "STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED",
    "STG26_CAL_POLICY_CANDIDATE_RUNTIME_FILENAME_LEAK",
    "STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK",
    "STG26_CAL_POLICY_CANDIDATE_UNKNOWN_EVIDENCE_CLASS",
]
