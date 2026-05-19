"""Stage 22.4 provider-failure tests for ``handle_provider_batch``.

Pins the provider-failure path of the Stage 22.4 batch
isolation helper:

  * A ``fetch_outcome.ok`` False outcome with an empty
    ``responses`` tuple captures exactly one
    ``ProviderFailureRecord`` and returns the
    ``provider_failed`` Stage22BatchHandlingResult outcome.
  * The Stage 22.1 classifier label is the source of truth for
    the captured ``failure_label`` (no duplicate label on the
    outcome record).
  * Provider-failure handling never calls the decoder or the
    decode-error classifier.
  * Contract violations raise
    ``Stage22BatchHandlingContractError``:
      - ``ok`` is False with non-empty responses.
      - ``ok`` is True with ``status_class != "success"``.
  * Classifier-side exceptions from ``classify_failure``
    propagate as ``Stage22ClassifierContractError``.
  * A ``Stage22CaptureContractError`` raised by
    ``capture_provider_failure`` propagates unchanged
    (capture-failure is fatal).
  * ``observed_at_utc`` and ``provider_attempt_index`` flow
    through to the captured record verbatim.
  * No raw exception material reaches the captured record.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage22.constants import (
    INGEST_OUTCOME_PROVIDER_FAILED,
    PROVIDER_FAILURE_LABEL_FETCH_RATE_LIMITED,
    PROVIDER_FAILURE_LABEL_FETCH_5XX,
    PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
    PROVIDER_FAILURE_LABELS,
    STATUS_CLASS_CONNECTION,
    STATUS_CLASS_MALFORMED,
    STATUS_CLASS_RATE_LIMIT,
    STATUS_CLASS_SERVER_ERROR,
    STATUS_CLASS_SUCCESS,
    STATUS_CLASS_TIMEOUT,
    STATUS_CLASS_UNKNOWN,
    UPSTREAM_ERROR_TYPE_CONNECTION_REFUSED,
    UPSTREAM_ERROR_TYPE_NONE,
    UPSTREAM_ERROR_TYPE_RATE_LIMITED,
    UPSTREAM_ERROR_TYPE_SERVER_ERROR,
    UPSTREAM_ERROR_TYPE_TIMEOUT,
)
from PHX2.stage22.errors import (
    Stage22BatchHandlingContractError,
    Stage22CaptureContractError,
    Stage22ClassifierContractError,
)
from PHX2.stage22.failure_handling import (
    Stage22BatchHandlingResult,
    handle_provider_batch,
)
from PHX2.stage22.ingest_contracts import ProviderFetchOutcome
from PHX2.stage22.raw_capture import InMemoryRawCaptureWriter


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _failing_decode(_raw: Mapping[str, object]) -> object:
    raise AssertionError(
        "decode_event_fn must not be called on a provider-failed batch"
    )


def _failing_classify(_exc: BaseException) -> str:
    raise AssertionError(
        "classify_decode_error_fn must not be called on a "
        "provider-failed batch"
    )


def _outcome(
    *,
    ok: bool = False,
    responses: tuple[Mapping[str, object], ...] = (),
    status_class: str = STATUS_CLASS_TIMEOUT,
    upstream_error_type: str = UPSTREAM_ERROR_TYPE_TIMEOUT,
    provider_attempt_index: int = 0,
) -> ProviderFetchOutcome:
    return ProviderFetchOutcome(
        ok=ok,
        responses=responses,
        status_class=status_class,
        upstream_error_type=upstream_error_type,
        provider_attempt_index=provider_attempt_index,
    )


class _RejectingCaptureWriter:
    """RawCaptureWriter that raises ``Stage22CaptureContractError``
    from every method. Used to prove capture-failure is fatal.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def capture(self, *, envelope: object) -> None:
        self.calls.append("capture")
        raise Stage22CaptureContractError("rejected capture")

    def capture_malformed(self, *, record: object) -> None:
        self.calls.append("capture_malformed")
        raise Stage22CaptureContractError("rejected capture_malformed")

    def capture_provider_failure(self, *, record: object) -> None:
        self.calls.append("capture_provider_failure")
        raise Stage22CaptureContractError(
            "rejected capture_provider_failure"
        )


# ---------------------------------------------------------------------------
# Happy path: provider_failed outcome
# ---------------------------------------------------------------------------


