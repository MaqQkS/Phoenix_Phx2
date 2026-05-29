"""Stage 30.7.1 ATH-context models tests.

Covers the closed-set vocabularies + membership helpers, the lenient
``Stage30_7AthContextEvidence`` carrier (no construction validation),
the strict ``Stage30_7AthContextProjection`` output (construction-time
closed-set validation, ``runtime_consumable`` must be ``False``), the
frozen-dataclass immutability of both, the forbidden-field-name guard,
and the absence of any forbidden field name on either dataclass.

Pure / offline. No live call, no provider, no Discord, no env, no
filesystem, no network.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_7_ath_context_models import (
    ATH_BASIS_MARKET_CAP_OBSERVED,
    ATH_BASIS_NONE,
    ATH_BASIS_PRICE_DERIVED,
    ATH_BASIS_VALUES,
    ATH_DISPLAY_UNKNOWN,
    ATH_REASON_KNOWN_USD_MARKET_CAP,
    ATH_REASON_UNKNOWN_INVALID_INPUT,
    ATH_REASON_VALUES,
    ATH_SOURCE_STATUS_CONFLICTING,
    ATH_SOURCE_STATUS_ERROR,
    ATH_SOURCE_STATUS_PRESENT,
    ATH_SOURCE_STATUS_STALE,
    ATH_SOURCE_STATUS_UNAVAILABLE,
    ATH_SOURCE_STATUS_VALUES,
    ATH_STATUS_KNOWN,
    ATH_STATUS_UNKNOWN,
    ATH_STATUS_UNVERIFIED,
    ATH_STATUS_VALUES,
    ATH_UNIT_SOL,
    ATH_UNIT_UNKNOWN,
    ATH_UNIT_USD,
    ATH_UNIT_VALUES,
    FORBIDDEN_RECORD_FIELD_NAMES,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION,
    STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION,
    STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
    STAGE30_7_1_MINOR_VERSION,
    Stage30_7AthContextError,
    Stage30_7AthContextEvidence,
    Stage30_7AthContextProjection,
    evidence_field_names,
    is_ath_basis_value,
    is_ath_reason_value,
    is_ath_source_status_value,
    is_ath_status_value,
    is_ath_unit_value,
    is_forbidden_record_field_name,
    projection_field_names,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_projection_kwargs() -> dict:
    return dict(
        schema_version=STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION,
        ath_status=ATH_STATUS_KNOWN,
        source_status=ATH_SOURCE_STATUS_PRESENT,
        ath_unit=ATH_UNIT_USD,
        basis=ATH_BASIS_MARKET_CAP_OBSERVED,
        ath_value="83000",
        ath_display_text="$83k",
        reason=ATH_REASON_KNOWN_USD_MARKET_CAP,
        should_display_value=True,
        should_trust_for_drawdown=True,
        projection_version=STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION,
        runtime_consumable=False,
    )


# ---------------------------------------------------------------------------
# 1. Versions + sentinel
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_7_1_MINOR_VERSION == "30.7.1"


def test_schema_and_projection_versions_pinned() -> None:
    assert STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION == (
        "stage30_7_1_v0_ath_context"
    )
    assert STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION == (
        "stage30_7_ath_context_projection_v0"
    )


def test_display_unknown_sentinel_and_default_unit() -> None:
    assert ATH_DISPLAY_UNKNOWN == "Unknown"
    assert STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT == "USD"


# ---------------------------------------------------------------------------
# 2. Closed sets + membership helpers
# ---------------------------------------------------------------------------


def test_ath_status_closed_set() -> None:
    assert ATH_STATUS_VALUES == (
        "ATH_KNOWN",
        "ATH_UNVERIFIED",
        "ATH_UNKNOWN",
    )
    for token in ATH_STATUS_VALUES:
        assert is_ath_status_value(token)
    assert not is_ath_status_value("ATH_MAYBE")
    assert not is_ath_status_value(None)
    assert not is_ath_status_value(123)


def test_ath_source_status_closed_set() -> None:
    assert ATH_SOURCE_STATUS_VALUES == (
        "PRESENT",
        "UNAVAILABLE",
        "ERROR",
        "STALE",
        "CONFLICTING",
    )
    for token in ATH_SOURCE_STATUS_VALUES:
        assert is_ath_source_status_value(token)
    assert not is_ath_source_status_value("OK")
    assert not is_ath_source_status_value(None)


def test_ath_unit_closed_set() -> None:
    assert ATH_UNIT_VALUES == ("USD", "SOL", "UNKNOWN")
    for token in ATH_UNIT_VALUES:
        assert is_ath_unit_value(token)
    assert not is_ath_unit_value("EUR")
    assert not is_ath_unit_value(None)


def test_ath_basis_closed_set() -> None:
    assert ATH_BASIS_VALUES == (
        "ATH_MARKET_CAP_OBSERVED",
        "ATH_PRICE_DERIVED",
        "ATH_BASIS_NONE",
    )
    for token in ATH_BASIS_VALUES:
        assert is_ath_basis_value(token)
    assert not is_ath_basis_value("ATH_GUESSED")
    assert not is_ath_basis_value(None)


def test_ath_reason_closed_set() -> None:
    assert ATH_REASON_VALUES == (
        "ATH_KNOWN_USD_MARKET_CAP",
        "ATH_UNVERIFIED_PRICE_DERIVED",
        "ATH_UNKNOWN_SOURCE_UNAVAILABLE",
        "ATH_UNKNOWN_SOURCE_ERROR",
        "ATH_UNKNOWN_SOURCE_STALE",
        "ATH_UNKNOWN_SOURCE_CONFLICTING",
        "ATH_UNKNOWN_VALUE_MISSING",
        "ATH_UNKNOWN_VALUE_NOT_NUMERIC",
        "ATH_UNKNOWN_VALUE_NOT_FINITE",
        "ATH_UNKNOWN_VALUE_NON_POSITIVE",
        "ATH_UNKNOWN_UNIT_UNSUPPORTED",
        "ATH_UNKNOWN_UNIT_INCOMPATIBLE",
        "ATH_UNKNOWN_REDACTION_UNSAFE",
        "ATH_UNKNOWN_INVALID_INPUT",
    )
    for token in ATH_REASON_VALUES:
        assert is_ath_reason_value(token)
    assert not is_ath_reason_value("ATH_UNKNOWN_WHATEVER")
    assert not is_ath_reason_value(None)


# ---------------------------------------------------------------------------
# 3. Evidence is a LENIENT frozen carrier
# ---------------------------------------------------------------------------


def test_evidence_defaults_are_safe() -> None:
    ev = Stage30_7AthContextEvidence()
    assert ev.ath_value is None
    assert ev.ath_unit is None
    assert ev.source_status is None
    assert ev.basis is None
    # Fail-closed default: an omitted redaction proof is NOT trusted, so
    # the default is False (an evidence built without explicitly
    # asserting redaction_safe=True can never project to ATH_KNOWN).
    assert ev.redaction_safe is False
    assert ev.source_label is None
    assert ev.observed_at_utc is None


def test_evidence_accepts_valid_known_inputs() -> None:
    ev = Stage30_7AthContextEvidence(
        ath_value="125000",
        ath_unit=ATH_UNIT_USD,
        source_status=ATH_SOURCE_STATUS_PRESENT,
        basis=ATH_BASIS_MARKET_CAP_OBSERVED,
        redaction_safe=True,
        source_label="ath_offline_fake",
        observed_at_utc="2026-05-29T00:00:00Z",
    )
    assert ev.ath_value == "125000"
    assert ev.ath_unit == "USD"


def test_evidence_is_lenient_and_does_not_validate() -> None:
    # A bad value / bad unit / bad source status / bad basis must NOT
    # raise at construction (it fails closed in the projection adapter).
    ev = Stage30_7AthContextEvidence(
        ath_value=object(),
        ath_unit="EUR",
        source_status="WHATEVER",
        basis="ATH_GUESSED",
        redaction_safe="yes",
    )
    assert ev.ath_unit == "EUR"
    assert ev.source_status == "WHATEVER"
    assert ev.basis == "ATH_GUESSED"


def test_evidence_is_frozen() -> None:
    ev = Stage30_7AthContextEvidence()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.ath_value = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. Projection is a STRICT frozen output
# ---------------------------------------------------------------------------


def test_valid_projection_constructs() -> None:
    proj = Stage30_7AthContextProjection(**_valid_projection_kwargs())
    assert proj.ath_status == ATH_STATUS_KNOWN
    assert proj.ath_display_text == "$83k"
    assert proj.runtime_consumable is False


def test_projection_is_frozen() -> None:
    proj = Stage30_7AthContextProjection(**_valid_projection_kwargs())
    with pytest.raises(dataclasses.FrozenInstanceError):
        proj.ath_status = ATH_STATUS_UNKNOWN  # type: ignore[misc]


def test_projection_runtime_consumable_true_rejected() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["runtime_consumable"] = True
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "RUNTIME_CONSUMABLE_MUST_BE_FALSE"


def test_projection_runtime_consumable_non_bool_rejected() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["runtime_consumable"] = 0
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "RUNTIME_CONSUMABLE_NOT_BOOL"


def test_projection_rejects_unknown_status() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["ath_status"] = "ATH_MAYBE"
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "ATH_STATUS_INVALID"


def test_projection_rejects_unknown_source_status() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["source_status"] = "OK"
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "SOURCE_STATUS_INVALID"


def test_projection_rejects_unknown_unit() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["ath_unit"] = "EUR"
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "ATH_UNIT_INVALID"


def test_projection_rejects_unknown_basis() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["basis"] = "ATH_GUESSED"
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "ATH_BASIS_INVALID"


def test_projection_rejects_unknown_reason() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["reason"] = "ATH_UNKNOWN_WHATEVER"
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "ATH_REASON_INVALID"


def test_projection_rejects_empty_schema_version() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["schema_version"] = ""
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "SCHEMA_VERSION_INVALID"


def test_projection_rejects_empty_projection_version() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["projection_version"] = ""
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "PROJECTION_VERSION_INVALID"


def test_projection_rejects_non_string_ath_value_echo() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["ath_value"] = 83000  # must be canonical text or None
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "ATH_VALUE_ECHO_INVALID"


def test_projection_rejects_empty_ath_value_echo() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["ath_value"] = ""
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "ATH_VALUE_ECHO_INVALID"


def test_projection_allows_none_ath_value_echo() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["ath_status"] = ATH_STATUS_UNKNOWN
    kwargs["ath_value"] = None
    kwargs["ath_display_text"] = ATH_DISPLAY_UNKNOWN
    kwargs["reason"] = ATH_REASON_UNKNOWN_INVALID_INPUT
    kwargs["should_display_value"] = False
    kwargs["should_trust_for_drawdown"] = False
    proj = Stage30_7AthContextProjection(**kwargs)
    assert proj.ath_value is None


def test_projection_rejects_empty_display_text() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["ath_display_text"] = ""
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "ATH_DISPLAY_TEXT_INVALID"


def test_projection_rejects_non_bool_should_flags() -> None:
    kwargs = _valid_projection_kwargs()
    kwargs["should_display_value"] = "yes"
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "SHOULD_DISPLAY_VALUE_NOT_BOOL"

    kwargs = _valid_projection_kwargs()
    kwargs["should_trust_for_drawdown"] = 1
    with pytest.raises(Stage30_7AthContextError) as exc:
        Stage30_7AthContextProjection(**kwargs)
    assert exc.value.reason == "SHOULD_TRUST_FOR_DRAWDOWN_NOT_BOOL"


# ---------------------------------------------------------------------------
# 5. Forbidden-field-name guard + no forbidden field on either dataclass
# ---------------------------------------------------------------------------


def test_forbidden_field_name_guard() -> None:
    assert callable(is_forbidden_record_field_name)
    assert len(FORBIDDEN_RECORD_FIELD_NAMES) >= 20
    assert is_forbidden_record_field_name("raw_payload")
    assert is_forbidden_record_field_name("rpc_url")
    assert is_forbidden_record_field_name("source_event_ref")
    assert is_forbidden_record_field_name("web" + "hook_url")
    assert not is_forbidden_record_field_name("ath_value")
    assert not is_forbidden_record_field_name("source_status")
    assert not is_forbidden_record_field_name(123)


def test_no_forbidden_field_name_on_either_dataclass() -> None:
    for name in evidence_field_names() + projection_field_names():
        assert not is_forbidden_record_field_name(name), (
            f"Stage 30.7.1 dataclass field {name!r} is forbidden"
        )


def test_evidence_and_projection_field_names_pinned() -> None:
    assert evidence_field_names() == (
        "ath_value",
        "ath_unit",
        "source_status",
        "basis",
        "redaction_safe",
        "source_label",
        "observed_at_utc",
    )
    assert projection_field_names() == (
        "schema_version",
        "ath_status",
        "source_status",
        "ath_unit",
        "basis",
        "ath_value",
        "ath_display_text",
        "reason",
        "should_display_value",
        "should_trust_for_drawdown",
        "projection_version",
        "runtime_consumable",
    )


# ---------------------------------------------------------------------------
# 6. Closed-set tokens are distinct strings (no accidental aliasing)
# ---------------------------------------------------------------------------


def test_all_closed_set_tokens_are_distinct() -> None:
    everything = (
        ATH_STATUS_VALUES
        + ATH_SOURCE_STATUS_VALUES
        + ATH_BASIS_VALUES
        + ATH_REASON_VALUES
    )
    # ATH_UNIT_VALUES intentionally shares the token "UNKNOWN" with no
    # other set member name, so it is checked on its own.
    assert len(set(everything)) == len(everything)
    assert len(set(ATH_UNIT_VALUES)) == len(ATH_UNIT_VALUES)
    # Spot-check a few cross-set members are referenced (import sanity).
    assert ATH_STATUS_UNVERIFIED in ATH_STATUS_VALUES
    assert ATH_SOURCE_STATUS_CONFLICTING in ATH_SOURCE_STATUS_VALUES
    assert ATH_SOURCE_STATUS_ERROR in ATH_SOURCE_STATUS_VALUES
    assert ATH_SOURCE_STATUS_STALE in ATH_SOURCE_STATUS_VALUES
    assert ATH_SOURCE_STATUS_UNAVAILABLE in ATH_SOURCE_STATUS_VALUES
    assert ATH_UNIT_SOL in ATH_UNIT_VALUES
    assert ATH_UNIT_UNKNOWN in ATH_UNIT_VALUES
    assert ATH_BASIS_PRICE_DERIVED in ATH_BASIS_VALUES
    assert ATH_BASIS_NONE in ATH_BASIS_VALUES
    assert Decimal("1") == Decimal("1.0")  # decimal import sanity
