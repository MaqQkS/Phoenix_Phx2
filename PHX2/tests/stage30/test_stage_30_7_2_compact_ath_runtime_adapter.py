"""Stage 30.7.2 compact ATH runtime adapter unit tests.

Pins the Stage 30.7.2 offline runtime seam
(``stage30_7_compact_ath_runtime_adapter``):

  * ``ath_projection_to_compact_text(projection)`` returns
    ``projection.ath_display_text`` (a ``$Y`` value) ONLY for a trusted
    ``ATH_KNOWN`` projection whose ``should_display_value`` is ``True``;
    every other projection (``ATH_UNVERIFIED`` / ``ATH_UNKNOWN`` /
    malformed / ``None`` / non-displayable) fails closed to ``Unknown``.
    It NEVER reads ``runtime_consumable`` as a live-send permission.
  * ``build_ath_text_from_evidence(evidence, market_context_unit)``
    projects fake evidence via the Stage 30.7.1 projector and converts
    it to the compact display string, fail-closing to ``Unknown`` for
    every degraded evidence (price-derived, redaction-unsafe, SOL,
    missing, non-PRESENT, unit-incompatible).
  * ``Stage30_7_2AthDisplayResolver`` bundles fake evidence + a market-
    context unit and exposes ``resolve_display_text`` returning the same
    string.

Fake / offline only. No live provider call, no Discord send, no network,
no env read, no filesystem write. Stdlib + pytest only.
"""

from __future__ import annotations

from types import SimpleNamespace

from PHX2.stage30.stage30_7_ath_context_models import (
    ATH_BASIS_MARKET_CAP_OBSERVED,
    ATH_BASIS_NONE,
    ATH_BASIS_PRICE_DERIVED,
    ATH_DISPLAY_UNKNOWN,
    ATH_SOURCE_STATUS_PRESENT,
    ATH_SOURCE_STATUS_UNAVAILABLE,
    ATH_STATUS_KNOWN,
    ATH_STATUS_UNKNOWN,
    ATH_STATUS_UNVERIFIED,
    ATH_UNIT_SOL,
    ATH_UNIT_UNKNOWN,
    ATH_UNIT_USD,
    Stage30_7AthContextEvidence,
)
from PHX2.stage30.stage30_7_ath_context_projection import (
    project_ath_context,
)
from PHX2.stage30.stage30_7_compact_ath_runtime_adapter import (
    STAGE30_7_2_MINOR_VERSION,
    Stage30_7_2AthDisplayResolver,
    ath_projection_to_compact_text,
    build_ath_text_from_evidence,
)


# ---------------------------------------------------------------------------
# Fakes / builders
# ---------------------------------------------------------------------------


_TOKEN_MINT: str = "FakeMintPhx2NotWso1ForStage307_2Base58222222"
_OBS_TS: str = "2026-05-29T00:00:00Z"


def _evidence(
    *,
    ath_value: object = 120000,
    ath_unit: object = ATH_UNIT_USD,
    source_status: object = ATH_SOURCE_STATUS_PRESENT,
    basis: object = ATH_BASIS_MARKET_CAP_OBSERVED,
    redaction_safe: bool = True,
) -> Stage30_7AthContextEvidence:
    return Stage30_7AthContextEvidence(
        ath_value=ath_value,
        ath_unit=ath_unit,
        source_status=source_status,
        basis=basis,
        redaction_safe=redaction_safe,
    )


def _known_projection() -> object:
    return project_ath_context(_evidence())


# ---------------------------------------------------------------------------
# 0. Version pin
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_7_2_MINOR_VERSION == "30.7.2"


# ---------------------------------------------------------------------------
# 1. ath_projection_to_compact_text on real projections
# ---------------------------------------------------------------------------


def test_known_projection_renders_dollar_value() -> None:
    projection = _known_projection()
    assert projection.ath_status == ATH_STATUS_KNOWN
    assert projection.should_display_value is True
    assert ath_projection_to_compact_text(projection) == "$120k"


