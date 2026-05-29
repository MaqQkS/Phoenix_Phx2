"""Stage 30.7.1 ATH-context projection adapter tests.

Covers ``project_ath_context``:

  * the trusted ``ATH_KNOWN`` path (PRESENT + positive finite USD value
    + compatible USD market context + observed-market-cap basis) and
    its compact ``$Y`` formatting,
  * source dominance (UNAVAILABLE / ERROR / STALE / CONFLICTING all
    render ``Unknown``),
  * value fail-closed (missing / non-numeric / NaN / infinite /
    non-positive),
  * unit safety (UNKNOWN / unsupported / incompatible-with-market-
    context all render ``Unknown``; USD and SOL are never mixed),
  * basis honesty (a price-derived ATH is ATH_UNVERIFIED, never
    ATH_KNOWN, and is not trusted for drawdown / tier; a basis with no
    support is invalid input),
  * redaction-unsafe fail-closed,
  * malformed / ``None`` evidence fail-closed,
  * ``runtime_consumable`` hard-locked ``False`` on every projection,
  * deterministic repeated output,
  * every closed-set reason token is reachable.

Pure / offline. No live call, no provider, no Discord, no env, no
filesystem, no network.
"""

from __future__ import annotations

from decimal import Decimal

from PHX2.stage30.stage30_7_ath_context_models import (
    ATH_BASIS_MARKET_CAP_OBSERVED,
    ATH_BASIS_NONE,
    ATH_BASIS_PRICE_DERIVED,
    ATH_DISPLAY_UNKNOWN,
    ATH_REASON_KNOWN_USD_MARKET_CAP,
    ATH_REASON_UNKNOWN_INVALID_INPUT,
    ATH_REASON_UNKNOWN_REDACTION_UNSAFE,
    ATH_REASON_UNKNOWN_SOURCE_CONFLICTING,
    ATH_REASON_UNKNOWN_SOURCE_ERROR,
    ATH_REASON_UNKNOWN_SOURCE_STALE,
    ATH_REASON_UNKNOWN_SOURCE_UNAVAILABLE,
    ATH_REASON_UNKNOWN_UNIT_INCOMPATIBLE,
    ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED,
    ATH_REASON_UNKNOWN_VALUE_MISSING,
    ATH_REASON_UNKNOWN_VALUE_NON_POSITIVE,
    ATH_REASON_UNKNOWN_VALUE_NOT_FINITE,
    ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC,
    ATH_REASON_UNVERIFIED_PRICE_DERIVED,
    ATH_REASON_VALUES,
    ATH_SOURCE_STATUS_CONFLICTING,
    ATH_SOURCE_STATUS_ERROR,
    ATH_SOURCE_STATUS_PRESENT,
    ATH_SOURCE_STATUS_STALE,
    ATH_SOURCE_STATUS_UNAVAILABLE,
    ATH_STATUS_KNOWN,
    ATH_STATUS_UNKNOWN,
    ATH_STATUS_UNVERIFIED,
    ATH_UNIT_SOL,
    ATH_UNIT_UNKNOWN,
    ATH_UNIT_USD,
    Stage30_7AthContextEvidence,
    Stage30_7AthContextProjection,
)
from PHX2.stage30.stage30_7_ath_context_projection import (
    project_ath_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _known_evidence(**overrides: object) -> Stage30_7AthContextEvidence:
    """Build a PRESENT + USD + observed-market-cap + redaction-safe
    evidence (the ``ATH_KNOWN`` shape), then apply overrides.
    """
    base: dict = dict(
        ath_value="83000",
        ath_unit=ATH_UNIT_USD,
        source_status=ATH_SOURCE_STATUS_PRESENT,
        basis=ATH_BASIS_MARKET_CAP_OBSERVED,
        redaction_safe=True,
        source_label="ath_offline_fake",
    )
    base.update(overrides)
    return Stage30_7AthContextEvidence(**base)


def _assert_unknown(
    proj: Stage30_7AthContextProjection,
    *,
    reason: str,
) -> None:
    assert proj.ath_status == ATH_STATUS_UNKNOWN
    assert proj.ath_display_text == ATH_DISPLAY_UNKNOWN
    assert proj.ath_display_text == "Unknown"
    assert proj.ath_value is None
    assert proj.should_display_value is False
    assert proj.should_trust_for_drawdown is False
    assert proj.runtime_consumable is False
    assert proj.reason == reason


# ---------------------------------------------------------------------------
# 1. Trusted ATH_KNOWN path
# ---------------------------------------------------------------------------


def test_known_usd_market_cap_observed() -> None:
    proj = project_ath_context(_known_evidence())
    assert proj.ath_status == ATH_STATUS_KNOWN
    assert proj.source_status == ATH_SOURCE_STATUS_PRESENT
    assert proj.ath_unit == ATH_UNIT_USD
    assert proj.basis == ATH_BASIS_MARKET_CAP_OBSERVED
    assert proj.ath_display_text == "$83k"
    assert proj.ath_value == "83000"
    assert proj.reason == ATH_REASON_KNOWN_USD_MARKET_CAP
    assert proj.should_display_value is True
    assert proj.should_trust_for_drawdown is True
    assert proj.runtime_consumable is False


def test_known_accepts_int_float_decimal_value() -> None:
    for value, expected_display in (
        (83000, "$83k"),
        (83000.0, "$83k"),
        (Decimal("83000"), "$83k"),
    ):
        proj = project_ath_context(_known_evidence(ath_value=value))
        assert proj.ath_status == ATH_STATUS_KNOWN
        assert proj.ath_display_text == expected_display


def test_known_default_market_context_unit_is_usd() -> None:
    # No explicit market_context_unit -> default USD -> compatible.
    proj = project_ath_context(_known_evidence(ath_value="125000"))
    assert proj.ath_status == ATH_STATUS_KNOWN
    assert proj.ath_display_text == "$125k"


# ---------------------------------------------------------------------------
# 2. Compact USD formatting (deterministic, ROUND_DOWN, k / M)
# ---------------------------------------------------------------------------


def test_compact_usd_formatting_buckets() -> None:
    cases = {
        "27": "$27",
        "999": "$999",
        "1000": "$1k",
        "12345": "$12.3k",
        "83000": "$83k",
        "999999": "$999.9k",
        "1000000": "$1M",
        "1234567": "$1.2M",
        "1500000": "$1.5M",
    }
    for value_text, expected in cases.items():
        proj = project_ath_context(_known_evidence(ath_value=value_text))
        assert proj.ath_status == ATH_STATUS_KNOWN, value_text
        assert proj.ath_display_text == expected, (
            f"{value_text} -> {proj.ath_display_text!r} != {expected!r}"
        )


# ---------------------------------------------------------------------------
# 3. Source dominance
# ---------------------------------------------------------------------------


def test_source_unavailable_renders_unknown() -> None:
    proj = project_ath_context(
        _known_evidence(source_status=ATH_SOURCE_STATUS_UNAVAILABLE)
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_SOURCE_UNAVAILABLE)
    assert proj.source_status == ATH_SOURCE_STATUS_UNAVAILABLE


def test_source_error_renders_unknown() -> None:
    proj = project_ath_context(
        _known_evidence(source_status=ATH_SOURCE_STATUS_ERROR)
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_SOURCE_ERROR)
    assert proj.source_status == ATH_SOURCE_STATUS_ERROR


def test_source_stale_renders_unknown() -> None:
    proj = project_ath_context(
        _known_evidence(source_status=ATH_SOURCE_STATUS_STALE)
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_SOURCE_STALE)
    assert proj.source_status == ATH_SOURCE_STATUS_STALE


def test_source_conflicting_renders_unknown() -> None:
    proj = project_ath_context(
        _known_evidence(source_status=ATH_SOURCE_STATUS_CONFLICTING)
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_SOURCE_CONFLICTING)
    assert proj.source_status == ATH_SOURCE_STATUS_CONFLICTING


def test_source_dominates_even_with_valid_value() -> None:
    # A claimed positive USD observed value with a non-PRESENT source
    # must STILL render Unknown (source dominance).
    proj = project_ath_context(
        _known_evidence(
            ath_value="999000",
            source_status=ATH_SOURCE_STATUS_ERROR,
        )
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_SOURCE_ERROR)


def test_off_closed_set_source_status_is_invalid_input() -> None:
    proj = project_ath_context(
        _known_evidence(source_status="OK")
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_INVALID_INPUT)
    assert proj.source_status == ATH_SOURCE_STATUS_UNAVAILABLE


def test_missing_source_status_is_invalid_input() -> None:
    proj = project_ath_context(_known_evidence(source_status=None))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_INVALID_INPUT)


