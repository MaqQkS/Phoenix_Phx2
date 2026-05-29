"""Stage 30.7.4 handoff document tests.

Asserts the Stage 30.7.4 handoff markdown
(``STAGE_30_7_ATH_CONTEXT_HANDOFF.md``) exists and contains the mandated
handoff content:

  * the accepted sanitized aliases (with their upstream alternates),
  * the required safe-display conditions,
  * the expected Unknown cases,
  * the compact path through the ``ath_context_resolver`` seam into the
    existing ``ath_mc_text`` slot,
  * a code-like pseudo example,
  * the future-integration warnings.

Doc only. No live call, no env read, no provider, no Discord.
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage30.stage30_7_4_manifest import (
    STAGE30_7_4_HANDOFF_BASENAME,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
HANDOFF_PATH: Path = STAGE30_ROOT / STAGE30_7_4_HANDOFF_BASENAME


def _handoff_text() -> str:
    return HANDOFF_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Doc exists
# ---------------------------------------------------------------------------


def test_handoff_doc_exists() -> None:
    assert HANDOFF_PATH.is_file(), (
        f"Stage 30.7.4 requires {STAGE30_7_4_HANDOFF_BASENAME}"
    )
    assert _handoff_text().strip() != ""


# ---------------------------------------------------------------------------
# 2. Accepted sanitized aliases
# ---------------------------------------------------------------------------


def test_handoff_lists_all_accepted_aliases() -> None:
    text = _handoff_text()
    for alias in (
        "ath_value",
        "ath_unit",
        "source_status",
        "ath_status",
        "basis",
        "drawdown_basis",
        "redaction_safe",
        "source_label",
        "ath_source",
        "observed_at_utc",
        "ath_observed_at_utc",
    ):
        assert alias in text, (
            f"handoff must list accepted alias {alias!r}"
        )


def test_handoff_pairs_upstream_alternate_aliases() -> None:
    # The "X or Y" upstream-alternate pairs must be documented together.
    normalized = _normalized(_handoff_text())
    for primary, alternate in (
        ("source_status", "ath_status"),
        ("basis", "drawdown_basis"),
        ("source_label", "ath_source"),
        ("observed_at_utc", "ath_observed_at_utc"),
    ):
        assert primary in normalized and alternate in normalized, (
            f"handoff must document the {primary!r}/{alternate!r} pair"
        )


# ---------------------------------------------------------------------------
# 3. Required safe display conditions
# ---------------------------------------------------------------------------


def test_handoff_states_required_safe_display_conditions() -> None:
    normalized = _normalized(_handoff_text())
    for condition in (
        "source PRESENT",
        "unit USD",
        "ATH_MARKET_CAP_OBSERVED",
        "MARKET_CAP_OBSERVED",
        "redaction_safe exactly True",
        "positive finite scalar",
    ):
        assert condition in normalized, (
            f"handoff must state required safe-display condition "
            f"{condition!r}"
        )


# ---------------------------------------------------------------------------
# 4. Expected Unknown cases
# ---------------------------------------------------------------------------


def test_handoff_states_expected_unknown_cases() -> None:
    normalized = _normalized(_handoff_text())
    for case in (
        "missing redaction_safe",
        "price-derived",
        "USDC",
        "SOL with USD context",
        "stale / error / conflicting / unavailable",
        "nested / raw-like payloads",
    ):
        assert case in normalized, (
            f"handoff must state expected Unknown case {case!r}"
        )


# ---------------------------------------------------------------------------
# 5. Compact path through ath_context_resolver + ath_mc_text
# ---------------------------------------------------------------------------


def test_handoff_states_compact_path() -> None:
    normalized = _normalized(_handoff_text())
    assert "ath_context_resolver" in normalized, (
        "handoff must reference the ath_context_resolver seam"
    )
    assert "ath_mc_text" in normalized, (
        "handoff must reference the ath_mc_text slot"
    )
    assert "Stage30_7_2AthDisplayResolver" in normalized, (
        "handoff must reference the Stage30_7_2AthDisplayResolver"
    )
    # The ordered path: sanitized bridge -> resolver -> seam -> slot.
    assert (
        "sanitized bridge -> Stage30_7_2AthDisplayResolver -> "
        "ath_context_resolver seam -> ath_mc_text" in normalized
    ), "handoff must contain the ordered compact path"


# ---------------------------------------------------------------------------
# 6. Pseudo example + future-integration warnings
# ---------------------------------------------------------------------------


def test_handoff_contains_pseudo_example() -> None:
    text = _handoff_text()
    # A code-like pseudo example referencing the bridge entry point.
    assert "```python" in text, (
        "handoff must contain a fenced code-like pseudo example"
    )
    assert (
        "build_stage30_ath_resolver_from_sanitized_evidence" in text
    ), "pseudo example must reference the bridge resolver builder"


def test_handoff_states_future_integration_warnings() -> None:
    normalized = _normalized(_handoff_text())
    for warning in (
        "do not import provider modules",
        "do not pass raw provider payloads",
        "do not use `runtime_consumable` as a live permission",
        "do not mix ATH display with tier recomputation",
    ):
        # Compare case-insensitively (the doc capitalizes the lead word).
        assert warning.lower() in normalized.lower(), (
            f"handoff must state future-integration warning {warning!r}"
        )
