"""Stage 27.0 spec-lock tests.

Pins:

  * ``PHX2/stage27/STAGE_27_0_SPEC_LOCK.md`` exists and carries
    the canonical Stage 27 mission sentence verbatim, the locked
    PHX1-parity definition, the locked tradeable definition, the
    locked "Stage 27 is not X / social" pin, the locked private-
    only routing pin, the locked no-public-routing /
    no-paid-tiers / no-enforcement pins, the locked pair-
    awareness contract (``quote_asset`` / ``pair_type`` /
    ``bonding_curve_version`` with values ``SOL`` / ``USDC`` /
    ``UNKNOWN`` and ``PUMP_SOL`` / ``PUMP_USDC`` / ``UNKNOWN`` and
    ``SOL_LEGACY`` / ``USDC_FIXED`` / ``UNKNOWN``), the locked
    USDC observe-only rule, the locked UNKNOWN-never-defaults-to-
    SOL rule, the locked UNKNOWN-LIVE-suppression rule, the
    locked two-factor LIVE authorization rule, and the locked
    Stage 28 hardening / Stage 29 enforcement / Stage 30+ X /
    social handoffs.
  * ``PHX2/stage27/`` contains only the Stage 27.0 scaffold
    (``__init__.py`` + ``STAGE_27_0_SPEC_LOCK.md``); no Stage
    27.1+ implementation file ships at Stage 27.0.
"""

from __future__ import annotations

from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"
SPEC_LOCK_PATH: Path = STAGE27_ROOT / "STAGE_27_0_SPEC_LOCK.md"


# Canonical Stage 27 mission sentence. Must appear verbatim in the
# spec lock doc; future Stage 27 substages must preserve it.
STAGE_27_MISSION_SENTENCE: str = (
    "Stage 27 turns PHX2 into a private live PHX1-parity tradeable "
    "ping runner, with pair-aware SOL/USDC handling, while keeping "
    "enforcement and public routing out of scope."
)


def _spec_lock_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Spec lock file exists
# ---------------------------------------------------------------------------


def test_stage27_package_init_exists():
    init_path = STAGE27_ROOT / "__init__.py"
    assert init_path.is_file(), (
        f"Stage 27.0 requires the package marker {init_path}"
    )