def test_unverified_price_derived_projection_renders_unknown() -> None:
    projection = project_ath_context(
        _evidence(basis=ATH_BASIS_PRICE_DERIVED)
    )
    assert projection.ath_status == ATH_STATUS_UNVERIFIED
    assert ath_projection_to_compact_text(projection) == ATH_DISPLAY_UNKNOWN
    assert ath_projection_to_compact_text(projection) == "Unknown"


def test_unknown_source_unavailable_projection_renders_unknown() -> None:
    projection = project_ath_context(
        _evidence(source_status=ATH_SOURCE_STATUS_UNAVAILABLE)
    )
    assert projection.ath_status == ATH_STATUS_UNKNOWN
    assert ath_projection_to_compact_text(projection) == "Unknown"


# ---------------------------------------------------------------------------
# 2. ath_projection_to_compact_text fail-closed paths
# ---------------------------------------------------------------------------


def test_none_projection_renders_unknown() -> None:
    assert ath_projection_to_compact_text(None) == "Unknown"


def test_malformed_projection_renders_unknown() -> None:
    bogus = SimpleNamespace(some_field="nope")
    assert ath_projection_to_compact_text(bogus) == "Unknown"


def test_known_status_but_should_display_false_renders_unknown() -> None:
    """Defensive: a projection-like object claiming ``ATH_KNOWN`` but
    with ``should_display_value`` not ``True`` must NOT render a value.
    """
    bogus = SimpleNamespace(
        ath_status=ATH_STATUS_KNOWN,
        should_display_value=False,
        ath_display_text="$120k",
    )
    assert ath_projection_to_compact_text(bogus) == "Unknown"


def test_known_status_but_empty_display_text_renders_unknown() -> None:
    bogus = SimpleNamespace(
        ath_status=ATH_STATUS_KNOWN,
        should_display_value=True,
        ath_display_text="",
    )
    assert ath_projection_to_compact_text(bogus) == "Unknown"


def test_known_status_but_nonstring_display_text_renders_unknown() -> None:
    bogus = SimpleNamespace(
        ath_status=ATH_STATUS_KNOWN,
        should_display_value=True,
        ath_display_text=120000,
    )
    assert ath_projection_to_compact_text(bogus) == "Unknown"


def test_adapter_does_not_consume_runtime_consumable_as_permission() -> None:
    """A trusted ``ATH_KNOWN`` projection still has ``runtime_consumable``
    hard-locked ``False`` (Stage 30.7.1); the adapter renders its value
    anyway -- it never treats that flag as a live-send / display
    permission gate.
    """
    projection = _known_projection()
    assert projection.runtime_consumable is False
    assert ath_projection_to_compact_text(projection) == "$120k"


# ---------------------------------------------------------------------------
# 3. build_ath_text_from_evidence
# ---------------------------------------------------------------------------


def test_build_text_known_usd_observed_renders_dollar_value() -> None:
    assert build_ath_text_from_evidence(_evidence()) == "$120k"


def test_build_text_known_usd_observed_string_value() -> None:
    assert (
        build_ath_text_from_evidence(_evidence(ath_value="83000")) == "$83k"
    )


def test_build_text_default_market_unit_is_usd() -> None:
    # No explicit market_context_unit -> USD default -> USD evidence is
    # compatible and renders a value.
    assert build_ath_text_from_evidence(_evidence()) == "$120k"


def test_build_text_price_derived_renders_unknown() -> None:
    assert (
        build_ath_text_from_evidence(_evidence(basis=ATH_BASIS_PRICE_DERIVED))
        == "Unknown"
    )


def test_build_text_redaction_unsafe_renders_unknown() -> None:
    assert (
        build_ath_text_from_evidence(_evidence(redaction_safe=False))
        == "Unknown"
    )


