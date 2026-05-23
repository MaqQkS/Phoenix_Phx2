"""Stage 28.2 restart-safe dispatch ledger operations.

This module provides the append-only JSONL ledger primitives that
let a future Stage 28.6 bounded private runner (and any other
Stage 28 caller) safely reserve a dispatch intent, record its
pre-send provenance reference, and record the terminal dispatch
result, while detecting duplicates and ambiguous resumed states
across process restarts.

Ledger contract:

  * Each ledger line is one JSON object terminated by ``\\n``.
  * Records are append-only: no deletion, no compaction, no
    in-place mutation. Replay reconstructs the latest known state
    per dedupe key by streaming the file end-to-end.
  * Records are deterministic: ``json.dumps`` is called with
    ``sort_keys=True`` and ``separators=(",", ":")`` so a given
    record always serializes to a byte-identical line.
  * Records are redaction-safe: no webhook URL, no provider
    endpoint, no API key, no bearer token, no auth header is ever
    written to a record. Caller inputs are validated against the
    Stage 28.2 dedupe-key and artifact-reference allowlists in
    ``dispatch_ledger_models``.

Lifecycle (future intended order, locked by the Stage 28.0 spec):

  1. ``reserve_dispatch_intent`` reserves a dedupe key BEFORE the
     send is attempted.
  2. ``record_pre_send`` records the pre-send provenance /
     artifact reference BEFORE the send is attempted.
  3. (the runner performs the actual private Discord send -- NOT
     part of Stage 28.2)
  4. ``record_terminal`` records the terminal dispatch result
     AFTER the send.

If a process crash leaves a dedupe key in a non-terminal state
(RESERVED or PRE_SEND_RECORDED), the next ``reserve_dispatch_intent``
call against the same key returns
``DISPATCH_DECISION_SUPPRESS_AMBIGUOUS`` (per the Stage 28.0
ambiguous-send-suppression principle).

If a dedupe key has reached any terminal state, a subsequent
``reserve_dispatch_intent`` returns
``DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL``.

Discipline:

  * No env reads. ``os.environ`` is never touched here. The
    ledger path is always a caller-supplied ``Path``.
  * No network, no HTTP, no gRPC, no Discord, no Telegram, no X /
    social, no provider client.
  * No retry / backoff / failure classification (those are Stage
    28.3a / 28.3b).
  * No transport (audited HTTP is Stage 28.4).
  * No heartbeat / health / runner (Stage 28.5 / 28.6 / 28.7).
  * No sleep / scheduling.
  * No parent-directory autocreation. The ledger writer requires
    the parent directory to already exist; this keeps Stage 28.2
    away from accidental directory creation under operator-
    supplied paths.

This module imports only stdlib (``json`` / ``pathlib`` /
``typing``) plus the Stage 28.2 models module. It does NOT
import Stage 21-27 production code, does NOT import Stage 28.1
production code, does NOT import any network / RPC / messaging /
DB / scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from PHX2.stage28.dispatch_ledger_models import (
    DEDUPE_STATE_DISPATCHED_AMBIGUOUS,
    DEDUPE_STATE_DISPATCHED_FAILED,
    DEDUPE_STATE_DISPATCHED_OK,
    DEDUPE_STATE_PRE_SEND_RECORDED,
    DEDUPE_STATE_REFUSED_PRE_SEND,
    DEDUPE_STATE_RESERVED,
    DEDUPE_NON_TERMINAL_STATES,
    DEDUPE_TERMINAL_STATES,
    DISPATCH_DECISION_PROCEED,
    DISPATCH_DECISION_REJECTED_INVALID_TRANSITION,
    DISPATCH_DECISION_SUPPRESS_AMBIGUOUS,
    DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL,
    DispatchDedupeDecision,
    DispatchDedupeKey,
    DedupeKeyState,
    FAILURE_REASON_VALUES,
    LedgerReplayState,
    RECORD_KIND_PRE_SEND,
    RECORD_KIND_RESERVE,
    RECORD_KIND_TERMINAL,
    RECORD_KIND_VALUES,
    STAGE28_2_SCHEMA_VERSION,
    Stage28_2InvalidArtifactReferenceError,
    Stage28_2InvalidDedupeKeyError,
    Stage28_2LedgerIOError,
    Stage28_2LedgerPathError,
    Stage28_2MalformedLedgerLineError,
    Stage28_2UnknownLedgerSchemaError,
    Stage28_2UnknownLedgerStateError,
    canonical_dedupe_key_serialization,
    is_artifact_reference_safe,
    is_dedupe_key_field_safe,
)


# ---------------------------------------------------------------------------
# Stage 28.2 accepted schema versions
# ---------------------------------------------------------------------------


# A tuple is used so a future Stage 28.2 schema bump can extend
# the accepted set while the existing v0 records remain replayable.
_ACCEPTED_SCHEMA_VERSIONS: tuple[str, ...] = (
    STAGE28_2_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


_LEDGER_PATH_SECRET_LIKE_SUBSTRINGS: tuple[str, ...] = (
    # URL / scheme substrings (concatenated so this source file
    # itself does not carry the literal URL prefix).
    "h" + "ttps:",
    "h" + "ttp:",
    "w" + "ss:",
    "w" + "s:",
    "://",
    # Auth / bearer substrings.
    "bearer",
    "authorization",
    "auth=",
    "token=",
    "apikey=",
    "key=",
    "secret=",
    # Webhook host fragments.
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/webhooks/",
)


def _safe_basename_or_none(path: Path) -> Optional[str]:
    """Return ``path.name`` if it passes the Stage 28.2 dedupe-key
    field allowlist, else ``None``.

    Used inside error reporting so the ledger never echoes a raw
    path that itself carries secret-looking material.
    """
    try:
        candidate = path.name
    except Exception:
        return None
    if is_dedupe_key_field_safe(candidate):
        return candidate
    if is_artifact_reference_safe(candidate):
        return candidate
    return None


def _validate_ledger_path(path: Path) -> None:
    """Validate that ``path`` is safe to use as a Stage 28.2
    ledger file.

    Rules:

      * the caller must supply an explicit ``Path``,
      * the path must not be an existing directory,
      * the path must not contain secret-looking substrings
        (URL / bearer / webhook fragments),
      * the parent directory must exist (Stage 28.2 does NOT
        auto-create parents).
    """
    if not isinstance(path, Path):
        raise Stage28_2LedgerPathError(
            reason="LEDGER_PATH_NOT_A_PATHLIB_PATH",
        )
    path_str = str(path)
    lowered = path_str.lower()
    for needle in _LEDGER_PATH_SECRET_LIKE_SUBSTRINGS:
        if needle in lowered:
            raise Stage28_2LedgerPathError(
                reason="LEDGER_PATH_SECRET_LIKE",
            )
    if path.exists() and path.is_dir():
        raise Stage28_2LedgerPathError(
            reason="LEDGER_PATH_IS_DIRECTORY",
            safe_basename=_safe_basename_or_none(path),
        )
    parent = path.parent
    if str(parent) and not parent.exists():
        raise Stage28_2LedgerPathError(
            reason="LEDGER_PARENT_DIRECTORY_MISSING",
            safe_basename=_safe_basename_or_none(path),
        )


# ---------------------------------------------------------------------------
# Record serialization
# ---------------------------------------------------------------------------


def _dedupe_key_to_dict(key: DispatchDedupeKey) -> dict:
    """Project a ``DispatchDedupeKey`` into a serialization-safe
    dict suitable for JSON record emission.
    """
    return {
        "token_mint": key.token_mint,
        "pair_quote_asset": key.pair_quote_asset,
        "event_kind": key.event_kind,
        "ping_type": key.ping_type,
        "normalized_event_id": key.normalized_event_id,
    }


def _serialize_record_dict(record: dict) -> str:
    """Serialize a record dict to a deterministic JSON line
    (terminated by ``\\n``).
    """
    return (
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    )


def _build_reserve_record_dict(key: DispatchDedupeKey) -> dict:
    return {
        "schema_version": STAGE28_2_SCHEMA_VERSION,
        "record_kind": RECORD_KIND_RESERVE,
        "dedupe_key": _dedupe_key_to_dict(key),
    }


def _build_pre_send_record_dict(
    key: DispatchDedupeKey,
    artifact_reference: str,
) -> dict:
    return {
        "schema_version": STAGE28_2_SCHEMA_VERSION,
        "record_kind": RECORD_KIND_PRE_SEND,
        "dedupe_key": _dedupe_key_to_dict(key),
        "artifact_reference": artifact_reference,
    }


def _build_terminal_record_dict(
    key: DispatchDedupeKey,
    terminal_status: str,
    failure_reason: Optional[str],
) -> dict:
    return {
        "schema_version": STAGE28_2_SCHEMA_VERSION,
        "record_kind": RECORD_KIND_TERMINAL,
        "dedupe_key": _dedupe_key_to_dict(key),
        "terminal_status": terminal_status,
        "failure_reason": failure_reason,
    }


# ---------------------------------------------------------------------------
# Append-only writer
# ---------------------------------------------------------------------------


def _append_record_line(path: Path, line: str) -> None:
    """Append one already-serialized ledger line to ``path``.

    The writer opens the file in binary append mode so existing
    content is never truncated, and writes a UTF-8-encoded bytes
    payload. OSError-like underlying failures are wrapped as
    ``Stage28_2LedgerIOError``.
    """
    payload = line.encode("utf-8")
    try:
        with path.open("ab") as handle:
            handle.write(payload)
    except OSError as exc:
        raise Stage28_2LedgerIOError(
            operation="LEDGER_APPEND",
            safe_basename=_safe_basename_or_none(path),
        ) from exc


# ---------------------------------------------------------------------------
# Record parsing (replay)
# ---------------------------------------------------------------------------


def _validate_record_dict(record: dict, line_index: int) -> None:
    """Validate that a parsed record dict carries the Stage 28.2
    locked closed-set fields. Raises a closed-set ledger error on
    any deviation.
    """
    schema_version = record.get("schema_version")
    if not isinstance(schema_version, str):
        raise Stage28_2MalformedLedgerLineError(
            line_index=line_index,
            reason="MISSING_SCHEMA_VERSION",
        )
    if schema_version not in _ACCEPTED_SCHEMA_VERSIONS:
        raise Stage28_2UnknownLedgerSchemaError(
            line_index=line_index,
            observed_length=len(schema_version),
        )

    record_kind = record.get("record_kind")
    if not isinstance(record_kind, str):
        raise Stage28_2MalformedLedgerLineError(
            line_index=line_index,
            reason="MISSING_RECORD_KIND",
        )
    if record_kind not in RECORD_KIND_VALUES:
        raise Stage28_2UnknownLedgerStateError(
            line_index=line_index,
            field_name="record_kind",
            observed_length=len(record_kind),
        )

    dedupe_key = record.get("dedupe_key")
    if not isinstance(dedupe_key, dict):
        raise Stage28_2MalformedLedgerLineError(
            line_index=line_index,
            reason="MISSING_DEDUPE_KEY",
        )

    required_key_fields = (
        "token_mint",
        "pair_quote_asset",
        "event_kind",
        "ping_type",
        "normalized_event_id",
    )
    if set(dedupe_key.keys()) != set(required_key_fields):
        raise Stage28_2MalformedLedgerLineError(
            line_index=line_index,
            reason="DEDUPE_KEY_FIELD_SET_MISMATCH",
        )
    for field_name in required_key_fields:
        value = dedupe_key[field_name]
        if not isinstance(value, str):
            raise Stage28_2MalformedLedgerLineError(
                line_index=line_index,
                reason="DEDUPE_KEY_FIELD_NOT_STR",
            )
        if not is_dedupe_key_field_safe(value):
            raise Stage28_2MalformedLedgerLineError(
                line_index=line_index,
                reason="DEDUPE_KEY_FIELD_UNSAFE",
            )

    if record_kind == RECORD_KIND_RESERVE:
        extra = set(record.keys()) - {
            "schema_version",
            "record_kind",
            "dedupe_key",
        }
        if extra:
            raise Stage28_2MalformedLedgerLineError(
                line_index=line_index,
                reason="RESERVE_RECORD_HAS_EXTRA_FIELDS",
            )
    elif record_kind == RECORD_KIND_PRE_SEND:
        if set(record.keys()) != {
            "schema_version",
            "record_kind",
            "dedupe_key",
            "artifact_reference",
        }:
            raise Stage28_2MalformedLedgerLineError(
                line_index=line_index,
                reason="PRE_SEND_RECORD_FIELD_SET_MISMATCH",
            )
        artifact_reference = record["artifact_reference"]
        if not isinstance(artifact_reference, str):
            raise Stage28_2MalformedLedgerLineError(
                line_index=line_index,
                reason="ARTIFACT_REFERENCE_NOT_STR",
            )
        if not is_artifact_reference_safe(artifact_reference):
            raise Stage28_2MalformedLedgerLineError(
                line_index=line_index,
                reason="ARTIFACT_REFERENCE_UNSAFE",
            )
    elif record_kind == RECORD_KIND_TERMINAL:
        if set(record.keys()) != {
            "schema_version",
            "record_kind",
            "dedupe_key",
            "terminal_status",
            "failure_reason",
        }:
            raise Stage28_2MalformedLedgerLineError(
                line_index=line_index,
                reason="TERMINAL_RECORD_FIELD_SET_MISMATCH",
            )
        terminal_status = record["terminal_status"]
        if not isinstance(terminal_status, str):
            raise Stage28_2MalformedLedgerLineError(
                line_index=line_index,
                reason="TERMINAL_STATUS_NOT_STR",
            )
        if terminal_status not in DEDUPE_TERMINAL_STATES:
            raise Stage28_2UnknownLedgerStateError(
                line_index=line_index,
                field_name="terminal_status",
                observed_length=len(terminal_status),
            )
        failure_reason = record["failure_reason"]
        if failure_reason is not None:
            if not isinstance(failure_reason, str):
                raise Stage28_2MalformedLedgerLineError(
                    line_index=line_index,
                    reason="FAILURE_REASON_NOT_STR_OR_NULL",
                )
            if failure_reason not in FAILURE_REASON_VALUES:
                raise Stage28_2UnknownLedgerStateError(
                    line_index=line_index,
                    field_name="failure_reason",
                    observed_length=len(failure_reason),
                )


def _parse_ledger_line(line: str, line_index: int) -> dict:
    """Parse one JSONL line and return the validated record dict."""
    # ``json.loads`` accepts the line with or without the trailing
    # newline; replay drops trailing whitespace before calling.
    stripped = line.rstrip("\n").rstrip("\r")
    if stripped == "":
        raise Stage28_2MalformedLedgerLineError(
            line_index=line_index,
            reason="EMPTY_LINE",
        )
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise Stage28_2MalformedLedgerLineError(
            line_index=line_index,
            reason="INVALID_JSON",
        ) from exc
    if not isinstance(parsed, dict):
        raise Stage28_2MalformedLedgerLineError(
            line_index=line_index,
            reason="NOT_A_JSON_OBJECT",
        )
    _validate_record_dict(parsed, line_index=line_index)
    return parsed


def _reconstruct_dedupe_key_from_record(
    record: dict,
) -> DispatchDedupeKey:
    """Reconstruct a ``DispatchDedupeKey`` from an already-validated
    record dict. Callers must ensure ``_validate_record_dict`` has
    been run on ``record`` first.
    """
    key_dict = record["dedupe_key"]
    return DispatchDedupeKey(
        token_mint=key_dict["token_mint"],
        pair_quote_asset=key_dict["pair_quote_asset"],
        event_kind=key_dict["event_kind"],
        ping_type=key_dict["ping_type"],
        normalized_event_id=key_dict["normalized_event_id"],
    )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def replay_ledger(path: Path) -> LedgerReplayState:
    """Replay the ledger at ``path`` into an immutable
    ``LedgerReplayState`` bundle.

    Behavior:

      * If ``path`` does not exist, returns an empty replay state
        (record_count = 0).
      * If ``path`` is an empty file, returns an empty replay
        state (record_count = 0).
      * If any line is malformed, carries an unknown schema
        version, carries an unknown state, or carries an
        out-of-allowlist dedupe-key / artifact-reference value,
        raises a closed-set Stage 28.2 ledger error.
      * OSError on read is wrapped as ``Stage28_2LedgerIOError``.

    The function does NOT auto-create the file or its parent
    directory.
    """
    _validate_ledger_path(path)

    if not path.exists():
        return LedgerReplayState(
            states_by_key={}, record_count=0
        )

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Stage28_2LedgerIOError(
            operation="LEDGER_READ",
            safe_basename=_safe_basename_or_none(path),
        ) from exc

    text = raw.decode("utf-8", errors="strict") if raw else ""

    states: dict[str, DedupeKeyState] = {}
    record_count = 0

    if text == "":
        return LedgerReplayState(
            states_by_key=states, record_count=record_count
        )

    lines = text.split("\n")
    # ``str.split`` on a trailing-newline-terminated file yields
    # an empty trailing element; drop it so we don't count it.
    if lines and lines[-1] == "":
        lines.pop()

    for one_based_index, line in enumerate(lines, start=1):
        record = _parse_ledger_line(line, line_index=one_based_index)
        key = _reconstruct_dedupe_key_from_record(record)
        canonical = canonical_dedupe_key_serialization(key)
        prior = states.get(canonical)
        record_kind = record["record_kind"]

        if prior is None:
            reserve_seen = record_kind == RECORD_KIND_RESERVE
            pre_send_seen = record_kind == RECORD_KIND_PRE_SEND
            terminal_seen = record_kind == RECORD_KIND_TERMINAL
            current_state, terminal_status, failure_reason = (
                _initial_state_for_record(record)
            )
            artifact_reference = (
                record["artifact_reference"]
                if record_kind == RECORD_KIND_PRE_SEND
                else None
            )
        else:
            reserve_seen = prior.reserve_seen or (
                record_kind == RECORD_KIND_RESERVE
            )
            pre_send_seen = prior.pre_send_seen or (
                record_kind == RECORD_KIND_PRE_SEND
            )
            terminal_seen = prior.terminal_seen or (
                record_kind == RECORD_KIND_TERMINAL
            )
            current_state, terminal_status, failure_reason = (
                _advance_state_for_record(prior, record)
            )
            if record_kind == RECORD_KIND_PRE_SEND:
                artifact_reference = record["artifact_reference"]
            else:
                artifact_reference = prior.artifact_reference

        states[canonical] = DedupeKeyState(
            dedupe_key=key,
            current_state=current_state,
            reserve_seen=reserve_seen,
            pre_send_seen=pre_send_seen,
            terminal_seen=terminal_seen,
            terminal_status=terminal_status,
            failure_reason=failure_reason,
            artifact_reference=artifact_reference,
        )
        record_count += 1

    return LedgerReplayState(
        states_by_key=dict(states), record_count=record_count
    )


def _initial_state_for_record(
    record: dict,
) -> tuple[str, Optional[str], Optional[str]]:
    """Return ``(current_state, terminal_status, failure_reason)``
    for the first record observed for a given dedupe key.
    """
    record_kind = record["record_kind"]
    if record_kind == RECORD_KIND_RESERVE:
        return DEDUPE_STATE_RESERVED, None, None
    if record_kind == RECORD_KIND_PRE_SEND:
        return DEDUPE_STATE_PRE_SEND_RECORDED, None, None
    # RECORD_KIND_TERMINAL.
    terminal_status = record["terminal_status"]
    return (
        terminal_status,
        terminal_status,
        record.get("failure_reason"),
    )


def _advance_state_for_record(
    prior: DedupeKeyState,
    record: dict,
) -> tuple[str, Optional[str], Optional[str]]:
    """Return ``(current_state, terminal_status, failure_reason)``
    after applying ``record`` to ``prior``.

    Append-only contract: once a key has reached a terminal state,
    later RESERVE / PRE_SEND records do NOT regress it. (A
    well-formed ledger should never write such records after
    terminal, but replay must be defensive about ordering noise.)
    """
    record_kind = record["record_kind"]

    if prior.terminal_seen:
        if record_kind == RECORD_KIND_TERMINAL:
            terminal_status = record["terminal_status"]
            return (
                terminal_status,
                terminal_status,
                record.get("failure_reason"),
            )
        # Defensive: append-only ledger should never carry RESERVE
        # / PRE_SEND after TERMINAL for the same key; replay holds
        # the terminal state to avoid silently regressing.
        return (
            prior.current_state,
            prior.terminal_status,
            prior.failure_reason,
        )

    if record_kind == RECORD_KIND_TERMINAL:
        terminal_status = record["terminal_status"]
        return (
            terminal_status,
            terminal_status,
            record.get("failure_reason"),
        )

    if record_kind == RECORD_KIND_PRE_SEND:
        return DEDUPE_STATE_PRE_SEND_RECORDED, None, None

    # RECORD_KIND_RESERVE -- the lifecycle's earliest stage; once
    # we've already advanced past it the state should not regress.
    if prior.current_state == DEDUPE_STATE_RESERVED:
        return DEDUPE_STATE_RESERVED, None, None
    return prior.current_state, prior.terminal_status, prior.failure_reason


# ---------------------------------------------------------------------------
# Dispatch decision helpers (pure, no I/O)
# ---------------------------------------------------------------------------


def classify_replay_state(
    replay: LedgerReplayState,
    key: DispatchDedupeKey,
) -> DispatchDedupeDecision:
    """Return the dispatch decision implied by the current replay
    state for ``key``, WITHOUT writing anything to the ledger.

    Pure: no I/O, no env access. The caller can use this helper
    to inspect what a reserve attempt would do without committing
    to it.
    """
    canonical = canonical_dedupe_key_serialization(key)
    prior = replay.states_by_key.get(canonical)
    if prior is None:
        return DispatchDedupeDecision(
            decision=DISPATCH_DECISION_PROCEED,
            current_state=None,
            dedupe_key=key,
        )
    if prior.current_state in DEDUPE_TERMINAL_STATES:
        return DispatchDedupeDecision(
            decision=DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL,
            current_state=prior.current_state,
            dedupe_key=key,
        )
    if prior.current_state in DEDUPE_NON_TERMINAL_STATES:
        return DispatchDedupeDecision(
            decision=DISPATCH_DECISION_SUPPRESS_AMBIGUOUS,
            current_state=prior.current_state,
            dedupe_key=key,
        )
    # Defensive: every reconstructed state should be in either
    # subset. If somehow not, classify as ambiguous to fail closed.
    return DispatchDedupeDecision(
        decision=DISPATCH_DECISION_SUPPRESS_AMBIGUOUS,
        current_state=prior.current_state,
        dedupe_key=key,
    )


# ---------------------------------------------------------------------------
# Public ledger operations
# ---------------------------------------------------------------------------


def reserve_dispatch_intent(
    *,
    ledger_path: Path,
    dedupe_key: DispatchDedupeKey,
    replay: LedgerReplayState,
) -> DispatchDedupeDecision:
    """Reserve a dispatch intent for ``dedupe_key`` against
    ``ledger_path``.

    Behavior:

      * If ``replay`` shows ``dedupe_key`` already in a terminal
        state, returns
        ``DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL`` and does
        NOT write to the ledger.
      * If ``replay`` shows ``dedupe_key`` in a non-terminal
        state (RESERVED / PRE_SEND_RECORDED), returns
        ``DISPATCH_DECISION_SUPPRESS_AMBIGUOUS`` and does NOT
        write to the ledger.
      * Otherwise appends one RESERVE record and returns
        ``DISPATCH_DECISION_PROCEED``.

    The caller is expected to refresh its ``replay`` after a
    successful PROCEED before issuing further operations against
    the same key; ``replay_ledger`` is cheap enough for that.
    """
    _validate_dedupe_key(dedupe_key)
    _validate_ledger_path(ledger_path)

    decision = classify_replay_state(replay, dedupe_key)
    if decision.decision != DISPATCH_DECISION_PROCEED:
        return decision

    record_dict = _build_reserve_record_dict(dedupe_key)
    line = _serialize_record_dict(record_dict)
    _append_record_line(ledger_path, line)
    return DispatchDedupeDecision(
        decision=DISPATCH_DECISION_PROCEED,
        current_state=DEDUPE_STATE_RESERVED,
        dedupe_key=dedupe_key,
    )


def record_pre_send(
    *,
    ledger_path: Path,
    dedupe_key: DispatchDedupeKey,
    artifact_reference: str,
    replay: LedgerReplayState,
) -> DispatchDedupeDecision:
    """Record the pre-send provenance / artifact reference for an
    already-reserved dedupe key.

    Behavior:

      * If ``replay`` shows ``dedupe_key`` already in a terminal
        state, returns
        ``DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL`` and does
        NOT write.
      * If ``replay`` shows ``dedupe_key`` already at
        ``PRE_SEND_RECORDED``, returns
        ``DISPATCH_DECISION_SUPPRESS_AMBIGUOUS`` and does NOT
        write (this would be a duplicate pre-send for the same
        intent, which is itself an ambiguous case).
      * If ``replay`` shows ``dedupe_key`` at ``RESERVED``,
        appends one PRE_SEND record and returns
        ``DISPATCH_DECISION_PROCEED``.
      * If ``replay`` does NOT show ``dedupe_key`` at all (no
        reserve was ever observed), returns
        ``DISPATCH_DECISION_REJECTED_INVALID_TRANSITION`` and does
        NOT write. The Stage 28.0 spec lock pins
        reserve-before-pre-send.
    """
    _validate_dedupe_key(dedupe_key)
    if not is_artifact_reference_safe(artifact_reference):
        raise Stage28_2InvalidArtifactReferenceError(
            reason="ARTIFACT_REFERENCE_UNSAFE",
        )
    _validate_ledger_path(ledger_path)

    canonical = canonical_dedupe_key_serialization(dedupe_key)
    prior = replay.states_by_key.get(canonical)

    if prior is None:
        return DispatchDedupeDecision(
            decision=DISPATCH_DECISION_REJECTED_INVALID_TRANSITION,
            current_state=None,
            dedupe_key=dedupe_key,
        )
    if prior.current_state in DEDUPE_TERMINAL_STATES:
        return DispatchDedupeDecision(
            decision=DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL,
            current_state=prior.current_state,
            dedupe_key=dedupe_key,
        )
    if prior.current_state == DEDUPE_STATE_PRE_SEND_RECORDED:
        return DispatchDedupeDecision(
            decision=DISPATCH_DECISION_SUPPRESS_AMBIGUOUS,
            current_state=prior.current_state,
            dedupe_key=dedupe_key,
        )
    if prior.current_state != DEDUPE_STATE_RESERVED:
        return DispatchDedupeDecision(
            decision=DISPATCH_DECISION_REJECTED_INVALID_TRANSITION,
            current_state=prior.current_state,
            dedupe_key=dedupe_key,
        )

    record_dict = _build_pre_send_record_dict(
        dedupe_key, artifact_reference
    )
    line = _serialize_record_dict(record_dict)
    _append_record_line(ledger_path, line)
    return DispatchDedupeDecision(
        decision=DISPATCH_DECISION_PROCEED,
        current_state=DEDUPE_STATE_PRE_SEND_RECORDED,
        dedupe_key=dedupe_key,
    )


def record_terminal(
    *,
    ledger_path: Path,
    dedupe_key: DispatchDedupeKey,
    terminal_status: str,
    replay: LedgerReplayState,
    failure_reason: Optional[str] = None,
) -> DispatchDedupeDecision:
    """Record the terminal dispatch result for a dedupe key.

    ``terminal_status`` must be one of ``DEDUPE_TERMINAL_STATES``.
    ``failure_reason`` must be ``None`` or in
    ``FAILURE_REASON_VALUES``.

    Behavior:

      * If ``replay`` shows ``dedupe_key`` already terminal,
        returns ``DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL``
        and does NOT write.
      * Otherwise appends one TERMINAL record and returns
        ``DISPATCH_DECISION_PROCEED``.

    Note: a terminal record may legitimately follow a RESERVE
    without an intervening PRE_SEND (e.g. ``REFUSED_PRE_SEND`` when
    the runner refused to send because the pre-send artifact
    write failed). Stage 28.2 does not enforce a pre-send-before-
    terminal transition.
    """
    _validate_dedupe_key(dedupe_key)
    if terminal_status not in DEDUPE_TERMINAL_STATES:
        raise Stage28_2UnknownLedgerStateError(
            line_index=0,
            field_name="terminal_status",
            observed_length=(
                len(terminal_status)
                if isinstance(terminal_status, str)
                else -1
            ),
        )
    if failure_reason is not None and (
        failure_reason not in FAILURE_REASON_VALUES
    ):
        raise Stage28_2UnknownLedgerStateError(
            line_index=0,
            field_name="failure_reason",
            observed_length=(
                len(failure_reason)
                if isinstance(failure_reason, str)
                else -1
            ),
        )
    _validate_ledger_path(ledger_path)

    canonical = canonical_dedupe_key_serialization(dedupe_key)
    prior = replay.states_by_key.get(canonical)

    if prior is not None and prior.current_state in DEDUPE_TERMINAL_STATES:
        return DispatchDedupeDecision(
            decision=DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL,
            current_state=prior.current_state,
            dedupe_key=dedupe_key,
        )

    record_dict = _build_terminal_record_dict(
        dedupe_key, terminal_status, failure_reason
    )
    line = _serialize_record_dict(record_dict)
    _append_record_line(ledger_path, line)
    return DispatchDedupeDecision(
        decision=DISPATCH_DECISION_PROCEED,
        current_state=terminal_status,
        dedupe_key=dedupe_key,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_dedupe_key(key: DispatchDedupeKey) -> None:
    """Validate that a caller-supplied ``DispatchDedupeKey``
    carries safe values. (``build_dispatch_dedupe_key`` already
    enforces this at construction, but a caller can bypass that
    by constructing the NamedTuple directly; the ledger layer
    rejects unsafe values defensively before writing.)
    """
    if not isinstance(key, DispatchDedupeKey):
        raise Stage28_2InvalidDedupeKeyError(
            field_name="dedupe_key",
            reason="DEDUPE_KEY_NOT_NAMED_TUPLE",
        )
    pairs: tuple[tuple[str, Any], ...] = (
        ("token_mint", key.token_mint),
        ("pair_quote_asset", key.pair_quote_asset),
        ("event_kind", key.event_kind),
        ("ping_type", key.ping_type),
        ("normalized_event_id", key.normalized_event_id),
    )
    for field_name, value in pairs:
        if not is_dedupe_key_field_safe(value):
            raise Stage28_2InvalidDedupeKeyError(
                field_name=field_name,
                reason="DEDUPE_KEY_FIELD_UNSAFE",
            )


def lookup_state(
    replay: LedgerReplayState,
    key: DispatchDedupeKey,
) -> Optional[DedupeKeyState]:
    """Return the reconstructed ``DedupeKeyState`` for ``key`` if
    present in ``replay``, else ``None``. Pure helper.
    """
    canonical = canonical_dedupe_key_serialization(key)
    state = replay.states_by_key.get(canonical)
    return state


__all__ = (
    "replay_ledger",
    "classify_replay_state",
    "reserve_dispatch_intent",
    "record_pre_send",
    "record_terminal",
    "lookup_state",
)
