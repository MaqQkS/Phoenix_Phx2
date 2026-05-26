"""Stage 29.5 migration evidence closed-set vocabularies and
immutable record shapes.

Stage 29.5 ships the migration evidence adapter layer that lets
the existing Stage 28.9 private operator ping render path
surface post-migration ATH verification context. The records in
this module are the in-memory data classes that the Stage 29.5
Helius WS adapter, the Stage 29.5 artifact reader, the Stage
29.5 candidate-to-migration join layer, and the Stage 29.5
private ping migration context projection all share.

Closed-set vocabularies (pinned by Stage 29.5.0 spec-lock
section 6):

  * ``migration_status``       -- ``PRESENT`` / ``MISSING`` /
                                  ``CONFLICTING`` / ``INVALID`` /
                                  ``STALE``
  * ``migration_source``       -- ``HELIUS_WS`` /
                                  ``STAGE29_MIGRATION_ARTIFACT`` /
                                  ``SYNTHETIC_TEST_ONLY`` /
                                  ``UNKNOWN``
  * ``migration_join_status``  -- ``JOINED`` / ``NO_MATCH`` /
                                  ``MULTIPLE_MATCHES`` /
                                  ``SOURCE_INVALID`` /
                                  ``TIME_WINDOW_INVALID`` /
                                  ``PAIR_MISMATCH``
  * ``measurement_status``     -- ``MISSING_MIGRATION`` /
                                  ``PARTIAL_MIGRATION_PRESENT`` /
                                  ``COMPLETE`` /
                                  ``INVALID_MIGRATION`` /
                                  ``CONFLICTING_MIGRATION``
  * warning codes (8)          -- ``MIGRATION_MISSING`` /
                                  ``POST_MIGRATION_ATH_UNVERIFIED`` /
                                  ``MIGRATION_SOURCE_UNKNOWN`` /
                                  ``MIGRATION_CONFLICT`` /
                                  ``MIGRATION_STALE`` /
                                  ``MIGRATION_TIMESTAMP_INVALID`` /
                                  ``MIGRATION_PAIR_MISMATCH`` /
                                  ``MIGRATION_SLOT_MISSING``
  * ``redaction_status``       -- ``SAFE`` / ``REDACTED``
  * ``filter_enforcement_status`` (locked) --
                                  ``NOT_ACTIVE_STAGE_29_PENDING``

Stage 29.5 deliberately does NOT carry:

  * raw Helius WS provider payloads (no field ever takes a raw
    payload blob),
  * raw API keys, webhook URLs, endpoint URLs (no field admits
    them),
  * wallet / private-key / signer fields (no field admits them),
  * fabricated migration timestamps or invented migration slot
    values (every required axis stays ``None`` when the
    upstream source did not supply it).

This module imports ONLY stdlib (``dataclasses`` / ``typing``).
It does NOT import:

  * Stage 21-26 production code,
  * Stage 27 production code (Stage 29.5 projection consumes
    Stage 27 records read-only from a different module),
  * Stage 28 production code,
  * Stage 29.1 / 29.2 / 29.3 / 29.4 production code,
  * any network / RPC / WS / messaging / DB / scheduler /
    secrets / wallet / trading / Discord / Telegram / X /
    dotenv / keyring library,
  * ``os`` / the process environment,
  * any PHX1 / legacy Phoenix-1 source tree module.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` /
    ``os.environb`` are never touched.
  * No network.
  * No top-level Call (no implicit I/O at import time).
  * Every dataclass validates closed-set tokens at
    ``__post_init__`` so the closed-set contract cannot be
    bypassed.
  * ``filter_enforcement_status`` defaults to
    ``NOT_ACTIVE_STAGE_29_PENDING`` and any other value is
    rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Schema versions
# ---------------------------------------------------------------------------


STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION: str = (
    "stage29_5_v0_migration_evidence"
)
STAGE29_5_MIGRATION_JOIN_SCHEMA_VERSION: str = (
    "stage29_5_v0_migration_join"
)
STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION: str = (
    "stage29_5_v0_private_ping_context"
)


# ---------------------------------------------------------------------------
# Closed-set: migration_status
# ---------------------------------------------------------------------------


MIGRATION_STATUS_PRESENT: str = "PRESENT"
MIGRATION_STATUS_MISSING: str = "MISSING"
MIGRATION_STATUS_CONFLICTING: str = "CONFLICTING"
MIGRATION_STATUS_INVALID: str = "INVALID"
MIGRATION_STATUS_STALE: str = "STALE"

STAGE29_5_MIGRATION_STATUS_VALUES: Tuple[str, ...] = (
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_CONFLICTING,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_STALE,
)


def is_stage29_5_migration_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE29_5_MIGRATION_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: migration_source
# ---------------------------------------------------------------------------


MIGRATION_SOURCE_HELIUS_WS: str = "HELIUS_WS"
MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT: str = (
    "STAGE29_MIGRATION_ARTIFACT"
)
MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY: str = (
    "SYNTHETIC_TEST_ONLY"
)
MIGRATION_SOURCE_UNKNOWN_STAGE29_5: str = "UNKNOWN"

STAGE29_5_MIGRATION_SOURCE_VALUES: Tuple[str, ...] = (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
)


def is_stage29_5_migration_source_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE29_5_MIGRATION_SOURCE_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: migration_join_status
# ---------------------------------------------------------------------------


MIGRATION_JOIN_STATUS_JOINED: str = "JOINED"
MIGRATION_JOIN_STATUS_NO_MATCH: str = "NO_MATCH"
MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES: str = "MULTIPLE_MATCHES"
MIGRATION_JOIN_STATUS_SOURCE_INVALID: str = "SOURCE_INVALID"
MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID: str = (
    "TIME_WINDOW_INVALID"
)
MIGRATION_JOIN_STATUS_PAIR_MISMATCH: str = "PAIR_MISMATCH"

STAGE29_5_MIGRATION_JOIN_STATUS_VALUES: Tuple[str, ...] = (
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_NO_MATCH,
    MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
    MIGRATION_JOIN_STATUS_SOURCE_INVALID,
    MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
    MIGRATION_JOIN_STATUS_PAIR_MISMATCH,
)


def is_stage29_5_migration_join_status_value(
    value: object,
) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE29_5_MIGRATION_JOIN_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: measurement_status
# ---------------------------------------------------------------------------


MEASUREMENT_STATUS_MISSING_MIGRATION: str = "MISSING_MIGRATION"
MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT: str = (
    "PARTIAL_MIGRATION_PRESENT"
)
MEASUREMENT_STATUS_COMPLETE: str = "COMPLETE"
MEASUREMENT_STATUS_INVALID_MIGRATION: str = "INVALID_MIGRATION"
MEASUREMENT_STATUS_CONFLICTING_MIGRATION: str = (
    "CONFLICTING_MIGRATION"
)

STAGE29_5_MEASUREMENT_STATUS_VALUES: Tuple[str, ...] = (
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_INVALID_MIGRATION,
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
)


def is_stage29_5_measurement_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE29_5_MEASUREMENT_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: warning codes
# ---------------------------------------------------------------------------


WARNING_MIGRATION_MISSING: str = "MIGRATION_MISSING"
WARNING_POST_MIGRATION_ATH_UNVERIFIED: str = (
    "POST_MIGRATION_ATH_UNVERIFIED"
)
WARNING_MIGRATION_SOURCE_UNKNOWN: str = (
    "MIGRATION_SOURCE_UNKNOWN"
)
WARNING_MIGRATION_CONFLICT: str = "MIGRATION_CONFLICT"
WARNING_MIGRATION_STALE: str = "MIGRATION_STALE"
WARNING_MIGRATION_TIMESTAMP_INVALID: str = (
    "MIGRATION_TIMESTAMP_INVALID"
)
WARNING_MIGRATION_PAIR_MISMATCH: str = (
    "MIGRATION_PAIR_MISMATCH"
)
WARNING_MIGRATION_SLOT_MISSING: str = (
    "MIGRATION_SLOT_MISSING"
)

STAGE29_5_WARNING_CODE_VALUES: Tuple[str, ...] = (
    WARNING_MIGRATION_MISSING,
    WARNING_POST_MIGRATION_ATH_UNVERIFIED,
    WARNING_MIGRATION_SOURCE_UNKNOWN,
    WARNING_MIGRATION_CONFLICT,
    WARNING_MIGRATION_STALE,
    WARNING_MIGRATION_TIMESTAMP_INVALID,
    WARNING_MIGRATION_PAIR_MISMATCH,
    WARNING_MIGRATION_SLOT_MISSING,
)


def is_stage29_5_warning_code_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE29_5_WARNING_CODE_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: redaction_status
# ---------------------------------------------------------------------------


REDACTION_STATUS_SAFE: str = "SAFE"
REDACTION_STATUS_REDACTED: str = "REDACTED"

STAGE29_5_REDACTION_STATUS_VALUES: Tuple[str, ...] = (
    REDACTION_STATUS_SAFE,
    REDACTION_STATUS_REDACTED,
)


def is_stage29_5_redaction_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE29_5_REDACTION_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Filter enforcement status (locked verbatim)
# ---------------------------------------------------------------------------


FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING: str = (
    "NOT_ACTIVE_STAGE_29_PENDING"
)

STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES: Tuple[str, ...] = (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
)


# ---------------------------------------------------------------------------
# Closed-set: refusal_reason (for the Stage 29.5 error type)
# ---------------------------------------------------------------------------


REFUSAL_REASON_NONE: str = "NONE"
REFUSAL_REASON_MALFORMED_PAYLOAD: str = "MALFORMED_PAYLOAD"
REFUSAL_REASON_UNSUPPORTED_KIND: str = "UNSUPPORTED_KIND"
REFUSAL_REASON_MISSING_REQUIRED_AXIS: str = (
    "MISSING_REQUIRED_AXIS"
)
REFUSAL_REASON_UNREADABLE_ARTIFACT: str = (
    "UNREADABLE_ARTIFACT"
)
REFUSAL_REASON_SOURCE_INVALID: str = "SOURCE_INVALID"
REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED: str = (
    "SYNTHETIC_SOURCE_REJECTED"
)
REFUSAL_REASON_BUDGET_EXCEEDED: str = "BUDGET_EXCEEDED"

STAGE29_5_REFUSAL_REASON_VALUES: Tuple[str, ...] = (
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_MALFORMED_PAYLOAD,
    REFUSAL_REASON_UNSUPPORTED_KIND,
    REFUSAL_REASON_MISSING_REQUIRED_AXIS,
    REFUSAL_REASON_UNREADABLE_ARTIFACT,
    REFUSAL_REASON_SOURCE_INVALID,
    REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED,
    REFUSAL_REASON_BUDGET_EXCEEDED,
)


def is_stage29_5_refusal_reason_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE29_5_REFUSAL_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Safe-shape validators
# ---------------------------------------------------------------------------


_MIN_SAFE_BASE58_LENGTH: int = 32
_MAX_SAFE_BASE58_LENGTH: int = 64


def is_safe_mint_or_pool_string(value: object) -> bool:
    """Return True iff value is a printable string in the
    canonical safe length range [32, 64]. The Stage 29.5 records
    never accept anything shorter or longer; the bound is a
    defensive sanity check that excludes obviously truncated or
    obviously-too-long bytes blobs.
    """
    if not isinstance(value, str):
        return False
    n = len(value)
    if n < _MIN_SAFE_BASE58_LENGTH:
        return False
    if n > _MAX_SAFE_BASE58_LENGTH:
        return False
    return value.isprintable() and not any(
        ch.isspace() for ch in value
    )


def is_safe_iso8601_utc_string(value: object) -> bool:
    """Return True iff value is a non-empty printable string that
    ends with a UTC marker (``Z`` or ``+00:00``).

    Stage 29.5 never parses the timestamp here; it only enforces
    that the supplied value is UTC-shaped so downstream
    lexicographic comparison stays meaningful. The Stage 29.5
    join layer compares timestamps as strings; the Stage 27.4
    reader is the authority for parsing.
    """
    if not isinstance(value, str):
        return False
    if not value:
        return False
    if not value.isprintable():
        return False
    if any(ch.isspace() for ch in value):
        return False
    return value.endswith("Z") or value.endswith("+00:00")


# ---------------------------------------------------------------------------
# Immutable record: migration evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5MigrationEvidenceRecord:
    """Immutable Stage 29.5 migration evidence record.

    Closed-set fields only. The Stage 29.5 Helius WS adapter and
    the Stage 29.5 artifact reader both emit instances of this
    record. The Stage 29.5 join layer is the only consumer.

    Validators enforce:

      * ``migration_status`` ∈
        :data:`STAGE29_5_MIGRATION_STATUS_VALUES`
      * ``migration_source`` ∈
        :data:`STAGE29_5_MIGRATION_SOURCE_VALUES`
      * ``observed_at_utc`` is a UTC-shaped ISO-8601 string
      * ``migration_status=PRESENT`` requires the quartet
        (``base_mint``, ``pool_account``, ``pool_program_id``,
        ``quote_mint``), the ``migration_timestamp_utc``, all
        non-``None``, AND ``migration_source != UNKNOWN``.
      * ``migration_status=MISSING`` requires every optional
        axis (``base_mint``, ``pool_account``,
        ``pool_program_id``, ``quote_mint``,
        ``migration_timestamp_utc``, ``migration_slot``,
        ``migration_signature``, ``source_event_ref``) to be
        ``None`` AND ``migration_source ∈ {UNKNOWN}``.
      * ``migration_slot`` if present must be a non-negative
        ``int``.

    No raw payload, no secret value, no webhook URL admitted.
    """

    migration_status: str
    migration_source: str
    base_mint: Optional[str]
    pool_account: Optional[str]
    pool_program_id: Optional[str]
    quote_mint: Optional[str]
    migration_timestamp_utc: Optional[str]
    migration_slot: Optional[int]
    migration_signature: Optional[str]
    observed_at_utc: str
    source_event_ref: Optional[str]
    schema_version: str = (
        STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if not is_stage29_5_migration_status_value(
            self.migration_status
        ):
            raise ValueError(
                "Stage29_5MigrationEvidenceRecord."
                "migration_status must be a closed-set token; "
                f"got {self.migration_status!r}"
            )
        if not is_stage29_5_migration_source_value(
            self.migration_source
        ):
            raise ValueError(
                "Stage29_5MigrationEvidenceRecord."
                "migration_source must be a closed-set token; "
                f"got {self.migration_source!r}"
            )
        if not is_safe_iso8601_utc_string(
            self.observed_at_utc
        ):
            raise ValueError(
                "Stage29_5MigrationEvidenceRecord."
                "observed_at_utc must be a UTC-shaped ISO-8601 "
                f"string; got {self.observed_at_utc!r}"
            )
        for axis_name, axis_value in (
            ("base_mint", self.base_mint),
            ("pool_account", self.pool_account),
            ("pool_program_id", self.pool_program_id),
            ("quote_mint", self.quote_mint),
        ):
            if axis_value is not None and not (
                is_safe_mint_or_pool_string(axis_value)
            ):
                raise ValueError(
                    "Stage29_5MigrationEvidenceRecord."
                    f"{axis_name} must be a safe-shape printable "
                    f"string of length 32..64; got "
                    f"{axis_value!r}"
                )
        if (
            self.migration_timestamp_utc is not None
            and not is_safe_iso8601_utc_string(
                self.migration_timestamp_utc
            )
        ):
            raise ValueError(
                "Stage29_5MigrationEvidenceRecord."
                "migration_timestamp_utc must be UTC-shaped "
                "ISO-8601 when populated; got "
                f"{self.migration_timestamp_utc!r}"
            )
        if self.migration_slot is not None and not (
            isinstance(self.migration_slot, int)
            and not isinstance(self.migration_slot, bool)
            and self.migration_slot >= 0
        ):
            raise ValueError(
                "Stage29_5MigrationEvidenceRecord."
                "migration_slot must be a non-negative int when "
                f"populated; got {self.migration_slot!r}"
            )
        if (
            self.migration_signature is not None
            and not isinstance(self.migration_signature, str)
        ):
            raise ValueError(
                "Stage29_5MigrationEvidenceRecord."
                "migration_signature must be a string when "
                f"populated; got "
                f"{self.migration_signature!r}"
            )
        if self.source_event_ref is not None and not (
            isinstance(self.source_event_ref, str)
        ):
            raise ValueError(
                "Stage29_5MigrationEvidenceRecord."
                "source_event_ref must be a string when "
                f"populated; got {self.source_event_ref!r}"
            )
        if not isinstance(self.schema_version, str):
            raise ValueError(
                "Stage29_5MigrationEvidenceRecord."
                "schema_version must be a string"
            )
        if (
            self.migration_status
            == MIGRATION_STATUS_PRESENT
        ):
            quartet = (
                self.base_mint,
                self.pool_account,
                self.pool_program_id,
                self.quote_mint,
            )
            if any(v is None for v in quartet):
                raise ValueError(
                    "Stage29_5MigrationEvidenceRecord with "
                    "migration_status=PRESENT requires the "
                    "quartet (base_mint, pool_account, "
                    "pool_program_id, quote_mint) populated"
                )
            if self.migration_timestamp_utc is None:
                raise ValueError(
                    "Stage29_5MigrationEvidenceRecord with "
                    "migration_status=PRESENT requires "
                    "migration_timestamp_utc populated"
                )
            if (
                self.migration_source
                == MIGRATION_SOURCE_UNKNOWN_STAGE29_5
            ):
                raise ValueError(
                    "Stage29_5MigrationEvidenceRecord with "
                    "migration_status=PRESENT cannot pair with "
                    "migration_source=UNKNOWN"
                )
        if (
            self.migration_status
            == MIGRATION_STATUS_MISSING
        ):
            optionals = (
                self.base_mint,
                self.pool_account,
                self.pool_program_id,
                self.quote_mint,
                self.migration_timestamp_utc,
                self.migration_slot,
                self.migration_signature,
                self.source_event_ref,
            )
            if any(v is not None for v in optionals):
                raise ValueError(
                    "Stage29_5MigrationEvidenceRecord with "
                    "migration_status=MISSING requires every "
                    "optional axis to be None"
                )
            if (
                self.migration_source
                != MIGRATION_SOURCE_UNKNOWN_STAGE29_5
            ):
                raise ValueError(
                    "Stage29_5MigrationEvidenceRecord with "
                    "migration_status=MISSING requires "
                    "migration_source=UNKNOWN"
                )


# ---------------------------------------------------------------------------
# Immutable record: candidate-to-migration join
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5MigrationJoinRecord:
    """Immutable Stage 29.5 candidate-to-migration join record.

    The Stage 29.5 join layer is the sole authority that
    constructs this record.

    Validators enforce:

      * ``migration_join_status`` ∈
        :data:`STAGE29_5_MIGRATION_JOIN_STATUS_VALUES`
      * ``candidate_base_mint`` is a safe-shape printable string
        of length 32..64.
      * ``matched_evidence_count`` is a non-negative int and
        equals ``len(matched_evidence)``.
      * ``joined_at_utc`` is UTC-shaped ISO-8601.
      * Time-window strings, when populated, are UTC-shaped
        ISO-8601.
    """

    migration_join_status: str
    candidate_base_mint: str
    candidate_pool_account: Optional[str]
    candidate_pool_program_id: Optional[str]
    candidate_quote_mint: Optional[str]
    matched_evidence_count: int
    matched_evidence: Tuple[
        Stage29_5MigrationEvidenceRecord, ...
    ]
    time_window_start_utc: Optional[str]
    time_window_end_utc: Optional[str]
    joined_at_utc: str
    schema_version: str = (
        STAGE29_5_MIGRATION_JOIN_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if not is_stage29_5_migration_join_status_value(
            self.migration_join_status
        ):
            raise ValueError(
                "Stage29_5MigrationJoinRecord."
                "migration_join_status must be a closed-set "
                f"token; got {self.migration_join_status!r}"
            )
        if not is_safe_mint_or_pool_string(
            self.candidate_base_mint
        ):
            raise ValueError(
                "Stage29_5MigrationJoinRecord."
                "candidate_base_mint must be a safe-shape "
                "printable string of length 32..64; got "
                f"{self.candidate_base_mint!r}"
            )
        for axis_name, axis_value in (
            (
                "candidate_pool_account",
                self.candidate_pool_account,
            ),
            (
                "candidate_pool_program_id",
                self.candidate_pool_program_id,
            ),
            (
                "candidate_quote_mint",
                self.candidate_quote_mint,
            ),
        ):
            if axis_value is not None and not (
                is_safe_mint_or_pool_string(axis_value)
            ):
                raise ValueError(
                    "Stage29_5MigrationJoinRecord."
                    f"{axis_name} must be a safe-shape "
                    "printable string of length 32..64 when "
                    f"populated; got {axis_value!r}"
                )
        if not (
            isinstance(self.matched_evidence_count, int)
            and not isinstance(
                self.matched_evidence_count, bool
            )
            and self.matched_evidence_count >= 0
        ):
            raise ValueError(
                "Stage29_5MigrationJoinRecord."
                "matched_evidence_count must be a non-negative "
                f"int; got {self.matched_evidence_count!r}"
            )
        if not isinstance(self.matched_evidence, tuple):
            raise ValueError(
                "Stage29_5MigrationJoinRecord."
                "matched_evidence must be a tuple"
            )
        for record in self.matched_evidence:
            if not isinstance(
                record, Stage29_5MigrationEvidenceRecord
            ):
                raise ValueError(
                    "Stage29_5MigrationJoinRecord."
                    "matched_evidence entries must be "
                    "Stage29_5MigrationEvidenceRecord "
                    "instances"
                )
        if (
            len(self.matched_evidence)
            != self.matched_evidence_count
        ):
            raise ValueError(
                "Stage29_5MigrationJoinRecord."
                "matched_evidence_count must equal "
                "len(matched_evidence)"
            )
        for window_name, window_value in (
            (
                "time_window_start_utc",
                self.time_window_start_utc,
            ),
            (
                "time_window_end_utc",
                self.time_window_end_utc,
            ),
        ):
            if window_value is not None and not (
                is_safe_iso8601_utc_string(window_value)
            ):
                raise ValueError(
                    "Stage29_5MigrationJoinRecord."
                    f"{window_name} must be UTC-shaped "
                    "ISO-8601 when populated; got "
                    f"{window_value!r}"
                )
        if not is_safe_iso8601_utc_string(
            self.joined_at_utc
        ):
            raise ValueError(
                "Stage29_5MigrationJoinRecord."
                "joined_at_utc must be UTC-shaped ISO-8601; "
                f"got {self.joined_at_utc!r}"
            )
        if not isinstance(self.schema_version, str):
            raise ValueError(
                "Stage29_5MigrationJoinRecord."
                "schema_version must be a string"
            )


# ---------------------------------------------------------------------------
# Immutable record: private ping migration context projection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5PrivatePingMigrationContext:
    """Immutable Stage 29.5 private ping migration context.

    The Stage 29.5 projection layer is the sole authority that
    constructs this record. The record becomes a private ping
    rendering input.

    Validators enforce:

      * ``measurement_status`` ∈
        :data:`STAGE29_5_MEASUREMENT_STATUS_VALUES`
      * each token in ``warnings`` ∈
        :data:`STAGE29_5_WARNING_CODE_VALUES`
      * ``warnings`` carries no duplicates
      * ``migration_source`` ∈
        :data:`STAGE29_5_MIGRATION_SOURCE_VALUES`
      * ``join_status_echoed`` ∈
        :data:`STAGE29_5_MIGRATION_JOIN_STATUS_VALUES`
      * ``redaction_status`` ∈
        :data:`STAGE29_5_REDACTION_STATUS_VALUES`
      * ``filter_enforcement_status`` is locked to
        ``NOT_ACTIVE_STAGE_29_PENDING``
      * ``observed_at_utc`` is UTC-shaped ISO-8601
    """

    measurement_status: str
    warnings: Tuple[str, ...]
    migration_timestamp_utc: Optional[str]
    migration_slot: Optional[int]
    migration_source: str
    post_migration_ath_verified: Optional[bool]
    join_status_echoed: str
    redaction_status: str
    filter_enforcement_status: str
    observed_at_utc: str
    schema_version: str = (
        STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if not is_stage29_5_measurement_status_value(
            self.measurement_status
        ):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "measurement_status must be a closed-set token; "
                f"got {self.measurement_status!r}"
            )
        if not isinstance(self.warnings, tuple):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "warnings must be a tuple"
            )
        seen: set = set()
        for code in self.warnings:
            if not is_stage29_5_warning_code_value(code):
                raise ValueError(
                    "Stage29_5PrivatePingMigrationContext."
                    "warnings entries must each be a "
                    "closed-set warning code; got "
                    f"{code!r}"
                )
            if code in seen:
                raise ValueError(
                    "Stage29_5PrivatePingMigrationContext."
                    "warnings must not contain duplicates; "
                    f"duplicate token {code!r}"
                )
            seen.add(code)
        if (
            self.migration_timestamp_utc is not None
            and not is_safe_iso8601_utc_string(
                self.migration_timestamp_utc
            )
        ):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "migration_timestamp_utc must be UTC-shaped "
                "ISO-8601 when populated; got "
                f"{self.migration_timestamp_utc!r}"
            )
        if self.migration_slot is not None and not (
            isinstance(self.migration_slot, int)
            and not isinstance(self.migration_slot, bool)
            and self.migration_slot >= 0
        ):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "migration_slot must be a non-negative int "
                "when populated"
            )
        if not is_stage29_5_migration_source_value(
            self.migration_source
        ):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "migration_source must be a closed-set token; "
                f"got {self.migration_source!r}"
            )
        if self.post_migration_ath_verified is not None and (
            not isinstance(
                self.post_migration_ath_verified, bool
            )
        ):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "post_migration_ath_verified must be bool or "
                "None"
            )
        if not is_stage29_5_migration_join_status_value(
            self.join_status_echoed
        ):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "join_status_echoed must be a closed-set "
                f"token; got {self.join_status_echoed!r}"
            )
        if not is_stage29_5_redaction_status_value(
            self.redaction_status
        ):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "redaction_status must be a closed-set token; "
                f"got {self.redaction_status!r}"
            )
        if (
            self.filter_enforcement_status
            != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "filter_enforcement_status is locked to "
                "NOT_ACTIVE_STAGE_29_PENDING; got "
                f"{self.filter_enforcement_status!r}"
            )
        if not is_safe_iso8601_utc_string(
            self.observed_at_utc
        ):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "observed_at_utc must be UTC-shaped ISO-8601; "
                f"got {self.observed_at_utc!r}"
            )
        if not isinstance(self.schema_version, str):
            raise ValueError(
                "Stage29_5PrivatePingMigrationContext."
                "schema_version must be a string"
            )


# ---------------------------------------------------------------------------
# Stage 29.5 exception type
# ---------------------------------------------------------------------------


class Stage29_5MigrationEvidenceError(Exception):
    """Stage 29.5 closed-set refusal-reason exception.

    Raised by the Stage 29.5 Helius WS adapter and the Stage
    29.5 artifact reader when an upstream payload cannot be
    parsed into a :class:`Stage29_5MigrationEvidenceRecord`.

    The exception carries a closed-set refusal_reason token and
    a short safe-to-display detail message. It never carries a
    raw payload, a raw URL, or a raw secret value.
    """

    def __init__(
        self,
        refusal_reason: str,
        detail: str = "",
    ) -> None:
        if not is_stage29_5_refusal_reason_value(
            refusal_reason
        ):
            raise ValueError(
                "Stage29_5MigrationEvidenceError refusal_reason "
                f"must be a closed-set token; got "
                f"{refusal_reason!r}"
            )
        if not isinstance(detail, str):
            raise ValueError(
                "Stage29_5MigrationEvidenceError detail must "
                "be a string"
            )
        super().__init__(
            f"{refusal_reason}: {detail}" if detail
            else refusal_reason
        )
        self.refusal_reason: str = refusal_reason
        self.detail: str = detail


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = (
    "STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION",
    "STAGE29_5_MIGRATION_JOIN_SCHEMA_VERSION",
    "STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION",
    "MIGRATION_STATUS_PRESENT",
    "MIGRATION_STATUS_MISSING",
    "MIGRATION_STATUS_CONFLICTING",
    "MIGRATION_STATUS_INVALID",
    "MIGRATION_STATUS_STALE",
    "STAGE29_5_MIGRATION_STATUS_VALUES",
    "is_stage29_5_migration_status_value",
    "MIGRATION_SOURCE_HELIUS_WS",
    "MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT",
    "MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY",
    "MIGRATION_SOURCE_UNKNOWN_STAGE29_5",
    "STAGE29_5_MIGRATION_SOURCE_VALUES",
    "is_stage29_5_migration_source_value",
    "MIGRATION_JOIN_STATUS_JOINED",
    "MIGRATION_JOIN_STATUS_NO_MATCH",
    "MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES",
    "MIGRATION_JOIN_STATUS_SOURCE_INVALID",
    "MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID",
    "MIGRATION_JOIN_STATUS_PAIR_MISMATCH",
    "STAGE29_5_MIGRATION_JOIN_STATUS_VALUES",
    "is_stage29_5_migration_join_status_value",
    "MEASUREMENT_STATUS_MISSING_MIGRATION",
    "MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT",
    "MEASUREMENT_STATUS_COMPLETE",
    "MEASUREMENT_STATUS_INVALID_MIGRATION",
    "MEASUREMENT_STATUS_CONFLICTING_MIGRATION",
    "STAGE29_5_MEASUREMENT_STATUS_VALUES",
    "is_stage29_5_measurement_status_value",
    "WARNING_MIGRATION_MISSING",
    "WARNING_POST_MIGRATION_ATH_UNVERIFIED",
    "WARNING_MIGRATION_SOURCE_UNKNOWN",
    "WARNING_MIGRATION_CONFLICT",
    "WARNING_MIGRATION_STALE",
    "WARNING_MIGRATION_TIMESTAMP_INVALID",
    "WARNING_MIGRATION_PAIR_MISMATCH",
    "WARNING_MIGRATION_SLOT_MISSING",
    "STAGE29_5_WARNING_CODE_VALUES",
    "is_stage29_5_warning_code_value",
    "REDACTION_STATUS_SAFE",
    "REDACTION_STATUS_REDACTED",
    "STAGE29_5_REDACTION_STATUS_VALUES",
    "is_stage29_5_redaction_status_value",
    "FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING",
    "STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES",
    "REFUSAL_REASON_NONE",
    "REFUSAL_REASON_MALFORMED_PAYLOAD",
    "REFUSAL_REASON_UNSUPPORTED_KIND",
    "REFUSAL_REASON_MISSING_REQUIRED_AXIS",
    "REFUSAL_REASON_UNREADABLE_ARTIFACT",
    "REFUSAL_REASON_SOURCE_INVALID",
    "REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED",
    "REFUSAL_REASON_BUDGET_EXCEEDED",
    "STAGE29_5_REFUSAL_REASON_VALUES",
    "is_stage29_5_refusal_reason_value",
    "is_safe_mint_or_pool_string",
    "is_safe_iso8601_utc_string",
    "Stage29_5MigrationEvidenceRecord",
    "Stage29_5MigrationJoinRecord",
    "Stage29_5PrivatePingMigrationContext",
    "Stage29_5MigrationEvidenceError",
)
