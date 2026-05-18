"""Stage 22 ingest-hardening contracts and models (foundation only at 22.1).

This module ships the typed ``NamedTuple`` records and the
fakeable ``Protocol`` contracts that every Stage 22.2+
implementation must satisfy. No runtime behavior is implemented
here -- this is the contract surface only.

Records:

  * ``ProviderFetchOutcome``  -- per-attempt provider fetch result
  * ``ProviderFailureRecord`` -- audit-safe provider failure record
  * ``MalformedEventRecord``  -- audit-safe per-event decode-failure record
  * ``IngestEventKey``        -- composite dedupe key
  * ``IngestEventEnvelope``   -- normalized event + ingest metadata
  * ``DedupeOutcome``         -- ledger check outcome
  * ``RetryCap``              -- retry attempt cap
  * ``RetryDecision``         -- retry decision token + provenance
  * ``Stage22IngestResult``   -- top-level Stage 22 ingest run summary

Protocols:

  * ``DedupeLedger``      -- check_and_record + mark_dispatched
  * ``RawCaptureWriter``  -- capture + capture_malformed + capture_provider_failure

Field-shape invariants (locked at 22.1):

  * No record carries any field named ``api_key``, ``webhook_url``,
    ``rpc_url``, ``raw_response_body``, ``exception_message``,
    ``exception_repr``, ``headers``, ``authorization``, ``bearer``,
    ``password``, ``secret``, or ``credential``. This is enforced
    by ``test_no_secret_leaks.py``.
  * ``ProviderFetchOutcome.responses`` is a tuple of
    *adapter-shaped sanitized* mappings: no raw bytes, no raw
    response bodies, no headers, no auth fields, no URLs, and no
    raw exception material. Deep redaction enforcement is a
    Stage 22.2+ concern; the contract here defines the seam.
  * ``ProviderFailureRecord.upstream_error_type`` is a sanitized
    category token from ``UPSTREAM_ERROR_TYPES``, NOT a raw
    exception class name or message.
  * ``MalformedEventRecord.provider_event_id`` may be the empty
    string when the envelope is too malformed to extract it;
    ``raw_event_hash`` is always non-empty (the canonical
    correlation key).
  * ``IngestEventKey`` includes ``event_id`` so the future
    dedupe ledger keys primarily on the Stage 21-derived stable
    id, with ``provider_event_id`` and ``raw_event_hash`` as
    audit / tamper-detection fields.

This module does NOT:

  * import any network / RPC / messaging / DB / scheduler library;
  * import the Stage 21 fake-path modules, the Stage 21.3B Helius
    adapter, the Stage 21.3C Discord transport, the Stage 21.4
    private smoke runner, the Stage 21 ``config`` / env-read
    seam, or the Stage 21.3A live-readiness boundary;
  * read ``os.environ`` / ``os.getenv``;
  * perform any I/O on import.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, Protocol

from PHX2.stage21.normalized_events import NormalizedLiveEvent


# ---------------------------------------------------------------------------
# ProviderFetchOutcome
# ---------------------------------------------------------------------------


class ProviderFetchOutcome(NamedTuple):
    """Per-attempt provider fetch outcome (adapter-side contract).

    Fields:

      * ``ok``                     -- True iff the adapter classified
                                      the fetch as successful. False
                                      on any failure surface.
      * ``responses``              -- Tuple of adapter-shaped sanitized
                                      response envelope mappings. Each
                                      mapping is the adapter's structured
                                      view of one upstream response (no
                                      raw bytes, no headers, no URLs, no
                                      auth fields, no exception material).
                                      Empty tuple when ``ok`` is False.
      * ``status_class``           -- One of ``STATUS_CLASSES``. Required;
                                      ``success`` when ``ok`` is True,
                                      otherwise the classifier-input
                                      category.
      * ``upstream_error_type``    -- One of ``UPSTREAM_ERROR_TYPES``.
                                      Empty string (``""``) when ``ok``
                                      is True; otherwise the sanitized
                                      adapter-mapped category. NEVER a
                                      raw ``type(exc).__name__`` or
                                      exception message.
      * ``provider_attempt_index`` -- 0-based attempt index inside the
                                      enclosing fetch loop. The future
                                      bounded runner increments this
                                      across retries.

    The ``failure_label`` is deliberately NOT a field on this
    record. The Stage 22 classifier (``failure_classification``
    module) is the single source of truth for the closed-set
    label; duplicating it here would couple the outcome shape to
    the classifier and create two competing label values.
    """

    ok: bool
    responses: tuple[Mapping[str, object], ...]
    status_class: str
    upstream_error_type: str
    provider_attempt_index: int


# ---------------------------------------------------------------------------
# ProviderFailureRecord
# ---------------------------------------------------------------------------


class ProviderFailureRecord(NamedTuple):
    """Audit-safe record of a single provider failure.

    Stage 22.2+ capture writers persist instances of this record
    to provide an audit trail of every failed fetch attempt.
    Every field is a closed-set token or a short non-secret
    string -- no raw exception material, no URLs, no API keys.

    Fields:

      * ``provider_id``            -- short non-secret operator label
                                      identifying the producing provider
                                      (e.g. ``"helius"``). Matches the
                                      Stage 21.3A readiness-gate
                                      ``provider_id`` vocabulary.
      * ``failure_label``          -- one of ``PROVIDER_FAILURE_LABELS``.
      * ``status_class``           -- one of ``STATUS_CLASSES``.
      * ``upstream_error_type``    -- one of ``UPSTREAM_ERROR_TYPES``.
      * ``provider_attempt_index`` -- 0-based attempt index.
      * ``observed_at_utc``        -- ISO-8601 UTC string. The caller is
                                      responsible for sourcing this from
                                      an injected clock; the record is
                                      a pure value type and does NOT
                                      derive the timestamp itself.
    """

    provider_id: str
    failure_label: str
    status_class: str
    upstream_error_type: str
    provider_attempt_index: int
    observed_at_utc: str


# ---------------------------------------------------------------------------
# MalformedEventRecord
# ---------------------------------------------------------------------------


class MalformedEventRecord(NamedTuple):
    """Audit-safe record of a single per-event decode failure.

    Stage 22.2+ capture writers persist instances of this record
    to provide a quarantine trail of every envelope that failed
    the Stage 21.3A ``decode_provider_event`` boundary. Every
    field is a closed-set token or a short non-secret string.

    Fields:

      * ``provider_id``        -- short non-secret operator label
                                  (e.g. ``"helius"``).
      * ``provider_event_id``  -- caller-supplied id from the envelope.
                                  May be the empty string when the
                                  envelope is too malformed to extract
                                  the id; ``raw_event_hash`` remains the
                                  canonical correlation key in that case.
      * ``reason``             -- one of ``MALFORMED_EVENT_REASONS``.
      * ``failed_at_utc``      -- ISO-8601 UTC string, caller-supplied.
      * ``raw_event_hash``     -- sha256 hex of the canonical envelope
                                  encoding. Always non-empty. The future
                                  decode wrapper derives this exactly
                                  once per envelope; the record stores
                                  the result.
    """

    provider_id: str
    provider_event_id: str
    reason: str
    failed_at_utc: str
    raw_event_hash: str


# ---------------------------------------------------------------------------
# IngestEventKey
# ---------------------------------------------------------------------------


class IngestEventKey(NamedTuple):
    """Composite key the future ``DedupeLedger`` uses to identify an event.

    Stage 22.1 locks the field order at:

      * ``provider_id``        -- which provider produced the event.
      * ``chain``              -- which chain (e.g. ``solana_mainnet``).
      * ``event_id``           -- the Stage 21-derived stable normalized
                                  event id (``"evt_<24 hex>"``). PRIMARY
                                  dedupe axis: identical events from the
                                  same provider on the same chain produce
                                  identical ``event_id`` values.
      * ``provider_event_id``  -- caller-supplied id from the envelope.
                                  AUDIT / correlation field.
      * ``raw_event_hash``     -- sha256 hex of the canonical envelope.
                                  TAMPER-DETECTION field: catches
                                  "same id, different content" drift.

    The future ledger MUST treat the full tuple as the unique
    key, not just ``event_id``. The composite shape lets a
    ledger detect the rare but important case where a malicious
    or buggy provider re-uses an event_id with mutated content.
    """

    provider_id: str
    chain: str
    event_id: str
    provider_event_id: str
    raw_event_hash: str


# ---------------------------------------------------------------------------
# IngestEventEnvelope
# ---------------------------------------------------------------------------


class IngestEventEnvelope(NamedTuple):
    """Stage 21 ``NormalizedLiveEvent`` wrapped with Stage 22 ingest metadata.

    Fields:

      * ``event``                  -- the Stage 21-owned normalized event
                                      (imported from
                                      ``PHX2.stage21.normalized_events``).
                                      Stage 22.1 binds to the Stage 21
                                      shape; coordinated drift requires
                                      a cross-stage bump.
      * ``ingest_key``             -- the Stage 22 ``IngestEventKey``
                                      derived from the event plus the
                                      ``provider_id`` / chain
                                      enrichment.
      * ``received_at_utc``        -- ISO-8601 UTC string, caller-supplied
                                      from an injected clock. Marks the
                                      moment the envelope entered the
                                      Stage 22 ingest seam (post-decode,
                                      pre-dedupe).
      * ``provider_attempt_index`` -- 0-based attempt index that produced
                                      this envelope. Preserved so the
                                      capture writer can correlate good
                                      events with the failure record
                                      surface across retries.
    """

    event: NormalizedLiveEvent
    ingest_key: IngestEventKey
    received_at_utc: str
    provider_attempt_index: int


# ---------------------------------------------------------------------------
# DedupeOutcome
# ---------------------------------------------------------------------------


class DedupeOutcome(NamedTuple):
    """Outcome of a single ``DedupeLedger.check_and_record`` call.

    Fields:

      * ``outcome``     -- one of ``DEDUPE_OUTCOMES``.
      * ``ingest_key``  -- echo of the ``IngestEventKey`` checked. The
                           caller can match the outcome back to the
                           requesting envelope without holding extra
                           state.
    """

    outcome: str
    ingest_key: IngestEventKey


# ---------------------------------------------------------------------------
# RetryCap
# ---------------------------------------------------------------------------


class RetryCap(NamedTuple):
    """Locked retry attempt cap.

    Stage 22.1 keeps the shape minimal: a single positive
    ``max_attempts`` integer. Per-failure-label caps and explicit
    backoff schedules are Stage 22.2+ extensions; they can land
    additively without breaking this record's binary layout.
    """

    max_attempts: int


# ---------------------------------------------------------------------------
# RetryDecision
# ---------------------------------------------------------------------------


class RetryDecision(NamedTuple):
    """Retry decision plus the failure provenance that produced it.

    Fields:

      * ``decision``       -- one of ``RETRY_DECISIONS``.
      * ``failure_label``  -- one of ``PROVIDER_FAILURE_LABELS``. The
                              label the classifier emitted for the
                              attempt that produced this decision.
      * ``attempt_index``  -- 0-based attempt index. Lets the future
                              retry policy reason about cap interaction
                              ("attempt 2 of 3 -> retry"; "attempt 3 of
                              3 -> max_attempts_exhausted").
    """

    decision: str
    failure_label: str
    attempt_index: int


# ---------------------------------------------------------------------------
# Stage22IngestResult
# ---------------------------------------------------------------------------


class Stage22IngestResult(NamedTuple):
    """Top-level Stage 22 ingest run summary.

    Stage 22.1 ships only the record shape; no runner constructs
    instances of it. The future bounded runner returns one
    ``Stage22IngestResult`` per ``run_one_ingest_pass`` (or
    equivalent) invocation.

    Fields:

      * ``outcome``                  -- one of ``INGEST_RUNNER_OUTCOMES``.
      * ``events_received``          -- total envelopes seen from the
                                        provider across all attempts.
      * ``events_normalized``        -- envelopes that passed decode.
      * ``events_malformed``         -- envelopes that failed decode
                                        (quarantined).
      * ``events_new``               -- envelopes the ledger reported as
                                        ``new``.
      * ``events_dispatched``        -- envelopes the transport accepted
                                        (``TransportResult.dispatched``
                                        was True).
      * ``events_transport_refused`` -- envelopes the transport returned
                                        with ``dispatched=False``.
      * ``provider_attempts``        -- total provider fetch attempts.
      * ``last_failure_label``       -- last classified failure label;
                                        empty string when no provider
                                        failure occurred.
      * ``provider_id``              -- which provider this run targeted.
    """

    outcome: str
    events_received: int
    events_normalized: int
    events_malformed: int
    events_new: int
    events_dispatched: int
    events_transport_refused: int
    provider_attempts: int
    last_failure_label: str
    provider_id: str


# ---------------------------------------------------------------------------
# DedupeLedger Protocol
# ---------------------------------------------------------------------------


class DedupeLedger(Protocol):
    """Stage 22 dedupe ledger contract (Protocol; no implementation in 22.1).

    Implementations supply two methods. Tests construct fakes by
    writing a simple class that matches the Protocol -- no
    inheritance required, no DB / file system / network library
    required.

    Contract semantics:

      * ``check_and_record`` MUST be atomic: a successful "this is
        a new key" outcome implies the ledger has already recorded
        the key in its persistent state. The future implementation
        is responsible for race-safety; the Protocol does not pin
        the strategy (SQLite ``INSERT ... ON CONFLICT``, file-lock,
        single-writer JSONL, etc.).
      * ``mark_dispatched`` MUST be idempotent: calling it twice
        with the same key is a no-op on the second call.
      * The ``ledger_unavailable`` outcome is the soft-fail token
        for ``check_and_record``. Hard contract violations (e.g.
        ``mark_dispatched`` for an unknown key) raise
        ``Stage22LedgerContractError`` from the future
        implementation.
    """

    def check_and_record(
        self,
        *,
        key: IngestEventKey,
    ) -> DedupeOutcome: ...

    def mark_dispatched(
        self,
        *,
        key: IngestEventKey,
    ) -> None: ...


# ---------------------------------------------------------------------------
# RawCaptureWriter Protocol
# ---------------------------------------------------------------------------


class RawCaptureWriter(Protocol):
    """Stage 22 raw-capture writer contract (Protocol; no implementation in 22.1).

    Implementations supply three methods, one per record family.
    Tests construct fakes by writing a simple class that matches
    the Protocol -- no JSONL / file system / DB library required.

    Contract semantics:

      * Each method MUST be durable on success: when the call
        returns, the record is persisted (or queued in a manner
        the implementation explicitly documents as durable).
      * Each method MAY raise ``Stage22CaptureContractError`` on
        a hard contract violation (record shape mismatch, target
        path invalid, durability assertion failure). Transient
        I/O failures are the implementation's concern; the
        Protocol does not pin a retry semantics.
      * The capture writer MUST NOT log / persist / emit any
        secret material. Each record family is designed to be
        secret-free by construction; the writer is the second
        line of defense against accidental leakage and MAY
        re-validate inputs before writing.
    """

    def capture(
        self,
        *,
        envelope: IngestEventEnvelope,
    ) -> None: ...

    def capture_malformed(
        self,
        *,
        record: MalformedEventRecord,
    ) -> None: ...

    def capture_provider_failure(
        self,
        *,
        record: ProviderFailureRecord,
    ) -> None: ...


__all__ = [
    "DedupeLedger",
    "DedupeOutcome",
    "IngestEventEnvelope",
    "IngestEventKey",
    "MalformedEventRecord",
    "ProviderFailureRecord",
    "ProviderFetchOutcome",
    "RawCaptureWriter",
    "RetryCap",
    "RetryDecision",
    "Stage22IngestResult",
]
