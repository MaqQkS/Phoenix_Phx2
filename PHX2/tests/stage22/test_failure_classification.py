"""Stage 22.1 failure classifier tests.

Pins the closed-set behavior of ``classify_failure``:

  * Each known ``status_class`` (other than ``success``) maps to
    the expected ``PROVIDER_FAILURE_LABELS`` token.
  * Every label in ``PROVIDER_FAILURE_LABELS`` is reachable from
    at least one classifier input.
  * Out-of-set inputs raise ``Stage22ClassifierContractError``.
  * Successful outcomes (``ok=True``) raise rather than returning.
  * The classifier is pure / deterministic.
  * The classifier output is always a member of
    ``PROVIDER_FAILURE_LABELS``.
"""

from __future__ import annotations

import pytest

from PHX2.stage22.constants import (
    PROVIDER_FAILURE_LABELS,
    STATUS_CLASS_AUTH,
    STATUS_CLASS_CLIENT_ERROR,
    STATUS_CLASS_CONNECTION,
    STATUS_CLASS_MALFORMED,
    STATUS_CLASS_RATE_LIMIT,
    STATUS_CLASS_SERVER_ERROR,
    STATUS_CLASS_SUCCESS,
    STATUS_CLASS_TIMEOUT,
    STATUS_CLASS_UNKNOWN,
    STATUS_CLASSES,
    UPSTREAM_ERROR_TYPE_AUTH_ERROR,
    UPSTREAM_ERROR_TYPE_CLIENT_ERROR,
    UPSTREAM_ERROR_TYPE_CONNECTION_REFUSED,
    UPSTREAM_ERROR_TYPE_DNS_ERROR,
    UPSTREAM_ERROR_TYPE_MALFORMED_RESPONSE,
    UPSTREAM_ERROR_TYPE_NONE,
    UPSTREAM_ERROR_TYPE_RATE_LIMITED,
    UPSTREAM_ERROR_TYPE_SERVER_ERROR,
    UPSTREAM_ERROR_TYPE_TIMEOUT,
    UPSTREAM_ERROR_TYPE_TLS_ERROR,
    UPSTREAM_ERROR_TYPE_UNKNOWN,
    UPSTREAM_ERROR_TYPES,
)
from PHX2.stage22.errors import Stage22ClassifierContractError
from PHX2.stage22.failure_classification import classify_failure
from PHX2.stage22.ingest_contracts import ProviderFetchOutcome


def _make_outcome(
    *,
    ok: bool = False,
    status_class: str = STATUS_CLASS_TIMEOUT,
    upstream_error_type: str = UPSTREAM_ERROR_TYPE_TIMEOUT,
    attempt_index: int = 0,
) -> ProviderFetchOutcome:
    return ProviderFetchOutcome(
        ok=ok,
        responses=(),
        status_class=status_class,
        upstream_error_type=upstream_error_type,
        provider_attempt_index=attempt_index,
    )


# ---------------------------------------------------------------------------
# Mapping per status_class
# ---------------------------------------------------------------------------


def test_timeout_status_class_maps_to_fetch_timeout_label():
    out = _make_outcome(
        status_class=STATUS_CLASS_TIMEOUT,
        upstream_error_type=UPSTREAM_ERROR_TYPE_TIMEOUT,
    )
    assert classify_failure(outcome=out) == "provider_fetch_timeout"


def test_rate_limit_status_class_maps_to_rate_limited_label():
    out = _make_outcome(
        status_class=STATUS_CLASS_RATE_LIMIT,
        upstream_error_type=UPSTREAM_ERROR_TYPE_RATE_LIMITED,
    )
    assert classify_failure(outcome=out) == "provider_fetch_rate_limited"


def test_server_error_status_class_maps_to_5xx_label():
    out = _make_outcome(
        status_class=STATUS_CLASS_SERVER_ERROR,
        upstream_error_type=UPSTREAM_ERROR_TYPE_SERVER_ERROR,
    )
    assert classify_failure(outcome=out) == "provider_fetch_5xx"


def test_client_error_status_class_maps_to_4xx_label():
    out = _make_outcome(
        status_class=STATUS_CLASS_CLIENT_ERROR,
        upstream_error_type=UPSTREAM_ERROR_TYPE_CLIENT_ERROR,
    )
    assert classify_failure(outcome=out) == "provider_fetch_4xx"


def test_auth_status_class_maps_to_auth_label():
    out = _make_outcome(
        status_class=STATUS_CLASS_AUTH,
        upstream_error_type=UPSTREAM_ERROR_TYPE_AUTH_ERROR,
    )
    assert classify_failure(outcome=out) == "provider_fetch_auth"


def test_connection_status_class_maps_to_connection_label():
    out = _make_outcome(
        status_class=STATUS_CLASS_CONNECTION,
        upstream_error_type=UPSTREAM_ERROR_TYPE_CONNECTION_REFUSED,
    )
    assert classify_failure(outcome=out) == "provider_fetch_connection"


def test_malformed_status_class_maps_to_returned_malformed_label():
    out = _make_outcome(
        status_class=STATUS_CLASS_MALFORMED,
        upstream_error_type=UPSTREAM_ERROR_TYPE_MALFORMED_RESPONSE,
    )
    assert classify_failure(outcome=out) == "provider_returned_malformed"


def test_unknown_status_class_maps_to_fetch_other_label():
    out = _make_outcome(
        status_class=STATUS_CLASS_UNKNOWN,
        upstream_error_type=UPSTREAM_ERROR_TYPE_UNKNOWN,
    )
    assert classify_failure(outcome=out) == "provider_fetch_other"


