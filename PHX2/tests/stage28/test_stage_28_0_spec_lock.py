"""Stage 28.0 spec-lock tests.

Pins:

  * ``PHX2/stage28/STAGE_28_0_SPEC_LOCK.md`` exists and carries
    the canonical Stage 28 scope sentence verbatim, the Stage
    27 reuse rules, the planned substage list through 28.8,
    the dedupe ambiguous-send-suppression principle, the
    bounded-retry-no-infinite-retry principle, the provider-
    neutral config alias principle, the Dexscreener non-
    authority principle, the audited transport privacy /
    redaction principle, the Stage 28 must-not surfaces, and
    the deferred ownership for Stage 29 enforcement and Stage
    30+ X / social.
  * ``PHX2/stage28/`` contains only the Stage 28.0 scaffold
    (``__init__.py`` + ``STAGE_28_0_SPEC_LOCK.md``); no Stage
    28.1+ implementation file ships at Stage 28.0.
  * ``PHX2/tests/stage28/`` contains only the Stage 28.0 tests
    package marker and this spec-lock test file.
  * The Stage 28.0 spec lock carries no URL literal, no
    webhook host literal, and no raw secret-looking value.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
TESTS_STAGE28_ROOT: Path = PHX2_ROOT / "tests" / "stage28"
SPEC_LOCK_PATH: Path = STAGE28_ROOT / "STAGE_28_0_SPEC_LOCK.md"


# Canonical Stage 28 scope sentence. Must appear verbatim in the
# spec-lock doc; future Stage 28 substages must preserve it.
STAGE_28_SCOPE_SENTENCE: str = (
    "Stage 28 is private live runner reliability hardening."
)


def _spec_lock_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Stage 28 package + tests package + spec lock file exist
# ---------------------------------------------------------------------------


def test_stage28_package_init_exists():
    init_path = STAGE28_ROOT / "__init__.py"
    assert init_path.is_file(), (
        f"Stage 28.0 requires the package marker {init_path}"
    )


def test_stage28_tests_package_init_exists():
    init_path = TESTS_STAGE28_ROOT / "__init__.py"
    assert init_path.is_file(), (
        f"Stage 28.0 requires the tests package marker {init_path}"
    )


def test_stage28_spec_lock_doc_exists():
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 28.0 requires the spec-lock document {SPEC_LOCK_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Canonical Stage 28 scope sentence exists verbatim
# ---------------------------------------------------------------------------


def test_spec_lock_contains_canonical_scope_sentence_verbatim():
    normalized = _normalized_whitespace(_spec_lock_text())
    assert STAGE_28_SCOPE_SENTENCE in normalized, (
        "spec lock must contain the canonical Stage 28 scope "
        "sentence verbatim (whitespace-normalized match)"
    )


def test_spec_lock_names_stage_28_explicitly():
    text = _spec_lock_text()
    assert "Stage 28" in text


# ---------------------------------------------------------------------------
# 3. Stage 27 reuse rules
# ---------------------------------------------------------------------------


_STAGE_27_REUSE_PHRASES: tuple[str, ...] = (
    "live_operator_config",
    "live_secrets_readiness",
    "live_run_identity",
    "pump pair classifier",
    "pair detection contracts",
    "provider ingest composition",
    "price / ATH context reader",
    "live measurement context",
    "live candidate assembler",
    "private ping renderer",
    "private ping provenance",
    "bounded dry-run runner",
    "live smoke dispatch",
    "seven-gate chokepoint",
    "private Discord sender",
    "Stage 27 pair suppression rules",
)


@pytest.mark.parametrize("phrase", _STAGE_27_REUSE_PHRASES)
def test_spec_lock_lists_each_stage_27_reuse_surface(phrase):
    normalized = _normalized_whitespace(_spec_lock_text())
    assert phrase in normalized, (
        f"spec lock missing Stage 27 reuse phrase {phrase!r}"
    )


def test_spec_lock_says_stage_28_must_not_reimplement_stage_27_surfaces():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "do not reimplement" in normalized or (
        "must not reimplement" in normalized
    )


# ---------------------------------------------------------------------------
# 4. Planned substage list through 28.8
# ---------------------------------------------------------------------------


_PLANNED_STAGE_28_SUBSTAGES: tuple[str, ...] = (
    "28.0",
    "28.1",
    "28.2",
    "28.3a",
    "28.3b",
    "28.4",
    "28.5",
    "28.6",
    "28.7",
    "28.8",
)


@pytest.mark.parametrize("substage", _PLANNED_STAGE_28_SUBSTAGES)
def test_spec_lock_names_each_planned_substage(substage):
    text = _spec_lock_text()
    assert substage in text, (
        f"spec lock missing planned Stage 28 substage label "
        f"{substage!r}"
    )


_PLANNED_STAGE_28_SCOPE_PHRASES: tuple[str, ...] = (
    "spec lock",
    "reliability charter",
    "provider-neutral config wrapper",
    "restart-safe dispatch ledger",
    "failure classification",
    "retry policy",
    "audited private HTTP Discord transport",
    "heartbeat",
    "health snapshot",
    "CLI status",
    "longer-session bounded private runner",
    "graceful shutdown",
    "longer-session smoke harness",
    "closure audit",
    "Stage 29 handoff",
)


@pytest.mark.parametrize("phrase", _PLANNED_STAGE_28_SCOPE_PHRASES)
def test_spec_lock_pins_each_planned_substage_scope_phrase(phrase):
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert phrase.lower() in normalized, (
        f"spec lock missing planned substage scope phrase "
        f"{phrase!r}"
    )


def test_spec_lock_requires_explicit_operator_authorization_for_later_substages():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "explicit operator authorization" in normalized


# ---------------------------------------------------------------------------
# 5. Dedupe ambiguous-send suppression principle
# ---------------------------------------------------------------------------


def test_spec_lock_locks_restart_safe_dedupe_principle():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "restart-safe dedupe" in normalized
    assert "must survive process restart" in normalized


def test_spec_lock_locks_ambiguous_send_suppression_principle():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "ambiguous" in normalized
    assert (
        "suppress re-send" in normalized
        or "suppresses re-send" in normalized
    )


def test_spec_lock_locks_duplicate_replay_never_pings():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "duplicate replay must never generate another private "
        "discord ping"
    ) in normalized


def test_spec_lock_locks_reserve_before_send_principle():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "reserve / write dedupe intent before attempting send"
        in normalized
    )


def test_spec_lock_locks_dedupe_is_not_enforcement():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "dedupe is not enforcement" in normalized
    assert "is not policy approval" in normalized
    assert "is not trade gating" in normalized


# ---------------------------------------------------------------------------
# 6. Bounded retry / no infinite retry principle
# ---------------------------------------------------------------------------


def test_spec_lock_locks_bounded_retry_principle():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "every retry must be bounded" in normalized
    assert "no infinite retry loops" in normalized


def test_spec_lock_locks_no_unbounded_queue_or_silent_drop():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "no unbounded retry queues" in normalized
    assert "no silent drops" in normalized
    assert "no retry storms" in normalized


def test_spec_lock_locks_no_auto_restart_daemon():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "no auto-restart daemon, watchdog, or autorestart service"
        in normalized
    )


def test_spec_lock_locks_exhausted_retry_emits_closed_set_failure_reason():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "every exhausted retry path must produce a closed-set "
        "failure reason"
    ) in normalized


def test_spec_lock_locks_artifact_write_fail_closed():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "artifact write failures must fail closed before dispatch"
        in normalized
    )


def test_spec_lock_locks_pair_unknown_disagree_not_retryable():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "unknown / disagree pair cases are not retryable" in normalized


def test_spec_lock_locks_discord_429_retry_after_principle():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "discord 429" in normalized
    assert "retry-after" in normalized


# ---------------------------------------------------------------------------
# 7. Provider-neutral config alias principle
# ---------------------------------------------------------------------------


def test_spec_lock_locks_provider_neutral_naming_intent():
    text = _spec_lock_text()
    assert "PHX2_PROVIDER_GRPC_ENDPOINT" in text


def test_spec_lock_locks_legacy_alias_preservation_principle():
    text = _spec_lock_text()
    assert "HELIUS_GRPC_ENDPOINT" in text
    normalized = _normalized_whitespace(text).lower()
    assert "legacy alias" in normalized
    assert "prefer the new provider-neutral name when present" in normalized


def test_spec_lock_locks_conflicting_config_refuses_start():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "if the new and legacy names are both set and disagree, "
        "the runner must refuse to start"
    ) in normalized


def test_spec_lock_locks_never_log_raw_secret_values():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "never log raw" in normalized
    assert "api keys" in normalized
    assert "bearer tokens" in normalized
    assert "auth headers" in normalized


# ---------------------------------------------------------------------------
# 8. Dexscreener non-authority principle
# ---------------------------------------------------------------------------


def test_spec_lock_locks_dexscreener_not_dispatch_authority():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "dexscreener must not become a dispatch authority in stage 28"
        in normalized
    )


def test_spec_lock_locks_dexscreener_must_not_bypass_stage_25_measurement():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "dexscreener must not bypass stage 25 measurement contracts"
        in normalized
    )


def test_spec_lock_locks_birdeye_remains_live_dispatch_authority():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "birdeye" in normalized
    assert (
        "remains the live dispatch authority" in normalized
        or "remains the live dispatch authority unless" in normalized
    )


def test_spec_lock_locks_price_api_failure_suppresses_pings():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "price api failure must suppress tradeable private pings"
        in normalized
    )


# ---------------------------------------------------------------------------
# 9. Audited transport privacy / redaction principle
# ---------------------------------------------------------------------------


def test_spec_lock_locks_audited_transport_private_only():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "the audited transport must remain private-operator only"
        in normalized
    )


def test_spec_lock_locks_audited_transport_no_channel_or_public_routing():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "must not add channel routing, subscriber routing, public "
        "routing, or paid-tier routing"
    ) in normalized


def test_spec_lock_locks_audited_transport_no_secret_leak():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "must not leak" in normalized
    assert "secret values" in normalized
    assert (
        "records, exceptions, logs, artifacts, or metrics" in normalized
    )


def test_spec_lock_locks_audited_transport_exactly_one_send_per_intent():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "exactly-one-send semantics per send intent" in normalized


def test_spec_lock_locks_audited_transport_retry_attempts_recorded():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "must record those attempts" in normalized


# ---------------------------------------------------------------------------
# 10. Stage 28 must-not surfaces
# ---------------------------------------------------------------------------


_STAGE_28_MUST_NOT_SURFACES: tuple[str, ...] = (
    "public routing",
    "subscriber routing",
    "paid tier routing",
    "broad Discord distribution",
    "Telegram",
    "X / social",
    "Stage 29 enforcement",
    "approval semantics",
    "activation semantics",
    "runtime allow / block gates from Stage 26 policy candidates",
    "automated trading",
    "wallet / private-key / signer logic",
    "position sizing",
    "trade execution",
    "public dashboard / control panel",
    "HTTP control server",
    "daemon / systemd / watchdog / autorestart service",
)


@pytest.mark.parametrize("phrase", _STAGE_28_MUST_NOT_SURFACES)
def test_spec_lock_lists_each_must_not_surface(phrase):
    text = _spec_lock_text()
    assert phrase in text, (
        f"spec lock missing Stage 28 must-not surface {phrase!r}"
    )


def test_spec_lock_explicitly_says_stage_28_must_not_include():
    text = _spec_lock_text()
    assert "Stage 28 must not include" in text


def test_spec_lock_explicitly_says_no_alter_stage_27_dispatch():
    text = _spec_lock_text()
    assert "alter Stage 27.7b dispatch behavior" in text


# ---------------------------------------------------------------------------
# 11. Deferred ownership: Stage 29 enforcement, Stage 30+ X/social
# ---------------------------------------------------------------------------


def test_spec_lock_pins_stage_29_owns_enforcement():
    text = _spec_lock_text()
    assert (
        "Stage 29 owns approved enforcement / live gating." in text
    )
    normalized = _normalized_whitespace(text).lower()
    assert "requires its own explicit authorization" in normalized


def test_spec_lock_pins_stage_30_plus_owns_x_social():
    text = _spec_lock_text()
    assert "Stage 30+ owns the X / social sidecar." in text
    normalized = _normalized_whitespace(text).lower()
    assert "must stay out of stage 28" in normalized


def test_spec_lock_pins_portfolio_thesis_dashboard_separate():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "portfolio" in normalized
    assert "thesis journal" in normalized
    assert "dashboard" in normalized
    assert "not stage 28" in normalized


# ---------------------------------------------------------------------------
# 12. Closed-set vocabulary placeholders
# ---------------------------------------------------------------------------


_CLOSED_SET_VOCABULARY_PLACEHOLDERS: tuple[str, ...] = (
    "run_mode",
    "stop_reason",
    "dedupe_state",
    "dispatch_terminal_state",
    "retry_outcome",
    "failure_kind",
    "provider_status",
    "price_status",
    "artifact_status",
    "heartbeat_status",
    "redaction_status",
)


@pytest.mark.parametrize(
    "placeholder", _CLOSED_SET_VOCABULARY_PLACEHOLDERS
)
def test_spec_lock_names_each_closed_set_vocabulary_placeholder(
    placeholder,
):
    text = _spec_lock_text()
    assert placeholder in text, (
        f"spec lock missing closed-set vocabulary placeholder "
        f"{placeholder!r}"
    )


def test_spec_lock_says_closed_set_vocabularies_are_names_only_at_28_0():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert (
        "stage 28.0 must not ship runtime models, enums, or "
        "constants for these vocabularies"
    ) in normalized


# ---------------------------------------------------------------------------
# 13. Reliability surfaces Stage 28 may own
# ---------------------------------------------------------------------------


_RELIABILITY_SURFACES_STAGE_28_MAY_OWN: tuple[str, ...] = (
    "crash recovery story",
    "restart-safe dedupe",
    "ambiguous send handling",
    "bounded retry / backoff",
    "provider disconnect / reconnect handling",
    "Discord 429 / 5xx handling",
    "price API timeout handling",
    "stale price suppression",
    "artifact write fail-closed behavior",
    "malformed event capture / suppression",
    "graceful shutdown",
    "heartbeat / health snapshots",
    "final run summary",
    "operator-visible CLI status",
    "provider-neutral Chainstack / Helius naming cleanup",
    "safe transition from scratch transport to tracked audited "
    "private transport",
    "continued redaction of secrets",
)


@pytest.mark.parametrize(
    "phrase", _RELIABILITY_SURFACES_STAGE_28_MAY_OWN
)
def test_spec_lock_lists_each_reliability_surface(phrase):
    normalized = _normalized_whitespace(_spec_lock_text())
    assert phrase in normalized, (
        f"spec lock missing reliability surface {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 14. Health / status principles
# ---------------------------------------------------------------------------


def test_spec_lock_locks_no_public_dashboard_no_http_control_server():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "no public dashboard" in normalized
    assert "no http control server" in normalized


def test_spec_lock_locks_no_discord_operational_status_spam():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "no discord operational-status spam" in normalized


def test_spec_lock_locks_no_prometheus_or_exporter_scope():
    normalized = _normalized_whitespace(_spec_lock_text()).lower()
    assert "prometheus" in normalized
    assert "opentelemetry" in normalized
    assert (
        "no prometheus / opentelemetry / exporter scope in stage 28.0"
        in normalized
    )


# ---------------------------------------------------------------------------
# 15. Stage 28.0 file inventory — only the scaffold ships
# ---------------------------------------------------------------------------


# Stage 28.1 narrow amendment: the provider-neutral config
# wrapper substage is authorized and ships the inventory below.
# Stage 28.2 narrow amendment: the restart-safe dispatch ledger
# substage is authorized and ships the inventory below.
# Stage 28.3a narrow amendment: the failure-classification
# substage is authorized and ships the inventory below. Stage
# 28.3b+ implementation files remain blocked.
_STAGE_28_1_PRODUCTION_PY_BASENAMES: frozenset[str] = frozenset(
    {
        "provider_neutral_models.py",
        "provider_neutral_config.py",
        "provider_neutral_readiness.py",
        "stage28_1_manifest.py",
    }
)


_STAGE_28_1_TEST_BASENAMES: frozenset[str] = frozenset(
    {
        "test_stage_28_1_provider_neutral_models.py",
        "test_stage_28_1_provider_neutral_config.py",
        "test_stage_28_1_provider_neutral_readiness.py",
        "test_stage_28_1_boundaries.py",
    }
)


_STAGE_28_2_PRODUCTION_PY_BASENAMES: frozenset[str] = frozenset(
    {
        "dispatch_ledger_models.py",
        "dispatch_ledger.py",
        "stage28_2_manifest.py",
    }
)


_STAGE_28_2_TEST_BASENAMES: frozenset[str] = frozenset(
    {
        "test_stage_28_2_dispatch_ledger_models.py",
        "test_stage_28_2_dispatch_ledger.py",
        "test_stage_28_2_boundaries.py",
    }
)


_STAGE_28_3A_PRODUCTION_PY_BASENAMES: frozenset[str] = frozenset(
    {
        "failure_classification_models.py",
        "failure_classification.py",
        "stage28_3a_manifest.py",
    }
)


_STAGE_28_3A_TEST_BASENAMES: frozenset[str] = frozenset(
    {
        "test_stage_28_3a_failure_classification_models.py",
        "test_stage_28_3a_failure_classification.py",
        "test_stage_28_3a_boundaries.py",
    }
)


# Stage 28.3b narrow amendment: the retry-policy substage is
# authorized and ships the inventory below.
_STAGE_28_3B_PRODUCTION_PY_BASENAMES: frozenset[str] = frozenset(
    {
        "retry_policy_models.py",
        "retry_policy.py",
        "stage28_3b_manifest.py",
    }
)


_STAGE_28_3B_TEST_BASENAMES: frozenset[str] = frozenset(
    {
        "test_stage_28_3b_retry_policy_models.py",
        "test_stage_28_3b_retry_policy.py",
        "test_stage_28_3b_boundaries.py",
    }
)


# Stage 28.4 narrow amendment: the audited private Discord HTTP
# transport substage is authorized and ships the inventory below.
_STAGE_28_4_PRODUCTION_PY_BASENAMES: frozenset[str] = frozenset(
    {
        "audited_http_transport_models.py",
        "audited_http_transport.py",
        "stage28_4_manifest.py",
    }
)


_STAGE_28_4_TEST_BASENAMES: frozenset[str] = frozenset(
    {
        "test_stage_28_4_audited_http_transport_models.py",
        "test_stage_28_4_audited_http_transport.py",
        "test_stage_28_4_boundaries.py",
    }
)


# Stage 28.5 narrow amendment: the heartbeat / health-snapshot /
# CLI-status substage is authorized and ships the inventory
# below.
_STAGE_28_5_PRODUCTION_PY_BASENAMES: frozenset[str] = frozenset(
    {
        "health_status_models.py",
        "heartbeat_writer.py",
        "health_snapshot_writer.py",
        "cli_status_line.py",
        "stage28_5_manifest.py",
    }
)


_STAGE_28_5_TEST_BASENAMES: frozenset[str] = frozenset(
    {
        "test_stage_28_5_health_status_models.py",
        "test_stage_28_5_heartbeat_writer.py",
        "test_stage_28_5_health_snapshot_writer.py",
        "test_stage_28_5_cli_status_line.py",
        "test_stage_28_5_boundaries.py",
    }
)


# Stage 28.6 narrow amendment: the longer-session bounded private
# runner substage is authorized and ships the inventory below.
_STAGE_28_6_PRODUCTION_PY_BASENAMES: frozenset[str] = frozenset(
    {
        "session_runner_models.py",
        "bounded_private_session_runner.py",
        "stage28_6_manifest.py",
    }
)


_STAGE_28_6_TEST_BASENAMES: frozenset[str] = frozenset(
    {
        "test_stage_28_6_session_runner_models.py",
        "test_stage_28_6_bounded_private_session_runner.py",
        "test_stage_28_6_boundaries.py",
    }
)


# Stage 28.7 narrow amendment: the longer-session smoke harness +
# controlled live smoke runbook substage is authorized and ships
# the inventory below.
_STAGE_28_7_PRODUCTION_PY_BASENAMES: frozenset[str] = frozenset(
    {
        "longer_session_smoke_harness.py",
        "stage28_7_manifest.py",
    }
)


_STAGE_28_7_DOC_BASENAMES: frozenset[str] = frozenset(
    {
        "STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md",
        "STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md",
    }
)


_STAGE_28_7_TEST_BASENAMES: frozenset[str] = frozenset(
    {
        "test_stage_28_7_longer_session_smoke_harness.py",
        "test_stage_28_7_boundaries.py",
        "test_stage_28_7_smoke_docs.py",
    }
)


# Stage 28.8 narrow amendment: the closure audit + Stage 29
# handoff + Stage 28-wide manifest substage is authorized and
# ships the inventory below. Stage 29+ implementation files
# remain blocked.
_STAGE_28_8_PRODUCTION_PY_BASENAMES: frozenset[str] = frozenset(
    {
        "stage28_manifest.py",
    }
)


_STAGE_28_8_DOC_BASENAMES: frozenset[str] = frozenset(
    {
        "STAGE_28_CLOSURE_AUDIT.md",
        "STAGE_29_HANDOFF.md",
    }
)


_STAGE_28_8_TEST_BASENAMES: frozenset[str] = frozenset(
    {
        "test_stage_28_8_closure_audit.py",
        "test_stage_28_8_stage29_handoff.py",
        "test_stage_28_8_manifest.py",
        "test_stage_28_8_boundaries.py",
    }
)


_STAGE_28_0_ALLOWED_PRODUCTION_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "__init__.py",
            "STAGE_28_0_SPEC_LOCK.md",
        }
    )
    | _STAGE_28_1_PRODUCTION_PY_BASENAMES
    | _STAGE_28_2_PRODUCTION_PY_BASENAMES
    | _STAGE_28_3A_PRODUCTION_PY_BASENAMES
    | _STAGE_28_3B_PRODUCTION_PY_BASENAMES
    | _STAGE_28_4_PRODUCTION_PY_BASENAMES
    | _STAGE_28_5_PRODUCTION_PY_BASENAMES
    | _STAGE_28_6_PRODUCTION_PY_BASENAMES
    | _STAGE_28_7_PRODUCTION_PY_BASENAMES
    | _STAGE_28_7_DOC_BASENAMES
    | _STAGE_28_8_PRODUCTION_PY_BASENAMES
    | _STAGE_28_8_DOC_BASENAMES
)


_STAGE_28_0_ALLOWED_TEST_ENTRIES: frozenset[str] = (
    frozenset(
        {
            "__init__.py",
            "test_stage_28_0_spec_lock.py",
        }
    )
    | _STAGE_28_1_TEST_BASENAMES
    | _STAGE_28_2_TEST_BASENAMES
    | _STAGE_28_3A_TEST_BASENAMES
    | _STAGE_28_3B_TEST_BASENAMES
    | _STAGE_28_4_TEST_BASENAMES
    | _STAGE_28_5_TEST_BASENAMES
    | _STAGE_28_6_TEST_BASENAMES
    | _STAGE_28_7_TEST_BASENAMES
    | _STAGE_28_8_TEST_BASENAMES
)


def test_stage28_root_admits_only_28_0_scaffold_plus_28_1_surface():
    actual: set[str] = set()
    for entry in STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = actual - _STAGE_28_0_ALLOWED_PRODUCTION_ENTRIES
    assert not forbidden, (
        f"PHX2/stage28 admits only the Stage 28.0 scaffold plus "
        f"the Stage 28.1 + Stage 28.2 + Stage 28.3a + Stage 28.3b "
        f"+ Stage 28.4 + Stage 28.5 + Stage 28.6 + Stage 28.7 + "
        f"Stage 28.8 production / doc surface "
        f"({sorted(_STAGE_28_0_ALLOWED_PRODUCTION_ENTRIES)!r}); "
        f"Stage 29+ implementation files remain blocked. "
        f"Forbidden entries found: {sorted(forbidden)!r}"
    )
    missing = _STAGE_28_0_ALLOWED_PRODUCTION_ENTRIES - actual
    assert not missing, (
        f"Stage 28.0 / 28.1 / 28.2 / 28.3a / 28.3b / 28.4 / 28.5 "
        f"/ 28.6 / 28.7 / 28.8 inventory missing required "
        f"entries: {sorted(missing)!r}"
    )


def test_tests_stage28_root_admits_only_28_0_plus_28_1_test_files():
    actual: set[str] = set()
    for entry in TESTS_STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = actual - _STAGE_28_0_ALLOWED_TEST_ENTRIES
    assert not forbidden, (
        f"PHX2/tests/stage28 admits only the Stage 28.0 test set "
        f"plus the Stage 28.1 + Stage 28.2 + Stage 28.3a + Stage "
        f"28.3b + Stage 28.4 + Stage 28.5 + Stage 28.6 + Stage "
        f"28.7 + Stage 28.8 test surface "
        f"({sorted(_STAGE_28_0_ALLOWED_TEST_ENTRIES)!r}); Stage "
        f"29+ test files remain blocked. Forbidden entries "
        f"found: {sorted(forbidden)!r}"
    )
    missing = _STAGE_28_0_ALLOWED_TEST_ENTRIES - actual
    assert not missing, (
        f"Stage 28.0 / 28.1 / 28.2 / 28.3a / 28.3b / 28.4 / 28.5 "
        f"/ 28.6 / 28.7 / 28.8 tests package missing required "
        f"entries: {sorted(missing)!r}"
    )


# ---------------------------------------------------------------------------
# 16. Boundary scan blocks Stage 28.3+ implementation basenames
# ---------------------------------------------------------------------------


# Stage 28.1 narrow amendment: ``provider_neutral_config.py`` was
# promoted to the Stage 28.1 production surface.
# Stage 28.2 narrow amendment: ``dispatch_ledger.py`` and
# ``dispatch_ledger_models.py`` have been promoted to the Stage
# 28.2 production surface and removed from this forbidden list.
# Stage 28.3a narrow amendment: ``failure_classification.py`` and
# ``failure_classification_models.py`` have been promoted to the
# Stage 28.3a production surface and removed from this forbidden
# list.
# Stage 28.3b narrow amendment: ``retry_policy.py`` and
# ``retry_policy_models.py`` have been promoted to the Stage
# 28.3b production surface and removed from this forbidden list.
# Stage 28.4 narrow amendment: ``audited_http_transport.py`` and
# ``audited_http_transport_models.py`` have been promoted to the
# Stage 28.4 production surface and removed from this forbidden
# list. Stage 28.5 narrow amendment: ``heartbeat_writer.py``,
# ``health_snapshot_writer.py``, ``cli_status_line.py``,
# ``health_status_models.py``, and ``stage28_5_manifest.py`` have
# been promoted to the Stage 28.5 production surface. Stage 28.6
# narrow amendment: ``session_runner_models.py``,
# ``bounded_private_session_runner.py``, and
# ``stage28_6_manifest.py`` have been promoted to the Stage 28.6
# production surface. Stage 28.7 narrow amendment:
# ``longer_session_smoke_harness.py``, ``stage28_7_manifest.py``,
# ``STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md``, and
# ``STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md`` have been promoted
# to the Stage 28.7 production / doc surface. Stage 28.8 narrow
# amendment: ``stage28_manifest.py``,
# ``STAGE_28_CLOSURE_AUDIT.md``, and ``STAGE_29_HANDOFF.md`` have
# been promoted to the Stage 28.8 closure / handoff / manifest
# surface. Stage 29+ basenames remain blocked under
# ``PHX2/stage28/`` -- the scan keeps a small Stage 29-flavored
# denylist so an accidentally-misfiled Stage 29 file is caught.
_FORBIDDEN_STAGE_28_PLUS_BASENAMES: tuple[str, ...] = (
    "stage29_manifest.py",
    "STAGE_29_CLOSURE_AUDIT.md",
    "STAGE_30_HANDOFF.md",
)


@pytest.mark.parametrize(
    "basename", _FORBIDDEN_STAGE_28_PLUS_BASENAMES
)
def test_no_stage_28_2_plus_basename_under_stage28(basename):
    assert not (STAGE28_ROOT / basename).exists(), (
        f"PHX2/stage28 must not ship Stage 29+ implementation "
        f"basename {basename!r} under PHX2/stage28/"
    )


def test_no_extra_python_module_under_stage28():
    """Stage 28 .py inventory is the package marker plus the
    Stage 28.1 + Stage 28.2 + Stage 28.3a + Stage 28.3b + Stage
    28.4 + Stage 28.5 + Stage 28.6 + Stage 28.7 + Stage 28.8
    production .py surface; nothing else ships under
    ``PHX2/stage28/`` at Stage 28.8.

    Stage 29+ substages live in ``PHX2/stage29/`` and must not
    leak into the Stage 28 tree.
    """
    actual_py = {
        p.name
        for p in STAGE28_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    allowed_py = (
        {"__init__.py"}
        | set(_STAGE_28_1_PRODUCTION_PY_BASENAMES)
        | set(_STAGE_28_2_PRODUCTION_PY_BASENAMES)
        | set(_STAGE_28_3A_PRODUCTION_PY_BASENAMES)
        | set(_STAGE_28_3B_PRODUCTION_PY_BASENAMES)
        | set(_STAGE_28_4_PRODUCTION_PY_BASENAMES)
        | set(_STAGE_28_5_PRODUCTION_PY_BASENAMES)
        | set(_STAGE_28_6_PRODUCTION_PY_BASENAMES)
        | set(_STAGE_28_7_PRODUCTION_PY_BASENAMES)
        | set(_STAGE_28_8_PRODUCTION_PY_BASENAMES)
    )
    unexpected = actual_py - allowed_py
    assert not unexpected, (
        f"Stage 28 must not add new production .py modules beyond "
        f"the package marker and the Stage 28.1 + Stage 28.2 + "
        f"Stage 28.3a + Stage 28.3b + Stage 28.4 + Stage 28.5 + "
        f"Stage 28.6 + Stage 28.7 + Stage 28.8 surface; "
        f"unexpected files: {sorted(unexpected)}"
    )


_FORBIDDEN_PUBLIC_ROUTING_OR_ENFORCEMENT_BASENAMES: tuple[str, ...] = (
    "public_router.py",
    "subscriber_router.py",
    "paid_tier_router.py",
    "live_router.py",
    "telegram_sender.py",
    "telegram_client.py",
    "x_social.py",
    "social_sidecar.py",
    "tweet_ranking.py",
    "social_scoring.py",
    "enforcement_gate.py",
    "enforcement.py",
    "enforce_policy.py",
    "auto_trade.py",
    "position_sizer.py",
    "discord_bot.py",
    "slash_commands.py",
    "subscriber_models.py",
    "subscriber_db.py",
    "discord.py",
    "telegram.py",
    "dashboard.py",
    "http_control_server.py",
    "watchdog.py",
    "autorestart.py",
    "daemon.py",
)


@pytest.mark.parametrize(
    "basename", _FORBIDDEN_PUBLIC_ROUTING_OR_ENFORCEMENT_BASENAMES
)
def test_no_public_routing_enforcement_or_x_social_module_in_stage28(
    basename,
):
    assert not (STAGE28_ROOT / basename).exists()


# ---------------------------------------------------------------------------
# 17. Spec lock carries no URL / webhook host / raw secret literal
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
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


_FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES: tuple[str, ...] = (
    "webhook_url",
    "DISCORD_WEBHOOK_URL=",
    "HELIUS_API_KEY=",
    "HELIUS_RPC_URL=",
    "HELIUS_GRPC_ENDPOINT=",
    "raw_payload",
    "provider_payload",
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
