"""Stage 22 provider-failure classifier (pure function; active in 22.1).

This module owns the single pure mapping from
``ProviderFetchOutcome`` to a closed-set
``PROVIDER_FAILURE_LABELS`` token. It is the only Stage 22.1
production surface that performs runtime logic; every other
Stage 22.1 file is contracts / records / closed-set tokens.

Contract:

  * The classifier reads only the ``status_class`` and
    ``upstream_error_type`` fields of the supplied outcome.
    Other fields (responses, attempt_index) are passed through.
  * The classifier raises ``Stage22ClassifierContractError`` if
    ``outcome.ok is True`` (failure-classifying a successful
    outcome is incoherent), if ``status_class`` is outside
    ``STATUS_CLASSES``, or if ``upstream_error_type`` is outside
    ``UPSTREAM_ERROR_TYPES``.
  * The classifier is pure and deterministic: identical input
    produces identical output.
  * The classifier NEVER reads from the upstream exception's
    ``str``, ``repr``, ``args``, or any other unsanitized
    surface. The contract on the caller is to pre-sanitize the
    upstream exception into a category token from
    ``UPSTREAM_ERROR_TYPES`` before constructing the outcome.

Mapping:

    status_class          upstream_error_type           -> label
    --------------------- ---------------------------- ------
    timeout               (any)                         provider_fetch_timeout
    rate_limit            (any)                         provider_fetch_rate_limited
    server_error          (any)                         provider_fetch_5xx
    client_error          (any except auth_*/rate_*)    provider_fetch_4xx
    auth                  (any)                         provider_fetch_auth
    connection            (any)                         provider_fetch_connection
    malformed             (any)                         provider_returned_malformed
    unknown               (any)                         provider_fetch_other

If ``status_class`` is ``success`` the outcome's ``ok`` field
must be True; failure-classifying a successful outcome raises
``Stage22ClassifierContractError`` regardless of
``upstream_error_type``.

The mapping is deliberately status_class-first: the
``upstream_error_type`` token serves as a secondary axis for
audit / telemetry but does not change the resolved label in
22.1. A future Stage 22.2+ sub-stage MAY refine the mapping
(e.g. distinguish DNS vs TLS within ``connection``); the
contract surface stays stable because both axes remain in the
input shape.
"""

from __future__ import annotations

from PHX2.stage22.constants import (
    PROVIDER_FAILURE_LABEL_FETCH_4XX,
    PROVIDER_FAILURE_LABEL_FETCH_5XX,
    PROVIDER_FAILURE_LABEL_FETCH_AUTH,
    PROVIDER_FAILURE_LABEL_FETCH_CONNECTION,
    PROVIDER_FAILURE_LABEL_FETCH_OTHER,
    PROVIDER_FAILURE_LABEL_FETCH_RATE_LIMITED,
    PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
    PROVIDER_FAILURE_LABEL_RETURNED_MALFORMED,
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
    UPSTREAM_ERROR_TYPES,
)
from PHX2.stage22.errors import Stage22ClassifierContractError
from PHX2.stage22.ingest_contracts import ProviderFetchOutcome


# ---------------------------------------------------------------------------
# Locked status_class -> label mapping
# ---------------------------------------------------------------------------
#
# Stage 22.1 mapping is status_class-first; the upstream error
# type is preserved on the outcome for audit purposes but does
# not refine the resolved label in 22.1.


_STATUS_CLASS_TO_LABEL: dict[str, str] = {
    STATUS_CLASS_TIMEOUT: PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
    STATUS_CLASS_RATE_LIMIT: PROVIDER_FAILURE_LABEL_FETCH_RATE_LIMITED,
    STATUS_CLASS_SERVER_ERROR: PROVIDER_FAILURE_LABEL_FETCH_5XX,
    STATUS_CLASS_CLIENT_ERROR: PROVIDER_FAILURE_LABEL_FETCH_4XX,
    STATUS_CLASS_AUTH: PROVIDER_FAILURE_LABEL_FETCH_AUTH,
    STATUS_CLASS_CONNECTION: PROVIDER_FAILURE_LABEL_FETCH_CONNECTION,
    STATUS_CLASS_MALFORMED: PROVIDER_FAILURE_LABEL_RETURNED_MALFORMED,
    STATUS_CLASS_UNKNOWN: PROVIDER_FAILURE_LABEL_FETCH_OTHER,
}


def classify_failure(*, outcome: ProviderFetchOutcome) -> str:
    """Map a ``ProviderFetchOutcome`` to a closed-set failure label.

    Returns one of ``PROVIDER_FAILURE_LABELS``.

    Raises ``Stage22ClassifierContractError`` when:

      * ``outcome.ok`` is True (failure-classifying a successful
        outcome is incoherent), or
      * ``outcome.status_class`` is not a member of
        ``STATUS_CLASSES``, or
      * ``outcome.status_class`` is ``success`` (paired with the
        ``ok is True`` check; a successful status class cannot
        produce a failure label), or
      * ``outcome.upstream_error_type`` is not a member of
        ``UPSTREAM_ERROR_TYPES``.

    The function is pure: identical input produces identical
    output. No I/O, no logging, no env reads, no exception
    introspection.
    """
    if outcome.ok:
        raise Stage22ClassifierContractError(
            "classify_failure called on a successful outcome "
            "(outcome.ok is True)"
        )
    status_class = outcome.status_class
    upstream_error_type = outcome.upstream_error_type
    if status_class not in STATUS_CLASSES:
        raise Stage22ClassifierContractError(
            "classify_failure rejected unknown status_class for field "
            "'status_class'"
        )
    if status_class == STATUS_CLASS_SUCCESS:
        raise Stage22ClassifierContractError(
            "classify_failure rejected status_class 'success' on a "
            "non-ok outcome"
        )
    if upstream_error_type not in UPSTREAM_ERROR_TYPES:
        raise Stage22ClassifierContractError(
            "classify_failure rejected unknown upstream_error_type for "
            "field 'upstream_error_type'"
        )
    # The mapping is exhaustive over STATUS_CLASSES minus ``success``;
    # a missing entry would mean the closed-set or the table fell
    # out of sync, which the tests pin.
    return _STATUS_CLASS_TO_LABEL[status_class]


__all__ = [
    "classify_failure",
]
