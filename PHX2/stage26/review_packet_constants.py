"""Stage 26.6 operator review packet / approval handoff closed sets.

Stage 26.6 converts Stage 26.5 observe-only policy candidate
evidence into deterministic **operator review packets**. The output
is human-facing review material -- not approved policy, not runtime
policy, not enforcement rules, not dispatch instructions, not
subscriber routing. Stage 26.6 also exposes an approval-handoff
record with PENDING_OPERATOR_REVIEW placeholders, but Stage 26.6
NEVER grants approval, marks anything runtime-consumable, marks
anything enforcement-enabled, or wires any live decision path.

The closed sets declared here pin that discipline at the vocabulary
layer:

  * ``REVIEW_PACKET_KINDS``           -- one kind per packet-level
                                         payload: the operator review
                                         packet itself, the per-
                                         candidate review row stream,
                                         the per-build review summary,
                                         and the on-disk manifest.
  * ``REVIEW_PACKET_STATUSES``        -- packet-level outcome state.
                                         ``REVIEW_ONLY_PACKET`` is the
                                         normal observe-only outcome;
                                         the ``BLOCKED_*`` states
                                         record why a packet must NOT
                                         advance.
  * ``REVIEW_CANDIDATE_STATUSES``     -- per-candidate review state.
                                         ``READY_FOR_OPERATOR_REVIEW``
                                         simply means the upstream
                                         Stage 26.5 candidate cleared
                                         the Stage 26.5 ready
                                         readiness gate; it does NOT
                                         mean any policy is approved.
  * ``APPROVAL_HANDOFF_STATUSES``     -- approval-handoff state.
                                         ``PENDING_OPERATOR_REVIEW``
                                         is the only state Stage 26.6
                                         ever emits; the other tokens
                                         are forward-pointing
                                         placeholders for a future
                                         operator decision surface.
  * ``REVIEW_PACKET_ARTIFACT_KINDS``  -- closed set of artifact
                                         categories the deterministic
                                         writer emits.
  * ``STAGE26_REVIEW_PACKET_ERROR_CODES`` -- typed-error code tokens,
                                             all prefixed
                                             ``STG26_CAL_REVIEW_PACKET_``.

Stage 26.6 does NOT declare:

  * any operator approval decision vocabulary -- Stage 29+ wiring
    (never in 26).
  * any enforcement / dispatch tokens         -- Stage 29+.
  * any subscriber / public / private routing tokens -- Stage 29+.

Stage 26.6 imports nothing from ``PHX2.stage25`` directly. The
Stage 26.6 manifest self-entry sentinels mirror Stage 25's locked
convention but are declared in Stage 26.6 vocabulary so this module
remains free of Stage 25 imports.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 26.6 version axes
# ---------------------------------------------------------------------------


STAGE26_REVIEW_PACKET_VERSION: str = "stage26_review_packet_v0"


# Deterministic-ordering version. Bumping the deterministic ordering
# convention used by the builder requires bumping this axis so
# downstream consumers can pin the exact ordering they consumed.
STAGE26_REVIEW_PACKET_DETERMINISTIC_ORDERING_VERSION: str = (
    "stage26_review_packet_ordering_v0"
)


# Stage 26.6 artifact schema version. Bumping the on-disk row /
# summary / manifest JSON shape requires bumping this axis.
STAGE26_REVIEW_PACKET_ARTIFACT_SCHEMA_VERSION: str = (
    "stage26_review_packet_artifact_v0"
)


# ---------------------------------------------------------------------------
# REVIEW_PACKET_KINDS -- locked packet-level payload kinds
# ---------------------------------------------------------------------------


REVIEW_PACKET_KIND_OPERATOR_REVIEW_PACKET: str = (
    "OPERATOR_REVIEW_PACKET"
)
REVIEW_PACKET_KIND_OPERATOR_REVIEW_CANDIDATE_ROWS: str = (
    "OPERATOR_REVIEW_CANDIDATE_ROWS"
)
REVIEW_PACKET_KIND_OPERATOR_REVIEW_SUMMARY: str = (
    "OPERATOR_REVIEW_SUMMARY"
)
REVIEW_PACKET_KIND_OPERATOR_REVIEW_MANIFEST: str = (
    "OPERATOR_REVIEW_MANIFEST"
)


REVIEW_PACKET_KINDS: tuple[str, ...] = (
    REVIEW_PACKET_KIND_OPERATOR_REVIEW_PACKET,
    REVIEW_PACKET_KIND_OPERATOR_REVIEW_CANDIDATE_ROWS,
    REVIEW_PACKET_KIND_OPERATOR_REVIEW_SUMMARY,
    REVIEW_PACKET_KIND_OPERATOR_REVIEW_MANIFEST,
)


# ---------------------------------------------------------------------------
# REVIEW_PACKET_STATUSES -- packet-level outcome states
# ---------------------------------------------------------------------------


REVIEW_PACKET_STATUS_REVIEW_ONLY_PACKET: str = "REVIEW_ONLY_PACKET"
REVIEW_PACKET_STATUS_BLOCKED_APPROVAL_LEAK: str = (
    "BLOCKED_APPROVAL_LEAK"
)
REVIEW_PACKET_STATUS_BLOCKED_RUNTIME_LEAK: str = (
    "BLOCKED_RUNTIME_LEAK"
)
REVIEW_PACKET_STATUS_BLOCKED_ENFORCEMENT_LEAK: str = (
    "BLOCKED_ENFORCEMENT_LEAK"
)
REVIEW_PACKET_STATUS_BLOCKED_REDACTION_FAILED: str = (
    "BLOCKED_REDACTION_FAILED"
)
REVIEW_PACKET_STATUS_BLOCKED_INVALID_INPUT: str = (
    "BLOCKED_INVALID_INPUT"
)


REVIEW_PACKET_STATUSES: tuple[str, ...] = (
    REVIEW_PACKET_STATUS_REVIEW_ONLY_PACKET,
    REVIEW_PACKET_STATUS_BLOCKED_APPROVAL_LEAK,
    REVIEW_PACKET_STATUS_BLOCKED_RUNTIME_LEAK,
    REVIEW_PACKET_STATUS_BLOCKED_ENFORCEMENT_LEAK,
    REVIEW_PACKET_STATUS_BLOCKED_REDACTION_FAILED,
    REVIEW_PACKET_STATUS_BLOCKED_INVALID_INPUT,
)


# ---------------------------------------------------------------------------
# REVIEW_CANDIDATE_STATUSES -- per-candidate review states
# ---------------------------------------------------------------------------


REVIEW_CANDIDATE_STATUS_READY_FOR_OPERATOR_REVIEW: str = (
    "READY_FOR_OPERATOR_REVIEW"
)
REVIEW_CANDIDATE_STATUS_NEEDS_MORE_MEASURED_ROWS: str = (
    "NEEDS_MORE_MEASURED_ROWS"
)
REVIEW_CANDIDATE_STATUS_NEEDS_BETTER_COVERAGE: str = (
    "NEEDS_BETTER_COVERAGE"
)
REVIEW_CANDIDATE_STATUS_NEEDS_SCOPE_REVIEW: str = (
    "NEEDS_SCOPE_REVIEW"
)
REVIEW_CANDIDATE_STATUS_NEEDS_REJECTION_REVIEW: str = (
    "NEEDS_REJECTION_REVIEW"
)
REVIEW_CANDIDATE_STATUS_INVALID_FOR_OPERATOR_REVIEW: str = (
    "INVALID_FOR_OPERATOR_REVIEW"
)
REVIEW_CANDIDATE_STATUS_BLOCKED_POLICY_CANDIDATE_LEAK: str = (
    "BLOCKED_POLICY_CANDIDATE_LEAK"
)


REVIEW_CANDIDATE_STATUSES: tuple[str, ...] = (
    REVIEW_CANDIDATE_STATUS_READY_FOR_OPERATOR_REVIEW,
    REVIEW_CANDIDATE_STATUS_NEEDS_MORE_MEASURED_ROWS,
    REVIEW_CANDIDATE_STATUS_NEEDS_BETTER_COVERAGE,
    REVIEW_CANDIDATE_STATUS_NEEDS_SCOPE_REVIEW,
    REVIEW_CANDIDATE_STATUS_NEEDS_REJECTION_REVIEW,
    REVIEW_CANDIDATE_STATUS_INVALID_FOR_OPERATOR_REVIEW,
    REVIEW_CANDIDATE_STATUS_BLOCKED_POLICY_CANDIDATE_LEAK,
)


# ---------------------------------------------------------------------------
# APPROVAL_HANDOFF_STATUSES -- approval handoff placeholder states
# ---------------------------------------------------------------------------
#
# Stage 26.6 ALWAYS emits ``PENDING_OPERATOR_REVIEW``. The other two
# tokens exist in the closed set so a future operator-decision
# surface can read the vocabulary without re-defining it; Stage 26.6
# itself never emits them. In particular Stage 26.6 NEVER emits
# ``APPROVED``, ``AUTO_APPROVED``, or any other "approved" token --
# operator approval is out of Stage 26.6's locked scope.


APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW: str = (
    "PENDING_OPERATOR_REVIEW"
)
APPROVAL_HANDOFF_STATUS_NOT_APPROVED: str = "NOT_APPROVED"
APPROVAL_HANDOFF_STATUS_APPROVAL_NOT_IN_STAGE_SCOPE: str = (
    "APPROVAL_NOT_IN_STAGE_SCOPE"
)


APPROVAL_HANDOFF_STATUSES: tuple[str, ...] = (
    APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW,
    APPROVAL_HANDOFF_STATUS_NOT_APPROVED,
    APPROVAL_HANDOFF_STATUS_APPROVAL_NOT_IN_STAGE_SCOPE,
)


# ---------------------------------------------------------------------------
# REVIEW_PACKET_ARTIFACT_KINDS -- writer artifact categories
# ---------------------------------------------------------------------------


REVIEW_PACKET_ARTIFACT_KIND_REVIEW_PACKET: str = "REVIEW_PACKET"
REVIEW_PACKET_ARTIFACT_KIND_REVIEW_CANDIDATE_ROWS: str = (
    "REVIEW_CANDIDATE_ROWS"
)
REVIEW_PACKET_ARTIFACT_KIND_REVIEW_SUMMARY: str = "REVIEW_SUMMARY"
REVIEW_PACKET_ARTIFACT_KIND_REVIEW_MANIFEST: str = "REVIEW_MANIFEST"


REVIEW_PACKET_ARTIFACT_KINDS: tuple[str, ...] = (
    REVIEW_PACKET_ARTIFACT_KIND_REVIEW_PACKET,
    REVIEW_PACKET_ARTIFACT_KIND_REVIEW_CANDIDATE_ROWS,
    REVIEW_PACKET_ARTIFACT_KIND_REVIEW_SUMMARY,
    REVIEW_PACKET_ARTIFACT_KIND_REVIEW_MANIFEST,
)


# ---------------------------------------------------------------------------
# Stage 26.6 artifact basenames (locked, review-only filenames)
# ---------------------------------------------------------------------------


STAGE26_OPERATOR_REVIEW_PACKET_FILENAME: str = (
    "stage26_operator_review_packet.json"
)
STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME: str = (
    "stage26_operator_review_candidates.jsonl"
)
STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME: str = (
    "stage26_operator_review_summary.json"
)
STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME: str = (
    "stage26_operator_review_manifest.json"
)


STAGE26_REVIEW_PACKET_ARTIFACT_FILENAMES: tuple[str, ...] = (
    STAGE26_OPERATOR_REVIEW_PACKET_FILENAME,
    STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME,
    STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME,
    STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME,
)


# ---------------------------------------------------------------------------
# Manifest self-entry sentinels (mirror Stage 25 / 26.5 convention)
# ---------------------------------------------------------------------------


# The self-entry sentinel must NOT look like a 64-char lowercase hex
# digest so downstream readers cannot mistake it for a real sha256.
STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_SHA256: str = (
    "stage26_review_packet_manifest_self_entry_sentinel"
)
STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT: int = -1
STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_ROW_COUNT: int = -1


# Stage 26.6 review-only mode marker. Used in the writer's packet /
# summary / manifest body so a downstream consumer can immediately
# distinguish a Stage 26.6 review packet from any future approved /
# runtime / enforcement artifact.
STAGE26_REVIEW_PACKET_REVIEW_ONLY_MODE: str = (
    "stage26_operator_review_only"
)


# Redaction-confirmed token, written into the manifest body after the
# writer's redaction sweep passes. Mirrors Stage 25 / Stage 26.5's
# redaction discipline at the Stage 26.6 vocabulary layer.
STAGE26_REVIEW_PACKET_REDACTION_CONFIRMED_TOKEN: str = (
    "stage26_review_packet_redaction_confirmed"
)


# ---------------------------------------------------------------------------
# STAGE26_REVIEW_PACKET_ERROR_CODES -- typed-error code tokens
# ---------------------------------------------------------------------------


STG26_CAL_REVIEW_PACKET_INVALID_INPUT: str = (
    "STG26_CAL_REVIEW_PACKET_INVALID_INPUT"
)
STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK: str = (
    "STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK"
)
STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK: str = (
    "STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK"
)
STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK: str = (
    "STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK"
)
STG26_CAL_REVIEW_PACKET_REDACTION_FAILED: str = (
    "STG26_CAL_REVIEW_PACKET_REDACTION_FAILED"
)
STG26_CAL_REVIEW_PACKET_MANIFEST_INVALID: str = (
    "STG26_CAL_REVIEW_PACKET_MANIFEST_INVALID"
)
STG26_CAL_REVIEW_PACKET_HASH_MISMATCH: str = (
    "STG26_CAL_REVIEW_PACKET_HASH_MISMATCH"
)
STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID: str = (
    "STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID"
)
STG26_CAL_REVIEW_PACKET_RUNTIME_FILENAME_LEAK: str = (
    "STG26_CAL_REVIEW_PACKET_RUNTIME_FILENAME_LEAK"
)
STG26_CAL_REVIEW_PACKET_MIXED_MANIFEST_HASH: str = (
    "STG26_CAL_REVIEW_PACKET_MIXED_MANIFEST_HASH"
)
STG26_CAL_REVIEW_PACKET_UNKNOWN_CANDIDATE_KIND: str = (
    "STG26_CAL_REVIEW_PACKET_UNKNOWN_CANDIDATE_KIND"
)
STG26_CAL_REVIEW_PACKET_INVALID_STATUS: str = (
    "STG26_CAL_REVIEW_PACKET_INVALID_STATUS"
)


STAGE26_REVIEW_PACKET_ERROR_CODES: tuple[str, ...] = (
    STG26_CAL_REVIEW_PACKET_INVALID_INPUT,
    STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK,
    STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK,
    STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK,
    STG26_CAL_REVIEW_PACKET_REDACTION_FAILED,
    STG26_CAL_REVIEW_PACKET_MANIFEST_INVALID,
    STG26_CAL_REVIEW_PACKET_HASH_MISMATCH,
    STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID,
    STG26_CAL_REVIEW_PACKET_RUNTIME_FILENAME_LEAK,
    STG26_CAL_REVIEW_PACKET_MIXED_MANIFEST_HASH,
    STG26_CAL_REVIEW_PACKET_UNKNOWN_CANDIDATE_KIND,
    STG26_CAL_REVIEW_PACKET_INVALID_STATUS,
)


# ---------------------------------------------------------------------------
# Default builder config
# ---------------------------------------------------------------------------


# Stage 26.6 by default includes every Stage 26.5 candidate -- even
# the blocked / needs-* ones -- so the operator review surface can
# see WHY a particular candidate did not clear. The knob is exposed
# for downstream reviewers who only want the ready candidates.
DEFAULT_INCLUDE_BLOCKED_CANDIDATES: bool = True


# ---------------------------------------------------------------------------
# Forbidden runtime / approval / enforcement filename fragments
# ---------------------------------------------------------------------------
#
# Stage 26.6 outputs MUST NOT carry any of these markers. The writer
# rejects an output basename / payload that contains a runtime-policy
# fragment or an approval / enforcement / dispatch / live-routing
# fragment so a future contributor cannot silently re-purpose the
# writer as a runtime / approved / enforcement / dispatch artifact
# emitter. The substrings are deliberately fragments (not exact
# filenames) so a clever rename does not slip past the scan.


STAGE26_REVIEW_PACKET_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS: tuple[
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
    "approval_decision",
    "live_router",
    "subscriber_router",
    "discord_packet",
    "telegram_packet",
)


# ---------------------------------------------------------------------------
# Forbidden output-content substrings (redaction sweep)
# ---------------------------------------------------------------------------
#
# Stage 26.6 outputs MUST NOT carry secrets, env values, webhook URLs,
# API keys, RPC URLs, or tokens. The writer scans every serialized
# byte stream (packet JSON + candidate rows JSONL + summary JSON +
# manifest JSON) for these fragments before promoting the artifact
# set. ``operator_approved=true`` / ``runtime_consumable=true`` /
# ``enforcement_enabled=true`` fragments are forbidden as approval /
# runtime / enforcement leak markers.


STAGE26_REVIEW_PACKET_FORBIDDEN_OUTPUT_SUBSTRINGS: tuple[str, ...] = (
    # URL / webhook fragments. Each fragment is split so this source
    # file does not itself contain a literal URL prefix.
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
    # Approval / runtime / enforcement leak fragments.
    "operator_approved=true",
    "operator_approved=True",
    "operator_approved=1",
    "runtime_consumable=true",
    "runtime_consumable=True",
    "runtime_consumable=1",
    "enforcement_enabled=true",
    "enforcement_enabled=True",
    "enforcement_enabled=1",
    # Approval state leak fragments. Stage 26.6 only ever emits the
    # PENDING_OPERATOR_REVIEW state; any literal token containing
    # "APPROVED" in the artifact bytes (other than the
    # ``operator_approved`` / ``operator_approved_count`` /
    # ``operator_approved_false_count`` field names) is a leak.
    "\"AUTO_APPROVED\"",
    "\"APPROVED\"",
)


__all__ = [
    "APPROVAL_HANDOFF_STATUSES",
    "APPROVAL_HANDOFF_STATUS_APPROVAL_NOT_IN_STAGE_SCOPE",
    "APPROVAL_HANDOFF_STATUS_NOT_APPROVED",
    "APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW",
    "DEFAULT_INCLUDE_BLOCKED_CANDIDATES",
    "REVIEW_CANDIDATE_STATUSES",
    "REVIEW_CANDIDATE_STATUS_BLOCKED_POLICY_CANDIDATE_LEAK",
    "REVIEW_CANDIDATE_STATUS_INVALID_FOR_OPERATOR_REVIEW",
    "REVIEW_CANDIDATE_STATUS_NEEDS_BETTER_COVERAGE",
    "REVIEW_CANDIDATE_STATUS_NEEDS_MORE_MEASURED_ROWS",
    "REVIEW_CANDIDATE_STATUS_NEEDS_REJECTION_REVIEW",
    "REVIEW_CANDIDATE_STATUS_NEEDS_SCOPE_REVIEW",
    "REVIEW_CANDIDATE_STATUS_READY_FOR_OPERATOR_REVIEW",
    "REVIEW_PACKET_ARTIFACT_KINDS",
    "REVIEW_PACKET_ARTIFACT_KIND_REVIEW_CANDIDATE_ROWS",
    "REVIEW_PACKET_ARTIFACT_KIND_REVIEW_MANIFEST",
    "REVIEW_PACKET_ARTIFACT_KIND_REVIEW_PACKET",
    "REVIEW_PACKET_ARTIFACT_KIND_REVIEW_SUMMARY",
    "REVIEW_PACKET_KINDS",
    "REVIEW_PACKET_KIND_OPERATOR_REVIEW_CANDIDATE_ROWS",
    "REVIEW_PACKET_KIND_OPERATOR_REVIEW_MANIFEST",
    "REVIEW_PACKET_KIND_OPERATOR_REVIEW_PACKET",
    "REVIEW_PACKET_KIND_OPERATOR_REVIEW_SUMMARY",
    "REVIEW_PACKET_STATUSES",
    "REVIEW_PACKET_STATUS_BLOCKED_APPROVAL_LEAK",
    "REVIEW_PACKET_STATUS_BLOCKED_ENFORCEMENT_LEAK",
    "REVIEW_PACKET_STATUS_BLOCKED_INVALID_INPUT",
    "REVIEW_PACKET_STATUS_BLOCKED_REDACTION_FAILED",
    "REVIEW_PACKET_STATUS_BLOCKED_RUNTIME_LEAK",
    "REVIEW_PACKET_STATUS_REVIEW_ONLY_PACKET",
    "STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME",
    "STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME",
    "STAGE26_OPERATOR_REVIEW_PACKET_FILENAME",
    "STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME",
    "STAGE26_REVIEW_PACKET_ARTIFACT_FILENAMES",
    "STAGE26_REVIEW_PACKET_ARTIFACT_SCHEMA_VERSION",
    "STAGE26_REVIEW_PACKET_DETERMINISTIC_ORDERING_VERSION",
    "STAGE26_REVIEW_PACKET_ERROR_CODES",
    "STAGE26_REVIEW_PACKET_FORBIDDEN_OUTPUT_SUBSTRINGS",
    "STAGE26_REVIEW_PACKET_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS",
    "STAGE26_REVIEW_PACKET_REDACTION_CONFIRMED_TOKEN",
    "STAGE26_REVIEW_PACKET_REVIEW_ONLY_MODE",
    "STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_BYTE_COUNT",
    "STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_ROW_COUNT",
    "STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_SHA256",
    "STAGE26_REVIEW_PACKET_VERSION",
    "STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK",
    "STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK",
    "STG26_CAL_REVIEW_PACKET_HASH_MISMATCH",
    "STG26_CAL_REVIEW_PACKET_INVALID_INPUT",
    "STG26_CAL_REVIEW_PACKET_INVALID_STATUS",
    "STG26_CAL_REVIEW_PACKET_MANIFEST_INVALID",
    "STG26_CAL_REVIEW_PACKET_MIXED_MANIFEST_HASH",
    "STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID",
    "STG26_CAL_REVIEW_PACKET_REDACTION_FAILED",
    "STG26_CAL_REVIEW_PACKET_RUNTIME_FILENAME_LEAK",
    "STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK",
    "STG26_CAL_REVIEW_PACKET_UNKNOWN_CANDIDATE_KIND",
]
