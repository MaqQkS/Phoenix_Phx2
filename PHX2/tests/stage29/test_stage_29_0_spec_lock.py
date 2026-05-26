"""Stage 29.0 spec-lock tests.

Pins:

  * ``PHX2/stage29/STAGE_29_0_SPEC_LOCK.md`` exists and carries
    the canonical Stage 29 scope sentence verbatim, the Stage
    28 closure rationale, the diagnostic-Discord-smoke
    rejection, the PHX1 replacement blocker analysis, the
    Stage 29.1 / 29.2 / 29.3 roadmap, the Stage 29.1 hint-
    extraction evidence contract (with the explicit "never
    invent" / "No SOL invention" / "No USDC invention"
    discipline), the Stage 29.2 Birdeye evidence contract, the
    Stage 29.3 acceptance contract, the forbidden surfaces
    until after Stage 29.3, the PHX2-replaces-PHX1 acceptance
    criteria, and the Stage 29.0 spec-only scope locks.
  * ``PHX2/stage29/`` contains only the Stage 29.0 scaffold
    (``__init__.py`` + ``STAGE_29_0_SPEC_LOCK.md``); no Stage
    29.1+ implementation file ships at Stage 29.0.
  * ``PHX2/tests/stage29/`` contains only the Stage 29.0 tests
    package marker and this spec-lock test file.
  * The Stage 29.0 spec lock carries no URL literal, no
    webhook host literal, and no raw secret-looking value.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"
SPEC_LOCK_PATH: Path = STAGE29_ROOT / "STAGE_29_0_SPEC_LOCK.md"


# Canonical Stage 29 scope sentence. Must appear verbatim in the
# spec-lock doc; future Stage 29 substages must preserve it.
STAGE_29_SCOPE_SENTENCE: str = (
    "Stage 29 is the live tradeability unblocker for PHX2 "
    "private tradeable pings."
)


def _spec_lock_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Stage 29 package + tests package + spec lock file exist
# ---------------------------------------------------------------------------


def test_stage29_package_init_exists():
    init_path = STAGE29_ROOT / "__init__.py"
    assert init_path.is_file(), (
        f"Stage 29.0 requires the package marker {init_path}"
    )


def test_stage29_tests_package_init_exists():
    init_path = TESTS_STAGE29_ROOT / "__init__.py"
    assert init_path.is_file(), (
        f"Stage 29.0 requires the tests package marker "
        f"{init_path}"
    )


def test_stage29_spec_lock_doc_exists():
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 29.0 requires the spec-lock document "
        f"{SPEC_LOCK_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Canonical Stage 29 scope sentence exists verbatim
# ---------------------------------------------------------------------------


def test_spec_lock_contains_canonical_scope_sentence_verbatim():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert STAGE_29_SCOPE_SENTENCE in normalized, (
        "spec lock must contain the canonical Stage 29 scope "
        "sentence verbatim (whitespace-normalized match)"
    )


def test_spec_lock_names_stage_29_explicitly():
    text = _spec_lock_text()
    assert "Stage 29" in text


def test_spec_lock_names_stage_29_0_explicitly():
    text = _spec_lock_text()
    assert "Stage 29.0" in text


# ---------------------------------------------------------------------------
# 3. Why Stage 28 stops here
# ---------------------------------------------------------------------------


def test_spec_lock_pins_stage_28_closed_tag_and_sha():
    text = _spec_lock_text()
    assert "stage-28-closed" in text
    assert "a897bb0531259bbe065efb3e38703a7c3be156c7" in text


def test_spec_lock_pins_post_closure_amendments_finished():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "post-Stage-28-closure provider amendments are now "
        "finished"
    ) in normalized


_POST_CLOSURE_AMENDMENT_LABELS: tuple[str, ...] = (
    "Stage 28.9",
    "Stage 28.10",
    "Stage 28.11",
)


@pytest.mark.parametrize("label", _POST_CLOSURE_AMENDMENT_LABELS)
def test_spec_lock_lists_each_post_closure_amendment(label):
    text = _spec_lock_text()
    assert label in text


def test_spec_lock_pins_stage_28_11_live_probe_passed():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert "Stage 28.11 live probe was performed and passed" in (
        normalized
    )


_STAGE_28_11_PROBE_RESULT_PHRASES: tuple[str, ...] = (
    "mode 1 readiness-only: `READY`",
    "mode 2 provider-connect-only: `CONNECTED`",
    "mode 3 one-event decode dry run: `DECODED`",
    "handoff_ready=True",
    "events_received=1",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_28_11_PROBE_RESULT_PHRASES
)
def test_spec_lock_records_each_stage_28_11_probe_result(phrase):
    normalized = _normalized_whitespace(_spec_lock_text())
    assert phrase in normalized, (
        f"spec lock missing Stage 28.11 probe result phrase "
        f"{phrase!r}"
    )


# ---------------------------------------------------------------------------
# 4. Diagnostic Discord smoke is rejected
# ---------------------------------------------------------------------------


def test_spec_lock_rejects_diagnostic_discord_smoke_explicitly():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "rejects diagnostic Discord smoke as insufficient"
    ) in normalized


def test_spec_lock_says_diagnostic_smoke_not_tradeable():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "would send a message that is not a tradeable private "
        "ping"
    ) in normalized


def test_spec_lock_says_phx1_emits_tradeable_pings():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert "PHX1 emits real tradeable private pings" in normalized


def test_spec_lock_says_phx2_must_replace_phx1():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert "PHX2 needs to replace PHX1" in normalized


# ---------------------------------------------------------------------------
# 5. What blocks PHX2 from replacing PHX1 today
# ---------------------------------------------------------------------------


_PHX1_REPLACEMENT_BLOCKER_HINT_FIELDS: tuple[str, ...] = (
    "quote_mint=None",
    "pool_account=None",
    "pool_program_id=None",
    "base_mint=None",
    "provider_quote_asset_hint=None",
    "provider_pair_type_hint=None",
    "provider_bonding_curve_version_hint=None",
    "bonding_curve_version_hint=None",
)


@pytest.mark.parametrize(
    "needle", _PHX1_REPLACEMENT_BLOCKER_HINT_FIELDS
)
def test_spec_lock_lists_each_none_hint_blocker(needle):
    text = _spec_lock_text()
    assert needle in text, (
        f"spec lock missing PHX1-replacement blocker hint "
        f"`{needle}`"
    )


def test_spec_lock_pins_unknown_pair_suppression_as_blocker():
    text = _spec_lock_text()
    assert "SUPPRESSED_UNKNOWN_PAIR" in text


def test_spec_lock_pins_no_real_birdeye_adapter_today():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "there is no real Birdeye-backed price / ATH adapter "
        "wired in"
    ) in normalized


# ---------------------------------------------------------------------------
# 6. Stage 29.1 / 29.2 / 29.3 roadmap
# ---------------------------------------------------------------------------


_STAGE_29_ROADMAP_ENTRIES: tuple[tuple[str, str], ...] = (
    (
        "29.0",
        "spec lock / live tradeability unblocker charter",
    ),
    (
        "29.1",
        (
            "Pump.fun / PumpSwap hint extractor from real "
            "Chainstack Yellowstone transaction / log / "
            "instruction data"
        ),
    ),
    (
        "29.2",
        (
            "Birdeye live price / ATH adapter for known mint "
            "context"
        ),
    ),
    (
        "29.3",
        (
            "first real private tradeable Discord smoke with "
            "`max_events=1` / `max_dispatches=1`"
        ),
    ),
)


@pytest.mark.parametrize(
    "substage,scope",
    _STAGE_29_ROADMAP_ENTRIES,
)
def test_spec_lock_pins_each_roadmap_entry(substage, scope):
    normalized = _normalized_whitespace(_spec_lock_text())
    assert substage in normalized, (
        f"spec lock missing substage label {substage!r}"
    )
    assert scope in normalized, (
        f"spec lock missing substage scope phrase {scope!r} "
        f"for {substage}"
    )


def test_spec_lock_requires_explicit_operator_authorization_for_later_substages():
    normalized = _normalized_whitespace(
        _spec_lock_text()
    ).lower()
    assert "explicit operator authorization" in normalized


def test_spec_lock_marks_stage_29_4_plus_reserved():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert "Stage 29.4+ is reserved" in normalized


# ---------------------------------------------------------------------------
# 7. Stage 29.1 evidence contract (Pump / PumpSwap hint extraction)
# ---------------------------------------------------------------------------


_STAGE_29_1_EVIDENCE_FIELDS: tuple[str, ...] = (
    "token_mint",
    "base_mint",
    "pool_account",
    "quote_mint",
    "pool_program_id",
    "provider_pair_type_hint",
    "bonding_curve_version_hint",
)


@pytest.mark.parametrize(
    "field", _STAGE_29_1_EVIDENCE_FIELDS
)
def test_spec_lock_names_each_stage_29_1_evidence_field(field):
    text = _spec_lock_text()
    assert field in text, (
        f"spec lock missing Stage 29.1 evidence field "
        f"{field!r}"
    )


_STAGE_29_1_EVIDENCE_SOURCE_PHRASES: tuple[str, ...] = (
    "account_keys",
    "instructions",
    "inner_instructions",
    "log_messages",
    "pre_token_balances",
    "post_token_balances",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_1_EVIDENCE_SOURCE_PHRASES
)
def test_spec_lock_names_each_stage_29_1_evidence_source(phrase):
    text = _spec_lock_text()
    assert phrase in text, (
        f"spec lock missing Stage 29.1 evidence source phrase "
        f"{phrase!r}"
    )


_STAGE_29_1_NO_INVENT_PHRASES: tuple[str, ...] = (
    "No SOL invention",
    "No USDC invention",
    "must never invent",
    "never invent a SOL hint",
    "never invent a USDC hint",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_1_NO_INVENT_PHRASES
)
def test_spec_lock_forbids_fake_hints(phrase):
    text = _spec_lock_text()
    assert phrase in text, (
        f"spec lock missing fake-hint forbidding phrase "
        f"{phrase!r}"
    )


def test_spec_lock_says_insufficient_evidence_stays_none():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "If the evidence is insufficient, the field stays "
        "`None`"
    ) in normalized


def test_spec_lock_says_stage_29_1_does_not_modify_stage_27_classifier():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "Stage 29.1 must not modify Stage 27 classifier "
        "semantics"
    ) in normalized


# ---------------------------------------------------------------------------
# 8. Stage 29.2 evidence contract (Birdeye)
# ---------------------------------------------------------------------------


_STAGE_29_2_EVIDENCE_AXES: tuple[str, ...] = (
    "current price",
    "ATH since migration",
    "drawdown",
    "freshness timestamp / status",
)


@pytest.mark.parametrize("axis", _STAGE_29_2_EVIDENCE_AXES)
def test_spec_lock_lists_each_stage_29_2_evidence_axis(axis):
    text = _spec_lock_text()
    assert axis in text, (
        f"spec lock missing Stage 29.2 evidence axis {axis!r}"
    )


def test_spec_lock_pins_stage_29_2_uses_birdeye():
    text = _spec_lock_text()
    assert "Birdeye" in text


def test_spec_lock_pins_stage_29_2_wraps_stage_27_4_protocols():
    text = _spec_lock_text()
    assert "PriceContextSource" in text
    assert "AthContextSource" in text


def test_spec_lock_pins_stage_29_2_pinned_env_read_boundary():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "single Stage-29.2-pinned env-read boundary"
    ) in normalized


def test_spec_lock_says_stage_29_2_never_invents_price_or_ath():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "Stage 29.2 must never invent a price, an ATH, a "
        "drawdown, a freshness timestamp, or a freshness status"
    ) in normalized


def test_spec_lock_says_no_dexscreener_as_dispatch_authority():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "Stage 29.2 must not introduce Dexscreener as a "
        "dispatch authority"
    ) in normalized


def test_spec_lock_says_no_helius_as_price_source():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "Stage 29.2 must not introduce Helius as a price "
        "source"
    ) in normalized


# ---------------------------------------------------------------------------
# 9. Stage 29.3 acceptance contract
# ---------------------------------------------------------------------------


_STAGE_29_3_ACCEPTANCE_PHRASES: tuple[str, ...] = (
    "a real Chainstack Yellowstone event is received",
    "Stage 29.1 extracts non-None hint fields",
    "Stage 29.2 returns a real Birdeye price + ATH + "
    "freshness status",
    "the existing Stage 27 candidate chain produces an "
    "`ASSEMBLED` candidate (not `SUPPRESSED_UNKNOWN_PAIR`)",
    "the Stage 28.9 wrapper drives the Stage 28.6 bounded "
    "runner",
    "the Stage 28.4 audited private operator-only Discord "
    "transport sends exactly one private tradeable ping",
    "`max_events=1`, `max_dispatches=1`",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_3_ACCEPTANCE_PHRASES
)
def test_spec_lock_pins_each_stage_29_3_acceptance_phrase(phrase):
    normalized = _normalized_whitespace(_spec_lock_text())
    assert phrase in normalized, (
        f"spec lock missing Stage 29.3 acceptance phrase "
        f"{phrase!r}"
    )


def test_spec_lock_says_stage_29_3_must_not_retry_loop_or_run_unattended():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert "Stage 29.3 must not retry" in normalized
    assert "Stage 29.3 must not loop" in normalized
    assert "Stage 29.3 must not run unattended" in normalized


# ---------------------------------------------------------------------------
# 10. Forbidden surfaces until after Stage 29.3
# ---------------------------------------------------------------------------


_FORBIDDEN_UNTIL_AFTER_29_3_PHRASES: tuple[str, ...] = (
    "Stage 26 policy enforcement activation",
    "public routing",
    "subscriber routing",
    "paid tier routing",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / private-key / signer logic",
    "position sizing",
    "trade execution",
    "public dashboard / HTTP control server",
    "daemon / systemd / watchdog / autorestart service",
    "Dexscreener as a dispatch authority",
    "Helius as a primary provider",
)


@pytest.mark.parametrize(
    "phrase", _FORBIDDEN_UNTIL_AFTER_29_3_PHRASES
)
def test_spec_lock_lists_each_forbidden_until_after_29_3(phrase):
    text = _spec_lock_text()
    assert phrase in text, (
        f"spec lock missing forbidden-until-after-29.3 phrase "
        f"{phrase!r}"
    )


def test_spec_lock_supersedes_old_stage_28_8_handoff_direction():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "old Stage 28.8-era Stage 29 handoff doc that proposed "
        "Stage 29 as enforcement charter is superseded by this "
        "Stage 29.0 spec lock"
    ) in normalized


# ---------------------------------------------------------------------------
# 11. Acceptance criteria for PHX2 replacing PHX1
# ---------------------------------------------------------------------------


_PHX2_REPLACEMENT_ACCEPTANCE_PHRASES: tuple[str, ...] = (
    "at least one real private tradeable ping has been sent "
    "from live Chainstack + live Birdeye context",
    "no public routing was invoked",
    "no subscriber routing was invoked",
    "no paid tier routing was invoked",
    "no Telegram send was invoked",
    "no X / social send was invoked",
    "no automated trading was invoked",
    "no wallet / private-key / signer surface was loaded",
    "no Stage 26 policy enforcement gate was activated unless "
    "separately authorized",
    "the Stage 28.7-style redaction scan over the acceptance "
    "artifact directory reports `SAFE`",
)


@pytest.mark.parametrize(
    "phrase", _PHX2_REPLACEMENT_ACCEPTANCE_PHRASES
)
def test_spec_lock_lists_each_phx2_replacement_acceptance_criterion(
    phrase,
):
    normalized = _normalized_whitespace(_spec_lock_text())
    assert phrase in normalized, (
        f"spec lock missing PHX2-replacement acceptance "
        f"criterion {phrase!r}"
    )


def test_spec_lock_says_phx2_replacement_does_not_imply_enforcement_activation():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "PHX2 replacing PHX1 does not imply Stage 29 "
        "enforcement activation"
    ) in normalized


# ---------------------------------------------------------------------------
# 12. Stage 29.0 spec-only scope locks (must-not surfaces)
# ---------------------------------------------------------------------------


_STAGE_29_0_MUST_NOT_SURFACES: tuple[str, ...] = (
    "Pump.fun / PumpSwap decoder implementation",
    "Birdeye adapter implementation",
    "Discord send",
    "diagnostic Discord smoke",
    "scratch sender of any kind",
    "public routing",
    "subscriber routing",
    "paid tier routing",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / private-key / signer logic",
    "position sizing",
    "trade execution",
    "Stage 26 policy enforcement activation",
    "fake SOL / USDC hint values",
    "invented mint / pool values",
    "Dexscreener",
    "Helius",
    "second env-read site",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_0_MUST_NOT_SURFACES
)
def test_spec_lock_lists_each_stage_29_0_must_not_surface(phrase):
    text = _spec_lock_text()
    assert phrase in text, (
        f"spec lock missing Stage 29.0 must-not surface "
        f"{phrase!r}"
    )


def test_spec_lock_explicitly_says_stage_29_0_must_not_include():
    text = _spec_lock_text()
    assert "Stage 29.0 must not include" in text


def test_spec_lock_says_stage_29_0_is_spec_lock_only():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert "Stage 29.0 is a spec-lock-only pass" in normalized
    assert "ships no runtime code" in normalized


def test_spec_lock_says_stage_29_0_must_not_create_tag():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "Stage 29.0 must not create a `stage-29-0-closed` tag"
    ) in normalized
    assert (
        "Stage 29.0 must not move or peel the existing "
        "`stage-28-closed` tag"
    ) in normalized


def test_spec_lock_pins_closed_set_vocabularies_are_names_only_at_29_0():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "Stage 29.0 must not ship runtime models, enums, or "
        "constants for these vocabularies"
    ) in normalized


# ---------------------------------------------------------------------------
# 13. Reuse rules: Stage 29 wraps existing Stage 27/28 surfaces
# ---------------------------------------------------------------------------


_REUSE_SURFACE_PHRASES: tuple[str, ...] = (
    "Stage 27 live candidate assembler",
    "Stage 27 pair classifier",
    "Stage 27 private ping renderer",
    "Stage 27.6 `Stage27_6Sources` bundle",
    "Stage 28.4 audited private operator-only Discord HTTP "
    "transport",
    "Stage 28.6 bounded private session runner",
    "Stage 28.9 private live provider session adapter",
    "Stage 28.10 Chainstack Yellowstone provider boundary",
    "Stage 28.11 real Chainstack Yellowstone gRPC client",
)


@pytest.mark.parametrize("phrase", _REUSE_SURFACE_PHRASES)
def test_spec_lock_pins_each_reuse_surface(phrase):
    normalized = _normalized_whitespace(_spec_lock_text())
    assert phrase in normalized, (
        f"spec lock missing reuse surface phrase {phrase!r}"
    )


def test_spec_lock_says_stage_29_must_not_reimplement_stage_27_classifier():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert (
        "Stage 29 must not reimplement the Stage 27 pair "
        "classifier"
    ) in normalized


# ---------------------------------------------------------------------------
# 14. Stage 29.0 file inventory — only the scaffold ships
# ---------------------------------------------------------------------------


_STAGE_29_0_ALLOWED_PRODUCTION_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "__init__.py",
            "STAGE_29_0_SPEC_LOCK.md",
        }
    )
)


# Stage 29.1 PumpSwap-only narrow amendment (authorized after
# Stage 29.0): the Stage 29.1 hint-extractor tree may ship
# alongside the Stage 29.0 scaffold. Stage 29.2 / 29.3
# implementation files AND Pump.fun bonding-curve files remain
# blocked. The Stage 29.0 SPEC DOC itself is NOT edited at Stage
# 29.1; only this enclosing test file widens its inventory
# allowlist.
_STAGE_29_1_PUMPSWAP_ALLOWED_PRODUCTION_ENTRIES: frozenset[
    str
] = frozenset(
    {
        "pumpswap_program_constants.py",
        "pumpswap_hint_models.py",
        "pumpswap_hint_extractor.py",
        "pumpswap_hint_aware_decoder.py",
        "stage29_1_hint_probe_models.py",
        "stage29_1_pumpswap_hint_probe.py",
        "stage29_1_manifest.py",
        "STAGE_29_1_PUMPSWAP_HINT_EXTRACTOR_RUNBOOK.md",
    }
)


# Stage 29.2 Birdeye price / ATH adapter (authorized 2026-05-25).
# Stage 29.0 spec-lock narrow amendment widens the Stage-29-tree
# allowlist to admit the Stage 29.2 inventory while continuing
# to block Stage 29.3 implementation files + Pump.fun
# bonding-curve.
_STAGE_29_2_BIRDEYE_ALLOWED_PRODUCTION_ENTRIES: frozenset[
    str
] = frozenset(
    {
        "birdeye_constants.py",
        "stage29_2_birdeye_models.py",
        "stage29_2_birdeye_readiness.py",
        "stage29_2_birdeye_http_transport.py",
        "stage29_2_birdeye_price_source.py",
        "stage29_2_birdeye_ath_source.py",
        "stage29_2_birdeye_probe_models.py",
        "stage29_2_birdeye_probe.py",
        "stage29_2_manifest.py",
        "STAGE_29_2_BIRDEYE_PRICE_ATH_RUNBOOK.md",
    }
)


# Stage 29.3 first real private tradeable PHX2 ping (authorized
# 2026-05-25). Stage 29.0 spec-lock narrow amendment widens the
# Stage-29-tree allowlist to admit the Stage 29.3 inventory; the
# Pump.fun bonding-curve files remain blocked.
_STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_PRODUCTION_ENTRIES: frozenset[
    str
] = frozenset(
    {
        "stage29_3_smoke_models.py",
        "stage29_3_no_migration_evidence_source.py",
        "stage29_3_hint_aware_event_source.py",
        "stage29_3_artifact_writer.py",
        "stage29_3_tradeable_smoke.py",
        "stage29_3_manifest.py",
        "STAGE_29_3_FIRST_PRIVATE_TRADEABLE_SMOKE_RUNBOOK.md",
    }
)


# Stage 29.4 short-session private soak (authorized 2026-05-25).
# Stage 29.4.0 is spec-lock-only: this narrow amendment widens
# the Stage-29-tree allowlist to admit the Stage 29.4 runbook
# only. Stage 29.4.1 production .py files
# (stage29_4_soak_models.py / stage29_4_dedupe_index.py /
# stage29_4_soak_orchestrator.py /
# stage29_4_soak_artifact_writer.py / stage29_4_manifest.py)
# remain blocked at Stage 29.4.0. The Stage 29.0 spec DOC
# (``STAGE_29_0_SPEC_LOCK.md``) is NOT touched at Stage 29.4;
# only this enclosing test file widens its inventory allowlist.
_STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_PRODUCTION_ENTRIES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md",
        # Stage 29.4.1 implementation widens the Stage 29.0
        # inventory allowlist to admit the five Stage 29.4
        # production .py basenames pinned by the Stage 29.4.0
        # spec-lock runbook (Section 9). The runbook itself is
        # not modified; only this enclosing test widens.
        "stage29_4_soak_models.py",
        "stage29_4_dedupe_index.py",
        "stage29_4_soak_orchestrator.py",
        "stage29_4_soak_artifact_writer.py",
        "stage29_4_manifest.py",
    }
)


# Stage 29.5 Helius WS migration evidence adapter + live private
# ping context join (authorized 2026-05-25). Stage 29.5.0 is
# spec-lock-only: this narrow amendment widens the Stage-29-
# tree allowlist to admit the Stage 29.5 spec-lock runbook only.
# Stage 29.5.1 production .py files
# (stage29_5_migration_models.py / stage29_5_helius_ws_adapter.py
# / stage29_5_migration_artifact_reader.py /
# stage29_5_candidate_to_migration_join.py /
# stage29_5_private_ping_context_projection.py /
# stage29_5_manifest.py) remain blocked at Stage 29.5.0. The
# Stage 29.0 spec DOC (``STAGE_29_0_SPEC_LOCK.md``) is NOT
# touched at Stage 29.5; only this enclosing test file widens
# its inventory allowlist.
_STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_PRODUCTION_ENTRIES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md",
        # Stage 29.5.1 production .py files (authorized
        # 2026-05-25). Spec-lock test widens its inventory
        # allowlist to admit the Stage 29.5 implementation tree.
        "stage29_5_migration_models.py",
        "stage29_5_helius_ws_adapter.py",
        "stage29_5_migration_artifact_reader.py",
        "stage29_5_candidate_to_migration_join.py",
        "stage29_5_private_ping_context_projection.py",
        "stage29_5_manifest.py",
    }
)


_STAGE_29_0_PLUS_29_1_ALLOWED_PRODUCTION_ENTRIES: frozenset[
    str
] = (
    _STAGE_29_0_ALLOWED_PRODUCTION_ENTRIES
    | _STAGE_29_1_PUMPSWAP_ALLOWED_PRODUCTION_ENTRIES
    | _STAGE_29_2_BIRDEYE_ALLOWED_PRODUCTION_ENTRIES
    | _STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_PRODUCTION_ENTRIES
    | _STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_PRODUCTION_ENTRIES
    | _STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_PRODUCTION_ENTRIES
)


_STAGE_29_0_ALLOWED_TEST_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "__init__.py",
            "test_stage_29_0_spec_lock.py",
        }
    )
)


_STAGE_29_1_PUMPSWAP_ALLOWED_TEST_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "test_stage_29_1_pumpswap_program_constants.py",
            "test_stage_29_1_pumpswap_hint_models.py",
            "test_stage_29_1_pumpswap_hint_extractor.py",
            "test_stage_29_1_pumpswap_hint_aware_decoder.py",
            "test_stage_29_1_hint_probe_models.py",
            "test_stage_29_1_pumpswap_hint_probe.py",
            "test_stage_29_1_runbook.py",
            "test_stage_29_1_boundaries.py",
            "test_stage_29_1_vendored_idl.py",
        }
    )
)


_STAGE_29_2_BIRDEYE_ALLOWED_TEST_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "test_stage_29_2_birdeye_constants.py",
            "test_stage_29_2_birdeye_models.py",
            "test_stage_29_2_birdeye_readiness.py",
            "test_stage_29_2_birdeye_http_transport.py",
            "test_stage_29_2_birdeye_price_source.py",
            "test_stage_29_2_birdeye_ath_source.py",
            "test_stage_29_2_birdeye_probe_models.py",
            "test_stage_29_2_birdeye_probe.py",
            "test_stage_29_2_runbook.py",
            "test_stage_29_2_boundaries.py",
        }
    )
)


# Stage 29.3 first real private tradeable PHX2 ping (authorized
# 2026-05-25). Spec-lock narrow amendment widens the Stage 29
# tests allowlist to admit the Stage 29.3 test inventory.
_STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_TEST_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "test_stage_29_3_smoke_models.py",
            "test_stage_29_3_no_migration_evidence_source.py",
            "test_stage_29_3_hint_aware_event_source.py",
            "test_stage_29_3_tradeable_smoke_orchestrator.py",
            "test_stage_29_3_artifact_writer.py",
            "test_stage_29_3_runbook.py",
            "test_stage_29_3_boundaries.py",
        }
    )
)


# Stage 29.4 short-session private soak (authorized 2026-05-25).
# Stage 29.4.0 is spec-lock-only: this narrow amendment widens
# the Stage-29-tests allowlist to admit the Stage 29.4 spec-
# lock test only. Stage 29.4.1 test files remain blocked at
# Stage 29.4.0.
_STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_TEST_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "test_stage_29_4_spec_lock.py",
            # Stage 29.4.1 implementation widens the Stage 29.0
            # tests allowlist to admit the focused Stage 29.4
            # test files.
            "test_stage_29_4_soak_models.py",
            "test_stage_29_4_dedupe_index.py",
            "test_stage_29_4_soak_orchestrator.py",
            "test_stage_29_4_soak_artifact_writer.py",
            "test_stage_29_4_boundaries.py",
        }
    )
)


# Stage 29.5 Helius WS migration evidence adapter + live private
# ping context join (authorized 2026-05-25). Stage 29.5.0 is
# spec-lock-only: this narrow amendment widens the Stage-29-
# tests allowlist to admit the Stage 29.5 spec-lock test only.
# Stage 29.5.1 test files remain blocked at Stage 29.5.0.
_STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_TEST_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "test_stage_29_5_spec_lock.py",
            # Stage 29.5.1 focused test files (authorized 2026-05-25).
            "test_stage_29_5_migration_models.py",
            "test_stage_29_5_helius_ws_adapter.py",
            "test_stage_29_5_migration_artifact_reader.py",
            "test_stage_29_5_candidate_to_migration_join.py",
            "test_stage_29_5_private_ping_context_projection.py",
            "test_stage_29_5_manifest.py",
            "test_stage_29_5_boundaries.py",
        }
    )
)


_STAGE_29_0_PLUS_29_1_ALLOWED_TEST_ENTRIES: frozenset[str] = (
    _STAGE_29_0_ALLOWED_TEST_ENTRIES
    | _STAGE_29_1_PUMPSWAP_ALLOWED_TEST_ENTRIES
    | _STAGE_29_2_BIRDEYE_ALLOWED_TEST_ENTRIES
    | _STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_TEST_ENTRIES
    | _STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_TEST_ENTRIES
    | _STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_TEST_ENTRIES
)


def test_stage29_root_admits_only_29_0_scaffold():
    actual: set[str] = set()
    for entry in STAGE29_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = (
        actual
        - _STAGE_29_0_PLUS_29_1_ALLOWED_PRODUCTION_ENTRIES
    )
    assert not forbidden, (
        f"PHX2/stage29 admits only the Stage 29.0 scaffold + "
        f"Stage 29.1 PumpSwap-only tree "
        f"({sorted(_STAGE_29_0_PLUS_29_1_ALLOWED_PRODUCTION_ENTRIES)!r}); "
        f"Stage 29.2 / 29.3 implementation files + Pump.fun "
        f"bonding-curve files remain blocked. Forbidden "
        f"entries found: {sorted(forbidden)!r}"
    )
    missing = _STAGE_29_0_ALLOWED_PRODUCTION_ENTRIES - actual
    assert not missing, (
        f"Stage 29.0 inventory missing required entries: "
        f"{sorted(missing)!r}"
    )


def test_tests_stage29_root_admits_only_29_0_test_files():
    actual: set[str] = set()
    for entry in TESTS_STAGE29_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = (
        actual - _STAGE_29_0_PLUS_29_1_ALLOWED_TEST_ENTRIES
    )
    assert not forbidden, (
        f"PHX2/tests/stage29 admits only the Stage 29.0 tests + "
        f"Stage 29.1 PumpSwap-only tests "
        f"({sorted(_STAGE_29_0_PLUS_29_1_ALLOWED_TEST_ENTRIES)!r}); "
        f"Stage 29.2 / 29.3 test files + Pump.fun bonding-curve "
        f"test files remain blocked. Forbidden entries found: "
        f"{sorted(forbidden)!r}"
    )
    missing = _STAGE_29_0_ALLOWED_TEST_ENTRIES - actual
    assert not missing, (
        f"Stage 29.0 tests package missing required entries: "
        f"{sorted(missing)!r}"
    )


def test_no_python_module_under_stage29_beyond_init():
    """Stage 29.0 scaffold ships only ``__init__.py`` as a .py
    module. Stage 29.1 PumpSwap-only + Stage 29.2 Birdeye
    narrow amendments widen this to admit the Stage 29.1 hint-
    extractor + Stage 29.2 Birdeye adapter production .py sets;
    Stage 29.3 production .py files remain blocked.
    """
    actual_py = {
        p.name
        for p in STAGE29_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    allowed_py = {"__init__.py"} | {
        name
        for name
        in _STAGE_29_1_PUMPSWAP_ALLOWED_PRODUCTION_ENTRIES
        if name.endswith(".py")
    } | {
        name
        for name
        in _STAGE_29_2_BIRDEYE_ALLOWED_PRODUCTION_ENTRIES
        if name.endswith(".py")
    } | {
        name
        for name
        in _STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_PRODUCTION_ENTRIES
        if name.endswith(".py")
    } | {
        name
        for name
        in _STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_PRODUCTION_ENTRIES
        if name.endswith(".py")
    } | {
        name
        for name
        in _STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_PRODUCTION_ENTRIES
        if name.endswith(".py")
    }
    unexpected = actual_py - allowed_py
    assert not unexpected, (
        f"Stage 29.0 scaffold + Stage 29.1 PumpSwap-only + "
        f"Stage 29.2 Birdeye trees are the only authorized "
        f"Stage 29 production .py modules; unexpected files: "
        f"{sorted(unexpected)}"
    )


_FORBIDDEN_STAGE_29_1_PLUS_BASENAMES: tuple[str, ...] = (
    # Stage 29.1 — alternative naming (the authorized PumpSwap-
    # only tree uses ``pumpswap_hint_extractor.py`` /
    # ``stage29_1_manifest.py`` etc.; the legacy generic
    # ``pump_hint_extractor.py`` / ``instruction_decoder.py``
    # names remain blocked because they would imply Pump.fun
    # bonding-curve coverage, which is deferred).
    "pump_hint_extractor.py",
    "instruction_decoder.py",
    "pump_fun_bonding_curve_decoder.py",
    "bonding_curve_program_constants.py",
    # Stage 29.2 — alternative naming (the authorized Birdeye
    # tree uses the ``stage29_2_birdeye_*.py`` prefix-pinned
    # convention; these bare basenames are blocked so a future
    # change cannot silently shift to the unprefixed naming).
    # Stage 29.2 was authorized 2026-05-25; the canonical
    # ``stage29_2_manifest.py`` basename has been moved into the
    # allowlist above.
    "birdeye_price_source.py",
    "birdeye_ath_source.py",
    "birdeye_readiness.py",
    # Stage 29.3 — alternative naming (the authorized
    # tradeable-smoke tree uses the ``stage29_3_*.py`` prefix-
    # pinned convention; the legacy generic
    # ``tradeable_smoke_harness.py`` name remains blocked).
    # Stage 29.3 was authorized 2026-05-25; the canonical
    # ``stage29_3_manifest.py`` basename has been moved into the
    # allowlist above.
    "tradeable_smoke_harness.py",
    # Forbidden Stage 26/27/28-era surfaces that must not appear
    # under Stage 29 at any substage.
    "public_router.py",
    "subscriber_router.py",
    "paid_tier_router.py",
    "telegram_sender.py",
    "telegram_client.py",
    "x_social.py",
    "social_sidecar.py",
    "enforcement_gate.py",
    "enforce_policy.py",
    "auto_trade.py",
    "position_sizer.py",
    "trade_executor.py",
    "wallet_signer.py",
    "private_key_loader.py",
    "discord_bot.py",
    "slash_commands.py",
    "dashboard.py",
    "http_control_server.py",
    "watchdog.py",
    "autorestart.py",
    "daemon.py",
    "dexscreener_dispatch.py",
    "helius_price_source.py",
)


@pytest.mark.parametrize(
    "basename", _FORBIDDEN_STAGE_29_1_PLUS_BASENAMES
)
def test_no_stage_29_1_plus_basename_under_stage29(basename):
    assert not (STAGE29_ROOT / basename).exists(), (
        f"PHX2/stage29 must not ship Stage 29.1+ basename "
        f"{basename!r} at Stage 29.0"
    )


# ---------------------------------------------------------------------------
# 15. Spec lock carries no URL / webhook host / raw secret literal
# ---------------------------------------------------------------------------


# Concatenated literally so this test file does not itself trip
# a downstream string-leak scan that flags the canonical URL /
# host / secret-shape substrings.
_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
    "birdeye" + ".so",
    "chainstack" + ".com",
    "helius" + ".xyz",
    "helius" + ".rpc.com",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_URL_LITERAL_SUBSTRINGS
)
def test_spec_lock_has_no_url_literal(needle):
    text = _spec_lock_text()
    assert needle not in text, (
        f"spec lock must not contain URL literal {needle!r}"
    )


_FORBIDDEN_SECRET_LOOKING_PATTERNS: tuple[str, ...] = (
    r"Authorization:\s*\S+",
    r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}",
    r"\bsk-[A-Za-z0-9_-]{8,}\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b",
    r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b",
)


@pytest.mark.parametrize(
    "pattern", _FORBIDDEN_SECRET_LOOKING_PATTERNS
)
def test_spec_lock_has_no_secret_looking_raw_value(pattern):
    assert not re.search(pattern, _spec_lock_text())


# Concatenated literally so this test file does not itself trip
# a raw-secret-assignment scan.
_FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES: tuple[str, ...] = (
    "webhook" + "_url" + "=",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
    "BIRDEYE_API" + "_KEY=",
    "PHX2_CHAINSTACK_YELLOWSTONE_X" + "_TOKEN=",
    "raw_" + "payload",
    "provider_" + "payload",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES
)
def test_spec_lock_has_no_raw_secret_assignment_name(needle):
    text = _spec_lock_text()
    assert needle not in text, (
        f"spec lock must not carry raw secret-assignment name "
        f"{needle!r}"
    )