def test_stage27_spec_lock_doc_exists():
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 27.0 requires the spec-lock document {SPEC_LOCK_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Mission sentence exists exactly
# ---------------------------------------------------------------------------


def test_spec_lock_contains_canonical_mission_sentence_verbatim():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert STAGE_27_MISSION_SENTENCE in normalized, (
        "spec lock must contain the canonical Stage 27 mission "
        "sentence verbatim (whitespace-normalized match)"
    )


def test_spec_lock_names_stage_27_explicitly():
    text = _spec_lock_text()
    assert "Stage 27" in text


# ---------------------------------------------------------------------------
# 3. PHX1-parity definition exists
# ---------------------------------------------------------------------------


_PHX1_PARITY_POSITIVE_PHRASES: tuple[str, ...] = (
    "private operator Discord webhook delivery",
    "usable live ping field-set",
    "bounded operator-controlled runner lifecycle",
    "dedupe",
    "provenance",
    "manual trading",
)


@pytest.mark.parametrize("phrase", _PHX1_PARITY_POSITIVE_PHRASES)
def test_spec_lock_phx1_parity_positive_phrase(phrase):
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert phrase.lower() in normalized, (
        f"spec lock missing PHX1-parity positive phrase {phrase!r}"
    )


_PHX1_PARITY_NEGATIVE_PHRASES: tuple[str, ...] = (
    "public production",
    "paid routing",
    "broad Discord distribution",
    "latency guarantees",
    "signal-quality guarantees",
    "automated trading",
    "Stage 29 enforcement",
)


@pytest.mark.parametrize("phrase", _PHX1_PARITY_NEGATIVE_PHRASES)
def test_spec_lock_phx1_parity_negative_phrase(phrase):
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert phrase.lower() in normalized, (
        f"spec lock missing PHX1-parity excluded phrase {phrase!r}"
    )


def test_spec_lock_phx1_parity_definition_section_exists():
    text = _spec_lock_text()
    assert "PHX1-parity" in text


# ---------------------------------------------------------------------------
# 4. Tradeable definition exists
# ---------------------------------------------------------------------------


_TRADEABLE_POSITIVE_PHRASES: tuple[str, ...] = (
    "operator can manually act",
    "mint is present",
    "copy-pasteable",
    "pair type is known and displayed",
    "quote asset is displayed",
    "run_id",
    "ping_id",
)


@pytest.mark.parametrize("phrase", _TRADEABLE_POSITIVE_PHRASES)
def test_spec_lock_tradeable_positive_phrase(phrase):
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert phrase.lower() in normalized, (
        f"spec lock missing tradeable positive phrase {phrase!r}"
    )


_TRADEABLE_NEGATIVE_PHRASES: tuple[str, ...] = (
    "signal is guaranteed good",
    "auto-approves",
    "auto-executes",
    "Stage 26 policy candidates are enforced",
)


@pytest.mark.parametrize("phrase", _TRADEABLE_NEGATIVE_PHRASES)
def test_spec_lock_tradeable_negative_phrase(phrase):
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert phrase.lower() in normalized, (
        f"spec lock missing tradeable excluded phrase {phrase!r}"
    )


def test_spec_lock_tradeable_section_exists():
    text = _spec_lock_text()
    assert "tradeable" in text.lower()


# ---------------------------------------------------------------------------
# 5. No X / social language is locked
# ---------------------------------------------------------------------------


def test_spec_lock_locks_no_x_social():
    text = _spec_lock_text()
    assert "X/social" in text or "X / social" in text
    # The lock language must say Stage 27 is not the X/social
    # stage and that X/social is deferred to Stage 30+.
    normalized = _normalized_whitespace(text).lower()
    assert "stage 27 is not the x/social stage" in normalized or (
        "stage 27 is not the x / social stage" in normalized
    )
    assert "deferred to stage 30+" in normalized or (
        "stage 30+" in normalized
    )


def test_spec_lock_names_each_x_social_forbidden_surface():
    text = _spec_lock_text().lower()
    for needle in (
        "tweet ranking",
        "social scraping",
        "social sidecar",
        "social scoring",
    ):
        assert needle in text, (
            f"spec lock missing X/social forbidden surface {needle!r}"
        )


# ---------------------------------------------------------------------------
# 6. No public routing / no paid tiers / no enforcement is locked
# ---------------------------------------------------------------------------


def test_spec_lock_locks_no_public_routing():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "public routing" in normalized
    assert (
        "must not" in normalized
        or "private routing only" in normalized
        or "private only" in normalized
    )


def test_spec_lock_locks_no_subscriber_routing():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "subscriber routing" in normalized


def test_spec_lock_locks_no_paid_tiers():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "paid tiers" in normalized


def test_spec_lock_locks_no_broad_community_distribution():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "broad community distribution" in normalized or (
        "broad discord community distribution" in normalized
    )


def test_spec_lock_locks_no_telegram_unless_scoped():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "telegram" in normalized
    assert (
        "unless explicitly scoped later" in normalized
        or "unless separately scoped" in normalized
    )


def test_spec_lock_locks_no_enforcement():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    # The spec lock must lock that Stage 27 does not enforce Stage
    # 26 candidate policies, and that enforcement lives in Stage
    # 29.
    assert "must not enforce" in normalized
    assert "stage 29" in normalized


# ---------------------------------------------------------------------------
# 7. Pair-awareness is mandatory
# ---------------------------------------------------------------------------


def test_spec_lock_calls_pair_awareness_mandatory():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "pair-awareness is mandatory" in normalized or (
        "pair awareness is mandatory" in normalized
    )


_PAIR_AWARENESS_FIELDS: tuple[str, ...] = (
    "quote_asset",
    "pair_type",
    "bonding_curve_version",
    "quote_mint",
    "pair_detection_status",
    "pair_detection_confidence",
    "pair_detection_reason",
)


@pytest.mark.parametrize("field", _PAIR_AWARENESS_FIELDS)
def test_spec_lock_names_pair_awareness_field(field):
    text = _spec_lock_text()
    assert field in text, (
        f"spec lock missing pair-awareness field name {field!r}"
    )


def test_spec_lock_names_pair_detection_source_field():
    text = _spec_lock_text()
    assert (
        "pair_detection_source" in text
        or "detection_sources" in text
    )


_QUOTE_ASSET_VALUES: tuple[str, ...] = ("SOL", "USDC", "UNKNOWN")
_PAIR_TYPE_VALUES: tuple[str, ...] = (
    "PUMP_SOL",
    "PUMP_USDC",
    "UNKNOWN",
)
_BONDING_CURVE_VERSION_VALUES: tuple[str, ...] = (
    "SOL_LEGACY",
    "USDC_FIXED",
    "UNKNOWN",
)


@pytest.mark.parametrize("value", _QUOTE_ASSET_VALUES)
def test_spec_lock_names_quote_asset_value(value):
    text = _spec_lock_text()
    assert value in text, (
        f"spec lock missing quote_asset value {value!r}"
    )


@pytest.mark.parametrize("value", _PAIR_TYPE_VALUES)
def test_spec_lock_names_pair_type_value(value):
    text = _spec_lock_text()
    assert value in text, (
        f"spec lock missing pair_type value {value!r}"
    )


@pytest.mark.parametrize("value", _BONDING_CURVE_VERSION_VALUES)
def test_spec_lock_names_bonding_curve_version_value(value):
    text = _spec_lock_text()
    assert value in text, (
        f"spec lock missing bonding_curve_version value {value!r}"
    )


# ---------------------------------------------------------------------------
# 8. USDC observe-only rule
# ---------------------------------------------------------------------------


def test_spec_lock_locks_usdc_observe_only_rule():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "usdc-pair pings" in normalized
    assert "observe_only" in normalized or "observe-only" in normalized
    assert (
        "until phx2 has accumulated" in normalized
        or "until enough phx2" in normalized
        or "until phx2 has" in normalized
    )


def test_spec_lock_locks_sol_usdc_universe_separation():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "sol-pair" in normalized
    assert "usdc-pair" in normalized
    assert (
        "must stay separate" in normalized
        or "stay separate" in normalized
    )


def test_spec_lock_forbids_mixing_sol_usdc_ath_migration():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "must not mix" in normalized or "not mix" in normalized
    assert "ath" in normalized
    assert "migration" in normalized


# ---------------------------------------------------------------------------
# 9. UNKNOWN must not default to SOL
# ---------------------------------------------------------------------------


def test_spec_lock_locks_unknown_never_defaults_to_sol():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "unknown" in normalized
    assert (
        "must never default to" in normalized
        or "never default to" in normalized
    )
    assert "sol" in normalized


# ---------------------------------------------------------------------------
# 10. UNKNOWN LIVE suppression rule
# ---------------------------------------------------------------------------


def test_spec_lock_locks_unknown_live_suppression():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "unknown pair events must be suppressed in live mode"
        in normalized
    ) or (
        "unknown pair events" in normalized
        and "suppressed in live" in normalized
    )
    assert "dry-run" in normalized or "artifacts" in normalized


