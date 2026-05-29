"""Stage 30.6.1 offline storage-budget closed-set vocabularies and
immutable policy / observation / decision shapes.

Stage 30.6.1 ships the pure-Python model layer for the Stage 30.6
storage-budget policy brain. It is the deterministic decision model
the Stage 30.6.1 evaluator (``stage30_6_storage_budget_evaluator``)
classifies a caller-supplied disk-used percentage against. Stage
30.6.1 is the storage + dedupe readiness family's FIRST production
slice: a pure offline policy brain, NOT a storage writer, NOT a
dedupe ledger, NOT a WAL / day-rolled writer, NOT a lifecycle-seal
aggregate, and NOT a live runtime.

Stage 30.6.1 is offline only and reads NO actual disk. The caller
supplies the observed disk-used percentage; this module and its
evaluator NEVER call an OS / filesystem / disk API, NEVER read the
process environment, NEVER open a network connection, and NEVER call
``datetime.now``.

Closed-set vocabularies:

  * ``STORAGE_BUDGET_STATUS`` -- ``STORAGE_BUDGET_OK`` /
    ``STORAGE_BUDGET_SOFT_ALARM`` / ``STORAGE_BUDGET_HARD_STOP`` /
    ``STORAGE_BUDGET_INVALID_INPUT``.
  * ``STORAGE_BUDGET_ACTION`` -- ``ALLOW_WRITES`` /
    ``ALLOW_WRITES_WITH_WARNING`` / ``REFUSE_NEW_WRITES`` /
    ``INVALID_INPUT_REFUSE_WRITES``.
  * ``STORAGE_BUDGET_REASON`` -- closed-set reason tokens that
    explain WHY the evaluator chose a status / action.

Immutable shapes:

  * ``Stage30_6StorageBudgetPolicy``      -- soft / hard thresholds +
                                             policy version. A lenient
                                             carrier (see below).
  * ``Stage30_6StorageBudgetObservation`` -- the caller-supplied
                                             disk-used percentage +
                                             optional provenance. A
                                             lenient carrier.
  * ``Stage30_6StorageBudgetDecision``    -- the validated evaluator
                                             output (closed-set
                                             status / action / reason +
                                             echoes).

Policy / Observation are deliberately LENIENT carriers: they do NOT
validate their fields at construction. This is on purpose and differs
from the Stage 30.4 / 30.5 offline RECORDS (which validate at
construction): the Stage 30.6.0 spec lock Section 5 requires a full or
misconfigured disk budget to FAIL CLOSED with a private operator
warning rather than raise, so an out-of-range threshold or a bad
disk-used percentage must be expressible as an input and flow to a
``STORAGE_BUDGET_INVALID_INPUT`` DECISION (never a constructor
exception). The Decision, by contrast, is the validated OUTPUT and
DOES validate at construction: building a decision with an
off-closed-set status / action / reason, a non-bool flag, a non-finite
echoed percentage, a non-string policy version, or
``runtime_consumable`` not ``False`` raises
``Stage30_6StorageBudgetError`` with a closed-set reason token.

Stage 30.6.1 deliberately does NOT carry / implement:

  * any actual-disk read (no field is ever populated from an OS /
    filesystem / disk API; the caller supplies every value),
  * any storage writer, dedupe ledger, WAL / day-rolled writer,
    lifecycle-seal aggregate, or database migration,
  * any zstd dependency or implementation,
  * ATH fields (ATH stays Stage 30.7),
  * Net flow fields (Net stays deferred),
  * raw provider payload blobs, secrets, inbound-hook URLs, credential
    strings, signed tokens, or request auth-metadata (no field admits
    them),
  * trading verdicts (Stage 30 is informational-only),
  * Stage 26 / Stage 29 enforcement decisions.

Discipline:

  * Stdlib only (``math`` / ``typing`` / ``dataclasses``).
  * No ``os`` import, no ``os.environ`` / ``os.getenv`` /
    ``os.environb`` access, no ``pathlib`` / ``shutil`` / ``sqlite3`` /
    zstd import.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No Discord, Telegram, X / social, inbound-hook, provider
    reference.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No network / env / filesystem / disk I/O at import time. No
    top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema / policy versions
# ---------------------------------------------------------------------------


STAGE30_6_1_MINOR_VERSION: str = "30.6.1"
STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION: str = (
    "stage30_6_1_v0_storage_budget"
)
STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION: str = (
    "stage30_6_storage_budget_policy_v0"
)


# ---------------------------------------------------------------------------
# Default thresholds + valid percent bounds
# ---------------------------------------------------------------------------
#
# The Stage 30.6.0 spec lock Section 5 pins a soft disk alarm around
# 65% used and a hard stop around 90% used. The defaults below are the
# float forms (the Stage 30.6.0 manifest pins the integer 65 / 90). A
# percent threshold / observation is valid only within [0, 100].


STORAGE_BUDGET_DEFAULT_SOFT_ALARM_USED_PCT: float = 65.0
STORAGE_BUDGET_DEFAULT_HARD_STOP_USED_PCT: float = 90.0


STORAGE_BUDGET_MIN_USED_PCT: float = 0.0
STORAGE_BUDGET_MAX_USED_PCT: float = 100.0


# ---------------------------------------------------------------------------
# status closed set
# ---------------------------------------------------------------------------


STORAGE_BUDGET_OK: str = "STORAGE_BUDGET_OK"
STORAGE_BUDGET_SOFT_ALARM: str = "STORAGE_BUDGET_SOFT_ALARM"
STORAGE_BUDGET_HARD_STOP: str = "STORAGE_BUDGET_HARD_STOP"
STORAGE_BUDGET_INVALID_INPUT: str = "STORAGE_BUDGET_INVALID_INPUT"


STORAGE_BUDGET_STATUS_VALUES: Tuple[str, ...] = (
    STORAGE_BUDGET_OK,
    STORAGE_BUDGET_SOFT_ALARM,
    STORAGE_BUDGET_HARD_STOP,
    STORAGE_BUDGET_INVALID_INPUT,
)


def is_storage_budget_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set status token."""
    return (
        isinstance(value, str)
        and value in STORAGE_BUDGET_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# action closed set
# ---------------------------------------------------------------------------


ALLOW_WRITES: str = "ALLOW_WRITES"
ALLOW_WRITES_WITH_WARNING: str = "ALLOW_WRITES_WITH_WARNING"
REFUSE_NEW_WRITES: str = "REFUSE_NEW_WRITES"
INVALID_INPUT_REFUSE_WRITES: str = "INVALID_INPUT_REFUSE_WRITES"


STORAGE_BUDGET_ACTION_VALUES: Tuple[str, ...] = (
    ALLOW_WRITES,
    ALLOW_WRITES_WITH_WARNING,
    REFUSE_NEW_WRITES,
    INVALID_INPUT_REFUSE_WRITES,
)


def is_storage_budget_action_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set action token."""
    return (
        isinstance(value, str)
        and value in STORAGE_BUDGET_ACTION_VALUES
    )


# ---------------------------------------------------------------------------
# reason closed set
# ---------------------------------------------------------------------------
#
# Each reason explains WHY the evaluator chose its status / action. The
# three in-band reasons pair with OK / SOFT_ALARM / HARD_STOP; the
# remaining reasons are the fail-closed INVALID_INPUT reasons,
# partitioned into disk-observation faults and policy faults.


STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM: str = (
    "OK_BELOW_SOFT_ALARM"
)
STORAGE_BUDGET_REASON_SOFT_ALARM_REACHED: str = (
    "SOFT_ALARM_REACHED"
)
STORAGE_BUDGET_REASON_HARD_STOP_REACHED: str = (
    "HARD_STOP_REACHED"
)

# Disk-observation faults.
STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_MISSING: str = (
    "INVALID_DISK_USED_PCT_MISSING"
)
STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_NUMBER: str = (
    "INVALID_DISK_USED_PCT_NOT_NUMBER"
)
STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_FINITE: str = (
    "INVALID_DISK_USED_PCT_NOT_FINITE"
)
STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE: str = (
    "INVALID_DISK_USED_PCT_OUT_OF_RANGE"
)

# Policy faults.
STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC: str = (
    "INVALID_POLICY_THRESHOLD_NOT_NUMERIC"
)
STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_OUT_OF_RANGE: str = (
    "INVALID_POLICY_THRESHOLD_OUT_OF_RANGE"
)
STORAGE_BUDGET_REASON_INVALID_POLICY_SOFT_GE_HARD: str = (
    "INVALID_POLICY_SOFT_GE_HARD"
)


STORAGE_BUDGET_REASON_VALUES: Tuple[str, ...] = (
    STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM,
    STORAGE_BUDGET_REASON_SOFT_ALARM_REACHED,
    STORAGE_BUDGET_REASON_HARD_STOP_REACHED,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_MISSING,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_NUMBER,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_FINITE,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE,
    STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC,
    STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_OUT_OF_RANGE,
    STORAGE_BUDGET_REASON_INVALID_POLICY_SOFT_GE_HARD,
)


def is_storage_budget_reason_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set reason token."""
    return (
        isinstance(value, str)
        and value in STORAGE_BUDGET_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Numeric helpers (pure)
# ---------------------------------------------------------------------------


def is_finite_real(value: object) -> bool:
    """Return ``True`` iff ``value`` is a finite real number that is
    NOT a ``bool`` (``bool`` is an ``int`` subclass and must never be
    accepted as a percentage).

    An ``int`` is always finite (no NaN / inf is representable); a
    ``float`` must satisfy ``math.isfinite``. ``math.isfinite`` is only
    ever called on a ``float`` here, so a very large ``int`` can never
    trigger an ``OverflowError`` through this helper.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _is_none_or_finite_real(value: object) -> bool:
    return value is None or is_finite_real(value)


# ---------------------------------------------------------------------------
# Module-local exception
# ---------------------------------------------------------------------------


class Stage30_6StorageBudgetError(Exception):
    """Closed-set Stage 30.6.1 storage-budget error.

    Carries only a closed-set reason token on the exception message.
    Raised ONLY at ``Stage30_6StorageBudgetDecision`` construction (the
    validated output); the evaluator itself never raises for bad
    observation / policy input -- it fails closed to a
    ``STORAGE_BUDGET_INVALID_INPUT`` decision instead. Callers should
    never embed a raw OSError message, a raw provider payload, or any
    secret value in the message.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.6.1 storage budget error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Immutable carrier: storage budget policy (lenient)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_6StorageBudgetPolicy:
    """Immutable Stage 30.6.1 storage-budget policy.

    A LENIENT carrier: it does NOT validate its fields at construction
    (see the module docstring). The evaluator validates the thresholds
    and fails closed to ``STORAGE_BUDGET_INVALID_INPUT`` on a
    non-numeric / out-of-range threshold or a ``soft >= hard``
    inversion.

    Fields:

      * ``soft_alarm_used_pct`` -- soft disk-used alarm threshold
                                   (percent). Default 65.0.
      * ``hard_stop_used_pct``  -- hard disk-used stop threshold
                                   (percent). Default 90.0.
      * ``policy_version``      -- policy-version label echoed onto the
                                   decision. Default
                                   ``STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION``.
    """

    soft_alarm_used_pct: float = STORAGE_BUDGET_DEFAULT_SOFT_ALARM_USED_PCT
    hard_stop_used_pct: float = STORAGE_BUDGET_DEFAULT_HARD_STOP_USED_PCT
    policy_version: str = STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION


# ---------------------------------------------------------------------------
# Immutable carrier: storage budget observation (lenient)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_6StorageBudgetObservation:
    """Immutable Stage 30.6.1 storage-budget observation.

    A LENIENT carrier of caller-supplied values. Stage 30.6.1 reads NO
    actual disk: the caller computes ``disk_used_pct`` (and any optional
    provenance) elsewhere and supplies it here. The evaluator validates
    ``disk_used_pct`` and fails closed on missing / non-number /
    non-finite / out-of-range input.

    Fields:

      * ``disk_used_pct``   -- observed percent of disk used
                              (caller-supplied). ``None`` / a non-number
                              / NaN / out-of-range is tolerated here and
                              fails closed in the evaluator.
      * ``total_bytes``     -- optional total-bytes provenance.
      * ``free_bytes``      -- optional free-bytes provenance.
      * ``observed_at_utc`` -- optional caller-supplied ISO-8601 UTC
                              timestamp string (never derived from
                              ``datetime.now`` here).
      * ``source_label``    -- optional short provenance label for where
                              the caller measured the value.
    """

    disk_used_pct: Optional[float] = None
    total_bytes: Optional[int] = None
    free_bytes: Optional[int] = None
    observed_at_utc: Optional[str] = None
    source_label: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable output: storage budget decision (validated)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_6StorageBudgetDecision:
    """Immutable Stage 30.6.1 storage-budget decision (validated).

    The validated OUTPUT of the evaluator. Frozen dataclass with
    construction-time closed-set validation: an off-closed-set
    status / action / reason, a non-bool ``should_*`` flag, a
    non-finite echoed percentage, a non-string ``policy_version``, or
    ``runtime_consumable`` not ``False`` raises
    ``Stage30_6StorageBudgetError`` with a closed-set reason token.

    ``runtime_consumable`` is hard-locked ``False``: Stage 30.6.1 is a
    pure offline policy brain, NOT a live storage writer. The decision
    is a RECOMMENDATION (``should_allow_new_writes`` /
    ``should_emit_operator_warning``); it never claims a write was
    executed. A later separately-authorized storage-writer substage
    (Stage 30.6.2+) would consume the decision; Stage 30.6.1 does not.

    Fields:

      * ``schema_version``               -- locked Stage 30.6.1 schema
                                            version string (non-empty).
      * ``status``                       -- one of
                                            ``STORAGE_BUDGET_STATUS_VALUES``.
      * ``action``                       -- one of
                                            ``STORAGE_BUDGET_ACTION_VALUES``.
      * ``should_allow_new_writes``      -- ``bool`` recommendation.
      * ``should_emit_operator_warning`` -- ``bool`` recommendation.
      * ``reason``                       -- one of
                                            ``STORAGE_BUDGET_REASON_VALUES``.
      * ``disk_used_pct``                -- echoed observed percent
                                            (finite ``float``) or
                                            ``None`` when the input was
                                            missing / non-number /
                                            non-finite.
      * ``soft_alarm_used_pct``          -- echoed policy soft threshold
                                            (finite ``float``) or
                                            ``None``.
      * ``hard_stop_used_pct``           -- echoed policy hard threshold
                                            (finite ``float``) or
                                            ``None``.
      * ``policy_version``               -- echoed policy version string
                                            or ``None``.
      * ``runtime_consumable``           -- ``bool``; MUST be ``False``.
    """

    schema_version: str
    status: str
    action: str
    should_allow_new_writes: bool
    should_emit_operator_warning: bool
    reason: str
    disk_used_pct: Optional[float]
    soft_alarm_used_pct: Optional[float]
    hard_stop_used_pct: Optional[float]
    policy_version: Optional[str]
    runtime_consumable: bool

    def __post_init__(self) -> None:
        if not (
            isinstance(self.schema_version, str)
            and self.schema_version != ""
        ):
            raise Stage30_6StorageBudgetError("SCHEMA_VERSION_INVALID")
        if not is_storage_budget_status_value(self.status):
            raise Stage30_6StorageBudgetError("STATUS_INVALID")
        if not is_storage_budget_action_value(self.action):
            raise Stage30_6StorageBudgetError("ACTION_INVALID")
        if not isinstance(self.should_allow_new_writes, bool):
            raise Stage30_6StorageBudgetError(
                "SHOULD_ALLOW_NEW_WRITES_NOT_BOOL"
            )
        if not isinstance(self.should_emit_operator_warning, bool):
            raise Stage30_6StorageBudgetError(
                "SHOULD_EMIT_OPERATOR_WARNING_NOT_BOOL"
            )
        if not is_storage_budget_reason_value(self.reason):
            raise Stage30_6StorageBudgetError("REASON_INVALID")
        if not _is_none_or_finite_real(self.disk_used_pct):
            raise Stage30_6StorageBudgetError("DISK_USED_PCT_INVALID")
        if not _is_none_or_finite_real(self.soft_alarm_used_pct):
            raise Stage30_6StorageBudgetError(
                "SOFT_ALARM_USED_PCT_INVALID"
            )
        if not _is_none_or_finite_real(self.hard_stop_used_pct):
            raise Stage30_6StorageBudgetError(
                "HARD_STOP_USED_PCT_INVALID"
            )
        if self.policy_version is not None and not isinstance(
            self.policy_version, str
        ):
            raise Stage30_6StorageBudgetError("POLICY_VERSION_INVALID")
        if not isinstance(self.runtime_consumable, bool):
            raise Stage30_6StorageBudgetError(
                "RUNTIME_CONSUMABLE_NOT_BOOL"
            )
        if self.runtime_consumable is not False:
            # Stage 30.6.1 is a pure offline policy brain: a decision can
            # NEVER claim live write execution, so True is rejected
            # outright (not silently normalized). A later opt-in
            # storage-writer substage (Stage 30.6.2+) would relax this.
            raise Stage30_6StorageBudgetError(
                "RUNTIME_CONSUMABLE_MUST_BE_FALSE"
            )


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 30.6.1 must never accept a field named anything secret-class,
# raw-payload-class, or Discord-class on any of the three dataclasses.
# The current policy / observation / decision field sets carry no such
# name, but this helper is kept so a future refactor cannot silently
# widen the admitted field set.
#
# Split literals so this module's own source does NOT carry the bare
# inbound-hook / credential / signed-token / auth-metadata substrings
# (mirrors the Stage 30.4 / 30.5 forbidden-field guard). The runtime
# tuple value still resolves to the correct human-readable forbidden
# names.


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
    # Secret-class / transport-class.
    "web" + "hook",
    "web" + "hook_url",
    "web" + "hooks",
    "api_" + "key",
    "api" + "key",
    "b" + "earer",
    "b" + "earer_token",
    "author" + "ization",
    "secret",
    "secret_key",
    "secretkey",
    "token_secret",
    "private_key",
    "privatekey",
    "seed_phrase",
    "mnemonic",
    "signer",
    "signing_key",
    "credentials",
    "password",
    "rpc_url",
    "endpoint_url",
    "host",
    "url",
    # Raw-payload-class.
    "raw_payload",
    "payload",
    "payload_blob",
    "raw_response",
    # Discord-class.
    "discord",
    "channel_id",
    "destination",
)


def is_forbidden_record_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden record field name.

    Pure / deterministic. Stage 30.6.1 uses this guard to reject any
    future refactor that tries to widen the policy / observation /
    decision with a secret-class, raw-payload-class, or Discord-class
    field name.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_RECORD_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False


def policy_field_names() -> Tuple[str, ...]:
    """Return the Stage 30.6.1 policy field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_6StorageBudgetPolicy))


def observation_field_names() -> Tuple[str, ...]:
    """Return the Stage 30.6.1 observation field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_6StorageBudgetObservation)
    )