def test_provider_failure_outcome_is_provider_failed() -> None:
    writer = InMemoryRawCaptureWriter()
    result = handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(
            ok=False,
            responses=(),
            status_class=STATUS_CLASS_TIMEOUT,
            upstream_error_type=UPSTREAM_ERROR_TYPE_TIMEOUT,
            provider_attempt_index=2,
        ),
        observed_at_utc="2026-05-19T00:00:00Z",
        received_at_utc="2026-05-19T00:00:00Z",
        failed_at_utc="2026-05-19T00:00:00Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    assert isinstance(result, Stage22BatchHandlingResult)
    assert result.outcome == INGEST_OUTCOME_PROVIDER_FAILED


def test_provider_failure_captures_exactly_one_provider_failure_record() -> None:
    writer = InMemoryRawCaptureWriter()
    handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(),
        observed_at_utc="2026-05-19T00:00:01Z",
        received_at_utc="2026-05-19T00:00:01Z",
        failed_at_utc="2026-05-19T00:00:01Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    failures = writer.captured_provider_failures()
    assert len(failures) == 1
    assert writer.captured_normalized_events() == ()
    assert writer.captured_malformed_events() == ()


def test_provider_failure_record_has_closed_set_failure_label() -> None:
    writer = InMemoryRawCaptureWriter()
    handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(
            status_class=STATUS_CLASS_TIMEOUT,
            upstream_error_type=UPSTREAM_ERROR_TYPE_TIMEOUT,
        ),
        observed_at_utc="2026-05-19T00:00:02Z",
        received_at_utc="2026-05-19T00:00:02Z",
        failed_at_utc="2026-05-19T00:00:02Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    failure = writer.captured_provider_failures()[0]
    assert failure["failure_label"] in PROVIDER_FAILURE_LABELS
    assert failure["failure_label"] == PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT


def test_provider_failure_result_carries_classified_last_failure_label() -> None:
    writer = InMemoryRawCaptureWriter()
    result = handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(
            status_class=STATUS_CLASS_RATE_LIMIT,
            upstream_error_type=UPSTREAM_ERROR_TYPE_RATE_LIMITED,
        ),
        observed_at_utc="2026-05-19T00:00:03Z",
        received_at_utc="2026-05-19T00:00:03Z",
        failed_at_utc="2026-05-19T00:00:03Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    assert result.last_failure_label == (
        PROVIDER_FAILURE_LABEL_FETCH_RATE_LIMITED
    )
    assert result.provider_failures == 1
    assert result.events_received == 0
    assert result.events_normalized == 0
    assert result.events_malformed == 0
    assert result.envelopes == ()


def test_provider_failure_record_copies_provider_attempt_index() -> None:
    writer = InMemoryRawCaptureWriter()
    handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(provider_attempt_index=7),
        observed_at_utc="2026-05-19T00:00:04Z",
        received_at_utc="2026-05-19T00:00:04Z",
        failed_at_utc="2026-05-19T00:00:04Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    failure = writer.captured_provider_failures()[0]
    assert failure["provider_attempt_index"] == 7


def test_provider_failure_record_copies_observed_at_utc() -> None:
    writer = InMemoryRawCaptureWriter()
    handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(),
        observed_at_utc="2026-05-19T00:00:05Z",
        received_at_utc="2026-05-19T00:00:05Z",
        failed_at_utc="2026-05-19T00:00:05Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    failure = writer.captured_provider_failures()[0]
    assert failure["observed_at_utc"] == "2026-05-19T00:00:05Z"


def test_provider_failure_record_echoes_status_class_and_upstream_error_type() -> None:
    writer = InMemoryRawCaptureWriter()
    handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(
            status_class=STATUS_CLASS_SERVER_ERROR,
            upstream_error_type=UPSTREAM_ERROR_TYPE_SERVER_ERROR,
        ),
        observed_at_utc="2026-05-19T00:00:06Z",
        received_at_utc="2026-05-19T00:00:06Z",
        failed_at_utc="2026-05-19T00:00:06Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    failure = writer.captured_provider_failures()[0]
    assert failure["status_class"] == STATUS_CLASS_SERVER_ERROR
    assert failure["upstream_error_type"] == UPSTREAM_ERROR_TYPE_SERVER_ERROR
    assert failure["failure_label"] == PROVIDER_FAILURE_LABEL_FETCH_5XX


# ---------------------------------------------------------------------------
# Provider failure does not invoke the decoder
# ---------------------------------------------------------------------------