# ---------------------------------------------------------------------------
# Cross-axis coverage: each label is reachable from at least one input combo
# ---------------------------------------------------------------------------


def test_every_provider_failure_label_is_reachable():
    """Drives each known label from at least one classifier input combo,
    so no label is dead in the 22.1 mapping table.
    """
    reachable_pairs: dict[str, tuple[str, str]] = {
        "provider_fetch_timeout": (
            STATUS_CLASS_TIMEOUT,
            UPSTREAM_ERROR_TYPE_TIMEOUT,
        ),
        "provider_fetch_rate_limited": (
            STATUS_CLASS_RATE_LIMIT,
            UPSTREAM_ERROR_TYPE_RATE_LIMITED,
        ),
        "provider_fetch_5xx": (
            STATUS_CLASS_SERVER_ERROR,
            UPSTREAM_ERROR_TYPE_SERVER_ERROR,
        ),
        "provider_fetch_4xx": (
            STATUS_CLASS_CLIENT_ERROR,
            UPSTREAM_ERROR_TYPE_CLIENT_ERROR,
        ),
        "provider_fetch_connection": (
            STATUS_CLASS_CONNECTION,
            UPSTREAM_ERROR_TYPE_TLS_ERROR,
        ),
        "provider_fetch_auth": (
            STATUS_CLASS_AUTH,
            UPSTREAM_ERROR_TYPE_AUTH_ERROR,
        ),
        "provider_fetch_other": (
            STATUS_CLASS_UNKNOWN,
            UPSTREAM_ERROR_TYPE_UNKNOWN,
        ),
        "provider_returned_malformed": (
            STATUS_CLASS_MALFORMED,
            UPSTREAM_ERROR_TYPE_MALFORMED_RESPONSE,
        ),
    }
    # Every locked label must have a reachable input pair.
    for label in PROVIDER_FAILURE_LABELS:
        assert label in reachable_pairs, (
            f"label {label!r} has no reachable input pair in test"
        )
    # Each input pair drives its expected label.
    for label, (status_class, upstream_error_type) in reachable_pairs.items():
        out = _make_outcome(
            status_class=status_class,
            upstream_error_type=upstream_error_type,
        )
        assert classify_failure(outcome=out) == label


def test_classifier_output_is_always_a_locked_label():
    """For every valid (status_class != success, upstream_error_type)
    combination, the classifier output must be a member of
    ``PROVIDER_FAILURE_LABELS``.
    """
    label_set = set(PROVIDER_FAILURE_LABELS)
    for status_class in STATUS_CLASSES:
        if status_class == STATUS_CLASS_SUCCESS:
            continue
        for upstream_error_type in UPSTREAM_ERROR_TYPES:
            out = _make_outcome(
                status_class=status_class,
                upstream_error_type=upstream_error_type,
            )
            label = classify_failure(outcome=out)
            assert label in label_set, (
                f"classify_failure({status_class!r}, "
                f"{upstream_error_type!r}) -> {label!r} which is "
                "not a member of PROVIDER_FAILURE_LABELS"
            )


# ---------------------------------------------------------------------------
# Determinism / purity
# ---------------------------------------------------------------------------


def test_classifier_is_deterministic():
    out = _make_outcome(
        status_class=STATUS_CLASS_TIMEOUT,
        upstream_error_type=UPSTREAM_ERROR_TYPE_TIMEOUT,
    )
    results = {classify_failure(outcome=out) for _ in range(20)}
    assert results == {"provider_fetch_timeout"}


# ---------------------------------------------------------------------------
# Contract violations
# ---------------------------------------------------------------------------


def test_classifier_rejects_successful_outcome():
    out = _make_outcome(
        ok=True,
        status_class=STATUS_CLASS_SUCCESS,
        upstream_error_type=UPSTREAM_ERROR_TYPE_NONE,
    )
    with pytest.raises(Stage22ClassifierContractError):
        classify_failure(outcome=out)


def test_classifier_rejects_success_status_class_with_non_ok():
    """``status_class == 'success'`` paired with ``ok=False`` is a
    contract violation: the adapter would have produced an
    inconsistent outcome.
    """
    out = _make_outcome(
        ok=False,
        status_class=STATUS_CLASS_SUCCESS,
        upstream_error_type=UPSTREAM_ERROR_TYPE_UNKNOWN,
    )
    with pytest.raises(Stage22ClassifierContractError):
        classify_failure(outcome=out)


def test_classifier_rejects_unknown_status_class():
    out = _make_outcome(
        status_class="this_token_is_not_in_the_locked_set",
        upstream_error_type=UPSTREAM_ERROR_TYPE_UNKNOWN,
    )
    with pytest.raises(Stage22ClassifierContractError):
        classify_failure(outcome=out)


def test_classifier_rejects_unknown_upstream_error_type():
    out = _make_outcome(
        status_class=STATUS_CLASS_TIMEOUT,
        upstream_error_type="this_token_is_not_in_the_locked_set",
    )
    with pytest.raises(Stage22ClassifierContractError):
        classify_failure(outcome=out)


def test_classifier_keyword_only_signature():
    """The classifier accepts ``outcome`` as a keyword-only argument.

    Calling it positionally would be an API surface drift; the
    signature pin enforces keyword-only discipline matching the
    Stage 21 contract pattern.
    """
    out = _make_outcome()
    # Positional call should fail with TypeError per kwonly signature.
    with pytest.raises(TypeError):
        classify_failure(out)  # type: ignore[misc]