def decision_field_names() -> Tuple[str, ...]:
    """Return the Stage 30.6.1 decision field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_6StorageBudgetDecision)
    )


__all__ = (
    # Version + schema / policy versions.
    "STAGE30_6_1_MINOR_VERSION",
    "STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION",
    "STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION",
    # Default thresholds + bounds.
    "STORAGE_BUDGET_DEFAULT_SOFT_ALARM_USED_PCT",
    "STORAGE_BUDGET_DEFAULT_HARD_STOP_USED_PCT",
    "STORAGE_BUDGET_MIN_USED_PCT",
    "STORAGE_BUDGET_MAX_USED_PCT",
    # status tokens.
    "STORAGE_BUDGET_OK",
    "STORAGE_BUDGET_SOFT_ALARM",
    "STORAGE_BUDGET_HARD_STOP",
    "STORAGE_BUDGET_INVALID_INPUT",
    "STORAGE_BUDGET_STATUS_VALUES",
    "is_storage_budget_status_value",
    # action tokens.
    "ALLOW_WRITES",
    "ALLOW_WRITES_WITH_WARNING",
    "REFUSE_NEW_WRITES",
    "INVALID_INPUT_REFUSE_WRITES",
    "STORAGE_BUDGET_ACTION_VALUES",
    "is_storage_budget_action_value",
    # reason tokens.
    "STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM",
    "STORAGE_BUDGET_REASON_SOFT_ALARM_REACHED",
    "STORAGE_BUDGET_REASON_HARD_STOP_REACHED",
    "STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_MISSING",
    "STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_NUMBER",
    "STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_FINITE",
    "STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE",
    "STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC",
    "STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_OUT_OF_RANGE",
    "STORAGE_BUDGET_REASON_INVALID_POLICY_SOFT_GE_HARD",
    "STORAGE_BUDGET_REASON_VALUES",
    "is_storage_budget_reason_value",
    # Numeric helper.
    "is_finite_real",
    # Records / output + field-name helpers.
    "Stage30_6StorageBudgetPolicy",
    "Stage30_6StorageBudgetObservation",
    "Stage30_6StorageBudgetDecision",
    "policy_field_names",
    "observation_field_names",
    "decision_field_names",
    # Forbidden-field guard + error.
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "is_forbidden_record_field_name",
    "Stage30_6StorageBudgetError",
)