# ---------------------------------------------------------------------------
# 11. Two-factor LIVE authorization rule
# ---------------------------------------------------------------------------


def test_spec_lock_locks_two_factor_live_authorization():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    # The spec lock must require two independent live-mode
    # authorizations.
    assert "two independent live-mode authorizations" in normalized or (
        "two independent" in normalized
        and "live-mode" in normalized
    )


def test_spec_lock_names_both_live_authorization_factors():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    # Factor 1: local env / config flag.
    assert (
        "env / config flag" in normalized
        or "env/config flag" in normalized
        or "config flag" in normalized
    )
    # Factor 2: explicit CLI / operator argument.
    assert "cli" in normalized
    assert "operator argument" in normalized or "argument" in normalized


def test_spec_lock_locks_fail_closed_when_single_factor_present():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "fail closed" in normalized or "fail-closed" in normalized


# ---------------------------------------------------------------------------
# 12. Pair detection source hierarchy
# ---------------------------------------------------------------------------


_PAIR_DETECTION_SOURCES: tuple[str, ...] = (
    "on-chain pool quote mint",
    "bonding-curve metadata",
    "migration event",
    "provider-enriched payload",
    "known quote-mint fallback",
)


@pytest.mark.parametrize("phrase", _PAIR_DETECTION_SOURCES)
def test_spec_lock_documents_pair_detection_source(phrase):
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert phrase.lower() in normalized, (
        f"spec lock missing pair-detection source {phrase!r}"
    )


def test_spec_lock_locks_on_chain_strongest_evidence():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "on-chain quote mint" in normalized
    assert "strongest evidence" in normalized


def test_spec_lock_locks_fail_closed_on_disagreement_in_live():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "fail closed in live" in normalized or (
        "fail closed" in normalized and "live mode" in normalized
    )


