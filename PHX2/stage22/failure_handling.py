"""Stage 22.4 provider failure + malformed event handling.

Pure batch isolation helper that consumes a per-attempt
``ProviderFetchOutcome`` plus injected decode and classify
callables and returns a deterministic
``Stage22BatchHandlingResult``. Audit-safe records are written
through a caller-supplied ``RawCaptureWriter``.

The helper isolates three failure modes:

  * A failed fetch (``fetch_outcome.ok`` is False): one
    ``ProviderFailureRecord`` is captured; no decode is
    attempted. The result outcome is ``provider_failed``.
  * A successful fetch with zero events: no captures occur.
    The result outcome is ``provider_returned_zero``.
  * A successful fetch with one or more events: each event is
    decoded independently. A bad event is captured as a
    ``MalformedEventRecord`` and does not abort later good
    events in the same batch.

Outcome rules for the success path:

  * zero responses              -> ``provider_returned_zero``
  * all responses decode well   -> ``ok``
  * some good + some malformed  -> ``ok``
  * all responses malformed     -> ``all_malformed``

Capture-writer failures are FATAL: any
``Stage22CaptureContractError`` raised by the writer
propagates immediately. No further events in the batch are
processed and no result object is returned. Records captured
before the failure point remain in the writer's state.

The malformed-event ``raw_event_hash`` is derived
deterministically from a safe shallow projection of the raw
payload (canonical sorted-key JSON, strict ``allow_nan=False``,
sha256 hex). The helper NEVER trusts a ``raw_event_hash``
field supplied by the malformed payload itself: a malformed
payload is untrusted and lifting an attacker-supplied value
would create an integrity hole. If the payload cannot be
safely canonicalised (bytes / custom objects / non-string
mapping keys / non-finite floats / depth overflow), the helper
falls back to a deterministic structural projection of
``(provider_id, provider_attempt_index, batch_index)``.

The malformed-event ``provider_event_id`` is lifted from the
raw payload ONLY when it is a safe non-empty string: bounded
length, free of forbidden URL substrings, free of forbidden
secret-bearing substrings, free of long hex / long
token-shape runs. Any unsafe value becomes the empty string;
the canonical correlation key in that case is the derived
``raw_event_hash``.

Stage 22.4 is NOT a runner. The helper performs no retry,
no reconnect, no sleep, no transport send, no dedupe ledger
call, no readiness check, no filter / ATH / migration /
monetization / X / Telegram / Jito / Axiom decision.

This module imports only standard-library helpers
(``hashlib`` / ``json`` / ``collections.abc`` / ``typing``)
plus the Stage 22 contracts and the Stage 22 classifier. It
does NOT import ``PHX2.stage21`` directly; the Stage 21
decoder reaches this seam only via the caller-supplied
``decode_event_fn`` callable, and the Stage 21
``NormalizedLiveEvent`` type reaches this seam transitively
through ``PHX2.stage22.ingest_contracts``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Callable, NamedTuple

from PHX2.stage22.constants import (
    CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS,
    CAPTURE_FORBIDDEN_URL_SUBSTRINGS,
    CAPTURE_LONG_HEX_RUN_MIN_LEN,
    CAPTURE_LONG_TOKENISH_MIN_LEN,
    CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN,
    INGEST_OUTCOME_ALL_MALFORMED,
    INGEST_OUTCOME_OK,
    INGEST_OUTCOME_PROVIDER_FAILED,
    INGEST_OUTCOME_PROVIDER_RETURNED_ZERO,
    MALFORMED_EVENT_REASONS,
    MALFORMED_REASON_UNEXPECTED_ERROR,
    STATUS_CLASS_SUCCESS,
)
from PHX2.stage22.errors import Stage22BatchHandlingContractError
from PHX2.stage22.failure_classification import classify_failure
from PHX2.stage22.ingest_contracts import (
    IngestEventEnvelope,
    IngestEventKey,
    MalformedEventRecord,
    NormalizedLiveEvent,
    ProviderFailureRecord,
    ProviderFetchOutcome,
    RawCaptureWriter,
)


# ---------------------------------------------------------------------------
# Stage22BatchHandlingResult -- module-local NamedTuple
# ---------------------------------------------------------------------------


class Stage22BatchHandlingResult(NamedTuple):
    """Stage 22.4 batch-handling outcome record.

    Module-local NamedTuple. Stage22IngestResult (the top-level
    Stage 22.1 result shape) carries dedupe and transport
    counters that the Stage 22.4 isolation layer does not own
    yet; Stage 22.5 will lift this record into the Stage 22.1
    runner-result shape.

    Fields:

      * ``outcome``                 -- one of
                                      ``INGEST_RUNNER_OUTCOMES``
                                      from the subset
                                      ``{ok, provider_failed,
                                      provider_returned_zero,
                                      all_malformed}``.
      * ``provider_id``             -- echo of the caller-supplied
                                      provider id.
      * ``chain``                   -- echo of the caller-supplied
                                      chain.
      * ``provider_attempt_index``  -- echo of
                                      ``fetch_outcome.provider_attempt_index``.
      * ``events_received``         -- ``len(fetch_outcome.responses)``.
      * ``events_normalized``       -- successful per-event decode count.
      * ``events_malformed``        -- per-event decode failure count.
      * ``provider_failures``       -- ``1`` when
                                      ``outcome == provider_failed``,
                                      ``0`` otherwise.
      * ``last_failure_label``      -- classified failure label when
                                      ``provider_failures > 0``,
                                      empty string otherwise.
      * ``envelopes``               -- successfully-decoded
                                      ``IngestEventEnvelope`` tuple
                                      in input order.
    """

    outcome: str
    provider_id: str
    chain: str
    provider_attempt_index: int
    events_received: int
    events_normalized: int
    events_malformed: int
    provider_failures: int
    last_failure_label: str
    envelopes: tuple[IngestEventEnvelope, ...]


# ---------------------------------------------------------------------------
# Module-private constants
# ---------------------------------------------------------------------------


# Mixed-case hex alphabet for the long-hex-run detector. The
# 0-9 / a-f / A-F characters cover the realistic shapes for
# sha256 / md5 / random hex tokens.
_HEX_CHARS: str = "0123456789abcdefABCDEF"


# Token-shape characters beyond ``isalnum`` that still belong
# to a credential-shape run: ``+`` / ``=`` / ``_`` / ``-``.
# ``/`` is deliberately excluded so that legitimate file-path
# strings inside docstrings or constants do not look like
# tokens to the runtime sanitiser.
_TOKEN_SHAPE_EXTRA_CHARS: str = "+=_-"


# Recursion depth cap for the safe-shallow projection. The
# helper never recurses past this depth; payloads deeper than
# the cap fall back to the deterministic structural hash.
_HASH_DEPTH_CAP: int = 8


# ---------------------------------------------------------------------------
# Long-token leak shape detectors
# ---------------------------------------------------------------------------


def _looks_like_token_payload(s: str) -> bool:
    """Return True iff s has the mixed-content shape of a secret
    token: at least one ASCII letter, at least one digit, and
    alphanumeric density >= 0.8.
    """
    if s == "":
        return False
    has_letter = False
    has_digit = False
    alphanumeric = 0
    for ch in s:
        if ch.isalpha():
            has_letter = True
        if ch.isdigit():
            has_digit = True
        if ch.isalnum():
            alphanumeric += 1
    if not (has_letter and has_digit):
        return False
    return alphanumeric / len(s) >= 0.8


def _has_long_hex_run(s: str) -> bool:
    """Return True iff s contains a run of >= CAPTURE_LONG_HEX_RUN_MIN_LEN
    mixed-case hex characters.
    """
    run = 0
    for ch in s:
        if ch in _HEX_CHARS:
            run += 1
            if run >= CAPTURE_LONG_HEX_RUN_MIN_LEN:
                return True
        else:
            run = 0
    return False


def _has_long_tokenish_run(s: str) -> bool:
    """Return True iff s contains a maximal run of token-shape
    characters of length >= CAPTURE_LONG_TOKENISH_MIN_LEN that
    passes the mixed-content density heuristic.
    """
    candidate = ""
    for ch in s:
        if ch.isalnum() or ch in _TOKEN_SHAPE_EXTRA_CHARS:
            candidate += ch
        else:
            if (
                len(candidate) >= CAPTURE_LONG_TOKENISH_MIN_LEN
                and _looks_like_token_payload(candidate)
            ):
                return True
            candidate = ""
    if (
        len(candidate) >= CAPTURE_LONG_TOKENISH_MIN_LEN
        and _looks_like_token_payload(candidate)
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Safe provider_event_id extraction
# ---------------------------------------------------------------------------


def _is_utf8_safe_string(value: str) -> bool:
    """Return True iff ``value`` can be losslessly encoded as UTF-8.

    Lone surrogates (e.g. ``"\\ud800"``) round-trip through
    Python's str but raise ``UnicodeEncodeError`` on the strict
    UTF-8 codec. Such strings cannot be safely stored in a
    capture record, serialised to JSONL, or echoed in any
    audit channel that assumes UTF-8 on the wire. The helper
    is the second line of defense for caller-supplied string
    payload fields the Stage 22.4 batch helper lifts into a
    ``MalformedEventRecord``.
    """
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _extract_safe_provider_event_id(raw_payload: object) -> str:
    """Return the raw payload's provider_event_id if it is a safe
    non-empty string; otherwise return the empty string.

    Safe means:

      * The payload is a Mapping with a string-keyed entry
        ``provider_event_id``.
      * The value is a string of length
        <= ``CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN``.
      * The value is losslessly UTF-8 encodable (no lone
        surrogates or other codec-hostile content; see
        ``_is_utf8_safe_string``).
      * The value contains no entry from
        ``CAPTURE_FORBIDDEN_URL_SUBSTRINGS``
        (case-insensitive).
      * The value contains no entry from
        ``CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS``
        (case-insensitive).
      * The value contains no long hex run
        (>= ``CAPTURE_LONG_HEX_RUN_MIN_LEN`` hex chars).
      * The value contains no long token-shape run
        (>= ``CAPTURE_LONG_TOKENISH_MIN_LEN`` and mixed
        alphanumeric content).

    The helper NEVER raises on extraction failure: every
    rejection path returns the empty string. The canonical
    correlation key for the captured record in that case is
    the derived ``raw_event_hash``.
    """
    if not isinstance(raw_payload, Mapping):
        return ""
    value = raw_payload.get("provider_event_id", None)
    if not isinstance(value, str):
        return ""
    if value == "":
        return ""
    if len(value) > CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN:
        return ""
    if not _is_utf8_safe_string(value):
        return ""
    lowered = value.lower()
    for needle in CAPTURE_FORBIDDEN_URL_SUBSTRINGS:
        if needle in lowered:
            return ""
    for needle in CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS:
        if needle in lowered:
            return ""
    if _has_long_hex_run(value):
        return ""
    if _has_long_tokenish_run(value):
        return ""
    return value


# ---------------------------------------------------------------------------
# Deterministic raw_event_hash derivation
# ---------------------------------------------------------------------------


class _Unencodable(Exception):
    """Module-private sentinel: the malformed payload cannot be
    safely canonicalised for hashing.

    Caught only inside ``_derive_malformed_raw_event_hash``;
    never propagates outside this module.
    """


def _to_plain_for_hash(value: object, depth: int) -> object:
    """Recursively project a malformed-payload value into a
    JSON-encodable plain form, or raise ``_Unencodable``.

    Mappings (including ``MappingProxyType``) become plain
    dicts; ``list`` and ``tuple`` become lists; the JSON
    primitive types pass through. ``bytes``, sets, custom
    objects, and non-string mapping keys raise
    ``_Unencodable``. Non-finite floats are not rejected
    here -- the strict JSON encoder catches them.
    """
    if depth > _HASH_DEPTH_CAP:
        raise _Unencodable("depth cap exceeded")
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise _Unencodable("non-string mapping key")
            out[k] = _to_plain_for_hash(v, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_to_plain_for_hash(v, depth + 1) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if value is None:
        return None
    raise _Unencodable("unsupported value type")


def _canonicalize_for_hash(raw_payload: object) -> bytes:
    """Return canonical UTF-8 bytes for a safe shallow projection
    of ``raw_payload``, or raise ``_Unencodable``.

    Strict JSON only: ``sort_keys=True``,
    ``separators=(",", ":")``, ``allow_nan=False``. The
    ``allow_nan=False`` flag makes the encoder reject NaN /
    Infinity / -Infinity (non-finite floats) by raising
    ``ValueError``. ``ensure_ascii=False`` keeps the JSON text
    compact for legitimate non-ASCII content; the subsequent
    UTF-8 encode can then raise ``UnicodeEncodeError`` for
    pathological strings -- specifically lone surrogates such
    as ``"\\ud800"`` which the JSON encoder accepts but UTF-8
    cannot represent.

    All three failure modes (``TypeError`` / ``ValueError`` /
    ``UnicodeEncodeError``) are routed to ``_Unencodable`` so
    one bad malformed payload cannot abort the surrounding
    Stage 22.4 batch. The caller's fallback path produces a
    deterministic structural hash from
    ``(provider_id, provider_attempt_index, batch_index)``.
    """
    plain = _to_plain_for_hash(raw_payload, depth=0)
    try:
        text = json.dumps(
            plain,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _Unencodable("canonical material not safely encodable")


def _derive_malformed_raw_event_hash(
    *,
    raw_payload: object,
    provider_id: str,
    provider_attempt_index: int,
    batch_index: int,
) -> str:
    """Derive a deterministic 64-char lowercase-hex
    ``raw_event_hash`` for a malformed payload.

    Content path: canonical UTF-8 bytes of a safe shallow
    projection of the payload, sha256 hex. Different content
    (in any serialisable field, including a payload-supplied
    ``raw_event_hash`` field) produces a different hash; the
    payload-supplied value is NOT trusted -- it is just one
    input among many to the canonical projection.

    Fallback path: when ``_canonicalize_for_hash`` raises
    ``_Unencodable`` (bytes, custom objects, non-string
    mapping keys, non-finite floats, depth overflow, or a JSON
    text the UTF-8 codec refuses such as a lone surrogate),
    the helper hashes a deterministic projection of the call
    provenance: ``provider_id`` plus ``provider_attempt_index``
    plus ``batch_index``. The fallback uses
    ``ensure_ascii=True`` so the resulting JSON text is
    guaranteed UTF-8 encodable even if the caller-supplied
    ``provider_id`` would itself fail strict UTF-8 encoding.
    """
    try:
        material_bytes = _canonicalize_for_hash(raw_payload)
    except _Unencodable:
        material_bytes = json.dumps(
            {
                "fallback_provider_id": provider_id,
                "fallback_provider_attempt_index": provider_attempt_index,
                "fallback_batch_index": batch_index,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=True,
        ).encode("utf-8")
    return hashlib.sha256(material_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Provider failure path
# ---------------------------------------------------------------------------


def _handle_provider_failure(
    *,
    provider_id: str,
    chain: str,
    fetch_outcome: ProviderFetchOutcome,
    observed_at_utc: str,
    raw_capture_writer: RawCaptureWriter,
) -> Stage22BatchHandlingResult:
    """Build and capture the single ``ProviderFailureRecord`` for a
    failed fetch, then return the corresponding
    ``Stage22BatchHandlingResult``.

    Raises ``Stage22BatchHandlingContractError`` when
    ``fetch_outcome.responses`` is non-empty (a failed fetch
    cannot also carry events). The classifier call may raise
    ``Stage22ClassifierContractError``; that exception
    propagates unchanged.
    """
    if fetch_outcome.responses:
        raise Stage22BatchHandlingContractError(
            "fetch_outcome.ok is False but responses tuple is non-empty"
        )
    failure_label = classify_failure(outcome=fetch_outcome)
    failure_record = ProviderFailureRecord(
        provider_id=provider_id,
        failure_label=failure_label,
        status_class=fetch_outcome.status_class,
        upstream_error_type=fetch_outcome.upstream_error_type,
        provider_attempt_index=fetch_outcome.provider_attempt_index,
        observed_at_utc=observed_at_utc,
    )
    raw_capture_writer.capture_provider_failure(record=failure_record)
    return Stage22BatchHandlingResult(
        outcome=INGEST_OUTCOME_PROVIDER_FAILED,
        provider_id=provider_id,
        chain=chain,
        provider_attempt_index=fetch_outcome.provider_attempt_index,
        events_received=0,
        events_normalized=0,
        events_malformed=0,
        provider_failures=1,
        last_failure_label=failure_label,
        envelopes=(),
    )


# ---------------------------------------------------------------------------
# Per-event decode isolation
# ---------------------------------------------------------------------------


def _classify_decode_reason(
    *,
    decode_exc: BaseException,
    classify_decode_error_fn: Callable[[BaseException], str],
) -> str:
    """Map a decode-time exception to a closed-set malformed reason.

    Calls the injected classifier. A classifier that raises is
    mapped to ``MALFORMED_REASON_UNEXPECTED_ERROR`` and the
    batch continues. A classifier that returns a value outside
    ``MALFORMED_EVENT_REASONS`` is a hard contract violation
    and raises ``Stage22BatchHandlingContractError``.

    The raw exception is never echoed in any returned label.
    """
    try:
        reason = classify_decode_error_fn(decode_exc)
    except Exception:
        return MALFORMED_REASON_UNEXPECTED_ERROR
    if not isinstance(reason, str):
        raise Stage22BatchHandlingContractError(
            "classify_decode_error_fn returned a non-string value"
        )
    if reason not in MALFORMED_EVENT_REASONS:
        raise Stage22BatchHandlingContractError(
            "classify_decode_error_fn returned a token outside "
            "MALFORMED_EVENT_REASONS"
        )
    return reason


def _process_one_response(
    *,
    raw_response: object,
    batch_index: int,
    provider_id: str,
    chain: str,
    received_at_utc: str,
    failed_at_utc: str,
    provider_attempt_index: int,
    decode_event_fn: Callable[[Mapping[str, object]], NormalizedLiveEvent],
    classify_decode_error_fn: Callable[[BaseException], str],
    raw_capture_writer: RawCaptureWriter,
) -> tuple[IngestEventEnvelope, None] | tuple[None, MalformedEventRecord]:
    """Process a single raw response in isolation.

    Returns either ``(envelope, None)`` on successful decode or
    ``(None, malformed_record)`` on decode failure. Capture
    failures (``Stage22CaptureContractError``) propagate
    unchanged; ``Stage22BatchHandlingContractError`` from the
    contract checks below also propagates.
    """
    decode_failed = False
    decoded_value: object = None
    decode_exc_seen: BaseException | None = None
    try:
        decoded_value = decode_event_fn(raw_response)
    except Stage22BatchHandlingContractError:
        # Never reclassify our own contract violation.
        raise
    except Exception as exc:
        decode_failed = True
        decode_exc_seen = exc

    if decode_failed:
        assert decode_exc_seen is not None
        reason = _classify_decode_reason(
            decode_exc=decode_exc_seen,
            classify_decode_error_fn=classify_decode_error_fn,
        )
        safe_event_id = _extract_safe_provider_event_id(raw_response)
        derived_hash = _derive_malformed_raw_event_hash(
            raw_payload=raw_response,
            provider_id=provider_id,
            provider_attempt_index=provider_attempt_index,
            batch_index=batch_index,
        )
        malformed = MalformedEventRecord(
            provider_id=provider_id,
            provider_event_id=safe_event_id,
            reason=reason,
            failed_at_utc=failed_at_utc,
            raw_event_hash=derived_hash,
        )
        raw_capture_writer.capture_malformed(record=malformed)
        return (None, malformed)

    if not isinstance(decoded_value, NormalizedLiveEvent):
        raise Stage22BatchHandlingContractError(
            "decode_event_fn returned a value that is not a "
            "NormalizedLiveEvent"
        )
    event: NormalizedLiveEvent = decoded_value
    if event.chain != chain:
        raise Stage22BatchHandlingContractError(
            "decoded event.chain does not match caller-supplied chain"
        )
    key = IngestEventKey(
        provider_id=provider_id,
        chain=chain,
        event_id=event.event_id,
        provider_event_id=event.provider_event_id,
        raw_event_hash=event.raw_event_hash,
    )
    envelope = IngestEventEnvelope(
        event=event,
        ingest_key=key,
        received_at_utc=received_at_utc,
        provider_attempt_index=provider_attempt_index,
    )
    raw_capture_writer.capture(envelope=envelope)
    return (envelope, None)


# ---------------------------------------------------------------------------
# Public batch helper
# ---------------------------------------------------------------------------


def handle_provider_batch(
    *,
    provider_id: str,
    chain: str,
    fetch_outcome: ProviderFetchOutcome,
    observed_at_utc: str,
    received_at_utc: str,
    failed_at_utc: str,
    decode_event_fn: Callable[[Mapping[str, object]], NormalizedLiveEvent],
    classify_decode_error_fn: Callable[[BaseException], str],
    raw_capture_writer: RawCaptureWriter,
) -> Stage22BatchHandlingResult:
    """Decide the per-batch outcome for one provider fetch attempt.

    Pure batch isolation helper. Captures provider failures and
    per-event decode failures through the injected
    ``raw_capture_writer`` and returns a deterministic
    ``Stage22BatchHandlingResult`` describing the batch.

    Contract violations (Stage22BatchHandlingContractError):

      * ``fetch_outcome.ok`` is False with a non-empty
        ``responses`` tuple.
      * ``fetch_outcome.ok`` is True with a ``status_class``
        other than ``"success"``.
      * ``decode_event_fn`` returns a value that is not a
        ``NormalizedLiveEvent``.
      * The decoded event's ``chain`` does not match the
        caller-supplied chain.
      * ``classify_decode_error_fn`` returns a token outside
        ``MALFORMED_EVENT_REASONS``.

    Other propagated exceptions:

      * ``Stage22ClassifierContractError`` from
        ``classify_failure`` when the outcome carries an
        invalid status_class / upstream_error_type combination.
      * ``Stage22CaptureContractError`` from any capture-writer
        call. Capture failure is FATAL and aborts the batch.

    Stage 22.4 does NOT call dedupe, transport, retry, sleep,
    reconnect, readiness, or any runner-style coordination
    surface; those concerns belong to Stage 22.5+.
    """
    if not fetch_outcome.ok:
        return _handle_provider_failure(
            provider_id=provider_id,
            chain=chain,
            fetch_outcome=fetch_outcome,
            observed_at_utc=observed_at_utc,
            raw_capture_writer=raw_capture_writer,
        )

    # Success path. The adapter contract requires status_class
    # == "success" when ok is True; reject the incoherent
    # variant here so the failure surface is symmetric with
    # the ok=False path.
    if fetch_outcome.status_class != STATUS_CLASS_SUCCESS:
        raise Stage22BatchHandlingContractError(
            "fetch_outcome.ok is True but status_class is not 'success'"
        )

    responses = fetch_outcome.responses
    events_received = len(responses)
    provider_attempt_index = fetch_outcome.provider_attempt_index

    if events_received == 0:
        return Stage22BatchHandlingResult(
            outcome=INGEST_OUTCOME_PROVIDER_RETURNED_ZERO,
            provider_id=provider_id,
            chain=chain,
            provider_attempt_index=provider_attempt_index,
            events_received=0,
            events_normalized=0,
            events_malformed=0,
            provider_failures=0,
            last_failure_label="",
            envelopes=(),
        )

    envelopes_acc: list[IngestEventEnvelope] = []
    events_normalized = 0
    events_malformed = 0
    for batch_index, raw_response in enumerate(responses):
        envelope, _ = _process_one_response(
            raw_response=raw_response,
            batch_index=batch_index,
            provider_id=provider_id,
            chain=chain,
            received_at_utc=received_at_utc,
            failed_at_utc=failed_at_utc,
            provider_attempt_index=provider_attempt_index,
            decode_event_fn=decode_event_fn,
            classify_decode_error_fn=classify_decode_error_fn,
            raw_capture_writer=raw_capture_writer,
        )
        if envelope is not None:
            envelopes_acc.append(envelope)
            events_normalized += 1
        else:
            events_malformed += 1

    if events_normalized == 0:
        outcome = INGEST_OUTCOME_ALL_MALFORMED
    else:
        outcome = INGEST_OUTCOME_OK

    return Stage22BatchHandlingResult(
        outcome=outcome,
        provider_id=provider_id,
        chain=chain,
        provider_attempt_index=provider_attempt_index,
        events_received=events_received,
        events_normalized=events_normalized,
        events_malformed=events_malformed,
        provider_failures=0,
        last_failure_label="",
        envelopes=tuple(envelopes_acc),
    )


__all__ = [
    "Stage22BatchHandlingResult",
    "handle_provider_batch",
]
