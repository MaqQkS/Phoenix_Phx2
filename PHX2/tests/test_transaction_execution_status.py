"""Fail-closed transaction-execution-status classification (PHX2-E2E-007).

The migration-admission ``_transaction_failed`` helper historically defaulted a
malformed, non-``None`` error container (one lacking its inner ``.err`` field) to
empty bytes and therefore to *success*.  Under provider schema drift or an
unexpected protobuf wrapper shape a failed/indeterminate transaction could pass
that one execution-status gate.  These tests pin the corrected behavior:

  * only an explicitly recognized canonical success returns SUCCESS;
  * every recognized failure, and every malformed/unsupported/inaccessible or
    ambiguous representation, fails closed and is rejected before any migration
    proof is authorized or any trusted reserve observation is routed.

Everything here is deterministic and offline: synthetic attribute objects, the
vendored ``solana.storage.ConfirmedBlock`` protobuf, fake reserve indexes, and
no network/transport/env access.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import PHX2.tests.test_trusted_reserve_market_routing as trr
from PHX2.free_tier_producer.compat.build26_capture_artifacts import scan_text
from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_TRANSACTION_FAILED,
    POOL_CREATION_CPI_UNPROVEN,
    PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
    TRANSACTION_ERROR_ACCESS_FAILED,
    TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED,
    TRANSACTION_ERROR_PRESENCE_CONFLICT,
    TRANSACTION_ERROR_UNSUPPORTED_ENCODING,
    TRANSACTION_STATUS_FAIL_CLOSED_REASONS,
    MigrationAdmissionCounters,
    TransactionExecutionStatus,
    _transaction_failed,
    classify_transaction_execution_status,
    evaluate_migration_admission,
)
from PHX2.proto.stage28_11._generated import solana_storage_pb2 as pb
from PHX2.tests.test_migration_admission import build_pool_creation_update

S = TransactionExecutionStatus


# ---------------------------------------------------------------------------
# Synthetic provider shapes
# ---------------------------------------------------------------------------


class MalformedErrorContainer:
    """The exact audited hostile shape: a non-None error container with no
    recognized inner error field."""


class _MetaErrPropertyRaises:
    """Top-level meta whose ``err`` access raises."""

    @property
    def err(self):
        raise RuntimeError("err access failed")


class _InnerErrRaises:
    """Error wrapper whose inner ``err`` access raises."""

    @property
    def err(self):
        raise RuntimeError("inner err access failed")


class _GetattrRaises:
    """Object whose every attribute access raises."""

    def __getattr__(self, name):
        raise RuntimeError(f"getattr {name} failed")


class _Tripwire:
    """Error wrapper whose truthiness/repr must never be consulted.

    The classifier reads only the recognized inner field with a typed check; if
    it ever fell back to truthiness or ``repr`` the recorded ``consulted`` list
    would be non-empty.
    """

    consulted: list = []

    def __init__(self, inner):
        self._inner = inner

    @property
    def err(self):
        return self._inner

    def __bool__(self):
        _Tripwire.consulted.append("bool")
        raise AssertionError("__bool__ must not be consulted")

    def __repr__(self):
        _Tripwire.consulted.append("repr")
        raise AssertionError("__repr__ must not be consulted")


def _proto_success() -> pb.TransactionStatusMeta:
    return pb.TransactionStatusMeta()


def _proto_failed() -> pb.TransactionStatusMeta:
    meta = pb.TransactionStatusMeta()
    meta.err.err = b"\x08\x02\x10\x00"  # a populated serialized transaction error
    return meta


def _proto_like_unsupported() -> object:
    """A protobuf-style object whose ``err`` field is absent from its schema."""

    def _hasfield(_name):
        raise ValueError("Field err does not exist in message")

    return SimpleNamespace(HasField=_hasfield)


def _presence_conflict() -> object:
    """Claims (via HasField) that no error is present, yet carries error bytes."""
    return SimpleNamespace(HasField=lambda _name: False,
                           err=SimpleNamespace(err=b"\x09\x09"))


def _ns(err_inner) -> SimpleNamespace:
    return SimpleNamespace(err=SimpleNamespace(err=err_inner))


# ---------------------------------------------------------------------------
# The exact audited hostile probe
# ---------------------------------------------------------------------------


def test_exact_audit_hostile_probe_fails_closed_after_correction():
    # err=None -> success; err absent -> success; malformed -> fail-closed;
    # recognized nonempty bytes -> failed.  Only the malformed row changed (it
    # returned False/success before the fix).
    assert _transaction_failed(SimpleNamespace(err=None)) is False
    assert _transaction_failed(SimpleNamespace()) is False
    assert _transaction_failed(SimpleNamespace(err=MalformedErrorContainer())) is True
    assert _transaction_failed(SimpleNamespace(err=SimpleNamespace(err=b"\x01"))) is True


def test_malformed_container_classifies_as_malformed_not_success():
    meta = SimpleNamespace(err=MalformedErrorContainer())
    assert classify_transaction_execution_status(meta) is S.MALFORMED
    assert _transaction_failed(meta) is True


# ---------------------------------------------------------------------------
# Full documented decision table
# ---------------------------------------------------------------------------

# Each row: (label, meta, expected status).  Only the exact canonical success
# encodings may map to SUCCESS.
_DECISION_TABLE = [
    ("proto_canonical_success", _proto_success(), S.SUCCESS),
    ("proto_canonical_failure", _proto_failed(), S.FAILED),
    ("toplevel_err_none", SimpleNamespace(err=None), S.SUCCESS),
    ("toplevel_err_absent", SimpleNamespace(), S.SUCCESS),
    ("wrapper_missing_inner_field", SimpleNamespace(err=MalformedErrorContainer()), S.MALFORMED),
    ("inner_none", _ns(None), S.MALFORMED),
    ("inner_empty_bytes", _ns(b""), S.MALFORMED),
    ("inner_nonempty_bytes", _ns(b"\x01"), S.FAILED),
    ("inner_empty_str", _ns(""), S.MALFORMED),
    ("inner_nonempty_str", _ns("boom"), S.MALFORMED),
    ("inner_false", _ns(False), S.MALFORMED),
    ("inner_true", _ns(True), S.MALFORMED),
    ("inner_zero", _ns(0), S.MALFORMED),
    ("inner_nonzero_int", _ns(7), S.MALFORMED),
    ("inner_empty_list", _ns([]), S.MALFORMED),
    ("inner_nonempty_list", _ns([1]), S.MALFORMED),
    ("inner_empty_dict", _ns({}), S.MALFORMED),
    ("inner_nonempty_dict", _ns({"a": 1}), S.MALFORMED),
    ("inner_nested_unknown_object", _ns(object()), S.MALFORMED),
    ("proto_failure_message", _proto_failed(), S.FAILED),
    ("proto_like_unsupported_schema", _proto_like_unsupported(), S.UNSUPPORTED),
    ("presence_conflict", _presence_conflict(), S.PRESENCE_CONFLICT),
    ("meta_none", None, S.UNSUPPORTED),
    ("err_property_raises", _MetaErrPropertyRaises(), S.ACCESS_ERROR),
    ("getattr_raises", _GetattrRaises(), S.ACCESS_ERROR),
    ("inner_empty_bytearray", _ns(bytearray(b"")), S.MALFORMED),
    ("inner_nonempty_bytearray", _ns(bytearray(b"\x02")), S.FAILED),
]


@pytest.mark.parametrize("label,meta,expected",
                         _DECISION_TABLE, ids=[row[0] for row in _DECISION_TABLE])
def test_decision_table_classification(label, meta, expected):
    assert classify_transaction_execution_status(meta) is expected
    # The boolean boundary must agree: failed iff not SUCCESS.
    assert _transaction_failed(meta) is (expected is not S.SUCCESS)


def test_only_three_canonical_success_forms_exist():
    successes = [meta for _label, meta, expected in _DECISION_TABLE
                 if expected is S.SUCCESS]
    # Exactly three canonical success encodings: protobuf presence-unset,
    # attribute err=None, attribute err absent.
    assert len(successes) == 3


def test_falsey_arbitrary_values_do_not_become_success():
    for inner in (b"", "", 0, False, [], {}, (), bytearray(b"")):
        assert classify_transaction_execution_status(_ns(inner)) is not S.SUCCESS


# ---------------------------------------------------------------------------
# Canonical success / failure preserved (both provider shapes)
# ---------------------------------------------------------------------------


def test_protobuf_presence_api_is_authoritative():
    ok = _proto_success()
    assert ok.HasField("err") is False
    assert classify_transaction_execution_status(ok) is S.SUCCESS
    bad = _proto_failed()
    assert bad.HasField("err") is True
    assert classify_transaction_execution_status(bad) is S.FAILED


def test_recognized_nonempty_failure_bytes_reject():
    assert classify_transaction_execution_status(_ns(b"\x01\x02\x03")) is S.FAILED
    assert _transaction_failed(_ns(b"\x01\x02\x03")) is True


# ---------------------------------------------------------------------------
# Hostile objects: no unsafe magic methods invoked
# ---------------------------------------------------------------------------


def test_truthiness_and_repr_of_error_wrapper_are_never_consulted():
    _Tripwire.consulted.clear()
    # A tripwire wrapper carrying recognized failure bytes classifies as FAILED
    # purely from the typed inner read; bool()/repr() are never called.
    assert classify_transaction_execution_status(
        SimpleNamespace(err=_Tripwire(b"\x01"))) is S.FAILED
    # A tripwire wrapper with an unsupported inner object classifies MALFORMED.
    assert classify_transaction_execution_status(
        SimpleNamespace(err=_Tripwire(object()))) is S.MALFORMED
    assert _Tripwire.consulted == []


def test_attribute_access_exception_fails_closed_safely():
    assert classify_transaction_execution_status(_MetaErrPropertyRaises()) is S.ACCESS_ERROR
    assert classify_transaction_execution_status(_GetattrRaises()) is S.ACCESS_ERROR
    assert classify_transaction_execution_status(
        SimpleNamespace(err=_InnerErrRaises())) is S.ACCESS_ERROR
    assert _transaction_failed(_MetaErrPropertyRaises()) is True
    assert _transaction_failed(_GetattrRaises()) is True


def test_unsupported_type_and_presence_conflict_reject():
    # A bare object() has no ``err`` attribute at all => canonical "absent" =>
    # SUCCESS (an attribute provider with no error field succeeded); a *present*
    # non-None container is never success.
    assert classify_transaction_execution_status(object()) is S.SUCCESS
    assert classify_transaction_execution_status(SimpleNamespace(err=object())) is S.MALFORMED
    assert classify_transaction_execution_status(_proto_like_unsupported()) is S.UNSUPPORTED
    assert classify_transaction_execution_status(_presence_conflict()) is S.PRESENCE_CONFLICT


# ---------------------------------------------------------------------------
# Migration-admission integration
# ---------------------------------------------------------------------------


def _inject_malformed(update):
    update.transaction.transaction.meta.err = MalformedErrorContainer()
    return update


def _inject_unsupported(update):
    def _hf(_name):
        raise ValueError("field err absent from message")

    update.transaction.transaction.meta.HasField = _hf
    return update


def _inject_presence_conflict(update):
    meta = update.transaction.transaction.meta
    meta.HasField = lambda _name: False
    meta.err = SimpleNamespace(err=b"\x09\x09")
    return update


def _inject_access_error(update):
    update.transaction.transaction.meta.err = _InnerErrRaises()
    return update


def _inject_unsupported_inner_type(update):
    update.transaction.transaction.meta.err = SimpleNamespace(err="not-bytes")
    return update


def test_canonical_migration_still_admits():
    decision = evaluate_migration_admission(build_pool_creation_update())
    assert decision is not None and decision.admitted
    assert decision.proof is not None


def test_canonical_failed_transaction_rejects_with_failed_reason():
    decision = evaluate_migration_admission(build_pool_creation_update(failed=True))
    assert decision is not None and not decision.admitted
    assert decision.reason_codes == (MIGRATION_TRANSACTION_FAILED,)
    assert decision.proof is None


@pytest.mark.parametrize("discriminator", [
    PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
])
def test_malformed_transaction_rejects_before_migration_proof(discriminator):
    # An otherwise-genuine migrate/migrate_v2 whose error container is malformed
    # is rejected with the precise malformed reason and NEVER produces a proof.
    update = _inject_malformed(
        build_pool_creation_update(migrate_discriminator=discriminator))
    decision = evaluate_migration_admission(update)
    assert decision is not None and not decision.admitted
    assert decision.classification == POOL_CREATION_CPI_UNPROVEN
    assert decision.reason_codes == (TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED,)
    assert decision.proof is None
    assert decision.migration_version is None


def test_failed_reason_has_priority_over_lower_level_reasons():
    # A malformed error on a genuine migration must surface ONLY the tx-status
    # reason, not a downstream CPI/deposit/mint reason.
    update = _inject_malformed(build_pool_creation_update())
    decision = evaluate_migration_admission(update)
    assert decision.reason_codes == (TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED,)


@pytest.mark.parametrize("inject,reason", [
    (_inject_malformed, TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED),
    (_inject_unsupported, TRANSACTION_ERROR_UNSUPPORTED_ENCODING),
    (_inject_presence_conflict, TRANSACTION_ERROR_PRESENCE_CONFLICT),
    (_inject_access_error, TRANSACTION_ERROR_ACCESS_FAILED),
    (_inject_unsupported_inner_type, TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED),
])
def test_indeterminate_status_maps_to_precise_admission_reason(inject, reason):
    decision = evaluate_migration_admission(inject(build_pool_creation_update()))
    assert not decision.admitted
    assert decision.reason_codes == (reason,)
    assert decision.proof is None
    assert decision.classification == POOL_CREATION_CPI_UNPROVEN


def test_malformed_event_does_not_crash_admission():
    # A single malformed event is rejected and returns a decision, never raises.
    for err_obj in (MalformedErrorContainer(), _InnerErrRaises(),
                    SimpleNamespace(err=object()),
                    SimpleNamespace(err=SimpleNamespace(err=[1, 2, 3]))):
        update = build_pool_creation_update()
        update.transaction.transaction.meta.err = err_obj
        decision = evaluate_migration_admission(update)
        assert decision is not None and not decision.admitted
        assert decision.proof is None


def test_repeated_malformed_events_are_bounded_and_deterministic():
    results = []
    for _ in range(25):
        update = _inject_malformed(build_pool_creation_update())
        decision = evaluate_migration_admission(update)
        results.append((decision.admitted, decision.reason_codes))
    assert results == [(False, (TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED,))] * 25


# ---------------------------------------------------------------------------
# Downstream zero-work proof for a malformed event
# ---------------------------------------------------------------------------


def test_malformed_event_produces_no_admitted_candidate_or_proof():
    update = _inject_malformed(build_pool_creation_update())
    decision = evaluate_migration_admission(update)
    # Admission is the single gate every downstream stage depends on: no provider
    # handoff candidate, no watch seed, no baseline/ATH, no market-scheduler job,
    # no compose, no delivery reservation and no dedupe row can be produced from
    # a rejected decision that carries no proof.
    assert decision.admitted is False
    assert decision.proof is None
    assert decision.migration_version is None


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


def test_transaction_status_counters_increment_exactly_once():
    counters = MigrationAdmissionCounters()
    counters.record(evaluate_migration_admission(
        _inject_malformed(build_pool_creation_update())))
    snap = counters.snapshot()
    assert snap["rejected_transaction_status_fail_closed"] == 1
    assert snap["rejected_transaction_status_malformed"] == 1
    assert snap["rejected_transaction_status_unsupported"] == 0
    assert snap["rejected_transaction_status_access_error"] == 0
    assert snap["rejected_transaction_status_presence_conflict"] == 0
    assert snap["rejected_transaction_failed"] == 0
    # A recognized on-chain failure is counted separately.
    counters.record(evaluate_migration_admission(
        build_pool_creation_update(failed=True)))
    assert counters.snapshot()["rejected_transaction_failed"] == 1
    assert counters.snapshot()["rejected_transaction_status_fail_closed"] == 1


def test_counter_distinguishes_each_fail_closed_kind():
    counters = MigrationAdmissionCounters()
    cases = [
        (_inject_malformed, "rejected_transaction_status_malformed"),
        (_inject_unsupported, "rejected_transaction_status_unsupported"),
        (_inject_presence_conflict, "rejected_transaction_status_presence_conflict"),
        (_inject_access_error, "rejected_transaction_status_access_error"),
    ]
    for inject, _field in cases:
        counters.record(evaluate_migration_admission(inject(build_pool_creation_update())))
    snap = counters.snapshot()
    assert snap["rejected_transaction_status_malformed"] == 1
    assert snap["rejected_transaction_status_unsupported"] == 1
    assert snap["rejected_transaction_status_presence_conflict"] == 1
    assert snap["rejected_transaction_status_access_error"] == 1
    assert snap["rejected_transaction_status_fail_closed"] == 4


# ---------------------------------------------------------------------------
# Trusted gRPC reserve-routing integration
# ---------------------------------------------------------------------------


def test_malformed_transaction_yields_zero_trusted_reserve_observation():
    # The reserve router derives transaction_succeeded from the SAME fail-closed
    # boundary, so a malformed error can never open trusted price/MC routing.
    meta = SimpleNamespace(err=MalformedErrorContainer())
    assert _transaction_failed(meta) is True
    succeeded = not _transaction_failed(meta)
    assert succeeded is False

    index = trr._index()
    emitted = []
    index.add_routing_observer(emitted.append)
    # The event is stored but never trusted-routed (succeeded is False).
    assert trr._record(index, succeeded=succeeded, proven=True)
    assert emitted == []
    assert index.latest_routing_observation(trr.MINT) is None


def test_canonical_success_still_permits_trusted_reserve_routing():
    ok = SimpleNamespace()  # err absent => SUCCESS
    assert _transaction_failed(ok) is False
    index = trr._index()
    emitted = []
    index.add_routing_observer(emitted.append)
    assert trr._record(index, succeeded=not _transaction_failed(ok), proven=True)
    assert len(emitted) == 1
    assert emitted[0]["reserve_trusted_for_routing"] is True


# ---------------------------------------------------------------------------
# Redaction / diagnostic safety
# ---------------------------------------------------------------------------


def test_malformed_diagnostic_record_is_redaction_safe():
    update = _inject_malformed(build_pool_creation_update())
    decision = evaluate_migration_admission(update)
    record = decision.diagnostic_record()
    serialized = json.dumps(record, sort_keys=True)
    # No raw object repr, bytes, endpoints or credentials.
    assert "MalformedErrorContainer" not in serialized
    assert "object at 0x" not in serialized
    assert scan_text(serialized) == []
    assert TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED in record["reason_codes"]


def test_new_reason_codes_are_redaction_safe():
    for reason in sorted(TRANSACTION_STATUS_FAIL_CLOSED_REASONS):
        assert scan_text(reason) == []