def test_provider_failure_does_not_call_decoder() -> None:
    """The injected decoder raises AssertionError if called; the
    provider-failure path must never reach that surface.
    """
    writer = InMemoryRawCaptureWriter()
    # _failing_decode raises AssertionError; if the helper calls
    # it, that exception escapes the call below.
    handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(),
        observed_at_utc="2026-05-19T00:00:07Z",
        received_at_utc="2026-05-19T00:00:07Z",
        failed_at_utc="2026-05-19T00:00:07Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )


def test_provider_failure_does_not_call_decode_error_classifier() -> None:
    writer = InMemoryRawCaptureWriter()
    handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(),
        observed_at_utc="2026-05-19T00:00:08Z",
        received_at_utc="2026-05-19T00:00:08Z",
        failed_at_utc="2026-05-19T00:00:08Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )


# ---------------------------------------------------------------------------
# Contract violations
# ---------------------------------------------------------------------------


def test_contract_error_when_ok_false_with_non_empty_responses() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22BatchHandlingContractError):
        handle_provider_batch(
            provider_id="helius",
            chain="solana_mainnet",
            fetch_outcome=_outcome(
                ok=False,
                responses=({"any": "value"},),
            ),
            observed_at_utc="2026-05-19T00:00:09Z",
            received_at_utc="2026-05-19T00:00:09Z",
            failed_at_utc="2026-05-19T00:00:09Z",
            decode_event_fn=_failing_decode,
            classify_decode_error_fn=_failing_classify,
            raw_capture_writer=writer,
        )
    assert writer.captured_all() == ()


def test_contract_error_when_ok_true_with_non_success_status_class() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22BatchHandlingContractError):
        handle_provider_batch(
            provider_id="helius",
            chain="solana_mainnet",
            fetch_outcome=_outcome(
                ok=True,
                responses=(),
                status_class=STATUS_CLASS_TIMEOUT,
                upstream_error_type=UPSTREAM_ERROR_TYPE_TIMEOUT,
            ),
            observed_at_utc="2026-05-19T00:00:10Z",
            received_at_utc="2026-05-19T00:00:10Z",
            failed_at_utc="2026-05-19T00:00:10Z",
            decode_event_fn=_failing_decode,
            classify_decode_error_fn=_failing_classify,
            raw_capture_writer=writer,
        )
    assert writer.captured_all() == ()


# ---------------------------------------------------------------------------
# Classifier-side exception propagation
# ---------------------------------------------------------------------------


def test_classifier_failure_propagates() -> None:
    """``classify_failure`` raises ``Stage22ClassifierContractError``
    when ``status_class`` is outside ``STATUS_CLASSES``. The
    Stage 22.4 helper must let that exception propagate
    unchanged -- no wrapping, no swallowing.
    """
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22ClassifierContractError):
        handle_provider_batch(
            provider_id="helius",
            chain="solana_mainnet",
            fetch_outcome=ProviderFetchOutcome(
                ok=False,
                responses=(),
                status_class="not_a_real_status_class",
                upstream_error_type=UPSTREAM_ERROR_TYPE_TIMEOUT,
                provider_attempt_index=0,
            ),
            observed_at_utc="2026-05-19T00:00:11Z",
            received_at_utc="2026-05-19T00:00:11Z",
            failed_at_utc="2026-05-19T00:00:11Z",
            decode_event_fn=_failing_decode,
            classify_decode_error_fn=_failing_classify,
            raw_capture_writer=writer,
        )
    # Nothing captured -- the classifier error fired before
    # the writer was invoked.
    assert writer.captured_all() == ()


def test_classifier_failure_on_ok_true_outcome_propagates() -> None:
    """``classify_failure`` raises on an ok=True outcome. The
    Stage 22.4 helper guards against this earlier (it never
    enters the failure path on ok=True), but the test pins the
    invariant: every Stage22ClassifierContractError that does
    fire propagates unchanged.
    """
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22BatchHandlingContractError):
        # ok=True + non-success status_class: the helper raises
        # its OWN contract error before calling classify_failure.
        handle_provider_batch(
            provider_id="helius",
            chain="solana_mainnet",
            fetch_outcome=ProviderFetchOutcome(
                ok=True,
                responses=(),
                status_class=STATUS_CLASS_UNKNOWN,
                upstream_error_type=UPSTREAM_ERROR_TYPE_NONE,
                provider_attempt_index=0,
            ),
            observed_at_utc="2026-05-19T00:00:12Z",
            received_at_utc="2026-05-19T00:00:12Z",
            failed_at_utc="2026-05-19T00:00:12Z",
            decode_event_fn=_failing_decode,
            classify_decode_error_fn=_failing_classify,
            raw_capture_writer=writer,
        )


