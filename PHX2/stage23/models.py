"""Stage 23 immutable models and deterministic hash helpers (foundation only at 23.1).

This module ships the typed ``NamedTuple`` records that every
Stage 23.2+ filter / runner / artifact writer must satisfy, plus
the canonical-JSON deterministic hash helpers used to derive
``input_hash`` and ``evaluation_hash``.

Records:

  * ``Stage23FilterInput``       -- normalized observation snapshot
                                    for one event / token at one
                                    moment in time.
  * ``Stage23FilterResult``      -- one filter's verdict for one
                                    input. Label + data_status +
                                    reason codes + numeric features
                                    + missing features.
  * ``Stage23FilterEvaluation``  -- wrapper bundling input + result
                                    + provenance hashes + timestamps.

Hashing:

  * ``canonical_json``           -- canonical UTF-8 JSON encoding
                                    (sorted keys, no whitespace).
  * ``stage23_hash``             -- sha256 hex of a canonical JSON
                                    encoding of an arbitrary
                                    canonicalizable value.
  * ``compute_input_hash``       -- input-canonical hash for a
                                    ``Stage23FilterInput``.
  * ``compute_evaluation_hash``  -- evaluation-canonical hash for
                                    a ``Stage23FilterResult`` bound
                                    to a ``Stage23FilterInput``.

Design notes:

  * All records are ``NamedTuple`` so they are immutable, hashable
    by value, and trivially serializable. ``setattr`` raises.
  * Hashes are derived from a canonical-JSON encoding with sorted
    keys, so dict ordering does not affect the hash.
  * ``input_hash`` and ``evaluation_hash`` cover DISJOINT field
    sets: the input hash covers the input identity, and the
    evaluation hash covers (input_hash, filter_name,
    filter_family, filter_version, threshold_version, label,
    data_status, reason_codes, numeric_features,
    missing_features). Unstable runtime-only fields
    (``created_at_utc``) are NOT included in either hash.
  * Same logical input -> same input hash. Same evaluation body
    -> same evaluation hash. Changed label / reason / features
    changes the evaluation hash. Verified by the Stage 23.1
    model tests.

This module imports only stdlib (``hashlib`` / ``json``) plus the
Stage 23 constants and errors. It does NOT import any network /
RPC / messaging / DB / scheduler / secrets library, does NOT read
the process environment, does NOT define a CLI surface, and
contains no top-level I/O. It does NOT import Stage 21 or Stage
22 modules.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Mapping, NamedTuple

from PHX2.stage23.constants import (
    DATA_STATUSES,
    FILTER_FAMILIES,
    LABELS,
)
from PHX2.stage23.errors import Stage23ContractError


# ---------------------------------------------------------------------------
# Stage23FilterInput
# ---------------------------------------------------------------------------


class Stage23FilterInput(NamedTuple):
    """Normalized observation snapshot for one event / token.

    Stage 23 reads Stage 22-shaped artifacts; the input reader
    projects a single JSONL row into this immutable record.
    Every field is either a closed-set token, a short non-secret
    string, an int, or a flat mapping of safe scalar values.

    Fields:

      * ``token_mint``         -- token mint identifier. May be the
                                  empty string when the upstream
                                  artifact did not carry one.
      * ``provider_id``        -- short non-secret operator label
                                  (e.g. ``"helius"``). Required
                                  non-empty.
      * ``event_id``           -- Stage 22-derived stable normalized
                                  event id (``"evt_<24 hex>"``). May
                                  be the empty string for synthetic
                                  fixtures that do not carry one.
      * ``captured_event_id``  -- caller-supplied id from the
                                  upstream Stage 22 ``raw_capture``
                                  envelope. Audit-only; may be the
                                  empty string.
      * ``observed_at_utc``    -- ISO-8601 UTC string carried from
                                  the upstream artifact. May be the
                                  empty string.
      * ``slot``               -- slot number when present; -1 when
                                  absent (sentinel because
                                  ``Optional[int]`` would break the
                                  deterministic-hash contract).
      * ``signature``          -- transaction signature when present;
                                  empty string when absent.
      * ``payload_summary``    -- frozen flat mapping of safe scalar
                                  values projected from the upstream
                                  artifact. May be empty.
      * ``missing_fields``     -- tuple of preserved-field names that
                                  the upstream artifact did NOT
                                  carry. The reader populates this
                                  so downstream filters can reason
                                  about input completeness without
                                  re-checking source absence.
    """

    token_mint: str
    provider_id: str
    event_id: str
    captured_event_id: str
    observed_at_utc: str
    slot: int
    signature: str
    payload_summary: Mapping[str, object]
    missing_fields: tuple[str, ...]


# ---------------------------------------------------------------------------
# Stage23FilterResult
# ---------------------------------------------------------------------------


class Stage23FilterResult(NamedTuple):
    """One filter's verdict on one ``Stage23FilterInput``.

    Stage 23.2+ filters build instances of this record by running
    a pure function over a ``Stage23FilterInput``. Stage 23.1
    ships no filter logic; only the record shape is locked.

    Fields:

      * ``filter_name``       -- short non-secret filter id (e.g.
                                 ``"holder_top1_concentration"``).
                                 Required non-empty.
      * ``filter_family``     -- one of ``FILTER_FAMILIES``. The
                                 family the filter belongs to.
      * ``filter_version``    -- version string for the filter's
                                 implementation. Bumped when the
                                 filter logic changes.
      * ``threshold_version`` -- version string for the threshold
                                 configuration the filter consumed.
                                 Bumped independently of
                                 ``filter_version`` when ONLY the
                                 thresholds change.
      * ``label``             -- one of ``LABELS``.
      * ``data_status``       -- one of ``DATA_STATUSES``.
      * ``reason_codes``      -- tuple of short non-secret reason
                                 codes that explain the label.
                                 Deterministic (tuple, not list /
                                 set). May be empty.
      * ``numeric_features``  -- mapping of computed numeric
                                 features (e.g. ``"top1_pct": 0.42``).
                                 Each value is a float / int / bool.
                                 Hashing canonicalizes key order so
                                 dict insertion order does not
                                 affect the evaluation hash.
      * ``missing_features``  -- tuple of input-feature names that
                                 were absent from the input. Locked
                                 deterministic order (caller
                                 supplies it sorted).
    """

    filter_name: str
    filter_family: str
    filter_version: str
    threshold_version: str
    label: str
    data_status: str
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    missing_features: tuple[str, ...]


# ---------------------------------------------------------------------------
# Stage23FilterEvaluation
# ---------------------------------------------------------------------------


class Stage23FilterEvaluation(NamedTuple):
    """Bundled input + result + provenance hashes + timestamp.

    Every Stage 23.2+ filter produces one of these per
    (input, filter) pair. Stage 23.1 ships only the record
    shape; no filter constructs instances of it.

    Fields:

      * ``filter_input``    -- the ``Stage23FilterInput`` the
                               filter consumed.
      * ``filter_result``   -- the ``Stage23FilterResult`` the
                               filter produced.
      * ``input_hash``      -- deterministic hash of the input
                               (sha256 hex over canonical JSON).
                               Identical across runs for the
                               same logical input.
      * ``evaluation_hash`` -- deterministic hash of the
                               (input_hash, result_body) pair.
                               Identical across runs for the
                               same logical evaluation.
      * ``created_at_utc``  -- ISO-8601 UTC string. Injected by
                               the caller from an injected clock
                               in tests; NOT included in either
                               hash so re-runs at different wall
                               times produce identical hashes.
    """

    filter_input: Stage23FilterInput
    filter_result: Stage23FilterResult
    input_hash: str
    evaluation_hash: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Closed-set helpers
# ---------------------------------------------------------------------------


def assert_label_in_closed_set(label: str) -> None:
    """Raise ``Stage23ContractError`` if ``label`` is not a member of
    ``LABELS``.
    """
    if label not in LABELS:
        raise Stage23ContractError(
            f"label {label!r} is not a closed-set Stage 23 label"
        )


def assert_data_status_in_closed_set(data_status: str) -> None:
    """Raise ``Stage23ContractError`` if ``data_status`` is not a member
    of ``DATA_STATUSES``.
    """
    if data_status not in DATA_STATUSES:
        raise Stage23ContractError(
            f"data_status {data_status!r} is not a closed-set Stage 23 "
            "data_status"
        )


def assert_filter_family_in_closed_set(filter_family: str) -> None:
    """Raise ``Stage23ContractError`` if ``filter_family`` is not a
    member of ``FILTER_FAMILIES``.
    """
    if filter_family not in FILTER_FAMILIES:
        raise Stage23ContractError(
            f"filter_family {filter_family!r} is not a closed-set Stage "
            "23 filter family"
        )


# ---------------------------------------------------------------------------
# Canonical-JSON / hash helpers
# ---------------------------------------------------------------------------


def _canonicalize(value: object) -> object:
    """Reduce ``value`` to a json.dumps-able shape with deterministic ordering.

    Supported value types:

      * ``str`` / ``int`` / ``bool`` / ``None``
      * ``float`` (must be finite)
      * ``list`` / ``tuple``      -- canonicalized element-wise; emitted
                                     as a list.
      * ``Mapping``               -- canonicalized recursively; emitted
                                     as a dict with sorted keys. Keys
                                     must be strings.

    Any other type raises ``Stage23ContractError``.

    NaN / Infinity / -Infinity raise: they cannot round-trip
    through strict JSON.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Stage23ContractError(
                "non-finite float (NaN / Infinity) cannot be canonicalized"
            )
        return value
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise Stage23ContractError(
                    "canonicalize requires string mapping keys; got "
                    f"{type(key).__name__}"
                )
            out[key] = _canonicalize(val)
        return out
    raise Stage23ContractError(
        f"canonicalize cannot encode type {type(value).__name__}"
    )


