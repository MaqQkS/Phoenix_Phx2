"""Stage 22.1 ingest-contract shape tests.

Pins:

  * Every NamedTuple's ``_fields`` matches the locked field tuple.
  * Every Protocol subclasses ``typing.Protocol``.
  * Every Protocol method signature is keyword-only with an
    explicit return annotation.
  * NamedTuples are immutable (writing to a field raises
    ``AttributeError``).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Protocol, get_type_hints

import pytest

from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage22.ingest_contracts import (
    DedupeLedger,
    DedupeOutcome,
    IngestEventEnvelope,
    IngestEventKey,
    MalformedEventRecord,
    ProviderFailureRecord,
    ProviderFetchOutcome,
    RawCaptureWriter,
    RetryCap,
    RetryDecision,
    Stage22DispatchOutcome,
    Stage22IngestResult,
    Stage22PrivateTransport,
)


INGEST_CONTRACTS_PATH: Path = (
    Path(__file__).parent.parent.parent
    / "stage22"
    / "ingest_contracts.py"
)


# ---------------------------------------------------------------------------
# NamedTuple field locks
# ---------------------------------------------------------------------------


def test_provider_fetch_outcome_fields_are_locked():
    assert ProviderFetchOutcome._fields == (
        "ok",
        "responses",
        "status_class",
        "upstream_error_type",
        "provider_attempt_index",
    )


def test_provider_failure_record_fields_are_locked():
    assert ProviderFailureRecord._fields == (
        "provider_id",
        "failure_label",
        "status_class",
        "upstream_error_type",
        "provider_attempt_index",
        "observed_at_utc",
    )


def test_malformed_event_record_fields_are_locked():
    assert MalformedEventRecord._fields == (
        "provider_id",
        "provider_event_id",
        "reason",
        "failed_at_utc",
        "raw_event_hash",
    )


def test_ingest_event_key_fields_are_locked():
    # Per 22.1 design-lock §11 correction: ``event_id`` is added
    # so the future dedupe ledger keys primarily on the Stage 21
    # normalized event_id, with provider_event_id /
    # raw_event_hash as audit / tamper-detection fields.
    assert IngestEventKey._fields == (
        "provider_id",
        "chain",
        "event_id",
        "provider_event_id",
        "raw_event_hash",
    )


def test_ingest_event_envelope_fields_are_locked():
    assert IngestEventEnvelope._fields == (
        "event",
        "ingest_key",
        "received_at_utc",
        "provider_attempt_index",
    )


def test_dedupe_outcome_fields_are_locked():
    assert DedupeOutcome._fields == (
        "outcome",
        "ingest_key",
    )


def test_retry_cap_fields_are_locked():
    assert RetryCap._fields == (
        "max_attempts",
    )


def test_retry_decision_fields_are_locked():
    assert RetryDecision._fields == (
        "decision",
        "failure_label",
        "attempt_index",
    )


def test_stage22_ingest_result_fields_are_locked():
    assert Stage22IngestResult._fields == (
        "outcome",
        "events_received",
        "events_normalized",
        "events_malformed",
        "events_new",
        "events_dispatched",
        "events_transport_refused",
        "provider_attempts",
        "last_failure_label",
        "provider_id",
    )


# ---------------------------------------------------------------------------
# NamedTuple immutability
# ---------------------------------------------------------------------------


def test_provider_fetch_outcome_is_immutable():
    out = ProviderFetchOutcome(
        ok=True,
        responses=(),
        status_class="success",
        upstream_error_type="",
        provider_attempt_index=0,
    )
    with pytest.raises(AttributeError):
        out.ok = False  # type: ignore[misc]


def test_ingest_event_key_is_immutable():
    key = IngestEventKey(
        provider_id="helius",
        chain="solana_mainnet",
        event_id="evt_0123456789abcdef01234567",
        provider_event_id="prov-abc",
        raw_event_hash="0" * 64,
    )
    with pytest.raises(AttributeError):
        key.chain = "other"  # type: ignore[misc]


def test_retry_cap_is_immutable():
    cap = RetryCap(max_attempts=3)
    with pytest.raises(AttributeError):
        cap.max_attempts = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IngestEventEnvelope binds to Stage 21 NormalizedLiveEvent
# ---------------------------------------------------------------------------


def test_ingest_event_envelope_event_field_typed_as_normalized_live_event():
    hints = get_type_hints(IngestEventEnvelope)
    assert hints["event"] is NormalizedLiveEvent


# ---------------------------------------------------------------------------
# Protocol identity + base class
# ---------------------------------------------------------------------------


def _class_bases_from_ast(class_name: str) -> set[str]:
    """Return the AST-level base names of ``class_name`` in
    ``ingest_contracts.py``. Used to assert ``Protocol`` is a base
    without depending on CPython internals.
    """
    tree = ast.parse(INGEST_CONTRACTS_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            names: set[str] = set()
            for base in node.bases:
                if isinstance(base, ast.Name):
                    names.add(base.id)
                elif isinstance(base, ast.Attribute):
                    names.add(base.attr)
            return names
    raise AssertionError(
        f"class {class_name!r} not found in ingest_contracts.py"
    )


def test_dedupe_ledger_is_a_protocol():
    assert "Protocol" in _class_bases_from_ast("DedupeLedger")


def test_raw_capture_writer_is_a_protocol():
    assert "Protocol" in _class_bases_from_ast("RawCaptureWriter")


def test_dedupe_ledger_is_a_protocol_via_runtime_metadata():
    # ``Protocol`` subclasses carry the private CPython flag
    # ``_is_protocol = True``. Defensive runtime cross-check.
    assert getattr(DedupeLedger, "_is_protocol", False), (
        "DedupeLedger must subclass typing.Protocol"
    )


def test_raw_capture_writer_is_a_protocol_via_runtime_metadata():
    assert getattr(RawCaptureWriter, "_is_protocol", False), (
        "RawCaptureWriter must subclass typing.Protocol"
    )


# ---------------------------------------------------------------------------
# Protocol method signatures: keyword-only + return-annotated
# ---------------------------------------------------------------------------


def _function_signature(
    class_name: str,
    method_name: str,
) -> tuple[list[str], list[str], str | None]:
    """Return ``(positional_args, kwonly_args, return_name)`` for
    a method in ``ingest_contracts.py``. Return name is ``None``
    when no annotation is present.
    """
    tree = ast.parse(INGEST_CONTRACTS_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == method_name
                ):
                    positional = [a.arg for a in item.args.args]
                    kwonly = [a.arg for a in item.args.kwonlyargs]
                    if item.returns is None:
                        return_name = None
                    elif isinstance(item.returns, ast.Name):
                        return_name = item.returns.id
                    elif isinstance(item.returns, ast.Constant) and (
                        item.returns.value is None
                    ):
                        return_name = "None"
                    elif isinstance(item.returns, ast.Subscript):
                        # Not used in 22.1 Protocols, but keep
                        # graceful fallback.
                        return_name = "<subscript>"
                    else:
                        return_name = type(item.returns).__name__
                    return positional, kwonly, return_name
    raise AssertionError(
        f"method {class_name}.{method_name} not found"
    )


def test_dedupe_ledger_check_and_record_signature_is_kwonly():
    positional, kwonly, return_name = _function_signature(
        "DedupeLedger", "check_and_record"
    )
    assert positional == ["self"], (
        f"check_and_record positional args: {positional!r}"
    )
    assert kwonly == ["key"], (
        f"check_and_record kwonly args: {kwonly!r}"
    )
    assert return_name == "DedupeOutcome", (
        f"check_and_record returns {return_name!r}, expected "
        "'DedupeOutcome'"
    )


def test_dedupe_ledger_mark_dispatched_signature_is_kwonly():
    positional, kwonly, return_name = _function_signature(
        "DedupeLedger", "mark_dispatched"
    )
    assert positional == ["self"]
    assert kwonly == ["key"]
    assert return_name == "None"


def test_raw_capture_writer_capture_signature_is_kwonly():
    positional, kwonly, return_name = _function_signature(
        "RawCaptureWriter", "capture"
    )
    assert positional == ["self"]
    assert kwonly == ["envelope"]
    assert return_name == "None"


def test_raw_capture_writer_capture_malformed_signature_is_kwonly():
    positional, kwonly, return_name = _function_signature(
        "RawCaptureWriter", "capture_malformed"
    )
    assert positional == ["self"]
    assert kwonly == ["record"]
    assert return_name == "None"


def test_raw_capture_writer_capture_provider_failure_signature_is_kwonly():
    positional, kwonly, return_name = _function_signature(
        "RawCaptureWriter", "capture_provider_failure"
    )
    assert positional == ["self"]
    assert kwonly == ["record"]
    assert return_name == "None"


# ---------------------------------------------------------------------------
# Construction smoke tests (Protocol shape proof via in-memory fakes)
# ---------------------------------------------------------------------------


def test_dedupe_ledger_protocol_accepts_a_structural_fake():
    """A minimal in-memory class satisfies the Protocol shape."""
    captured_keys: list[IngestEventKey] = []
    dispatched_keys: list[IngestEventKey] = []

    class _FakeLedger:
        def check_and_record(
            self, *, key: IngestEventKey
        ) -> DedupeOutcome:
            captured_keys.append(key)
            return DedupeOutcome(outcome="new", ingest_key=key)

        def mark_dispatched(
            self, *, key: IngestEventKey
        ) -> None:
            dispatched_keys.append(key)

    fake: DedupeLedger = _FakeLedger()  # type: ignore[assignment]
    key = IngestEventKey(
        provider_id="helius",
        chain="solana_mainnet",
        event_id="evt_0123456789abcdef01234567",
        provider_event_id="prov-abc",
        raw_event_hash="0" * 64,
    )
    outcome = fake.check_and_record(key=key)
    assert outcome.outcome == "new"
    assert outcome.ingest_key == key
    assert fake.mark_dispatched(key=key) is None
    assert captured_keys == [key]
    assert dispatched_keys == [key]


def test_raw_capture_writer_protocol_accepts_a_structural_fake():
    captured_envelopes: list[IngestEventEnvelope] = []
    malformed_records: list[MalformedEventRecord] = []
    failure_records: list[ProviderFailureRecord] = []

    class _FakeWriter:
        def capture(
            self, *, envelope: IngestEventEnvelope
        ) -> None:
            captured_envelopes.append(envelope)

        def capture_malformed(
            self, *, record: MalformedEventRecord
        ) -> None:
            malformed_records.append(record)

        def capture_provider_failure(
            self, *, record: ProviderFailureRecord
        ) -> None:
            failure_records.append(record)

    fake: RawCaptureWriter = _FakeWriter()  # type: ignore[assignment]

    malformed = MalformedEventRecord(
        provider_id="helius",
        provider_event_id="prov-abc",
        reason="decode_shape_error",
        failed_at_utc="2026-05-18T00:00:00Z",
        raw_event_hash="0" * 64,
    )
    failure = ProviderFailureRecord(
        provider_id="helius",
        failure_label="provider_fetch_timeout",
        status_class="timeout",
        upstream_error_type="timeout",
        provider_attempt_index=0,
        observed_at_utc="2026-05-18T00:00:00Z",
    )
    fake.capture_malformed(record=malformed)
    fake.capture_provider_failure(record=failure)
    assert malformed_records == [malformed]
    assert failure_records == [failure]


# ---------------------------------------------------------------------------
# Forbidden field names: 22.1 records must not expose any secret-bearing
# field name even if instances are never populated with secrets.
# ---------------------------------------------------------------------------


_FORBIDDEN_RECORD_FIELD_NAMES: tuple[str, ...] = (
    "api_key",
    "webhook_url",
    "rpc_url",
    "raw_response_body",
    "exception_message",
    "exception_repr",
    "headers",
    "authorization",
    "bearer",
    "password",
    "secret",
    "credential",
)


_ALL_RECORD_TYPES = (
    ProviderFetchOutcome,
    ProviderFailureRecord,
    MalformedEventRecord,
    IngestEventKey,
    IngestEventEnvelope,
    DedupeOutcome,
    RetryCap,
    RetryDecision,
    Stage22IngestResult,
    Stage22DispatchOutcome,
)


def test_no_record_field_name_is_secret_bearing():
    for cls in _ALL_RECORD_TYPES:
        for field in cls._fields:
            lower = field.lower()
            for forbidden in _FORBIDDEN_RECORD_FIELD_NAMES:
                assert forbidden not in lower, (
                    f"{cls.__name__}.{field} contains forbidden "
                    f"secret-bearing substring {forbidden!r}"
                )


# ---------------------------------------------------------------------------
# Stage 22.5: Stage22DispatchOutcome NamedTuple + Stage22PrivateTransport
# ---------------------------------------------------------------------------


def test_stage22_dispatch_outcome_fields_are_locked():
    assert Stage22DispatchOutcome._fields == (
        "dispatched",
        "rejection_reason",
    )


def test_stage22_dispatch_outcome_is_immutable():
    out = Stage22DispatchOutcome(dispatched=True, rejection_reason="")
    with pytest.raises(AttributeError):
        out.dispatched = False  # type: ignore[misc]


def test_stage22_private_transport_is_a_protocol():
    assert "Protocol" in _class_bases_from_ast("Stage22PrivateTransport")


def test_stage22_private_transport_is_a_protocol_via_runtime_metadata():
    assert getattr(Stage22PrivateTransport, "_is_protocol", False), (
        "Stage22PrivateTransport must subclass typing.Protocol"
    )


def test_stage22_private_transport_dispatch_signature_is_kwonly():
    positional, kwonly, return_name = _function_signature(
        "Stage22PrivateTransport", "dispatch"
    )
    assert positional == ["self"]
    assert kwonly == ["envelope"]
    assert return_name == "Stage22DispatchOutcome"


def test_stage22_private_transport_protocol_accepts_a_structural_fake():
    seen: list[IngestEventEnvelope] = []

    class _FakeTransport:
        def dispatch(
            self, *, envelope: IngestEventEnvelope
        ) -> Stage22DispatchOutcome:
            seen.append(envelope)
            return Stage22DispatchOutcome(
                dispatched=True, rejection_reason=""
            )

    fake: Stage22PrivateTransport = _FakeTransport()  # type: ignore[assignment]
    key = IngestEventKey(
        provider_id="helius",
        chain="solana_mainnet",
        event_id="evt_0123456789abcdef01234567",
        provider_event_id="prov-abc",
        raw_event_hash="0" * 64,
    )
    # The Stage22DispatchOutcome smoke does not need a real
    # NormalizedLiveEvent value to be plausible; the Protocol
    # surface accepts any IngestEventEnvelope shape.
    envelope = IngestEventEnvelope(
        event=None,  # type: ignore[arg-type]
        ingest_key=key,
        received_at_utc="2026-05-18T00:00:00Z",
        provider_attempt_index=0,
    )
    outcome = fake.dispatch(envelope=envelope)
    assert outcome.dispatched is True
    assert outcome.rejection_reason == ""
    assert seen == [envelope]