# ---------------------------------------------------------------------------
# 4. Redaction safety
# ---------------------------------------------------------------------------


def test_redaction_unsafe_renders_unknown() -> None:
    proj = project_ath_context(_known_evidence(redaction_safe=False))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_REDACTION_UNSAFE)
    assert proj.source_status == ATH_SOURCE_STATUS_PRESENT


def test_redaction_non_true_value_renders_unknown() -> None:
    # Anything other than exactly True is treated as unsafe.
    proj = project_ath_context(_known_evidence(redaction_safe="yes"))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_REDACTION_UNSAFE)


# ---------------------------------------------------------------------------
# 5. Value fail-closed
# ---------------------------------------------------------------------------


def test_missing_value_renders_unknown() -> None:
    proj = project_ath_context(_known_evidence(ath_value=None))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_VALUE_MISSING)


def test_non_numeric_value_renders_unknown() -> None:
    for bad in ("abc", "1e5", "12.", "+5", " 12 ", object(), [1, 2], True):
        proj = project_ath_context(_known_evidence(ath_value=bad))
        _assert_unknown(
            proj, reason=ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC
        )


def test_nan_value_renders_unknown() -> None:
    proj = project_ath_context(
        _known_evidence(ath_value=float("nan"))
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_VALUE_NOT_FINITE)