def canonical_json(value: object) -> str:
    """Return the canonical JSON encoding of ``value``.

    Canonical form: sorted keys, no whitespace separators,
    ASCII-safe (non-ASCII characters are escaped via the JSON
    ``\\uXXXX`` form).
    """
    reduced = _canonicalize(value)
    return json.dumps(
        reduced,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def stage23_hash(value: object) -> str:
    """Return the sha256 hex digest of ``canonical_json(value)``."""
    encoded = canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# Hash builders for the Stage 23 evaluation surface
# ---------------------------------------------------------------------------


def _input_canonical_body(filter_input: Stage23FilterInput) -> dict[str, object]:
    """Build the canonical body that ``input_hash`` covers.

    The body is the input projection used as the dedupe identity
    for an evaluation. ``missing_fields`` is included so an input
    that was reconstructed from a less-complete upstream artifact
    hashes differently from one that carried every preserved
    field.
    """
    return {
        "token_mint": filter_input.token_mint,
        "provider_id": filter_input.provider_id,
        "event_id": filter_input.event_id,
        "captured_event_id": filter_input.captured_event_id,
        "observed_at_utc": filter_input.observed_at_utc,
        "slot": filter_input.slot,
        "signature": filter_input.signature,
        "payload_summary": _canonicalize(filter_input.payload_summary),
        "missing_fields": list(filter_input.missing_fields),
    }


def _result_canonical_body(filter_result: Stage23FilterResult) -> dict[str, object]:
    """Build the canonical body that ``evaluation_hash`` covers (sans input_hash).

    The result body intentionally separates ``filter_name`` /
    ``filter_family`` / ``filter_version`` / ``threshold_version``
    so a label change on the same filter version is a hash
    change, and a threshold-version bump alone is also a hash
    change.
    """
    return {
        "filter_name": filter_result.filter_name,
        "filter_family": filter_result.filter_family,
        "filter_version": filter_result.filter_version,
        "threshold_version": filter_result.threshold_version,
        "label": filter_result.label,
        "data_status": filter_result.data_status,
        "reason_codes": list(filter_result.reason_codes),
        "numeric_features": _canonicalize(filter_result.numeric_features),
        "missing_features": list(filter_result.missing_features),
    }


def compute_input_hash(filter_input: Stage23FilterInput) -> str:
    """Return the deterministic ``input_hash`` for ``filter_input``."""
    return stage23_hash(_input_canonical_body(filter_input))


def compute_evaluation_hash(
    *,
    filter_input: Stage23FilterInput,
    filter_result: Stage23FilterResult,
) -> str:
    """Return the deterministic ``evaluation_hash`` for an (input, result) pair.

    The evaluation hash binds the result body to the input hash
    so two different inputs producing the same result body do
    not collide on a single evaluation hash.
    """
    body: dict[str, object] = {
        "input_hash": compute_input_hash(filter_input),
        "result": _result_canonical_body(filter_result),
    }
    return stage23_hash(body)


# ---------------------------------------------------------------------------
# Constructors with closed-set validation
# ---------------------------------------------------------------------------


def build_filter_result(
    *,
    filter_name: str,
    filter_family: str,
    filter_version: str,
    threshold_version: str,
    label: str,
    data_status: str,
    reason_codes: tuple[str, ...],
    numeric_features: Mapping[str, object],
    missing_features: tuple[str, ...],
) -> Stage23FilterResult:
    """Build a ``Stage23FilterResult`` with closed-set validation.

    Validates that ``filter_family`` / ``label`` / ``data_status``
    are members of their closed sets, and that the required short
    non-secret string fields are non-empty. Raises
    ``Stage23ContractError`` on a violation.
    """
    if not isinstance(filter_name, str) or filter_name == "":
        raise Stage23ContractError("filter_name must be a non-empty string")
    assert_filter_family_in_closed_set(filter_family)
    if not isinstance(filter_version, str) or filter_version == "":
        raise Stage23ContractError(
            "filter_version must be a non-empty string"
        )
    if not isinstance(threshold_version, str) or threshold_version == "":
        raise Stage23ContractError(
            "threshold_version must be a non-empty string"
        )
    assert_label_in_closed_set(label)
    assert_data_status_in_closed_set(data_status)
    if not isinstance(reason_codes, tuple):
        raise Stage23ContractError("reason_codes must be a tuple")
    for code in reason_codes:
        if not isinstance(code, str) or code == "":
            raise Stage23ContractError(
                "each reason_code must be a non-empty string"
            )
    if not isinstance(numeric_features, Mapping):
        raise Stage23ContractError("numeric_features must be a mapping")
    if not isinstance(missing_features, tuple):
        raise Stage23ContractError("missing_features must be a tuple")
    for name in missing_features:
        if not isinstance(name, str) or name == "":
            raise Stage23ContractError(
                "each missing_feature name must be a non-empty string"
            )
    return Stage23FilterResult(
        filter_name=filter_name,
        filter_family=filter_family,
        filter_version=filter_version,
        threshold_version=threshold_version,
        label=label,
        data_status=data_status,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        missing_features=missing_features,
    )


def build_filter_evaluation(
    *,
    filter_input: Stage23FilterInput,
    filter_result: Stage23FilterResult,
    created_at_utc: str,
) -> Stage23FilterEvaluation:
    """Build a ``Stage23FilterEvaluation`` with deterministic hashes.

    The hashes are computed once at construction time and stored
    on the record. ``created_at_utc`` is required non-empty so
    the record's audit-time field carries a caller-injected clock
    value.
    """
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage23ContractError(
            "created_at_utc must be a non-empty string"
        )
    input_hash = compute_input_hash(filter_input)
    evaluation_hash = compute_evaluation_hash(
        filter_input=filter_input,
        filter_result=filter_result,
    )
    return Stage23FilterEvaluation(
        filter_input=filter_input,
        filter_result=filter_result,
        input_hash=input_hash,
        evaluation_hash=evaluation_hash,
        created_at_utc=created_at_utc,
    )


__all__ = [
    "Stage23FilterEvaluation",
    "Stage23FilterInput",
    "Stage23FilterResult",
    "assert_data_status_in_closed_set",
    "assert_filter_family_in_closed_set",
    "assert_label_in_closed_set",
    "build_filter_evaluation",
    "build_filter_result",
    "canonical_json",
    "compute_evaluation_hash",
    "compute_input_hash",
    "stage23_hash",
]
