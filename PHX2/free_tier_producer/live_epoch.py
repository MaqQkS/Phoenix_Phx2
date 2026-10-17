"""Durable live-only epoch ownership for production Yellowstone discovery.

Normal production intentionally makes no historical completeness claim.  Each
stream attempt starts at the current confirmed head, waits for confirmed slot
``H``, and admits migration events only from ``H + 1`` onward.  A continuity
break closes the prior epoch and creates a fresh, initially unarmed epoch.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PHX2.free_tier_producer.phx1_parity_policy import (
    ALERT_POLICY_MODES,
    normalize_alert_policy,
)


LIVE_EPOCH_SCHEMA_VERSION = "phx2_live_epoch_v1"
LIVE_EPOCH_BASENAME = "live_epoch_state.json"
LIVE_EPOCH_CURSOR_BASENAME = "live_epoch_stream_cursor.json"
LIVE_EPOCH_BACKUP_SUFFIX = ".bak"
LIVE_EPOCH_POLICY_IDENTITY_SCHEMA = "phx2_live_epoch_policy_identity_v1"
LIVE_EPOCH_RUN_IDENTITY_SCHEMA = "phx2_live_epoch_run_identity_v1"
LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA = (
    "phx2_closed_epoch_deployment_handoff_v1")
#: ``v2`` states the alert-policy transition explicitly.  ``v1`` records stay
#: valid forever and are NEVER rewritten: the production chain was written
#: before the alert policy was a deployment binding, and that chain is the
#: preserved evidence a pre-binding epoch is authenticated against.  Migrating
#: it to a new shape would destroy exactly what the compatibility path proves.
LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2 = (
    "phx2_closed_epoch_deployment_handoff_v2")
LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMAS = (
    LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA,
    LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2,
)
LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME = (
    "live_epoch_deployment_handoffs.jsonl")
LIVE_EPOCH_CLOSED_ARCHIVE_DIRNAME = "live_epoch_closed_archive"

PRODUCTION_MODE = "LIVE_EPOCH_WITH_DEX_BACKFILL"
HISTORICAL_REPLAY_STATUS = (
    "HISTORICAL_BLOCK_REPLAY_RETIRED_FROM_PRODUCTION")
CLEAN_RESTART_EPOCH_ROLLOVER = "CLEAN_RESTART_EPOCH_ROLLOVER"
CLOSED_EPOCH_DEPLOYMENT_HANDOFF = "CLOSED_EPOCH_DEPLOYMENT_HANDOFF"

EPOCH_STARTING = "EPOCH_STARTING"
EPOCH_HEALTHY = "EPOCH_HEALTHY"
EPOCH_CONTINUITY_BROKEN = "EPOCH_CONTINUITY_BROKEN"
EPOCH_CLOSED = "EPOCH_CLOSED"
EPOCH_INTEGRITY_FAILURE = "EPOCH_INTEGRITY_FAILURE"
EPOCH_STATUSES = (
    EPOCH_STARTING,
    EPOCH_HEALTHY,
    EPOCH_CONTINUITY_BROKEN,
    EPOCH_CLOSED,
    EPOCH_INTEGRITY_FAILURE,
)

PRE_BOUNDARY_NOT_ELIGIBLE = "PRE_BOUNDARY_NOT_ELIGIBLE"
# Backward-compatible symbol names now carry the accepted terminal
# classification.  No unarmed, missing-slot, or pre-boundary event can become
# eligible merely because it was observed by the new process.
EPOCH_EVENT_PRE_ARM_REJECTED = PRE_BOUNDARY_NOT_ELIGIBLE
EPOCH_EVENT_BEFORE_START_REJECTED = PRE_BOUNDARY_NOT_ELIGIBLE
EPOCH_EVENT_ADMITTED = "EPOCH_EVENT_ADMITTED"

_HISTORY_MAX = 32

_SEMANTIC_POLICY_KEYS = (
    "production_mode_binding",
    "historical_rpc_backfill_enabled_binding",
    "dexscreener_restart_backfill_enabled_binding",
    "delivery_policy_binding",
    "telegram_enabled_binding",
    "discord_enabled_binding",
    "structural_policy_binding",
    # The named alert policy (LEGACY | PHX1_PARITY) selects which eligibility
    # conditions are enforced, how long a candidate is watched, and whether a
    # send-time market refresh runs.  It is a safety-bearing deployment
    # binding, so a switch in EITHER direction is a semantic policy change and
    # needs an authenticated closed-epoch handoff exactly like the structural
    # policy.  It is deliberately NOT in _CANONICAL_SEMANTIC_POLICY: both
    # values are legitimate identities, and the value REQUIRED of a production
    # launcher is enforced by the launcher contract, not by making one of them
    # unrepresentable here (which would make the reverse handoff impossible).
    "alert_policy_binding",
    "state_directory_binding",
    "cursor_state_directory_binding",
    "canonical_ledger_path_binding",
    "wallet_enabled_binding",
    "signing_enabled_binding",
    "trading_enabled_binding",
)

#: The value a durable identity carries when the epoch predates this binding.
LEGACY_ALERT_POLICY_BINDING = "LEGACY"

_CANONICAL_SEMANTIC_POLICY = {
    "production_mode_binding": PRODUCTION_MODE,
    "historical_rpc_backfill_enabled_binding": False,
    # Bounded six-hour DexScreener candidate recovery is part of the armed
    # Helius-primary production contract (startup recovery + periodic safety
    # net).  Historical RPC block replay stays retired and disabled.
    "dexscreener_restart_backfill_enabled_binding": True,
    "delivery_policy_binding": "TELEGRAM_ONLY",
    "telegram_enabled_binding": True,
    "discord_enabled_binding": False,
    "structural_policy_binding": "SHADOW",
    "wallet_enabled_binding": False,
    "signing_enabled_binding": False,
    "trading_enabled_binding": False,
}

_DURABLE_POLICY_IDENTITY_KEYS = {
    "identity_schema",
    "repo_head_binding",
    "launcher_sha256_binding",
    *_SEMANTIC_POLICY_KEYS,
}

_LEGACY_DERIVABLE_POLICY_KEYS = {
    "canonical_ledger_path_binding",
    "wallet_enabled_binding",
    "signing_enabled_binding",
    "trading_enabled_binding",
    # Epochs closed before the alert policy became a deployment binding carry
    # no value.  They ran the committed default, so a canonical prior launcher
    # derives LEGACY -- which is what makes the first switch to PHX1_PARITY a
    # visible semantic change rather than a silent one.
    "alert_policy_binding",
}

#: Legacy-derived defaults for identities written before a key existed.
_LEGACY_POLICY_DEFAULTS = {
    "alert_policy_binding": LEGACY_ALERT_POLICY_BINDING,
}

#: The EXACT field shape of a durable identity written before the alert policy
#: became a deployment binding: every other key present, this one absent.  The
#: commit that introduced the binding added the field and nothing has ever
#: removed one, so this shape -- and only this shape -- provably predates it.
#: A modern identity missing the field is tampering, not history, and any other
#: missing-field combination keeps the strict rule.
_PRE_ALERT_POLICY_MISSING_KEYS = frozenset({"alert_policy_binding"})

#: The semantic-policy key set as it existed BEFORE the alert-policy binding.
#: Digesting a pre-binding identity over these keys reproduces the digest the
#: audit chain recorded when that deployment was armed; digesting a modern one
#: cannot, because its recorded digest already covered the alert policy.
_PRE_ALERT_POLICY_SEMANTIC_KEYS = tuple(
    key for key in _SEMANTIC_POLICY_KEYS if key != "alert_policy_binding")


class LiveEpochIntegrityError(RuntimeError):
    """The durable epoch document cannot safely authorize live admission."""


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _path_digest(path: object) -> str:
    normalized = os.path.normcase(os.path.abspath(os.path.normpath(str(path))))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _valid_utc(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _valid_lower_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == int(length)
        and all(char in "0123456789abcdef" for char in value)
    )


def build_durable_policy_identity(
    *,
    state_dir: object,
    cursor_state_dir: Optional[object] = None,
    canonical_ledger_path: Optional[object] = None,
    repo_head: Optional[str] = None,
    launcher_sha256: Optional[str] = None,
    delivery_policy: str = "TELEGRAM_ONLY",
    telegram_enabled: bool = True,
    discord_enabled: bool = False,
    structural_policy: str = "SHADOW",
    # Named alert policy. The default is the committed LEGACY behaviour, so an
    # identity built without stating a policy describes exactly what an
    # unflagged process actually runs.
    alert_policy: str = LEGACY_ALERT_POLICY_BINDING,
    # Default mirrors _CANONICAL_SEMANTIC_POLICY: bounded DEX candidate
    # recovery is part of the armed production contract (2026-07-30).
    dex_backfill_enabled: bool = True,
    wallet_enabled: bool = False,
    signing_enabled: bool = False,
    trading_enabled: bool = False,
) -> Dict[str, Any]:
    """Build the restart-stable identity that is allowed to authorize an epoch.

    Process IDs, run directories and startup instances deliberately do not live
    here.  They are recorded by :func:`build_run_instance_identity` so a clean
    reboot can change them without weakening any durable policy check.
    """

    state_digest = _path_digest(state_dir)
    cursor_digest = _path_digest(
        state_dir if cursor_state_dir is None else cursor_state_dir)
    return {
        "identity_schema": LIVE_EPOCH_POLICY_IDENTITY_SCHEMA,
        "repo_head_binding": str(repo_head or "").strip().lower() or None,
        "launcher_sha256_binding": (
            str(launcher_sha256 or "").strip().lower() or None),
        "state_directory_binding": state_digest,
        "cursor_state_directory_binding": cursor_digest,
        "canonical_ledger_path_binding": (
            _path_digest(canonical_ledger_path)
            if canonical_ledger_path is not None else None),
        "production_mode_binding": PRODUCTION_MODE,
        "delivery_policy_binding": str(delivery_policy),
        "telegram_enabled_binding": bool(telegram_enabled),
        "discord_enabled_binding": bool(discord_enabled),
        "structural_policy_binding": str(structural_policy).upper(),
        "alert_policy_binding": normalize_alert_policy(alert_policy),
        "historical_rpc_backfill_enabled_binding": False,
        "dexscreener_restart_backfill_enabled_binding": bool(
            dex_backfill_enabled),
        "wallet_enabled_binding": bool(wallet_enabled),
        "signing_enabled_binding": bool(signing_enabled),
        "trading_enabled_binding": bool(trading_enabled),
    }


def build_run_instance_identity(
    *,
    producer_pid: Optional[int] = None,
    process_start_utc: Optional[str] = None,
    run_dir: Optional[object] = None,
    startup_manifest_digest: Optional[str] = None,
    watchdog_pid: Optional[int] = None,
    launcher_wrapper_pid: Optional[int] = None,
    runtime_nonce: Optional[str] = None,
) -> Dict[str, Any]:
    """Build non-authorizing evidence for one process/run instance."""

    return {
        "identity_schema": LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
        "producer_pid": (
            int(producer_pid) if isinstance(producer_pid, int)
            and not isinstance(producer_pid, bool) and producer_pid > 0
            else None),
        "process_start_utc": (
            str(process_start_utc) if _valid_utc(process_start_utc) else None),
        "run_directory_binding": (
            _path_digest(run_dir) if run_dir is not None else None),
        "startup_manifest_binding": (
            str(startup_manifest_digest or "").strip().lower() or None),
        "watchdog_pid": (
            int(watchdog_pid) if isinstance(watchdog_pid, int)
            and not isinstance(watchdog_pid, bool) and watchdog_pid > 0
            else None),
        "launcher_wrapper_pid": (
            int(launcher_wrapper_pid)
            if isinstance(launcher_wrapper_pid, int)
            and not isinstance(launcher_wrapper_pid, bool)
            and launcher_wrapper_pid > 0 else None),
        "runtime_nonce": str(runtime_nonce or "") or None,
    }


HANDOFF_PRIOR_DOCUMENT_INVALID = "HANDOFF_PRIOR_DOCUMENT_INVALID"
HANDOFF_PRIOR_NOT_PRIMARY = "HANDOFF_PRIOR_NOT_AUTHENTICATED_PRIMARY"
HANDOFF_PRIOR_NOT_CLOSED = "HANDOFF_PRIOR_EPOCH_NOT_DEFINITIVELY_CLOSED"
HANDOFF_PRIOR_IDENTITY_INVALID = "HANDOFF_PRIOR_DEPLOYMENT_IDENTITY_INVALID"
HANDOFF_REPOSITORY_ROLLBACK = "HANDOFF_REPOSITORY_ROLLBACK"
HANDOFF_REPOSITORY_UNRELATED = "HANDOFF_REPOSITORY_HISTORY_UNRELATED"
HANDOFF_GIT_NOT_CLEAN = "HANDOFF_GIT_DIRTY_OR_UNFINISHED"
HANDOFF_CURRENT_LAUNCHER_NONCANONICAL = (
    "HANDOFF_CURRENT_LAUNCHER_NOT_CANONICALLY_GENERATED")
HANDOFF_CURRENT_LAUNCHER_HEAD_PIN = (
    "HANDOFF_CURRENT_LAUNCHER_HEAD_PIN_COUNT_NOT_ONE")
HANDOFF_CURRENT_LAUNCHER_LEDGER_PIN = (
    "HANDOFF_CURRENT_LAUNCHER_LEDGER_PIN_COUNT_NOT_ONE")
HANDOFF_CURRENT_LAUNCHER_REFUSED = "HANDOFF_CURRENT_LAUNCHER_CONTRACT_REFUSED"
HANDOFF_SEMANTIC_POLICY_INVALID = "HANDOFF_SEMANTIC_POLICY_INVALID"
HANDOFF_SEMANTIC_POLICY_CHANGED = "HANDOFF_SEMANTIC_POLICY_CHANGED"
HANDOFF_ACTIVE_WATCHDOG = "HANDOFF_ACTIVE_WATCHDOG"
HANDOFF_ACTIVE_PRODUCER = "HANDOFF_ACTIVE_PRODUCER"
HANDOFF_ACTIVE_YELLOWSTONE_OWNER = "HANDOFF_ACTIVE_YELLOWSTONE_OWNER"
HANDOFF_ACTIVE_TELEGRAM_OWNER = "HANDOFF_ACTIVE_TELEGRAM_DELIVERY_OWNER"
HANDOFF_ACTIVE_LEDGER_WRITER = "HANDOFF_ACTIVE_CANONICAL_LEDGER_WRITER"
HANDOFF_LIVE_OR_AMBIGUOUS_LOCK = "HANDOFF_LIVE_OR_AMBIGUOUS_LOCK"
HANDOFF_AUDIT_LOG_INVALID = "HANDOFF_AUDIT_LOG_INVALID"
HANDOFF_AUDIT_CONFLICT = "HANDOFF_AUDIT_CONFLICT"
HANDOFF_GENERATION_REGRESSION = "HANDOFF_GENERATION_REGRESSION"


@dataclass(frozen=True)
class ClosedEpochDeploymentHandoffContext:
    """Read-only facts required to authorize one deployment transition.

    OS/process inspection and canonical-launcher rendering stay outside this
    module.  The transition receives only redaction-safe booleans, counts,
    digests and commit identities, which makes the policy deterministic in
    tests and keeps credentials and endpoints out of the audit surface.
    """

    current_repository_head: str
    current_launcher_sha256: str
    repository_head_is_descendant: bool
    repository_rollback: bool = False
    git_clean_and_complete: bool = True
    current_launcher_canonical: bool = False
    current_launcher_head_pin_count: int = 0
    current_launcher_ledger_pin_count: int = 0
    current_launcher_contract_refusals: Tuple[str, ...] = ()
    prior_launcher_canonical: bool = False
    canonical_ledger_path_digest: str = ""
    watchdog_count: int = 0
    producer_count: int = 0
    yellowstone_owner_count: int = 0
    telegram_delivery_owner_count: int = 0
    canonical_ledger_writer_count: int = 0
    live_or_ambiguous_lock_count: int = 0
    handoff_at_utc: str = ""


@dataclass
class ClosedEpochDeploymentHandoffVerdict:
    allowed: bool
    refusals: List[str] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)
    audit_payload: Dict[str, Any] = field(default_factory=dict)
    existing_record: Dict[str, Any] = field(default_factory=dict)


def _semantic_policy_projection(
    identity: Mapping[str, Any],
    *,
    legacy_launcher_canonical: bool = False,
    legacy_defaults: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    projection = {key: identity.get(key) for key in _SEMANTIC_POLICY_KEYS}
    if legacy_launcher_canonical:
        defaults = dict(legacy_defaults or {})
        for key in (
            "canonical_ledger_path_binding",
            "wallet_enabled_binding",
            "signing_enabled_binding",
            "trading_enabled_binding",
        ):
            if projection.get(key) is None:
                projection[key] = defaults.get(key)
    # The alert policy derives its legacy value WITHOUT requiring a canonical
    # prior launcher, and deliberately IGNORES ``legacy_defaults``: an identity
    # written before the binding existed provably ran the committed LEGACY
    # default, so this is a statement of fact.  Letting a caller supply the
    # fill would let the CURRENT identity's value stand in for the prior one,
    # which would make the very first switch look like no change at all.
    if projection.get("alert_policy_binding") is None:
        projection["alert_policy_binding"] = LEGACY_ALERT_POLICY_BINDING
    return projection


def durable_semantic_policy_digest(
    identity: Mapping[str, Any],
    *,
    legacy_launcher_canonical: bool = False,
    legacy_defaults: Optional[Mapping[str, Any]] = None,
) -> str:
    """Digest only the safety-bearing semantic deployment policy."""

    return _digest(_semantic_policy_projection(
        identity,
        legacy_launcher_canonical=legacy_launcher_canonical,
        legacy_defaults=legacy_defaults,
    ))


def _definitive_closed_epoch(payload: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if payload.get("epoch_status") != EPOCH_CLOSED:
        return None
    epoch_id = payload.get("live_epoch_id")
    history = payload.get("epoch_history")
    if not isinstance(epoch_id, str) or not epoch_id \
            or not isinstance(history, list) or not history:
        return None
    closed = history[-1]
    if not isinstance(closed, Mapping):
        return None
    if closed.get("live_epoch_id") != epoch_id \
            or closed.get("epoch_status") != EPOCH_CLOSED \
            or closed.get("epoch_start_slot") != payload.get(
                "epoch_start_slot"):
        return None
    reason = closed.get("reason")
    if not isinstance(reason, str) or not reason or len(reason) > 64 \
            or reason.upper() != reason \
            or not reason.replace("_", "").isalnum() \
            or not _valid_utc(closed.get("closed_at_utc")):
        return None
    return dict(closed)


_HANDOFF_RECORD_PAYLOAD_KEYS = {
    "schema_version",
    "event_type",
    "prior_epoch_id",
    "prior_epoch_generation",
    "prior_epoch_document_digest",
    "prior_epoch_file_sha256",
    "prior_repository_head",
    "prior_launcher_sha256",
    "prior_closure_status",
    "prior_closure_reason",
    "new_repository_head",
    "new_launcher_sha256",
    "new_policy_identity_digest",
    "semantic_policy_digest_before",
    "semantic_policy_digest_after",
    "state_directory_digest",
    "cursor_state_directory_digest",
    "canonical_ledger_path_digest",
    "handoff_at_utc",
    "handoff_generation",
    "previous_record_digest",
    "validation_outcome",
}

#: ``v2`` states the alert-policy transition in the record itself instead of
#: leaving it implicit in the semantic digests.
_HANDOFF_ALERT_POLICY_KEYS = {
    "prior_alert_policy",
    "new_alert_policy",
    "alert_policy_changed",
}
_HANDOFF_RECORD_PAYLOAD_KEYS_V2 = (
    _HANDOFF_RECORD_PAYLOAD_KEYS | _HANDOFF_ALERT_POLICY_KEYS)

_HANDOFF_RECORD_PAYLOAD_KEYS_BY_SCHEMA = {
    LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA: _HANDOFF_RECORD_PAYLOAD_KEYS,
    LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2: _HANDOFF_RECORD_PAYLOAD_KEYS_V2,
}


def classify_deployment_handoff_log(
    path: object,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Authenticate an append-only, digest-chained handoff audit log."""

    target = Path(path)
    facts: Dict[str, Any] = {
        "record_count": 0,
        "last_generation": 0,
        "last_record_digest": None,
    }
    if not target.exists():
        return "MISSING", [], facts
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return "INVALID", [], facts
    if not lines:
        return "INVALID", [], facts
    records: List[Dict[str, Any]] = []
    previous_digest: Optional[str] = None
    for expected_generation, line in enumerate(lines, start=1):
        if not line.strip():
            return "INVALID", [], facts
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            return "INVALID", [], facts
        if not isinstance(document, dict):
            return "INVALID", [], facts
        supplied = document.get("record_digest")
        payload = {
            key: value for key, value in document.items()
            if key != "record_digest"
        }
        expected_keys = _HANDOFF_RECORD_PAYLOAD_KEYS_BY_SCHEMA.get(
            payload.get("schema_version"))
        if expected_keys is None or set(payload) != expected_keys \
                or not isinstance(supplied, str) \
                or supplied != _digest(payload):
            return "INVALID", [], facts
        if payload.get("event_type") \
                != CLOSED_EPOCH_DEPLOYMENT_HANDOFF \
                or payload.get("validation_outcome") != "ACCEPTED" \
                or payload.get("handoff_generation") != expected_generation \
                or payload.get("previous_record_digest") != previous_digest \
                or not _valid_utc(payload.get("handoff_at_utc")):
            return "INVALID", [], facts
        if payload.get("schema_version") \
                == LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2:
            prior_policy = payload.get("prior_alert_policy")
            new_policy = payload.get("new_alert_policy")
            changed = payload.get("alert_policy_changed")
            # A stated transition has to be internally consistent: both ends
            # named from the closed set, and the flag equal to whether they
            # actually differ.  A record that CLAIMS no change while naming two
            # different policies would otherwise launder a silent switch.
            if prior_policy not in ALERT_POLICY_MODES \
                    or new_policy not in ALERT_POLICY_MODES \
                    or not isinstance(changed, bool) \
                    or changed != (prior_policy != new_policy):
                return "INVALID", [], facts
        for digest_key in (
            "prior_epoch_document_digest",
            "prior_epoch_file_sha256",
            "prior_launcher_sha256",
            "new_launcher_sha256",
            "new_policy_identity_digest",
            "semantic_policy_digest_before",
            "semantic_policy_digest_after",
            "state_directory_digest",
            "cursor_state_directory_digest",
            "canonical_ledger_path_digest",
        ):
            value = payload.get(digest_key)
            if not _valid_lower_hex(value, 64):
                return "INVALID", [], facts
        for head_key in ("prior_repository_head", "new_repository_head"):
            value = payload.get(head_key)
            if not _valid_lower_hex(value, 40):
                return "INVALID", [], facts
        generation = payload.get("prior_epoch_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) \
                or generation < 0:
            return "INVALID", [], facts
        record = {**payload, "record_digest": supplied}
        records.append(record)
        previous_digest = supplied
    facts.update({
        "record_count": len(records),
        "last_generation": len(records),
        "last_record_digest": previous_digest,
    })
    return "VALID", records, facts


def pre_alert_policy_semantic_digest(identity: Mapping[str, Any]) -> str:
    """Digest an identity over the semantic keys that existed pre-binding.

    This is the digest the handoff chain recorded as
    ``semantic_policy_digest_after`` when a pre-binding deployment was armed,
    because back then ``_SEMANTIC_POLICY_KEYS`` did not include the alert
    policy.  Recomputing it is what proves a prior identity is BYTE-authentic
    against the chain AND that the chain itself predates the binding.
    """

    return _digest({
        key: identity.get(key) for key in _PRE_ALERT_POLICY_SEMANTIC_KEYS})


def attested_prior_deployment(
    records: Sequence[Mapping[str, Any]], prior_repository_head: object
) -> Optional[Dict[str, Any]]:
    """The MOST RECENT accepted record that armed ``prior_repository_head``.

    Most-recent-wins, and a non-matching newer record for the same head is a
    refusal rather than a reason to keep searching backwards: if that head was
    ever re-armed with a different launcher, the older record no longer
    describes the deployment being adopted.
    """

    head = str(prior_repository_head or "").strip().lower()
    if not _valid_lower_hex(head, 40):
        return None
    for item in reversed(list(records)):
        if item.get("new_repository_head") == head:
            return dict(item)
    return None


def prior_identity_predates_alert_policy_binding(
    prior_identity: Mapping[str, Any],
    *,
    records: Sequence[Mapping[str, Any]],
) -> bool:
    """Is this a GENUINELY pre-alert-policy identity, authenticated as such?

    ``prior_launcher_canonical`` cannot answer this.  It re-renders the prior
    head with the CURRENT launcher template, and the very commit that
    introduced ``alert_policy_binding`` also added the ``--alert-policy`` lines
    to that template -- so for exactly the epochs this compatibility path
    exists to adopt, the re-render can never reproduce the prior launcher hash.
    The preserved evidence is the digest-chained handoff log, which recorded
    that launcher as canonical for that head back when the renderer agreed.

    Every one of these must hold, and each closes a distinct forgery:

    * the field shape is EXACTLY the pre-binding one (no unknown keys, the
      alert policy the ONLY absent key) -- arbitrary omissions stay refused;
    * the schema is the current identity schema -- an unrelated schema is not
      silently adopted;
    * an accepted chain record armed this exact repo head;
    * that record's launcher is byte-equal to the identity's launcher binding;
    * the identity's PRE-binding semantic digest reproduces the digest that
      record stored.  A modern epoch with the field stripped fails here: its
      recorded digest already covered the alert policy, so the pre-binding
      recomputation cannot match.  A tampered semantic field fails too.
    """

    if not isinstance(prior_identity, Mapping) \
            or prior_identity.get("identity_schema") \
            != LIVE_EPOCH_POLICY_IDENTITY_SCHEMA:
        return False
    prior_keys = set(prior_identity)
    if (prior_keys - _DURABLE_POLICY_IDENTITY_KEYS):
        return False
    if (_DURABLE_POLICY_IDENTITY_KEYS - prior_keys) \
            != _PRE_ALERT_POLICY_MISSING_KEYS:
        return False
    head = str(prior_identity.get("repo_head_binding") or "").lower()
    launcher = str(
        prior_identity.get("launcher_sha256_binding") or "").lower()
    if not _valid_lower_hex(head, 40) or not _valid_lower_hex(launcher, 64):
        return False
    attested = attested_prior_deployment(records, head)
    if attested is None or attested.get("new_launcher_sha256") != launcher:
        return False
    return attested.get("semantic_policy_digest_after") == (
        pre_alert_policy_semantic_digest(prior_identity))


def closed_epoch_archive_path(
    epoch_path: object, prior_epoch_file_sha256: str
) -> Path:
    return (
        Path(epoch_path).parent
        / LIVE_EPOCH_CLOSED_ARCHIVE_DIRNAME
        / (str(prior_epoch_file_sha256).lower() + ".json")
    )


def _file_sha256(path: object) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _closed_epoch_archive_is_exact(
    epoch_path: object, prior_epoch_file_sha256: str
) -> bool:
    archive = closed_epoch_archive_path(
        epoch_path, prior_epoch_file_sha256)
    return _file_sha256(archive) == str(prior_epoch_file_sha256).lower()


def _matching_handoff_record(
    records: Sequence[Mapping[str, Any]],
    *,
    prior_epoch: Mapping[str, Any],
    current_policy_identity: Mapping[str, Any],
    prior_epoch_file_sha256: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    prior_identity = prior_epoch.get("durable_policy_identity")
    if not isinstance(prior_identity, Mapping):
        return None
    prior_document_digest = _digest(prior_epoch)
    new_policy_digest = _digest(current_policy_identity)
    before = durable_semantic_policy_digest(
        prior_identity,
        legacy_launcher_canonical=True,
        legacy_defaults=current_policy_identity,
    )
    after = durable_semantic_policy_digest(current_policy_identity)
    for item in reversed(list(records)):
        if item.get("prior_epoch_document_digest") == prior_document_digest \
                and item.get("prior_epoch_id") == prior_epoch.get(
                    "live_epoch_id") \
                and item.get("prior_epoch_generation") == prior_epoch.get(
                    "generation") \
                and (
                    prior_epoch_file_sha256 is None
                    or item.get("prior_epoch_file_sha256")
                    == prior_epoch_file_sha256
                ) \
                and item.get("new_policy_identity_digest") == new_policy_digest \
                and item.get("semantic_policy_digest_before") == before \
                and item.get("semantic_policy_digest_after") == after \
                and item.get("validation_outcome") == "ACCEPTED":
            return dict(item)
    return None


def closed_epoch_deployment_handoff_is_valid(
    *,
    epoch_path: object,
    current_policy_identity: Mapping[str, Any],
    handoff_path: Optional[object] = None,
) -> bool:
    """Read-only proof that one exact CLOSED document authorized this identity."""

    state, prior_epoch, facts = classify_live_epoch_document_set(epoch_path)
    if state != "VALID_CURRENT" or facts.get("selected") != "primary" \
            or _definitive_closed_epoch(prior_epoch) is None:
        return False
    path = (
        Path(handoff_path) if handoff_path is not None
        else Path(epoch_path).with_name(
            LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME))
    log_state, records, _ = classify_deployment_handoff_log(path)
    if log_state != "VALID":
        return False
    prior_file_sha256 = _file_sha256(epoch_path)
    if prior_file_sha256 is None \
            or not _closed_epoch_archive_is_exact(
                epoch_path, prior_file_sha256):
        return False
    return _matching_handoff_record(
        records,
        prior_epoch=prior_epoch,
        current_policy_identity=current_policy_identity,
        prior_epoch_file_sha256=prior_file_sha256,
    ) is not None


def validate_closed_epoch_deployment_handoff(
    *,
    epoch_path: object,
    current_policy_identity: Mapping[str, Any],
    context: ClosedEpochDeploymentHandoffContext,
    handoff_path: Optional[object] = None,
) -> ClosedEpochDeploymentHandoffVerdict:
    """Authorize only a fully stopped, forward-only CLOSED-epoch deployment.

    This does not mutate either epoch document.  It produces a safe audit
    payload which :func:`record_closed_epoch_deployment_handoff` may append
    after the caller has rechecked the same process/lock facts.
    """

    refusals: List[str] = []
    checks: Dict[str, Any] = {}
    state, prior_epoch, epoch_facts = classify_live_epoch_document_set(
        epoch_path)
    checks["prior_document_state"] = state
    checks["prior_selected"] = epoch_facts.get("selected")
    if state != "VALID_CURRENT":
        refusals.append(HANDOFF_PRIOR_DOCUMENT_INVALID)
    elif epoch_facts.get("selected") != "primary":
        refusals.append(HANDOFF_PRIOR_NOT_PRIMARY)
    closure = (
        _definitive_closed_epoch(prior_epoch)
        if state == "VALID_CURRENT" else None)
    if closure is None:
        refusals.append(HANDOFF_PRIOR_NOT_CLOSED)

    # Parsed here rather than at the point of use: the chain is the preserved
    # evidence a PRE-alert-policy identity is authenticated against, so the
    # identity gate below needs it.  Purely a read; its own refusal stays where
    # it was so the refusal ordering is unchanged.
    log_path = (
        Path(handoff_path) if handoff_path is not None
        else Path(epoch_path).with_name(
            LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME))
    log_state, records, log_facts = classify_deployment_handoff_log(log_path)

    prior_identity = prior_epoch.get("durable_policy_identity")
    prior_predates_alert_policy = False
    if not isinstance(prior_identity, Mapping) \
            or prior_identity.get("identity_schema") \
            != LIVE_EPOCH_POLICY_IDENTITY_SCHEMA:
        refusals.append(HANDOFF_PRIOR_IDENTITY_INVALID)
        prior_identity = {}
    else:
        prior_keys = set(prior_identity)
        unknown_prior_keys = (
            prior_keys - _DURABLE_POLICY_IDENTITY_KEYS)
        missing_prior_keys = (
            _DURABLE_POLICY_IDENTITY_KEYS - prior_keys)
        if unknown_prior_keys or (
                missing_prior_keys - _LEGACY_DERIVABLE_POLICY_KEYS):
            refusals.append(HANDOFF_PRIOR_IDENTITY_INVALID)
        # A genuinely pre-binding epoch cannot satisfy prior_launcher_canonical
        # -- the commit that added the binding also added the --alert-policy
        # lines to the launcher template, so re-rendering the prior head today
        # can never reproduce the launcher it actually ran.  The chain is what
        # authenticates it, and ONLY for the exact pre-binding field shape.
        prior_predates_alert_policy = (
            prior_identity_predates_alert_policy_binding(
                prior_identity, records=records))
        legacy_fill_authenticated = bool(
            context.prior_launcher_canonical or prior_predates_alert_policy)
        if missing_prior_keys and (
                not legacy_fill_authenticated
                or not missing_prior_keys.issubset(
                    _LEGACY_DERIVABLE_POLICY_KEYS)):
            refusals.append(HANDOFF_PRIOR_IDENTITY_INVALID)
    checks["prior_predates_alert_policy_binding"] = prior_predates_alert_policy
    if current_policy_identity.get("identity_schema") \
            != LIVE_EPOCH_POLICY_IDENTITY_SCHEMA \
            or set(current_policy_identity) != _DURABLE_POLICY_IDENTITY_KEYS:
        refusals.append(HANDOFF_SEMANTIC_POLICY_INVALID)

    prior_head = str(prior_identity.get("repo_head_binding") or "").lower()
    prior_launcher = str(
        prior_identity.get("launcher_sha256_binding") or "").lower()
    current_head = str(context.current_repository_head or "").lower()
    current_launcher = str(context.current_launcher_sha256 or "").lower()
    checks.update({
        "prior_repository_head": prior_head or None,
        "current_repository_head": current_head or None,
        "repository_head_is_descendant": bool(
            context.repository_head_is_descendant),
        "repository_rollback": bool(context.repository_rollback),
    })
    if not _valid_lower_hex(prior_head, 40) \
            or not _valid_lower_hex(prior_launcher, 64) \
            or not _valid_lower_hex(current_head, 40) \
            or not _valid_lower_hex(current_launcher, 64) \
            or prior_head == current_head:
        refusals.append(HANDOFF_PRIOR_IDENTITY_INVALID)
    if context.repository_rollback:
        refusals.append(HANDOFF_REPOSITORY_ROLLBACK)
    elif not context.repository_head_is_descendant:
        refusals.append(HANDOFF_REPOSITORY_UNRELATED)
    if not context.git_clean_and_complete:
        refusals.append(HANDOFF_GIT_NOT_CLEAN)
    if not context.current_launcher_canonical:
        refusals.append(HANDOFF_CURRENT_LAUNCHER_NONCANONICAL)
    if int(context.current_launcher_head_pin_count) != 1:
        refusals.append(HANDOFF_CURRENT_LAUNCHER_HEAD_PIN)
    if int(context.current_launcher_ledger_pin_count) != 1:
        refusals.append(HANDOFF_CURRENT_LAUNCHER_LEDGER_PIN)
    if context.current_launcher_contract_refusals:
        refusals.append(HANDOFF_CURRENT_LAUNCHER_REFUSED)

    current_projection = _semantic_policy_projection(
        current_policy_identity)
    legacy_defaults = dict(current_policy_identity)
    legacy_defaults.update({
        "canonical_ledger_path_binding":
            context.canonical_ledger_path_digest,
        "wallet_enabled_binding": False,
        "signing_enabled_binding": False,
        "trading_enabled_binding": False,
        # NOT inherited from the current identity. An epoch written before the
        # binding existed ran the committed LEGACY behaviour, full stop; the
        # projection enforces this independently, and stating it here keeps the
        # audited ``legacy_defaults`` payload honest about what was assumed.
        **_LEGACY_POLICY_DEFAULTS,
    })
    prior_projection = _semantic_policy_projection(
        prior_identity,
        legacy_launcher_canonical=bool(context.prior_launcher_canonical),
        legacy_defaults=legacy_defaults,
    )
    semantic_complete = all(
        current_projection.get(key) is not None
        and prior_projection.get(key) is not None
        for key in _SEMANTIC_POLICY_KEYS)
    canonical_semantics = all(
        current_projection.get(key) == value
        for key, value in _CANONICAL_SEMANTIC_POLICY.items())
    canonical_semantics = bool(
        canonical_semantics
        and current_projection.get("state_directory_binding")
        == current_projection.get("cursor_state_directory_binding")
        and current_projection.get("canonical_ledger_path_binding")
        == context.canonical_ledger_path_digest
        and bool(context.canonical_ledger_path_digest))
    semantic_equal = prior_projection == current_projection
    retirement_projection = dict(prior_projection)
    retirement_projection[
        "dexscreener_restart_backfill_enabled_binding"
    ] = False
    dex_authority_retired = bool(
        prior_projection.get(
            "dexscreener_restart_backfill_enabled_binding"
        ) is True
        and current_projection.get(
            "dexscreener_restart_backfill_enabled_binding"
        ) is False
        and retirement_projection == current_projection
    )
    # Sanctioned single-binding reinstatement: bounded DEX candidate recovery
    # returns to the armed production contract (prior epochs were written with
    # the binding False).  Exactly this one binding may flip False -> True;
    # any other simultaneous policy change still refuses.
    reinstatement_projection = dict(prior_projection)
    reinstatement_projection[
        "dexscreener_restart_backfill_enabled_binding"
    ] = True
    dex_backfill_reinstated = bool(
        prior_projection.get(
            "dexscreener_restart_backfill_enabled_binding"
        ) is False
        and current_projection.get(
            "dexscreener_restart_backfill_enabled_binding"
        ) is True
        and reinstatement_projection == current_projection
    )
    # Sanctioned single-binding alert-policy transition, in EITHER direction.
    # Without this arm a policy switch would be impossible rather than
    # handoff-gated: the refusal below authorizes only head/launcher changes,
    # so the switch could never be performed at all. Exactly this one binding
    # may differ; any other simultaneous policy change still refuses, and the
    # transition still has to clear every other handoff requirement (fully
    # stopped, forward-only, canonical launcher, audited).
    alert_policy_projection = dict(prior_projection)
    alert_policy_projection["alert_policy_binding"] = current_projection.get(
        "alert_policy_binding")
    prior_alert_policy = prior_projection.get("alert_policy_binding")
    current_alert_policy_value = current_projection.get("alert_policy_binding")
    alert_policy_changed = bool(
        prior_alert_policy != current_alert_policy_value
        and prior_alert_policy in ALERT_POLICY_MODES
        and current_alert_policy_value in ALERT_POLICY_MODES
        and alert_policy_projection == current_projection
    )
    checks.update({
        "semantic_policy_complete": semantic_complete,
        "canonical_semantics": canonical_semantics,
        "semantic_policy_equal": semantic_equal,
        "dex_candidate_authority_retired": dex_authority_retired,
        "dex_backfill_reinstated": dex_backfill_reinstated,
        "alert_policy_changed": alert_policy_changed,
        "prior_alert_policy": prior_alert_policy,
        "current_alert_policy": current_alert_policy_value,
        "prior_launcher_canonical": bool(context.prior_launcher_canonical),
    })
    if not semantic_complete or not canonical_semantics:
        refusals.append(HANDOFF_SEMANTIC_POLICY_INVALID)
    if (not semantic_equal and not dex_authority_retired
            and not dex_backfill_reinstated
            and not alert_policy_changed):
        refusals.append(HANDOFF_SEMANTIC_POLICY_CHANGED)

    owner_checks = (
        (context.watchdog_count, HANDOFF_ACTIVE_WATCHDOG),
        (context.producer_count, HANDOFF_ACTIVE_PRODUCER),
        (context.yellowstone_owner_count,
         HANDOFF_ACTIVE_YELLOWSTONE_OWNER),
        (context.telegram_delivery_owner_count,
         HANDOFF_ACTIVE_TELEGRAM_OWNER),
        (context.canonical_ledger_writer_count,
         HANDOFF_ACTIVE_LEDGER_WRITER),
        (context.live_or_ambiguous_lock_count,
         HANDOFF_LIVE_OR_AMBIGUOUS_LOCK),
    )
    for count, reason in owner_checks:
        if isinstance(count, bool) or not isinstance(count, int) or count != 0:
            refusals.append(reason)
    checks.update({
        "watchdog_count": context.watchdog_count,
        "producer_count": context.producer_count,
        "yellowstone_owner_count": context.yellowstone_owner_count,
        "telegram_delivery_owner_count":
            context.telegram_delivery_owner_count,
        "canonical_ledger_writer_count":
            context.canonical_ledger_writer_count,
        "live_or_ambiguous_lock_count":
            context.live_or_ambiguous_lock_count,
    })

    if log_state == "INVALID":
        refusals.append(HANDOFF_AUDIT_LOG_INVALID)
    prior_document_digest = (
        _digest(prior_epoch) if state == "VALID_CURRENT" else "")
    prior_file_sha256 = (
        _file_sha256(epoch_path) if state == "VALID_CURRENT" else None)
    current_policy_digest = _digest(current_policy_identity)
    existing = (
        _matching_handoff_record(
            records,
            prior_epoch=prior_epoch,
            current_policy_identity=current_policy_identity,
            prior_epoch_file_sha256=prior_file_sha256,
        )
        if log_state in ("VALID", "MISSING") and prior_epoch else None)
    for item in records:
        same_prior = item.get(
            "prior_epoch_document_digest") == prior_document_digest
        if same_prior and (
                item.get("new_policy_identity_digest")
                != current_policy_digest
                or item.get("new_repository_head") != current_head
                or item.get("new_launcher_sha256") != current_launcher):
            refusals.append(HANDOFF_AUDIT_CONFLICT)
    next_generation = int(log_facts.get("last_generation") or 0) + 1
    if existing and int(existing.get("handoff_generation") or 0) \
            > int(log_facts.get("last_generation") or 0):
        refusals.append(HANDOFF_GENERATION_REGRESSION)
    if existing and (
            prior_file_sha256 is None
            or not _closed_epoch_archive_is_exact(
                epoch_path, prior_file_sha256)):
        refusals.append(HANDOFF_AUDIT_LOG_INVALID)

    before_digest = _digest(prior_projection)
    after_digest = _digest(current_projection)
    audit_payload: Dict[str, Any] = {}
    if not refusals and not existing and closure is not None:
        audit_payload = {
            "schema_version": LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2,
            "event_type": CLOSED_EPOCH_DEPLOYMENT_HANDOFF,
            "prior_epoch_id": prior_epoch.get("live_epoch_id"),
            "prior_epoch_generation": int(
                prior_epoch.get("generation") or 0),
            "prior_epoch_document_digest": prior_document_digest,
            "prior_epoch_file_sha256": str(prior_file_sha256),
            "prior_repository_head": prior_head,
            "prior_launcher_sha256": prior_launcher,
            "prior_closure_status": EPOCH_CLOSED,
            "prior_closure_reason": closure.get("reason"),
            "new_repository_head": current_head,
            "new_launcher_sha256": current_launcher,
            "new_policy_identity_digest": current_policy_digest,
            "semantic_policy_digest_before": before_digest,
            "semantic_policy_digest_after": after_digest,
            "state_directory_digest": str(
                current_projection["state_directory_binding"]),
            "cursor_state_directory_digest": str(
                current_projection["cursor_state_directory_binding"]),
            "canonical_ledger_path_digest": str(
                current_projection["canonical_ledger_path_binding"]),
            "handoff_at_utc": (
                context.handoff_at_utc
                if _valid_utc(context.handoff_at_utc) else _utc_now()),
            "handoff_generation": next_generation,
            "previous_record_digest": log_facts.get(
                "last_record_digest"),
            # Stated outright, not left to be inferred from the two semantic
            # digests.  An adoption of a pre-binding epoch records
            # LEGACY -> PHX1_PARITY with alert_policy_changed=true, so the
            # transition is legible in the audit trail forever.
            "prior_alert_policy": prior_alert_policy,
            "new_alert_policy": current_alert_policy_value,
            "alert_policy_changed": bool(
                prior_alert_policy != current_alert_policy_value),
            "validation_outcome": "ACCEPTED",
        }
    ordered_refusals: List[str] = []
    for reason in refusals:
        if reason not in ordered_refusals:
            ordered_refusals.append(reason)
    checks.update({
        "handoff_log_state": log_state,
        "handoff_generation": (
            existing.get("handoff_generation") if existing
            else next_generation),
        "existing_idempotent_record": bool(existing),
        "semantic_policy_digest_before": before_digest,
        "semantic_policy_digest_after": after_digest,
    })
    return ClosedEpochDeploymentHandoffVerdict(
        allowed=not ordered_refusals,
        refusals=ordered_refusals,
        checks=checks,
        audit_payload=audit_payload,
        existing_record=dict(existing or {}),
    )


def record_closed_epoch_deployment_handoff(
    *,
    epoch_path: object,
    current_policy_identity: Mapping[str, Any],
    context: ClosedEpochDeploymentHandoffContext,
    handoff_path: Optional[object] = None,
) -> ClosedEpochDeploymentHandoffVerdict:
    """Append one authenticated audit event without rewriting the prior epoch."""

    target = (
        Path(handoff_path) if handoff_path is not None
        else Path(epoch_path).with_name(
            LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME))
    verdict = validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=current_policy_identity,
        context=context,
        handoff_path=target,
    )
    if not verdict.allowed or verdict.existing_record:
        return verdict
    payload = dict(verdict.audit_payload)
    try:
        prior_bytes = Path(epoch_path).read_bytes()
    except OSError:
        verdict.allowed = False
        verdict.refusals.append(HANDOFF_PRIOR_DOCUMENT_INVALID)
        return verdict
    prior_file_sha256 = hashlib.sha256(prior_bytes).hexdigest()
    if prior_file_sha256 != payload.get("prior_epoch_file_sha256"):
        verdict.allowed = False
        verdict.refusals.append(HANDOFF_PRIOR_DOCUMENT_INVALID)
        return verdict
    archive = closed_epoch_archive_path(epoch_path, prior_file_sha256)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        try:
            archive_matches = archive.read_bytes() == prior_bytes
        except OSError:
            archive_matches = False
        if not archive_matches:
            verdict.allowed = False
            verdict.refusals.append(HANDOFF_AUDIT_CONFLICT)
            return verdict
    else:
        archive_temp = archive.with_name(archive.name + ".tmp")
        try:
            with archive_temp.open("wb") as handle:
                handle.write(prior_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(archive_temp, archive)
        except OSError:
            try:
                archive_temp.unlink()
            except OSError:
                pass
            verdict.allowed = False
            verdict.refusals.append(HANDOFF_AUDIT_LOG_INVALID)
            return verdict
    if _file_sha256(archive) != prior_file_sha256:
        verdict.allowed = False
        verdict.refusals.append(HANDOFF_AUDIT_LOG_INVALID)
        return verdict
    document = {**payload, "record_digest": _digest(payload)}
    line = _canonical(document) + b"\n"
    try:
        existing_bytes = target.read_bytes() if target.exists() else b""
    except OSError:
        verdict.allowed = False
        verdict.refusals.append(HANDOFF_AUDIT_LOG_INVALID)
        return verdict
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(existing_bytes)
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except OSError:
        try:
            temp.unlink()
        except OSError:
            pass
        verdict.allowed = False
        verdict.refusals.append(HANDOFF_AUDIT_LOG_INVALID)
        return verdict
    state, records, _ = classify_deployment_handoff_log(target)
    if state != "VALID" or not records \
            or records[-1].get("record_digest") != document["record_digest"] \
            or not _closed_epoch_archive_is_exact(
                epoch_path, prior_file_sha256):
        verdict.allowed = False
        verdict.refusals.append(HANDOFF_AUDIT_LOG_INVALID)
        return verdict
    verdict.existing_record = dict(records[-1])
    return verdict


def _payload_is_valid(payload: Mapping[str, Any]) -> bool:
    """Validate the authenticated live-epoch payload itself."""

    if payload.get("schema_version") != LIVE_EPOCH_SCHEMA_VERSION:
        return False
    generation = payload.get("generation", 0)
    if isinstance(generation, bool) or not isinstance(generation, int) \
            or generation < 0:
        return False
    if payload.get("epoch_status") not in EPOCH_STATUSES:
        return False
    if not isinstance(payload.get("rollover_count"), int) \
            or isinstance(payload.get("rollover_count"), bool) \
            or int(payload["rollover_count"]) < 0:
        return False
    epoch_id = payload.get("live_epoch_id")
    if payload.get("epoch_status") != EPOCH_INTEGRITY_FAILURE \
            and (not isinstance(epoch_id, str) or not epoch_id):
        return False
    start = payload.get("epoch_start_slot")
    boundary = payload.get("observed_confirmed_boundary_slot")
    if start is not None and (
            isinstance(start, bool) or not isinstance(start, int) or start <= 0):
        return False
    if boundary is not None and (
            isinstance(boundary, bool) or not isinstance(boundary, int)
            or boundary <= 0):
        return False
    if payload.get("epoch_status") == EPOCH_HEALTHY:
        if start is None or boundary is None or start != boundary + 1:
            return False
        if not _valid_utc(payload.get("epoch_armed_at_utc")):
            return False
    if not _valid_utc(payload.get("updated_at_utc")):
        return False
    history = payload.get("epoch_history")
    if not isinstance(history, list) or len(history) > _HISTORY_MAX:
        return False
    durable_identity = payload.get("durable_policy_identity")
    if durable_identity is not None and (
            not isinstance(durable_identity, Mapping)
            or durable_identity.get("identity_schema")
            != LIVE_EPOCH_POLICY_IDENTITY_SCHEMA):
        return False
    run_identity = payload.get("run_instance_identity")
    if run_identity is not None and (
            not isinstance(run_identity, Mapping)
            or run_identity.get("identity_schema")
            != LIVE_EPOCH_RUN_IDENTITY_SCHEMA):
        return False
    deployment_handoff = payload.get("deployment_handoff")
    if deployment_handoff is not None:
        if not isinstance(deployment_handoff, Mapping) \
                or deployment_handoff.get("schema_version") \
                not in LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMAS:
            return False
        if not isinstance(deployment_handoff.get("handoff_generation"), int) \
                or isinstance(
                    deployment_handoff.get("handoff_generation"), bool) \
                or int(deployment_handoff["handoff_generation"]) <= 0:
            return False
        for key in (
            "record_digest",
            "prior_epoch_document_digest",
            "prior_epoch_file_sha256",
        ):
            value = deployment_handoff.get(key)
            if not isinstance(value, str) or len(value) != 64:
                return False
    return True


def classify_live_epoch_document(path: object) -> Tuple[str, Dict[str, Any]]:
    """Return ``(MISSING|VALID_CURRENT|INVALID, payload)`` without mutation."""

    target = Path(path)
    if not target.exists():
        return "MISSING", {}
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "INVALID", {}
    if not isinstance(document, dict):
        return "INVALID", {}
    supplied = document.get("document_digest")
    payload = {k: v for k, v in document.items() if k != "document_digest"}
    if not isinstance(supplied, str) or supplied != _digest(payload):
        return "INVALID", {}
    if not _payload_is_valid(payload):
        return "INVALID", {}
    return "VALID_CURRENT", payload


def classify_live_epoch_document_set(
    path: object,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """Select an authenticated primary/backup generation without mutation.

    A newer backup than primary is a rollback, and equal generations with
    different digests are a conflict.  Either condition fails closed.
    """

    primary_path = Path(path)
    backup_path = primary_path.with_name(
        primary_path.name + LIVE_EPOCH_BACKUP_SUFFIX)
    primary_state, primary = classify_live_epoch_document(primary_path)
    backup_state, backup = classify_live_epoch_document(backup_path)
    facts: Dict[str, Any] = {
        "primary_state": primary_state,
        "backup_state": backup_state,
        "selected": None,
        "recovered_from_backup": False,
        "generation_conflict": False,
    }
    primary_ok = primary_state == "VALID_CURRENT"
    backup_ok = backup_state == "VALID_CURRENT"
    if not primary_ok and not backup_ok:
        if primary_state == "MISSING" and backup_state == "MISSING":
            return "MISSING", {}, facts
        return "INVALID", {}, facts
    if primary_ok and backup_ok:
        primary_generation = int(primary.get("generation") or 0)
        backup_generation = int(backup.get("generation") or 0)
        if backup_generation > primary_generation:
            facts["generation_conflict"] = True
            return "INVALID", {}, facts
        if backup_generation == primary_generation \
                and _digest(primary) != _digest(backup):
            facts["generation_conflict"] = True
            return "INVALID", {}, facts
        facts["selected"] = "primary"
        return "VALID_CURRENT", primary, facts
    if primary_ok:
        facts["selected"] = "primary"
        return "VALID_CURRENT", primary, facts
    facts["selected"] = "backup"
    facts["recovered_from_backup"] = True
    return "VALID_BACKUP", backup, facts


def live_epoch_handoff_is_valid(
    heartbeat_epoch: Mapping[str, Any],
    durable_epoch: Mapping[str, Any],
) -> bool:
    """Prove a lagging heartbeat names the immediately prior closed epoch.

    This is deliberately narrower than "ignore PID/run changes": both documents
    must be authenticated by their owning readers, the heartbeat must itself
    report durability, and the old ID/start boundary must match the newest
    immutable closure record.  An unrelated or forged epoch ID still fails.
    """

    old_id = heartbeat_epoch.get("live_epoch_id")
    new_id = durable_epoch.get("live_epoch_id")
    if not isinstance(old_id, str) or not old_id \
            or not isinstance(new_id, str) or not new_id or old_id == new_id:
        return False
    if heartbeat_epoch.get("epoch_durable") is not True:
        return False
    history = durable_epoch.get("epoch_history")
    if not isinstance(history, list) or not history:
        return False
    closed = history[-1]
    if not isinstance(closed, Mapping):
        return False
    if closed.get("live_epoch_id") != old_id \
            or closed.get("epoch_status") != EPOCH_CLOSED:
        return False
    if closed.get("epoch_start_slot") != heartbeat_epoch.get(
            "epoch_start_slot"):
        return False
    closed_at = closed.get("closed_at_utc")
    if not _valid_utc(closed_at):
        return False
    last_break = durable_epoch.get("last_continuity_break")
    if not isinstance(last_break, Mapping):
        return False
    if last_break.get("observed_at_utc") != closed_at \
            or last_break.get("reason") != closed.get("reason"):
        return False
    return (
        durable_epoch.get("epoch_status") in (EPOCH_STARTING, EPOCH_HEALTHY)
        and isinstance(durable_epoch.get("rollover_count"), int)
        and int(durable_epoch["rollover_count"]) >= 1
    )


class LiveEpochManager:
    """Thread-safe durable epoch state with fail-closed corruption handling."""

    def __init__(
        self,
        *,
        state_dir: object,
        now_fn: Callable[[], str] = _utc_now,
        id_fn: Optional[Callable[[], str]] = None,
        durable_policy_identity: Optional[Mapping[str, Any]] = None,
        run_instance_identity: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.path = Path(state_dir) / LIVE_EPOCH_BASENAME
        self.backup_path = self.path.with_name(
            self.path.name + LIVE_EPOCH_BACKUP_SUFFIX)
        self._now = now_fn
        self._id = id_fn or (
            lambda: "epoch_" + uuid.uuid4().hex[:20])
        self._lock = threading.RLock()
        self._closed_epoch_queue: List[Dict[str, Any]] = []
        self._durable_policy_identity = dict(
            durable_policy_identity or build_durable_policy_identity(
                state_dir=state_dir))
        self._run_instance_identity = dict(run_instance_identity or {})
        state, payload, load_facts = classify_live_epoch_document_set(self.path)
        self._document_state = state
        self._load_facts = dict(load_facts)
        self._generation = int(payload.get("generation") or 0)
        self._integrity_failure = state == "INVALID"
        self._deployment_handoff_applied = False
        self._deployment_handoff_record: Dict[str, Any] = {}
        stored_policy = payload.get("durable_policy_identity")
        policy_mismatch = bool(
            isinstance(stored_policy, Mapping)
            and dict(stored_policy) != self._durable_policy_identity)
        handoff_valid = bool(
            policy_mismatch
            and state == "VALID_CURRENT"
            and closed_epoch_deployment_handoff_is_valid(
                epoch_path=self.path,
                current_policy_identity=self._durable_policy_identity,
            ))
        if handoff_valid:
            handoff_path = self.path.with_name(
                LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME)
            log_state, records, _ = classify_deployment_handoff_log(
                handoff_path)
            if log_state == "VALID":
                self._deployment_handoff_record = (
                    _matching_handoff_record(
                        records,
                        prior_epoch=payload,
                        current_policy_identity=self._durable_policy_identity,
                    ) or {})
            handoff_valid = bool(self._deployment_handoff_record)
        if policy_mismatch and not handoff_valid:
            self._integrity_failure = True
            self._document_state = "POLICY_IDENTITY_MISMATCH"
        self._state: Dict[str, Any] = (
            payload if state in ("VALID_CURRENT", "VALID_BACKUP") else {})
        if self._integrity_failure:
            self._state = {
                "schema_version": LIVE_EPOCH_SCHEMA_VERSION,
                "production_mode": PRODUCTION_MODE,
                "historical_completeness_required": False,
                "historical_rpc_backfill_enabled": False,
                "historical_recovery_status": HISTORICAL_REPLAY_STATUS,
                "live_epoch_id": None,
                "epoch_status": EPOCH_INTEGRITY_FAILURE,
                "epoch_start_slot": None,
                "observed_confirmed_boundary_slot": None,
                "epoch_started_at_utc": None,
                "epoch_armed_at_utc": None,
                "rollover_count": 0,
                "last_continuity_break": None,
                "epoch_history": [],
                "generation": self._generation,
                "durable_policy_identity": self._durable_policy_identity,
                "deployment_handoff": None,
                "run_instance_identity": (
                    dict(self._run_instance_identity)
                    if self._run_instance_identity else None),
                "updated_at_utc": self._now(),
            }
            return
        if handoff_valid:
            prior_history = list(self._state.get("epoch_history") or [])
            prior_rollovers = int(self._state.get("rollover_count") or 0)
            record = dict(self._deployment_handoff_record)
            self._state = self._new_starting_state(
                rollover_count=prior_rollovers + 1,
                history=prior_history[-_HISTORY_MAX:],
                last_break={
                    "reason": CLOSED_EPOCH_DEPLOYMENT_HANDOFF,
                    "observed_at_utc": str(record["handoff_at_utc"]),
                },
                deployment_handoff={
                    # The schema of the record actually being applied, not a
                    # constant: a v1 chain entry stays described as v1.
                    "schema_version": str(
                        record.get("schema_version")
                        or LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA),
                    "handoff_generation": int(
                        record["handoff_generation"]),
                    "record_digest": str(record["record_digest"]),
                    "prior_epoch_id": str(record["prior_epoch_id"]),
                    "prior_epoch_document_digest": str(
                        record["prior_epoch_document_digest"]),
                    "prior_epoch_file_sha256": str(
                        record["prior_epoch_file_sha256"]),
                },
            )
            self._persist()
            self._deployment_handoff_applied = True
            return
        same_run_restore = bool(
            self._run_instance_identity
            and isinstance(payload.get("run_instance_identity"), Mapping)
            and dict(payload["run_instance_identity"])
            == self._run_instance_identity)
        if state in ("VALID_CURRENT", "VALID_BACKUP") and same_run_restore:
            return
        prior_rollovers = int(self._state.get("rollover_count") or 0)
        prior_history = list(self._state.get("epoch_history") or [])
        prior_id = self._state.get("live_epoch_id")
        restart_observed_at = self._now()
        if isinstance(prior_id, str) and prior_id:
            self._closed_epoch_queue.append({
                "live_epoch_id": prior_id,
                "epoch_status": EPOCH_CLOSED,
                "reason": CLEAN_RESTART_EPOCH_ROLLOVER,
                "closed_at_utc": restart_observed_at,
                "epoch_start_slot": self._state.get("epoch_start_slot"),
            })
            prior_history.append({
                "live_epoch_id": prior_id,
                "epoch_status": EPOCH_CLOSED,
                "reason": CLEAN_RESTART_EPOCH_ROLLOVER,
                "closed_at_utc": restart_observed_at,
                "epoch_start_slot": self._state.get("epoch_start_slot"),
            })
            prior_rollovers += 1
        self._state = self._new_starting_state(
            rollover_count=prior_rollovers,
            history=prior_history[-_HISTORY_MAX:],
            last_break=(
                {"reason": CLEAN_RESTART_EPOCH_ROLLOVER,
                 "observed_at_utc": restart_observed_at}
                if prior_id else None),
            deployment_handoff=None,
        )
        self._persist()

    def _new_starting_state(
        self,
        *,
        rollover_count: int,
        history: List[Dict[str, Any]],
        last_break: Optional[Dict[str, Any]],
        deployment_handoff: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = self._now()
        return {
            "schema_version": LIVE_EPOCH_SCHEMA_VERSION,
            "production_mode": PRODUCTION_MODE,
            "historical_completeness_required": False,
            "historical_rpc_backfill_enabled": False,
            "historical_recovery_status": HISTORICAL_REPLAY_STATUS,
            "live_epoch_id": self._id(),
            "epoch_status": EPOCH_STARTING,
            "epoch_start_slot": None,
            "observed_confirmed_boundary_slot": None,
            "epoch_started_at_utc": now,
            "epoch_armed_at_utc": None,
            "rollover_count": int(rollover_count),
            "last_continuity_break": last_break,
            "epoch_history": list(history)[-_HISTORY_MAX:],
            "generation": self._generation,
            "durable_policy_identity": dict(self._durable_policy_identity),
            "deployment_handoff": (
                dict(deployment_handoff)
                if deployment_handoff is not None else None),
            "run_instance_identity": (
                dict(self._run_instance_identity)
                if self._run_instance_identity else None),
            "updated_at_utc": now,
        }

    @staticmethod
    def _write_atomic(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)

    def _persist(self) -> None:
        if self._integrity_failure:
            raise LiveEpochIntegrityError("EPOCH_INTEGRITY_FAILURE")
        payload = dict(self._state)
        payload["generation"] = self._generation + 1
        payload["updated_at_utc"] = self._now()
        document = {**payload, "document_digest": _digest(payload)}
        data = _canonical(document) + b"\n"
        primary_state, _ = classify_live_epoch_document(self.path)
        if primary_state == "VALID_CURRENT":
            current = self.path.read_bytes()
            self._write_atomic(self.backup_path, current)
        elif self.path.exists() and self._load_facts.get(
                "recovered_from_backup"):
            evidence = self.path.with_name(self.path.name + ".invalid")
            if not evidence.exists():
                shutil.copyfile(self.path, evidence)
        self._write_atomic(self.path, data)
        if not self.backup_path.exists():
            self._write_atomic(self.backup_path, data)
        state, verified, facts = classify_live_epoch_document_set(self.path)
        if state not in ("VALID_CURRENT", "VALID_BACKUP") \
                or int(verified.get("generation") or 0) != self._generation + 1:
            self._integrity_failure = True
            self._state["epoch_status"] = EPOCH_INTEGRITY_FAILURE
            raise LiveEpochIntegrityError("EPOCH_WRITE_READBACK_FAILED")
        self._generation = int(verified["generation"])
        self._state = verified
        self._document_state = "VALID_CURRENT"
        self._load_facts = dict(facts)

    @property
    def integrity_failure(self) -> bool:
        return self._integrity_failure

    def observe_confirmed_slot(
        self, slot: object, *, observed_at_utc: Optional[str] = None
    ) -> bool:
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            return False
        with self._lock:
            if self._integrity_failure:
                return False
            if self._state["epoch_status"] == EPOCH_HEALTHY:
                return True
            if self._state["epoch_status"] != EPOCH_STARTING:
                return False
            self._state["observed_confirmed_boundary_slot"] = int(slot)
            self._state["epoch_start_slot"] = int(slot) + 1
            self._state["epoch_status"] = EPOCH_HEALTHY
            self._state["epoch_armed_at_utc"] = (
                observed_at_utc if _valid_utc(observed_at_utc)
                else self._now())
            self._persist()
            return True

    def admit_event(self, slot: object) -> Tuple[bool, str, Optional[str]]:
        with self._lock:
            epoch_id = self._state.get("live_epoch_id")
            if self._integrity_failure:
                return False, EPOCH_INTEGRITY_FAILURE, epoch_id
            if self._state.get("epoch_status") != EPOCH_HEALTHY:
                return False, EPOCH_EVENT_PRE_ARM_REJECTED, epoch_id
            if isinstance(slot, bool) or not isinstance(slot, int):
                return False, EPOCH_EVENT_PRE_ARM_REJECTED, epoch_id
            if int(slot) < int(self._state["epoch_start_slot"]):
                return False, EPOCH_EVENT_BEFORE_START_REJECTED, epoch_id
            return True, EPOCH_EVENT_ADMITTED, epoch_id

    def rollover(self, reason: str) -> Optional[str]:
        """Close the current epoch and immediately persist a fresh unarmed one."""

        safe_reason = (
            reason if isinstance(reason, str) and reason
            and len(reason) <= 64 and reason.replace("_", "").isalnum()
            else "CONTINUITY_BREAK")
        with self._lock:
            if self._integrity_failure:
                return None
            old_id = str(self._state.get("live_epoch_id") or "")
            now = self._now()
            closed = {
                "live_epoch_id": old_id,
                "epoch_status": EPOCH_CLOSED,
                "reason": safe_reason,
                "closed_at_utc": now,
                "epoch_start_slot": self._state.get("epoch_start_slot"),
            }
            history = list(self._state.get("epoch_history") or [])
            history.append({
                **closed,
                "prior_transition": EPOCH_CONTINUITY_BROKEN,
            })
            self._closed_epoch_queue.append(dict(closed))
            self._state = self._new_starting_state(
                rollover_count=int(self._state.get("rollover_count") or 0) + 1,
                history=history[-_HISTORY_MAX:],
                last_break={"reason": safe_reason, "observed_at_utc": now},
                deployment_handoff=self._state.get("deployment_handoff"),
            )
            self._persist()
            return old_id or None

    def close(self, reason: str = "OPERATOR_SHUTDOWN") -> None:
        with self._lock:
            if self._integrity_failure:
                return
            now = self._now()
            self._state["epoch_status"] = EPOCH_CLOSED
            history = list(self._state.get("epoch_history") or [])
            history.append({
                "live_epoch_id": self._state.get("live_epoch_id"),
                "epoch_status": EPOCH_CLOSED,
                "reason": str(reason)[:64],
                "closed_at_utc": now,
                "epoch_start_slot": self._state.get("epoch_start_slot"),
            })
            self._state["epoch_history"] = history[-_HISTORY_MAX:]
            self._persist()

    def drain_closed_epochs(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = list(self._closed_epoch_queue)
            self._closed_epoch_queue.clear()
            return out

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **dict(self._state),
                "epoch_document_state": self._document_state,
                "epoch_durable": (
                    not self._integrity_failure
                    and self._document_state in (
                        "VALID_CURRENT", "VALID_BACKUP")),
                "epoch_generation": int(self._generation),
                "epoch_primary_state": self._load_facts.get("primary_state"),
                "epoch_backup_state": self._load_facts.get("backup_state"),
                "epoch_recovered_from_backup": bool(
                    self._load_facts.get("recovered_from_backup")),
                "deployment_handoff_applied": bool(
                    self._deployment_handoff_applied),
            }


__all__ = (
    "LIVE_EPOCH_SCHEMA_VERSION",
    "LIVE_EPOCH_BASENAME",
    "LIVE_EPOCH_CURSOR_BASENAME",
    "LIVE_EPOCH_BACKUP_SUFFIX",
    "LIVE_EPOCH_POLICY_IDENTITY_SCHEMA",
    "LIVE_EPOCH_RUN_IDENTITY_SCHEMA",
    "LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA",
    "LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2",
    "LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMAS",
    "LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME",
    "LIVE_EPOCH_CLOSED_ARCHIVE_DIRNAME",
    "PRODUCTION_MODE",
    "LEGACY_ALERT_POLICY_BINDING",
    "HISTORICAL_REPLAY_STATUS",
    "CLEAN_RESTART_EPOCH_ROLLOVER",
    "CLOSED_EPOCH_DEPLOYMENT_HANDOFF",
    "EPOCH_STARTING",
    "EPOCH_HEALTHY",
    "EPOCH_CONTINUITY_BROKEN",
    "EPOCH_CLOSED",
    "EPOCH_INTEGRITY_FAILURE",
    "EPOCH_STATUSES",
    "EPOCH_EVENT_PRE_ARM_REJECTED",
    "EPOCH_EVENT_BEFORE_START_REJECTED",
    "PRE_BOUNDARY_NOT_ELIGIBLE",
    "EPOCH_EVENT_ADMITTED",
    "LiveEpochIntegrityError",
    "LiveEpochManager",
    "ClosedEpochDeploymentHandoffContext",
    "ClosedEpochDeploymentHandoffVerdict",
    "classify_live_epoch_document",
    "classify_live_epoch_document_set",
    "classify_deployment_handoff_log",
    "closed_epoch_archive_path",
    "live_epoch_handoff_is_valid",
    "closed_epoch_deployment_handoff_is_valid",
    "validate_closed_epoch_deployment_handoff",
    "record_closed_epoch_deployment_handoff",
    "durable_semantic_policy_digest",
    "pre_alert_policy_semantic_digest",
    "attested_prior_deployment",
    "prior_identity_predates_alert_policy_binding",
    "build_durable_policy_identity",
    "build_run_instance_identity",
)