def test_infinite_value_renders_unknown() -> None:
    for bad in (float("inf"), float("-inf"), Decimal("Infinity")):
        proj = project_ath_context(_known_evidence(ath_value=bad))
        _assert_unknown(
            proj, reason=ATH_REASON_UNKNOWN_VALUE_NOT_FINITE
        )


def test_non_positive_value_renders_unknown() -> None:
    for bad in (0, 0.0, -5, "-5", "0", Decimal("0"), Decimal("-1")):
        proj = project_ath_context(_known_evidence(ath_value=bad))
        _assert_unknown(
            proj, reason=ATH_REASON_UNKNOWN_VALUE_NON_POSITIVE
        )


# ---------------------------------------------------------------------------
# 6. Unit safety (never mix USD and SOL)
# ---------------------------------------------------------------------------


def test_unit_unknown_renders_unknown() -> None:
    proj = project_ath_context(_known_evidence(ath_unit=ATH_UNIT_UNKNOWN))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED)


def test_unit_unrecognized_renders_unknown() -> None:
    proj = project_ath_context(_known_evidence(ath_unit="EUR"))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED)


def test_unit_missing_renders_unknown() -> None:
    proj = project_ath_context(_known_evidence(ath_unit=None))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED)


def test_sol_unit_against_usd_market_context_renders_unknown() -> None:
    proj = project_ath_context(
        _known_evidence(ath_unit=ATH_UNIT_SOL),
        market_context_unit=ATH_UNIT_USD,
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_UNIT_INCOMPATIBLE)


def test_usd_unit_against_sol_market_context_renders_unknown() -> None:
    proj = project_ath_context(
        _known_evidence(ath_unit=ATH_UNIT_USD),
        market_context_unit=ATH_UNIT_SOL,
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_UNIT_INCOMPATIBLE)


def test_sol_unit_against_sol_market_context_display_deferred() -> None:
    # SOL is a recognized, compatible unit but SOL display is deferred
    # in this slice -> Unknown (UNIT_UNSUPPORTED), never a $ value.
    proj = project_ath_context(
        _known_evidence(ath_unit=ATH_UNIT_SOL),
        market_context_unit=ATH_UNIT_SOL,
    )
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED)


# ---------------------------------------------------------------------------
# 7. Basis honesty
# ---------------------------------------------------------------------------


def test_price_derived_basis_is_unverified_not_known() -> None:
    proj = project_ath_context(
        _known_evidence(basis=ATH_BASIS_PRICE_DERIVED)
    )
    assert proj.ath_status == ATH_STATUS_UNVERIFIED
    assert proj.ath_status != ATH_STATUS_KNOWN
    # Display is Unknown even though a value exists; never trusted for
    # drawdown / tier.
    assert proj.ath_display_text == ATH_DISPLAY_UNKNOWN
    assert proj.should_display_value is False
    assert proj.should_trust_for_drawdown is False
    assert proj.reason == ATH_REASON_UNVERIFIED_PRICE_DERIVED
    assert proj.runtime_consumable is False
    # Provenance: the value echo is preserved on the UNVERIFIED record.
    assert proj.ath_value == "83000"
    assert proj.basis == ATH_BASIS_PRICE_DERIVED