def test_build_text_sol_unit_renders_unknown() -> None:
    assert (
        build_ath_text_from_evidence(_evidence(ath_unit=ATH_UNIT_SOL))
        == "Unknown"
    )


def test_build_text_unit_unknown_renders_unknown() -> None:
    assert (
        build_ath_text_from_evidence(_evidence(ath_unit=ATH_UNIT_UNKNOWN))
        == "Unknown"
    )


def test_build_text_basis_none_renders_unknown() -> None:
    assert (
        build_ath_text_from_evidence(_evidence(basis=ATH_BASIS_NONE))
        == "Unknown"
    )


def test_build_text_none_evidence_renders_unknown() -> None:
    assert build_ath_text_from_evidence(None) == "Unknown"


def test_build_text_non_present_source_renders_unknown() -> None:
    assert (
        build_ath_text_from_evidence(
            _evidence(source_status=ATH_SOURCE_STATUS_UNAVAILABLE)
        )
        == "Unknown"
    )


def test_build_text_unit_incompatible_with_market_unit_renders_unknown() -> (
    None
):
    # USD evidence against a SOL market context degrades to Unknown
    # (never mixing units).
    assert (
        build_ath_text_from_evidence(
            _evidence(ath_unit=ATH_UNIT_USD), market_context_unit="SOL"
        )
        == "Unknown"
    )


def test_build_text_garbage_evidence_renders_unknown() -> None:
    # A garbage duck-typed evidence object still fails closed (the Stage
    # 30.7.1 projector is total).
    assert (
        build_ath_text_from_evidence(SimpleNamespace(nope=True)) == "Unknown"
    )


# ---------------------------------------------------------------------------
# 4. Stage30_7_2AthDisplayResolver
# ---------------------------------------------------------------------------


def test_resolver_exposes_evidence_and_unit() -> None:
    ev = _evidence()
    resolver = Stage30_7_2AthDisplayResolver(evidence=ev)
    assert resolver.evidence is ev
    assert resolver.market_context_unit == "USD"


def test_resolver_resolves_known_to_dollar_value() -> None:
    resolver = Stage30_7_2AthDisplayResolver(evidence=_evidence())
    result = resolver.resolve_display_text(
        token_mint=_TOKEN_MINT,
        observed_at_utc=_OBS_TS,
    )
    assert result == "$120k"


def test_resolver_resolves_price_derived_to_unknown() -> None:
    resolver = Stage30_7_2AthDisplayResolver(
        evidence=_evidence(basis=ATH_BASIS_PRICE_DERIVED),
    )
    assert (
        resolver.resolve_display_text(
            token_mint=_TOKEN_MINT, observed_at_utc=_OBS_TS
        )
        == "Unknown"
    )


def test_resolver_resolves_none_evidence_to_unknown() -> None:
    resolver = Stage30_7_2AthDisplayResolver(evidence=None)
    assert (
        resolver.resolve_display_text(
            token_mint=_TOKEN_MINT, observed_at_utc=_OBS_TS
        )
        == "Unknown"
    )


def test_resolver_observed_at_utc_optional() -> None:
    resolver = Stage30_7_2AthDisplayResolver(evidence=_evidence())
    assert resolver.resolve_display_text(token_mint=_TOKEN_MINT) == "$120k"


def test_resolver_ignores_token_mint_value() -> None:
    # The offline projection is fully derived from the wrapped evidence;
    # a different / non-string token_mint does not change the result.
    resolver = Stage30_7_2AthDisplayResolver(evidence=_evidence())
    assert (
        resolver.resolve_display_text(token_mint=12345) == "$120k"
    )


def test_resolver_with_sol_market_unit_degrades_usd_to_unknown() -> None:
    resolver = Stage30_7_2AthDisplayResolver(
        evidence=_evidence(ath_unit=ATH_UNIT_USD),
        market_context_unit="SOL",
    )
    assert (
        resolver.resolve_display_text(token_mint=_TOKEN_MINT) == "Unknown"
    )