# ---------------------------------------------------------------------------
# 13. Stage 26 relationship: review-only, no enforcement
# ---------------------------------------------------------------------------


def test_spec_lock_says_stage26_outputs_review_only():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "stage 26" in normalized
    assert "review-only" in normalized or "review only" in normalized


def test_spec_lock_says_stage27_must_not_enforce_stage26_policies():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "must not enforce stage 26 candidate policies" in normalized or (
        "must not enforce" in normalized
        and "stage 26" in normalized
        and "candidate policies" in normalized
    )


# ---------------------------------------------------------------------------
# 14. Prior stage reuse (Stage 21 / 22)
# ---------------------------------------------------------------------------


def test_spec_lock_says_reuse_stage21_22_boundaries():
    text = _spec_lock_text()
    assert "Stage 21" in text
    assert "Stage 22" in text


def test_spec_lock_forbids_phx1_spaghetti_shape():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "phx1-spaghetti" in normalized or "phx1 spaghetti" in normalized
    assert "no single mega-runner" in normalized
    assert "no scattered env reads" in normalized
    assert "no global mutable" in normalized


# ---------------------------------------------------------------------------
# 15. Stage 28 hardening handoff exists
# ---------------------------------------------------------------------------


def test_spec_lock_pins_stage28_hardening_handoff():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "stage 28" in normalized
    assert "hardening" in normalized
    assert "crash recovery" in normalized
    assert "retries" in normalized
    assert "health checks" in normalized


# ---------------------------------------------------------------------------
# 16. Stage 29 approved enforcement handoff exists
# ---------------------------------------------------------------------------


def test_spec_lock_pins_stage29_enforcement_handoff():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "stage 29" in normalized
    assert (
        "approved enforcement" in normalized
        or "live gating" in normalized
    )


# ---------------------------------------------------------------------------
# 17. Stage 30+ X / social handoff exists
# ---------------------------------------------------------------------------


def test_spec_lock_pins_stage30_x_social_handoff():
    text = _spec_lock_text()
    assert "Stage 30+" in text
    normalized = _normalized_whitespace(text).lower()
    assert (
        "x/social sidecar" in normalized
        or "x / social sidecar" in normalized
        or "x/social" in normalized
        or "x / social" in normalized
    )


# ---------------------------------------------------------------------------
# 18. Substage plan present
# ---------------------------------------------------------------------------


_STAGE_27_SUBSTAGE_LABELS: tuple[str, ...] = (
    "27.0",
    "27.1",
    "27.2",
    "27.3",
    "27.4",
    "27.5",
    "27.6",
    "27.7a",
    "27.7b",
    "27.8",
)


@pytest.mark.parametrize("label", _STAGE_27_SUBSTAGE_LABELS)
def test_spec_lock_lists_substage_label(label):
    text = _spec_lock_text()
    assert label in text, (
        f"spec lock missing Stage 27 substage label {label!r}"
    )


def test_spec_lock_runner_scope_runs_dry_run_first():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "dry-run" in normalized


# ---------------------------------------------------------------------------
# 19. Closure / no-tag posture
# ---------------------------------------------------------------------------


def test_spec_lock_documents_no_tag_creation_by_implementation():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "no commit" in normalized
    assert "tag" in normalized
    assert "operator-only" in normalized or "operator only" in normalized


# ---------------------------------------------------------------------------
# 20. Stage 27.0 contains no implementation modules beyond the
#     allowed scaffold
# ---------------------------------------------------------------------------


# Stage 27.1 narrow amendment: the Stage 27.0 allowlist is
# extended to admit the Stage 27.1 production surface (operator
# config + secrets readiness + run identity + config errors +
# config models). Every Stage 27.2+ implementation basename
# remains blocked below.
_STAGE_27_0_ALLOWED_ENTRIES: frozenset[str] = frozenset(
    {
        # Stage 27.0 scaffold.
        "__init__.py",
        "STAGE_27_0_SPEC_LOCK.md",
        # Stage 27.1 production surface.
        "live_config_errors.py",
        "live_config_models.py",
        "live_run_identity.py",
        "live_secrets_readiness.py",
        "live_operator_config.py",
    }
)