def test_basis_none_with_value_is_invalid_input() -> None:
    proj = project_ath_context(_known_evidence(basis=ATH_BASIS_NONE))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_INVALID_INPUT)


def test_off_closed_set_basis_is_invalid_input() -> None:
    proj = project_ath_context(_known_evidence(basis="ATH_GUESSED"))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_INVALID_INPUT)


def test_missing_basis_is_invalid_input() -> None:
    proj = project_ath_context(_known_evidence(basis=None))
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_INVALID_INPUT)


# ---------------------------------------------------------------------------
# 8. Malformed / None evidence fail-closed (no exception escapes)
# ---------------------------------------------------------------------------


def test_none_evidence_renders_unknown() -> None:
    proj = project_ath_context(None)
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_INVALID_INPUT)


def test_empty_evidence_renders_unknown() -> None:
    proj = project_ath_context(Stage30_7AthContextEvidence())
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_INVALID_INPUT)


def test_arbitrary_object_evidence_renders_unknown() -> None:
    proj = project_ath_context(object())
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_INVALID_INPUT)


def test_malicious_evidence_property_raises_fails_closed() -> None:
    class _Hostile:
        @property
        def source_status(self) -> str:
            raise RuntimeError("boom")

    proj = project_ath_context(_Hostile())
    _assert_unknown(proj, reason=ATH_REASON_UNKNOWN_INVALID_INPUT)


def test_duck_typed_evidence_missing_redaction_safe_fails_closed() -> None:
    """Codex regression: a malformed duck-typed evidence object that
    OMITS ``redaction_safe`` must fail closed even with a PRESENT source
    + a valid USD observed-market-cap value -- a missing redaction proof
    is never trusted, so it must NOT return ATH_KNOWN / "$83k".
    """

    class _NoRedactionProof:
        source_status = ATH_SOURCE_STATUS_PRESENT
        ath_value = "83000"
        ath_unit = ATH_UNIT_USD
        basis = ATH_BASIS_MARKET_CAP_OBSERVED
        # intentionally NO redaction_safe attribute

    proj = project_ath_context(_NoRedactionProof())
    assert proj.ath_status == ATH_STATUS_UNKNOWN
    assert proj.ath_display_text == "Unknown"
    assert proj.reason == ATH_REASON_UNKNOWN_REDACTION_UNSAFE
    assert proj.should_display_value is False
    assert proj.should_trust_for_drawdown is False
    assert proj.runtime_consumable is False


def test_duck_typed_evidence_with_redaction_proof_still_known() -> None:
    """Contrast to the regression above: a duck-typed object that DOES
    assert ``redaction_safe = True`` (with the same PRESENT source +
    valid USD observed-market-cap value) still reaches ATH_KNOWN /
    "$83k". The fix only fails the MISSING-proof case closed.
    """

    class _WithRedactionProof:
        source_status = ATH_SOURCE_STATUS_PRESENT
        ath_value = "83000"
        ath_unit = ATH_UNIT_USD
        basis = ATH_BASIS_MARKET_CAP_OBSERVED
        redaction_safe = True

    proj = project_ath_context(_WithRedactionProof())
    assert proj.ath_status == ATH_STATUS_KNOWN
    assert proj.ath_display_text == "$83k"
    assert proj.should_display_value is True
    assert proj.should_trust_for_drawdown is True
    assert proj.runtime_consumable is False


def test_dataclass_evidence_omitting_redaction_safe_fails_closed() -> None:
    """Codex regression #2: the official Stage30_7AthContextEvidence
    dataclass now DEFAULTS ``redaction_safe=False``, so constructing it
    with valid ATH fields but OMITTING ``redaction_safe`` must fail
    closed -- it must NOT project to ATH_KNOWN / "$83k".
    """
    ev = Stage30_7AthContextEvidence(
        source_status=ATH_SOURCE_STATUS_PRESENT,
        ath_value="83000",
        ath_unit=ATH_UNIT_USD,
        basis=ATH_BASIS_MARKET_CAP_OBSERVED,
        # redaction_safe omitted -> defaults False -> fail closed.
    )
    assert ev.redaction_safe is False
    proj = project_ath_context(ev)
    assert proj.ath_status == ATH_STATUS_UNKNOWN
    assert proj.ath_display_text == "Unknown"
    assert proj.reason == ATH_REASON_UNKNOWN_REDACTION_UNSAFE
    assert proj.should_display_value is False
    assert proj.should_trust_for_drawdown is False
    assert proj.runtime_consumable is False