# ---------------------------------------------------------------------------
# Capture failure is fatal
# ---------------------------------------------------------------------------


def test_capture_provider_failure_exception_propagates() -> None:
    writer = _RejectingCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        handle_provider_batch(
            provider_id="helius",
            chain="solana_mainnet",
            fetch_outcome=_outcome(),
            observed_at_utc="2026-05-19T00:00:13Z",
            received_at_utc="2026-05-19T00:00:13Z",
            failed_at_utc="2026-05-19T00:00:13Z",
            decode_event_fn=_failing_decode,
            classify_decode_error_fn=_failing_classify,
            raw_capture_writer=writer,
        )
    # The writer recorded exactly one call -- the
    # provider-failure capture attempt.
    assert writer.calls == ["capture_provider_failure"]


# ---------------------------------------------------------------------------
# No raw exception material reaches the captured record
# ---------------------------------------------------------------------------


def test_provider_failure_record_contains_no_exception_material() -> None:
    """The captured record must only carry closed-set tokens and
    caller-supplied non-secret strings. No raw exception text,
    no headers, no auth fields, no URLs.
    """
    writer = InMemoryRawCaptureWriter()
    handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(
            status_class=STATUS_CLASS_CONNECTION,
            upstream_error_type=UPSTREAM_ERROR_TYPE_CONNECTION_REFUSED,
        ),
        observed_at_utc="2026-05-19T00:00:14Z",
        received_at_utc="2026-05-19T00:00:14Z",
        failed_at_utc="2026-05-19T00:00:14Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    failure = writer.captured_provider_failures()[0]
    forbidden_substrings = (
        "http" + "://",
        "https" + "://",
        "ws" + "://",
        "wss" + "://",
        "Bearer",
        "Authorization",
        "api_key",
        "secret",
        "password",
        "Traceback",
    )
    for value in failure.values():
        text = str(value).lower()
        for needle in forbidden_substrings:
            assert needle.lower() not in text, (
                f"failure record value {value!r} contains forbidden "
                f"substring {needle!r}"
            )


# ---------------------------------------------------------------------------
# Multiple classifier-mapped labels reach the closed-set token tuple
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status_class,upstream_error_type,expected_label",
    [
        (
            STATUS_CLASS_TIMEOUT,
            UPSTREAM_ERROR_TYPE_TIMEOUT,
            PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
        ),
        (
            STATUS_CLASS_RATE_LIMIT,
            UPSTREAM_ERROR_TYPE_RATE_LIMITED,
            PROVIDER_FAILURE_LABEL_FETCH_RATE_LIMITED,
        ),
        (
            STATUS_CLASS_SERVER_ERROR,
            UPSTREAM_ERROR_TYPE_SERVER_ERROR,
            PROVIDER_FAILURE_LABEL_FETCH_5XX,
        ),
    ],
)
def test_classifier_label_in_provider_failure_record(
    status_class: str,
    upstream_error_type: str,
    expected_label: str,
) -> None:
    writer = InMemoryRawCaptureWriter()
    result = handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(
            status_class=status_class,
            upstream_error_type=upstream_error_type,
        ),
        observed_at_utc="2026-05-19T00:00:15Z",
        received_at_utc="2026-05-19T00:00:15Z",
        failed_at_utc="2026-05-19T00:00:15Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    failure = writer.captured_provider_failures()[0]
    assert failure["failure_label"] == expected_label
    assert result.last_failure_label == expected_label


def test_malformed_status_class_maps_to_returned_malformed_label() -> None:
    """``status_class == "malformed"`` is a FETCH-level malformed
    response (distinct from per-event decode failure). The
    classifier maps it to ``provider_returned_malformed``.
    """
    writer = InMemoryRawCaptureWriter()
    result = handle_provider_batch(
        provider_id="helius",
        chain="solana_mainnet",
        fetch_outcome=_outcome(
            status_class=STATUS_CLASS_MALFORMED,
            upstream_error_type=UPSTREAM_ERROR_TYPE_TIMEOUT,
        ),
        observed_at_utc="2026-05-19T00:00:16Z",
        received_at_utc="2026-05-19T00:00:16Z",
        failed_at_utc="2026-05-19T00:00:16Z",
        decode_event_fn=_failing_decode,
        classify_decode_error_fn=_failing_classify,
        raw_capture_writer=writer,
    )
    assert result.last_failure_label == "provider_returned_malformed"
    assert result.last_failure_label in PROVIDER_FAILURE_LABELS
