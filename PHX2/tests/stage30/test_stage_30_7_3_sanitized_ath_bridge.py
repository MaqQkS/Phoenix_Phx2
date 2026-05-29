"""Stage 30.7.3 sanitized upstream ATH-evidence bridge unit tests.

Pins the Stage 30.7.3 offline bridge
(``stage30_7_sanitized_ath_bridge``) that normalizes a sanitized upstream
ATH-evidence shape (Stage 25 / 27.4 / 29.2-style scalar summary) into the
Stage 30.7.1 ATH-context evidence carrier and reuses the EXISTING Stage
30.7.1 projection + Stage 30.7.2 compact adapter to produce the compact
``ATH`` display string:

  * ``sanitized_ath_evidence_to_stage30_evidence`` maps the upstream
    source-status / unit / basis / redaction / value onto the Stage 30.7
    closed sets per the documented table.
  * KNOWN observed USD (PRESENT + positive value + USD + observed-market-
    cap + redaction_safe True)        -> ``$120k``
  * price-derived / redaction-unsafe / SOL / USDC / non-PRESENT / basis-
    none / nested-value / None / garbage -> ``Unknown`` (fail closed)
  * the bridge consumes a Stage-30-owned dataclass, a duck-typed object
    (incl. Stage 27-ish ``ath_status`` / ``drawdown_basis`` aliases), or a
    plain ``dict`` -- WITHOUT importing any Stage 25 / 27 / 28 / 29 module.
  * the bridge never raises (fails closed to ``Unknown``) and never carries
    a nested / raw-like value into the evidence value slot.
  * ``build_stage30_ath_resolver_from_sanitized_evidence`` returns the Stage
    30.7.2 resolver the Stage 30.4.2 ``ath_context_resolver`` seam consumes.

Fake / offline only. No live provider call, no Discord send, no network,
no env read, no filesystem write. Stdlib + pytest only.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from PHX2.stage30.stage30_7_ath_context_models import (
    ATH_BASIS_MARKET_CAP_OBSERVED,
    ATH_BASIS_NONE,
    ATH_BASIS_PRICE_DERIVED,
    ATH_DISPLAY_UNKNOWN,
    ATH_SOURCE_STATUS_CONFLICTING,
    ATH_SOURCE_STATUS_ERROR,
    ATH_SOURCE_STATUS_PRESENT,
    ATH_SOURCE_STATUS_STALE,
    ATH_SOURCE_STATUS_UNAVAILABLE,
    ATH_UNIT_SOL,
    ATH_UNIT_UNKNOWN,
    ATH_UNIT_USD,
    Stage30_7AthContextEvidence,
)
from PHX2.stage30.stage30_7_compact_ath_runtime_adapter import (
    Stage30_7_2AthDisplayResolver,
)
from PHX2.stage30.stage30_7_sanitized_ath_bridge import (
    STAGE30_7_3_MINOR_VERSION,
    STAGE30_7_3_SOURCE_LABEL,
    Stage30_7_3SanitizedUpstreamAthEvidence,
    build_stage30_ath_resolver_from_sanitized_evidence,
    sanitized_ath_evidence_to_compact_text,
    sanitized_ath_evidence_to_stage30_evidence,
)


# ---------------------------------------------------------------------------
# Locked constants + helpers
# ---------------------------------------------------------------------------


_OBS_TS: str = "2026-05-29T00:00:00Z"
_TOKEN_MINT: str = "FakeMintPhx2ForStage307_3Base582222222222222"


def _evidence(
    **overrides: object,
) -> Stage30_7_3SanitizedUpstreamAthEvidence:
    """A KNOWN observed-market-cap USD sanitized evidence (the headline
    case), with per-field overrides for the degraded cases.
    """
    base = dict(
        ath_value=120000,
        ath_unit="USD",
        source_status="PRESENT",
        basis="ATH_MARKET_CAP_OBSERVED",
        redaction_safe=True,
    )
    base.update(overrides)
    return Stage30_7_3SanitizedUpstreamAthEvidence(**base)  # type: ignore[arg-type]


def _to_evidence(raw: object) -> Stage30_7AthContextEvidence:
    return sanitized_ath_evidence_to_stage30_evidence(raw)


def _to_text(raw: object, market_context_unit: str = "USD") -> str:
    return sanitized_ath_evidence_to_compact_text(
        raw, market_context_unit=market_context_unit
    )


# ---------------------------------------------------------------------------
# 0. Version + source label
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_7_3_MINOR_VERSION == "30.7.3"


def test_source_label_pinned() -> None:
    assert STAGE30_7_3_SOURCE_LABEL == "sanitized_upstream_ath_evidence"


# ---------------------------------------------------------------------------
# 1. The Stage 30.7.3 goal proof: KNOWN observed USD -> $120k
# ---------------------------------------------------------------------------


def test_known_observed_usd_renders_dollar_value() -> None:
    evidence = _to_evidence(_evidence())
    assert isinstance(evidence, Stage30_7AthContextEvidence)
    assert evidence.source_status == ATH_SOURCE_STATUS_PRESENT
    assert evidence.ath_unit == ATH_UNIT_USD
    assert evidence.basis == ATH_BASIS_MARKET_CAP_OBSERVED
    assert evidence.redaction_safe is True
    assert _to_text(_evidence()) == "$120k"


def test_known_observed_usd_string_value() -> None:
    assert _to_text(_evidence(ath_value="83000")) == "$83k"


def test_default_market_unit_is_usd() -> None:
    # No explicit market_context_unit -> USD default -> USD evidence renders.
    assert sanitized_ath_evidence_to_compact_text(_evidence()) == "$120k"


# ---------------------------------------------------------------------------
# 2. Source-status mapping matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "upstream,expected",
    [
        ("PRESENT", ATH_SOURCE_STATUS_PRESENT),
        ("UNAVAILABLE", ATH_SOURCE_STATUS_UNAVAILABLE),
        ("STALE", ATH_SOURCE_STATUS_STALE),
        ("CONFLICTING", ATH_SOURCE_STATUS_CONFLICTING),
        ("ERROR", ATH_SOURCE_STATUS_ERROR),
        ("SOURCE_ERROR", ATH_SOURCE_STATUS_ERROR),
        # NOT_APPLICABLE / UNSUPPORTED_PAIR / UNKNOWN / unrecognized / non-str
        # / missing -> UNAVAILABLE (fail closed).
        ("NOT_APPLICABLE", ATH_SOURCE_STATUS_UNAVAILABLE),
        ("UNSUPPORTED_PAIR", ATH_SOURCE_STATUS_UNAVAILABLE),
        ("UNKNOWN", ATH_SOURCE_STATUS_UNAVAILABLE),
        ("DEFINITELY_PRESENT_TRUST_ME", ATH_SOURCE_STATUS_UNAVAILABLE),
        (None, ATH_SOURCE_STATUS_UNAVAILABLE),
        (12345, ATH_SOURCE_STATUS_UNAVAILABLE),
    ],
)
def test_source_status_mapping(upstream: object, expected: str) -> None:
    assert _to_evidence(_evidence(source_status=upstream)).source_status == (
        expected
    )


# ---------------------------------------------------------------------------
# 3. Unit mapping matrix (USDC -> UNKNOWN, never USD)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "upstream,expected",
    [
        ("USD", ATH_UNIT_USD),
        ("SOL", ATH_UNIT_SOL),
        ("USDC", ATH_UNIT_UNKNOWN),
        ("UNKNOWN", ATH_UNIT_UNKNOWN),
        ("EUR", ATH_UNIT_UNKNOWN),
        (None, ATH_UNIT_UNKNOWN),
        (999, ATH_UNIT_UNKNOWN),
    ],
)
def test_unit_mapping(upstream: object, expected: str) -> None:
    assert _to_evidence(_evidence(ath_unit=upstream)).ath_unit == expected


def test_usdc_unit_never_renders_a_value() -> None:
    # USDC degrades to UNKNOWN unit -> Unknown (never silently shown as USD).
    assert _to_text(_evidence(ath_unit="USDC")) == ATH_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# 4. Basis mapping matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "upstream,expected",
    [
        ("ATH_MARKET_CAP_OBSERVED", ATH_BASIS_MARKET_CAP_OBSERVED),
        ("MARKET_CAP_OBSERVED", ATH_BASIS_MARKET_CAP_OBSERVED),
        ("ATH_PRICE_DERIVED", ATH_BASIS_PRICE_DERIVED),
        ("PRICE_DERIVED", ATH_BASIS_PRICE_DERIVED),
        # Stage 27 drawdown_basis values are NOT ATH-measurement bases.
        ("FROM_POST_MIGRATION_ATH", ATH_BASIS_NONE),
        ("NOT_APPLICABLE", ATH_BASIS_NONE),
        ("UNKNOWN", ATH_BASIS_NONE),
        (None, ATH_BASIS_NONE),
        (3.14, ATH_BASIS_NONE),
    ],
)
def test_basis_mapping(upstream: object, expected: str) -> None:
    assert _to_evidence(_evidence(basis=upstream)).basis == expected


# ---------------------------------------------------------------------------
# 5. Degraded evidence -> Unknown (projection fail-closed)
# ---------------------------------------------------------------------------


def test_price_derived_renders_unknown() -> None:
    assert _to_text(_evidence(basis="ATH_PRICE_DERIVED")) == "Unknown"


def test_basis_none_renders_unknown() -> None:
    # A positive USD value with no observed / price-derived basis is
    # internally inconsistent -> Unknown.
    assert _to_text(_evidence(basis="FROM_POST_MIGRATION_ATH")) == "Unknown"


@pytest.mark.parametrize(
    "status",
    ["UNAVAILABLE", "ERROR", "SOURCE_ERROR", "STALE", "CONFLICTING"],
)
def test_non_present_source_renders_unknown(status: str) -> None:
    assert _to_text(_evidence(source_status=status)) == "Unknown"


def test_sol_evidence_with_usd_market_context_renders_unknown() -> None:
    assert _to_text(_evidence(ath_unit="SOL")) == "Unknown"


def test_sol_evidence_with_sol_market_context_still_unknown() -> None:
    # A SOL ATH display is deferred in the Stage 30.7.1 projection even when
    # the market context is SOL, so the bridge renders Unknown.
    assert (
        _to_text(_evidence(ath_unit="SOL"), market_context_unit="SOL")
        == "Unknown"
    )


def test_unit_unknown_renders_unknown() -> None:
    assert _to_text(_evidence(ath_unit="UNKNOWN")) == "Unknown"


# ---------------------------------------------------------------------------
# 6. Redaction: only an explicit True trusts the evidence
# ---------------------------------------------------------------------------


def test_redaction_safe_false_renders_unknown() -> None:
    assert _to_text(_evidence(redaction_safe=False)) == "Unknown"


def test_redaction_safe_missing_renders_unknown() -> None:
    # A duck-typed shape with no redaction_safe attribute at all -> False
    # (fail closed) -> Unknown.
    duck = SimpleNamespace(
        ath_value=120000,
        ath_unit="USD",
        source_status="PRESENT",
        basis="ATH_MARKET_CAP_OBSERVED",
    )
    assert _to_evidence(duck).redaction_safe is False
    assert _to_text(duck) == "Unknown"


@pytest.mark.parametrize("non_true", [1, "true", "True", "yes", 0, None])
def test_redaction_safe_non_true_renders_unknown(non_true: object) -> None:
    # Anything other than the bool True fails closed.
    assert _to_evidence(_evidence(redaction_safe=non_true)).redaction_safe is (
        False
    )
    assert _to_text(_evidence(redaction_safe=non_true)) == "Unknown"


# ---------------------------------------------------------------------------
# 7. Value sanitization: nested / raw-like values are rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [
        {"raw": "payload"},
        ["120000"],
        ("120000",),
        {120000},
        b"120000",
        bytearray(b"120000"),
    ],
)
def test_nested_value_rejected_as_missing(bad_value: object) -> None:
    assert _to_evidence(_evidence(ath_value=bad_value)).ath_value is None
    assert _to_text(_evidence(ath_value=bad_value)) == "Unknown"


def test_none_value_renders_unknown() -> None:
    assert _to_text(_evidence(ath_value=None)) == "Unknown"


def test_non_positive_value_renders_unknown() -> None:
    assert _to_text(_evidence(ath_value=0)) == "Unknown"
    assert _to_text(_evidence(ath_value=-120000)) == "Unknown"


# ---------------------------------------------------------------------------
# 8. None / garbage evidence -> Unknown (total, never raises)
# ---------------------------------------------------------------------------


def test_none_evidence_renders_unknown() -> None:
    ev = _to_evidence(None)
    assert ev.source_status == ATH_SOURCE_STATUS_UNAVAILABLE
    assert ev.ath_unit == ATH_UNIT_UNKNOWN
    assert ev.basis == ATH_BASIS_NONE
    assert ev.redaction_safe is False
    assert _to_text(None) == "Unknown"


@pytest.mark.parametrize(
    "garbage",
    [123, 3.14, "a bare string", object(), SimpleNamespace(nope=True)],
)
def test_garbage_evidence_renders_unknown(garbage: object) -> None:
    assert _to_text(garbage) == "Unknown"


def test_bridge_never_raises_for_pathological_object() -> None:
    class _Raises:
        @property
        def ath_value(self) -> object:
            raise RuntimeError("boom")

    # The bridge reads via a guarded getattr; a raising property degrades to
    # a missing value rather than propagating.
    assert _to_text(_Raises()) == "Unknown"


# ---------------------------------------------------------------------------
# 9. Duck-typed Stage 27-ish shape (aliases) WITHOUT importing Stage 27
# ---------------------------------------------------------------------------


def test_ath_status_alias_consulted_when_source_status_absent() -> None:
    # A Stage 27.4-style object exposes the source status on ``ath_status``;
    # the bridge consults the alias and renders a value.
    duck = SimpleNamespace(
        ath_value=120000,
        ath_unit="USD",
        ath_status="PRESENT",  # alias for source_status
        basis="ATH_MARKET_CAP_OBSERVED",
        redaction_safe=True,
    )
    assert _to_evidence(duck).source_status == ATH_SOURCE_STATUS_PRESENT
    assert _to_text(duck) == "$120k"


def test_realistic_stage27_price_ath_record_renders_unknown() -> None:
    # A sanitized copy of a real Stage 27.4 ATH context record: a PRESENT
    # price ATH with a drawdown_basis (NOT an observed market cap). The
    # bridge honestly degrades it to Unknown -- it never promotes a price
    # ATH to a known market cap. Imports no Stage 27 module (SimpleNamespace).
    duck = SimpleNamespace(
        ath_value="0.00012345",
        ath_unit="USD",
        ath_status="PRESENT",
        drawdown_basis="FROM_POST_MIGRATION_ATH",  # alias for basis
        ath_source="some_source_family",  # alias for source_label
        ath_observed_at_utc=_OBS_TS,  # alias for observed_at_utc
        redaction_safe=True,
        # Extra upstream fields the bridge must IGNORE (never read / echo).
        ath_reason="OK",
        migration_signature="rawsig_DO_NOT_LEAK",
    )
    evidence = _to_evidence(duck)
    assert evidence.basis == ATH_BASIS_NONE
    assert evidence.source_label == "some_source_family"
    assert evidence.observed_at_utc == _OBS_TS
    assert _to_text(duck) == "Unknown"


def test_present_field_none_does_not_fall_through_to_alias() -> None:
    # A field present as None counts as present; an explicit source_status=None
    # does NOT fall through to ath_status (documented _read_first behavior).
    duck = SimpleNamespace(source_status=None, ath_status="PRESENT")
    assert _to_evidence(duck).source_status == ATH_SOURCE_STATUS_UNAVAILABLE


# ---------------------------------------------------------------------------
# 10. dict-like input
# ---------------------------------------------------------------------------


def test_dict_like_input_renders_value() -> None:
    d = {
        "ath_value": 120000,
        "ath_unit": "USD",
        "source_status": "PRESENT",
        "basis": "ATH_MARKET_CAP_OBSERVED",
        "redaction_safe": True,
    }
    assert _to_text(d) == "$120k"


def test_dict_like_input_with_aliases() -> None:
    d = {
        "ath_value": 120000,
        "ath_unit": "USD",
        "ath_status": "PRESENT",
        "drawdown_basis": "MARKET_CAP_OBSERVED",
        "redaction_safe": True,
    }
    assert _to_text(d) == "$120k"


def test_empty_dict_renders_unknown() -> None:
    assert _to_text({}) == "Unknown"


# ---------------------------------------------------------------------------
# 11. Provenance fields carried (guarded) but never required
# ---------------------------------------------------------------------------


def test_safe_provenance_carried() -> None:
    ev = _to_evidence(
        _evidence(source_label="lbl", observed_at_utc=_OBS_TS)
    )
    assert ev.source_label == "lbl"
    assert ev.observed_at_utc == _OBS_TS


def test_non_string_provenance_dropped() -> None:
    duck = SimpleNamespace(
        ath_value=120000,
        ath_unit="USD",
        source_status="PRESENT",
        basis="ATH_MARKET_CAP_OBSERVED",
        redaction_safe=True,
        source_label=12345,
        observed_at_utc=67890,
    )
    ev = _to_evidence(duck)
    assert ev.source_label is None
    assert ev.observed_at_utc is None
    # Provenance has no effect on the display.
    assert _to_text(duck) == "$120k"


# ---------------------------------------------------------------------------
# 12. Resolver builder returns the Stage 30.7.2 resolver
# ---------------------------------------------------------------------------


def test_builder_returns_stage30_7_2_resolver_known() -> None:
    resolver = build_stage30_ath_resolver_from_sanitized_evidence(
        raw_evidence=_evidence(),
    )
    assert isinstance(resolver, Stage30_7_2AthDisplayResolver)
    assert (
        resolver.resolve_display_text(
            token_mint=_TOKEN_MINT, observed_at_utc=_OBS_TS
        )
        == "$120k"
    )


def test_builder_returns_resolver_degraded() -> None:
    resolver = build_stage30_ath_resolver_from_sanitized_evidence(
        raw_evidence=_evidence(basis="ATH_PRICE_DERIVED"),
    )
    assert (
        resolver.resolve_display_text(token_mint=_TOKEN_MINT) == "Unknown"
    )


def test_builder_threads_market_context_unit() -> None:
    # USD evidence against a SOL market context degrades to Unknown.
    resolver = build_stage30_ath_resolver_from_sanitized_evidence(
        raw_evidence=_evidence(),
        market_context_unit="SOL",
    )
    assert (
        resolver.resolve_display_text(token_mint=_TOKEN_MINT) == "Unknown"
    )


def test_builder_none_evidence_resolves_unknown() -> None:
    resolver = build_stage30_ath_resolver_from_sanitized_evidence(
        raw_evidence=None,
    )
    assert (
        resolver.resolve_display_text(token_mint=_TOKEN_MINT) == "Unknown"
    )


# ---------------------------------------------------------------------------
# 13. Sanitized dataclass shape carries only safe scalar fields
# ---------------------------------------------------------------------------


def test_sanitized_dataclass_field_set() -> None:
    import dataclasses

    field_names = {
        f.name
        for f in dataclasses.fields(Stage30_7_3SanitizedUpstreamAthEvidence)
    }
    assert field_names == {
        "ath_value",
        "ath_unit",
        "source_status",
        "basis",
        "redaction_safe",
        "source_label",
        "observed_at_utc",
    }


def test_sanitized_dataclass_defaults_fail_closed() -> None:
    # An all-default sanitized evidence projects to Unknown.
    ev = Stage30_7_3SanitizedUpstreamAthEvidence()
    assert ev.redaction_safe is False
    assert _to_text(ev) == "Unknown"