def test_dataclass_evidence_with_redaction_safe_true_still_known() -> None:
    """The explicit ``redaction_safe=True`` valid path is preserved: a
    dataclass evidence with a PRESENT source + a valid USD observed-
    market-cap value + an explicit redaction proof still projects to
    ATH_KNOWN / "$83k".
    """
    ev = Stage30_7AthContextEvidence(
        source_status=ATH_SOURCE_STATUS_PRESENT,
        ath_value="83000",
        ath_unit=ATH_UNIT_USD,
        basis=ATH_BASIS_MARKET_CAP_OBSERVED,
        redaction_safe=True,
    )
    proj = project_ath_context(ev)
    assert proj.ath_status == ATH_STATUS_KNOWN
    assert proj.ath_display_text == "$83k"
    assert proj.reason == ATH_REASON_KNOWN_USD_MARKET_CAP
    assert proj.should_display_value is True
    assert proj.should_trust_for_drawdown is True
    assert proj.runtime_consumable is False


# ---------------------------------------------------------------------------
# 9. Determinism + totality + every reason reachable
# ---------------------------------------------------------------------------


def test_deterministic_repeated_output() -> None:
    ev = _known_evidence(ath_value="654321")
    first = project_ath_context(ev)
    second = project_ath_context(ev)
    assert first == second
    assert first.ath_display_text == "$654.3k"


def test_runtime_consumable_false_on_every_path() -> None:
    evidences = (
        _known_evidence(),
        _known_evidence(source_status=ATH_SOURCE_STATUS_ERROR),
        _known_evidence(ath_value=None),
        _known_evidence(ath_unit=ATH_UNIT_SOL),
        _known_evidence(basis=ATH_BASIS_PRICE_DERIVED),
        _known_evidence(redaction_safe=False),
        None,
    )
    for ev in evidences:
        proj = project_ath_context(ev)
        assert proj.runtime_consumable is False


def test_every_reason_token_is_reachable() -> None:
    observed = set()
    observed.add(project_ath_context(_known_evidence()).reason)
    observed.add(
        project_ath_context(
            _known_evidence(basis=ATH_BASIS_PRICE_DERIVED)
        ).reason
    )
    observed.add(
        project_ath_context(
            _known_evidence(source_status=ATH_SOURCE_STATUS_UNAVAILABLE)
        ).reason
    )
    observed.add(
        project_ath_context(
            _known_evidence(source_status=ATH_SOURCE_STATUS_ERROR)
        ).reason
    )
    observed.add(
        project_ath_context(
            _known_evidence(source_status=ATH_SOURCE_STATUS_STALE)
        ).reason
    )
    observed.add(
        project_ath_context(
            _known_evidence(source_status=ATH_SOURCE_STATUS_CONFLICTING)
        ).reason
    )
    observed.add(
        project_ath_context(_known_evidence(ath_value=None)).reason
    )
    observed.add(
        project_ath_context(_known_evidence(ath_value="abc")).reason
    )
    observed.add(
        project_ath_context(
            _known_evidence(ath_value=float("nan"))
        ).reason
    )
    observed.add(
        project_ath_context(_known_evidence(ath_value=0)).reason
    )
    observed.add(
        project_ath_context(
            _known_evidence(ath_unit=ATH_UNIT_UNKNOWN)
        ).reason
    )
    observed.add(
        project_ath_context(
            _known_evidence(ath_unit=ATH_UNIT_SOL),
            market_context_unit=ATH_UNIT_USD,
        ).reason
    )
    observed.add(
        project_ath_context(_known_evidence(redaction_safe=False)).reason
    )
    observed.add(project_ath_context(None).reason)
    assert observed == set(ATH_REASON_VALUES), (
        f"unreached reasons: {sorted(set(ATH_REASON_VALUES) - observed)}"
    )