def test_stage27_root_is_only_stage_27_0_scaffold():
    """``PHX2/stage27/`` carries only the Stage 27.0 + 27.1 surface.

    The ``__pycache__`` bytecode directory is build noise, not
    Stage 27 source surface, and is excluded from this check.
    Every other top-level entry must be inside the locked
    allowlist. Stage 27.2+ implementation files remain blocked.
    """
    assert STAGE27_ROOT.is_dir(), (
        f"Stage 27.0 requires the package directory {STAGE27_ROOT}"
    )
    actual: set[str] = set()
    for entry in STAGE27_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = actual - _STAGE_27_0_ALLOWED_ENTRIES
    assert not forbidden, (
        "PHX2/stage27 admits only the Stage 27.0 + 27.1 file set "
        f"({sorted(_STAGE_27_0_ALLOWED_ENTRIES)!r}). Stage 27.2+ "
        f"implementation files remain blocked. Forbidden entries "
        f"found: {sorted(forbidden)!r}"
    )


# ---------------------------------------------------------------------------
# 21. Forbidden Stage 27.2+ implementation files do NOT exist yet
# ---------------------------------------------------------------------------


# Stage 27.1 narrow amendment: ``live_operator_config.py`` and
# ``live_secrets_readiness.py`` have been promoted to the
# Stage 27.1 production surface and removed from the forbidden
# list. Every other Stage 27.2+ implementation basename remains
# blocked.
_STAGE_27_2_PLUS_FORBIDDEN_BASENAMES: tuple[str, ...] = (
    "pair_detection_contracts.py",
    "pump_pair_classifier.py",
    "live_provider_composition.py",
    "price_ath_context_reader.py",
    "private_ping_renderer.py",
    "private_discord_sender.py",
    "live_candidate_assembler.py",
    "bounded_tradeable_ping_runner.py",
    "live_dedupe.py",
)


@pytest.mark.parametrize(
    "basename", _STAGE_27_2_PLUS_FORBIDDEN_BASENAMES
)
def test_no_stage_27_2_plus_implementation_file_under_stage27(
    basename,
):
    path = STAGE27_ROOT / basename
    assert not path.exists(), (
        f"Stage 27.1 must not ship Stage 27.2+ implementation "
        f"file {basename!r} under PHX2/stage27/; got {path}"
    )


_STAGE_27_1_LOCKED_PY_MODULES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "live_config_errors.py",
        "live_config_models.py",
        "live_run_identity.py",
        "live_secrets_readiness.py",
        "live_operator_config.py",
    }
)


def test_stage27_root_py_modules_match_locked_27_1_set():
    """Stage 27.1 admits exactly the locked production .py set.

    Stage 27.0 originally asserted only ``__init__.py`` could exist
    under ``PHX2/stage27/``. Stage 27.1 promotes the five operator-
    config production modules. Every other .py is rejected (would
    indicate Stage 27.2+ implementation creep).
    """
    py_files = {
        p.name
        for p in STAGE27_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    unexpected = py_files - _STAGE_27_1_LOCKED_PY_MODULES
    assert not unexpected, (
        f"Stage 27.1 must ship only the locked production .py set "
        f"({sorted(_STAGE_27_1_LOCKED_PY_MODULES)!r}); unexpected "
        f".py files under PHX2/stage27/: {sorted(unexpected)!r}"
    )


def test_stage27_root_has_only_spec_lock_md():
    md_files = {
        p.name
        for p in STAGE27_ROOT.iterdir()
        if p.is_file() and p.suffix == ".md"
    }
    assert md_files == {"STAGE_27_0_SPEC_LOCK.md"}, (
        f"Stage 27.0 must ship exactly one markdown document "
        f"(STAGE_27_0_SPEC_LOCK.md); got {sorted(md_files)!r}"
    )


# ---------------------------------------------------------------------------
# 22. Stage 27.0 explicit-non-goals list is present and complete
# ---------------------------------------------------------------------------


_STAGE_27_EXPLICIT_NON_GOALS: tuple[str, ...] = (
    "Axiom reopening",
    "global-fee reopening",
    "Stage 24 reopening",
    "Stage 25 artifact mutation",
    "Stage 26 artifact mutation",
    "bypassing Stage 21 / 22 live-ingest boundaries",
    "paid alert logic",
)


@pytest.mark.parametrize("phrase", _STAGE_27_EXPLICIT_NON_GOALS)
def test_spec_lock_lists_explicit_non_goal(phrase):
    text = _spec_lock_text()
    assert phrase in text, (
        f"spec lock missing explicit non-goal {phrase!r}"
    )
