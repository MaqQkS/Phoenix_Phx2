"""Stage 27.2 pair-detection module-local exception hierarchy and
closed-set assertion helpers.

Stage 27.2 follows the Stage 25 / Stage 26 / Stage 27.1 discipline:
module-local exception types rooted at plain ``Exception``, NOT at
a central PHX2 error registry.

Hierarchy:

    Stage27PairDetectionError(Exception)
    ├── Stage27InvalidPairInputError
    └── Stage27UnknownPairVocabularyError

Every Stage 27.2 pair-detection error type is engineered so that
``str()`` and ``repr()`` of an instance NEVER carries a raw
provider payload blob, a raw secret value, or a raw webhook URL.
Error messages may only reference:

  * the closed-set field name
  * the closed-set vocabulary token kind
  * the offending closed-set token value (which is itself a
    closed-set candidate string, not a raw payload)

The error types do NOT accept a raw provider payload blob as a
constructor argument. The caller must redact at the call site
before raising.

The module-level helpers ``assert_quote_asset`` / ``assert_pair_type``
/ ``assert_bonding_curve_version`` / ``assert_pair_detection_status``
/ ``assert_pair_detection_confidence`` / ``assert_pair_detection_source``
/ ``assert_live_policy`` / ``assert_calibration_lane`` raise
``Stage27UnknownPairVocabularyError`` when given a value outside
the closed-set vocabulary. They are intended for use at the
classifier boundary and for downstream consumers that want to
defensively re-check a closed-set token.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage27.pair_detection_constants import (
    BONDING_CURVE_VERSION_VALUES,
    CALIBRATION_LANE_VALUES,
    LIVE_POLICY_VALUES,
    PAIR_DETECTION_CONFIDENCE_VALUES,
    PAIR_DETECTION_SOURCE_VALUES,
    PAIR_DETECTION_STATUS_VALUES,
    PAIR_TYPE_VALUES,
    QUOTE_ASSET_VALUES,
)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class Stage27PairDetectionError(Exception):
    """Base type for every Stage 27.2 pair-detection violation.

    Module-local; intentionally not a subclass of any central PHX2
    error registry so the prior-stage closed code registries stay
    out of Stage 27.2's surface.
    """


class Stage27InvalidPairInputError(Stage27PairDetectionError):
    """Raised when the classifier receives a structurally invalid input.

    The classifier is tolerant of optional / missing hint fields and
    returns ``UNRESOLVED`` for the no-evidence case. This error is
    reserved for the case where the input is not a
    ``PairDetectionInputRecord`` at all (e.g. ``None`` or a dict).
    """

    def __init__(
        self,
        reason: str,
        *,
        offending_type_name: Optional[str] = None,
    ) -> None:
        self.reason: str = reason
        self.offending_type_name: Optional[str] = offending_type_name
        msg = f"invalid pair-detection input: reason={reason!r}"
        if offending_type_name is not None:
            msg += f" type={offending_type_name!r}"
        super().__init__(msg)


class Stage27UnknownPairVocabularyError(Stage27PairDetectionError):
    """Raised when a closed-set token is outside the locked vocabulary.

    Carries only the closed-set kind tag and the offending token
    string. Never carries a raw payload blob.
    """

    def __init__(self, kind: str, value: str) -> None:
        self.kind: str = kind
        self.value: str = value
        super().__init__(
            f"unknown Stage 27.2 vocabulary token: "
            f"kind={kind!r} value={value!r}"
        )


# ---------------------------------------------------------------------------
# Closed-set assertion helpers
# ---------------------------------------------------------------------------


def assert_quote_asset(value: str) -> str:
    """Return ``value`` if it is a known ``QUOTE_ASSET`` token.

    Raises ``Stage27UnknownPairVocabularyError`` otherwise.
    """
    if value not in QUOTE_ASSET_VALUES:
        raise Stage27UnknownPairVocabularyError("quote_asset", value)
    return value


def assert_pair_type(value: str) -> str:
    """Return ``value`` if it is a known ``PAIR_TYPE`` token."""
    if value not in PAIR_TYPE_VALUES:
        raise Stage27UnknownPairVocabularyError("pair_type", value)
    return value


def assert_bonding_curve_version(value: str) -> str:
    """Return ``value`` if it is a known ``BONDING_CURVE_VERSION`` token."""
    if value not in BONDING_CURVE_VERSION_VALUES:
        raise Stage27UnknownPairVocabularyError(
            "bonding_curve_version", value
        )
    return value


def assert_pair_detection_status(value: str) -> str:
    """Return ``value`` if it is a known ``PAIR_DETECTION_STATUS`` token."""
    if value not in PAIR_DETECTION_STATUS_VALUES:
        raise Stage27UnknownPairVocabularyError(
            "pair_detection_status", value
        )
    return value


def assert_pair_detection_confidence(value: str) -> str:
    """Return ``value`` if it is a known ``PAIR_DETECTION_CONFIDENCE`` token."""
    if value not in PAIR_DETECTION_CONFIDENCE_VALUES:
        raise Stage27UnknownPairVocabularyError(
            "pair_detection_confidence", value
        )
    return value


def assert_pair_detection_source(value: str) -> str:
    """Return ``value`` if it is a known ``PAIR_DETECTION_SOURCE`` token."""
    if value not in PAIR_DETECTION_SOURCE_VALUES:
        raise Stage27UnknownPairVocabularyError(
            "pair_detection_source", value
        )
    return value


def assert_live_policy(value: str) -> str:
    """Return ``value`` if it is a known ``LIVE_POLICY`` token."""
    if value not in LIVE_POLICY_VALUES:
        raise Stage27UnknownPairVocabularyError("live_policy", value)
    return value


def assert_calibration_lane(value: str) -> str:
    """Return ``value`` if it is a known ``CALIBRATION_LANE`` token."""
    if value not in CALIBRATION_LANE_VALUES:
        raise Stage27UnknownPairVocabularyError(
            "calibration_lane", value
        )
    return value
