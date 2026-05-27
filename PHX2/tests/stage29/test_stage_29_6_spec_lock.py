"""Stage 29.6 bounded private single-shot live proof spec-lock pins.

Pins:

  * Stage 29.6 runbook exists at the locked path.
  * Stage 29.6 spec-lock markdown exists at the locked path.
  * Canonical Stage 29.6 mission sentence appears verbatim in the
    runbook (whitespace-normalized match).
  * Stage 29.6 ships ZERO production .py file under
    ``PHX2/stage29/`` whose basename starts with ``stage29_6_`` or
    ``stage_29_6_`` (the Option A no-production-code stance).
  * Runbook pins Option A and explicitly names the no-new-
    production-code stance.
  * Runbook names the three Stage 29.3 ceremony mode tokens
    (``READINESS_ONLY`` / ``CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY``
    / ``ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN``).
  * Runbook pins ``max_events=1`` and ``max_dispatches=1``.
  * Runbook names the three Stage 29.3 optional kwargs
    ``migration_source`` / ``migration_context_renderer`` /
    ``private_discord_body_injector`` verbatim.
  * Runbook names the two operator authorization gates
    ``live_env_ready=True`` and ``live_operator_request=True``.
  * Runbook explicitly forbids Stage 30, Stage 26 / Stage 29
    enforcement activation, public / subscriber / paid routing,
    Telegram / X / social senders, Axiom / Ante filters, and
    trading / wallet / signing surfaces.
  * Runbook names the Stage 29.5.6 1900-char combined-content
    cap and the full-first / compact-fallback / skip-only-when-
    both-overflow discipline.
  * Runbook names the expected acceptance artifact basenames.
  * Runbook does NOT carry any URL host, bearer / authorization
    header, API-key prefix, raw secret, Pump.fun program-id, or
    Phoenix_Bot legacy substring.
  * Runbook acceptance criteria letters A through R are named.

No live network calls. No real Chainstack / Birdeye / Helius /
Discord traffic. Pure read-only repo inspection.
"""

from __future__ import annotations

import re
from pathlib import Path


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"


RUNBOOK_PATH: Path = (
    STAGE29_ROOT / "STAGE_29_6_BOUNDED_LIVE_PROOF_RUNBOOK.md"
)
SPEC_LOCK_PATH: Path = (
    STAGE29_ROOT / "STAGE_29_6_SPEC_LOCK.md"
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _spec_lock_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# 1. File presence
# ---------------------------------------------------------------------------


def test_runbook_file_exists() -> None:
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 29.6 runbook must exist at {RUNBOOK_PATH}"
    )


def test_spec_lock_file_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 29.6 spec-lock markdown must exist at "
        f"{SPEC_LOCK_PATH}"
    )


def test_spec_lock_test_file_exists() -> None:
    path = TESTS_STAGE29_ROOT / "test_stage_29_6_spec_lock.py"
    assert path.is_file(), (
        f"Stage 29.6 spec-lock test must exist at {path}"
    )


def test_bounded_live_proof_test_file_exists() -> None:
    path = (
        TESTS_STAGE29_ROOT
        / "test_stage_29_6_bounded_live_proof.py"
    )
    assert path.is_file(), (
        f"Stage 29.6 bounded live proof test must exist at "
        f"{path}"
    )


# ---------------------------------------------------------------------------
# 2. Canonical Stage 29.6 mission sentence
# ---------------------------------------------------------------------------


def test_canonical_mission_sentence_verbatim() -> None:
    expected = (
        "Stage 29.6 is the bounded private single-shot live "
        "proof substage that uses the existing Stage 29.3 mode "
        "3 `ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN` entrypoint "
        "wired with the already-committed Stage 29.5.5 "
        "migration context recorder, the already-committed "
        "Stage 29.5.5 side-channel artifact writer, and the "
        "already-committed Stage 29.5.6 private Discord body "
        "injector to prove end-to-end that exactly one private "
        "operator Discord ping reaches the operator-supplied "
        "private webhook"
    )
    normalized_source = _normalize_whitespace(_runbook_text())
    assert _normalize_whitespace(expected) in normalized_source


# ---------------------------------------------------------------------------
# 3. Option A no-production-code stance
# ---------------------------------------------------------------------------


def test_no_stage_29_6_production_py_file_present() -> None:
    """Stage 29.6 Option A: zero new production .py file under
    PHX2/stage29/ whose basename starts with ``stage29_6_`` or
    ``stage_29_6_`` (matches both lowercase orientations).
    """
    offenders: list[str] = []
    for entry in STAGE29_ROOT.iterdir():
        if entry.is_dir():
            continue
        name = entry.name
        if not name.endswith(".py"):
            continue
        lower = name.lower()
        if lower.startswith("stage29_6_") or lower.startswith(
            "stage_29_6_",
        ):
            offenders.append(name)
    assert not offenders, (
        f"Stage 29.6 Option A forbids any stage29_6_*.py "
        f"production module under PHX2/stage29/; found "
        f"{sorted(offenders)!r}"
    )


def test_no_stage_29_6_production_module_under_stage29() -> None:
    """The Stage 29.6 Option A inventory under PHX2/stage29/ is
    exactly the two markdown files; no additional Stage 29.6
    file (any extension) may ship without a separate
    authorization.
    """
    allowed_stage_29_6_entries: frozenset[str] = frozenset(
        {
            "STAGE_29_6_BOUNDED_LIVE_PROOF_RUNBOOK.md",
            "STAGE_29_6_SPEC_LOCK.md",
        }
    )
    actual_stage_29_6_entries: set[str] = set()
    for entry in STAGE29_ROOT.iterdir():
        if entry.is_dir():
            continue
        name = entry.name
        lower = name.lower()
        if (
            lower.startswith("stage29_6_")
            or lower.startswith("stage_29_6_")
            or name.startswith("STAGE_29_6_")
        ):
            actual_stage_29_6_entries.add(name)
    forbidden = (
        actual_stage_29_6_entries - allowed_stage_29_6_entries
    )
    assert not forbidden, (
        f"Stage 29.6 Option A admits only the two markdown "
        f"files {sorted(allowed_stage_29_6_entries)!r} under "
        f"PHX2/stage29/; found additional Stage 29.6 entries: "
        f"{sorted(forbidden)!r}"
    )


def test_no_stage_29_6_module_under_phx2_tests_stage29() -> None:
    """The Stage 29.6 test inventory under PHX2/tests/stage29/
    is exactly the two test files.
    """
    allowed_stage_29_6_test_entries: frozenset[str] = frozenset(
        {
            "test_stage_29_6_spec_lock.py",
            "test_stage_29_6_bounded_live_proof.py",
        }
    )
    actual_stage_29_6_test_entries: set[str] = set()
    for entry in TESTS_STAGE29_ROOT.iterdir():
        if entry.is_dir():
            continue
        name = entry.name
        if name.startswith("test_stage_29_6_"):
            actual_stage_29_6_test_entries.add(name)
    forbidden = (
        actual_stage_29_6_test_entries
        - allowed_stage_29_6_test_entries
    )
    assert not forbidden, (
        f"Stage 29.6 admits only the two test files "
        f"{sorted(allowed_stage_29_6_test_entries)!r} under "
        f"PHX2/tests/stage29/; found additional Stage 29.6 "
        f"test entries: {sorted(forbidden)!r}"
    )


# ---------------------------------------------------------------------------
# 4. Option A stance in the runbook
# ---------------------------------------------------------------------------


def test_runbook_pins_option_a() -> None:
    src = _runbook_text()
    lower = src.lower()
    assert "option a" in lower, (
        "Stage 29.6 runbook must pin the Option A stance"
    )


def test_runbook_pins_zero_new_production_py_file() -> None:
    src = _runbook_text()
    lower = src.lower()
    assert (
        "zero new production .py file" in lower
        or "zero new `stage29_6_" in lower
        or "no new `stage29_6_" in lower
        or "ships zero new" in lower
    ), (
        "Stage 29.6 runbook must explicitly state the no-new-"
        "production-code stance"
    )


def test_spec_lock_pins_option_a() -> None:
    src = _spec_lock_text()
    lower = src.lower()
    assert "option a" in lower
    assert (
        "zero new production .py file" in lower
        or "no new production .py file" in lower
        or "ships zero new production" in lower
        or "ships zero" in lower
    )


# ---------------------------------------------------------------------------
# 5. Stage 29.3 ceremony pins (mode tokens + bounded caps)
# ---------------------------------------------------------------------------


def test_runbook_names_every_stage_29_3_mode() -> None:
    src = _runbook_text()
    for token in (
        "READINESS_ONLY",
        "CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY",
        "ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN",
    ):
        assert token in src, (
            f"Stage 29.6 runbook must name Stage 29.3 mode "
            f"{token!r}"
        )


def test_runbook_pins_max_events_and_max_dispatches() -> None:
    src = _runbook_text()
    assert "max_events=1" in src, (
        "Stage 29.6 runbook must pin max_events=1"
    )
    assert "max_dispatches=1" in src, (
        "Stage 29.6 runbook must pin max_dispatches=1"
    )


def test_runbook_pins_ceremony_phase_sequence() -> None:
    src = _runbook_text()
    for marker in (
        "Phase 0",
        "Phase 1",
        "Phase 2",
        "Phase 3",
        "Phase 4",
        "Phase 5",
        "Phase 6",
    ):
        assert marker in src, (
            f"Stage 29.6 runbook must declare ceremony "
            f"{marker!r}"
        )


def test_runbook_describes_readiness_then_connect_then_mode3() -> None:
    """The runbook must describe the readiness-only → connect-
    only → mode-3 phase order. Order is critical: readiness
    gates must pass before any live call; the connect-only
    proof must precede the dispatch phase.

    We anchor on the Section 6 phase HEADERS (``### Phase 1`` /
    ``### Phase 2`` / ``### Phase 3``) so cross-section prose
    references to the same phase tokens (e.g. Section 0's
    "Phase 2 Birdeye call" note) do not confuse the ordering
    check.
    """
    src = _runbook_text()
    readiness_idx = src.find("### Phase 1")
    connect_idx = src.find("### Phase 2")
    dispatch_idx = src.find("### Phase 3")
    assert 0 < readiness_idx < connect_idx < dispatch_idx, (
        "Stage 29.6 runbook must declare Section 6 Phase 1 "
        "(readiness) before Phase 2 (connect) before Phase 3 "
        "(dispatch)"
    )


# ---------------------------------------------------------------------------
# 6. Exact wiring pin (three optional kwargs + recorder + writer + injector)
# ---------------------------------------------------------------------------


def test_runbook_names_three_stage_29_3_optional_kwargs() -> None:
    src = _runbook_text()
    for kwarg in (
        "migration_source",
        "migration_context_renderer",
        "private_discord_body_injector",
    ):
        assert kwarg in src, (
            f"Stage 29.6 runbook must name Stage 29.3 optional "
            f"kwarg {kwarg!r}"
        )


def test_runbook_names_stage_29_5_5_recorder_class() -> None:
    src = _runbook_text()
    assert "Stage29_5_5MigrationContextRecorder" in src


def test_runbook_names_stage_29_5_5_renderer_function() -> None:
    src = _runbook_text()
    assert (
        "render_private_discord_migration_context_block" in src
    )


def test_runbook_names_stage_29_5_5_side_channel_writer() -> None:
    src = _runbook_text()
    assert "Stage29_5_5SideChannelArtifactWriter" in src


def test_runbook_names_stage_29_5_6_injector_class() -> None:
    src = _runbook_text()
    assert "Stage29_5_6PrivateDiscordBodyInjector" in src


def test_runbook_names_stage_29_3_entrypoint() -> None:
    src = _runbook_text()
    assert "run_stage29_3_first_private_tradeable_smoke" in src


# ---------------------------------------------------------------------------
# 7. Operator authorization gates
# ---------------------------------------------------------------------------


def test_runbook_names_operator_authorization_gates() -> None:
    src = _runbook_text()
    assert "live_env_ready=True" in src, (
        "Stage 29.6 runbook must name the live_env_ready=True "
        "operator authorization gate"
    )
    assert "live_operator_request=True" in src, (
        "Stage 29.6 runbook must name the "
        "live_operator_request=True operator authorization gate"
    )


# ---------------------------------------------------------------------------
# 8. Stage 29.6 forbidden surfaces named in the runbook
# ---------------------------------------------------------------------------


_REQUIRED_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "Stage 30",
    "Telegram",
    "Axiom",
    "Ante",
)


def test_runbook_forbids_stage_30() -> None:
    src = _runbook_text()
    # The runbook must mention Stage 30 only in a forbidding /
    # deferring context. We verify both that Stage 30 appears
    # and that it appears next to a "NOT", "remain undefined",
    # "ZERO", or "do NOT start" qualifier.
    assert "Stage 30" in src
    normalized = _normalize_whitespace(src).lower()
    assert (
        "stage 30 remains undefined" in normalized
        or "zero stage 30" in normalized
        or "no stage 30" in normalized
        or "do not start stage 30" in normalized
        or "never starts stage 30" in normalized
        or "not started" in normalized
    ), (
        "Stage 29.6 runbook must explicitly forbid / defer "
        "Stage 30"
    )


def test_runbook_forbids_telegram_x_social() -> None:
    src = _runbook_text()
    lower = src.lower()
    assert "telegram" in lower
    assert "social" in lower
    # The runbook mentions these as NON-goals / forbidden
    # surfaces.
    normalized = _normalize_whitespace(src).lower()
    assert (
        "zero telegram" in normalized
        or "no telegram" in normalized
        or "never sends" in normalized
        or "must not" in normalized
        or "telegram, x, or social" in normalized
        or "telegram / x / social" in normalized
        or "telegram / x / any social" in normalized
    )


def test_runbook_forbids_public_subscriber_paid_routing() -> None:
    src = _runbook_text()
    lower = src.lower()
    for token in ("public", "subscriber", "paid"):
        assert token in lower, (
            f"Stage 29.6 runbook must mention forbidden "
            f"audience {token!r}"
        )


def test_runbook_forbids_enforcement_activation() -> None:
    src = _runbook_text()
    lower = src.lower()
    assert "enforcement" in lower
    assert "activation" in lower or "activate" in lower
    normalized = _normalize_whitespace(src).lower()
    assert (
        "never activates" in normalized
        or "no stage 26" in normalized
        or "no enforcement activation" in normalized
        or "zero stage 26" in normalized
        or "zero enforcement" in normalized
    )


def test_runbook_forbids_trading_wallet_signing() -> None:
    src = _runbook_text()
    lower = src.lower()
    for token in ("trading", "wallet", "signing"):
        assert token in lower, (
            f"Stage 29.6 runbook must mention forbidden "
            f"surface {token!r}"
        )


def test_runbook_forbids_axiom_and_ante_filters() -> None:
    src = _runbook_text()
    for token in ("Axiom", "Ante"):
        assert token in src, (
            f"Stage 29.6 runbook must mention forbidden "
            f"filter {token!r}"
        )


def test_runbook_forbids_new_data_sources() -> None:
    src = _runbook_text()
    lower = src.lower()
    assert (
        "new data source" in lower
        or "new data sources" in lower
    )


# ---------------------------------------------------------------------------
# 9. Stage 29.5.6 cap / fallback discipline pins
# ---------------------------------------------------------------------------


def test_runbook_pins_1900_char_combined_content_cap() -> None:
    src = _runbook_text()
    assert "1900" in src, (
        "Stage 29.6 runbook must pin the Stage 29.5.6 1900-char "
        "combined-content cap"
    )


def test_runbook_describes_full_first_compact_second_skip_third() -> None:
    src = _runbook_text()
    lower = src.lower()
    assert "full block" in lower or "full rendered" in lower
    assert "compact" in lower
    assert "fallback" in lower or "fall back" in lower or (
        "falls back" in lower
    )


def test_runbook_describes_skip_only_on_compact_also_overflow() -> None:
    src = _runbook_text()
    lower = src.lower()
    assert (
        "skip-only-when-both-overflow" in lower
        or "when the full would overflow" in lower
        or "skip-only-when-compact-also-overflows" in lower
        or "when the full would overflow the 1900-char "
        "combined-content cap" in lower
        or "exceed the 1900-char combined-content cap" in lower
    )


# ---------------------------------------------------------------------------
# 10. Acceptance-criteria letters A through R
# ---------------------------------------------------------------------------


def test_acceptance_criteria_letters_a_through_r_named() -> None:
    src = _runbook_text()
    for letter in (
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
        "O",
        "P",
        "Q",
        "R",
    ):
        assert f"**{letter}.**" in src, (
            f"Stage 29.6 runbook must name acceptance criterion "
            f"{letter!r}"
        )


# ---------------------------------------------------------------------------
# 11. Expected artifact basenames documented in the runbook
# ---------------------------------------------------------------------------


_EXPECTED_ARTIFACT_BASENAMES: tuple[str, ...] = (
    "stage28_9_dispatch_ledger.jsonl",
    "stage28_9_heartbeat.jsonl",
    "stage28_9_health_snapshot.json",
    "stage28_9_final_run_summary.json",
    "stage29_3_tradeable_smoke_result.json",
    "stage29_3_extracted_hints.json",
    "stage29_3_birdeye_evidence.json",
    "stage29_3_redaction_scan.json",
    "stage29_5_5_side_channel_migration_context_artifact.json",
)


def test_runbook_documents_expected_artifact_basenames() -> None:
    src = _runbook_text()
    for name in _EXPECTED_ARTIFACT_BASENAMES:
        assert name in src, (
            f"Stage 29.6 runbook must document expected "
            f"acceptance artifact basename {name!r}"
        )


# ---------------------------------------------------------------------------
# 12. No URL host / raw secret / Pump.fun program-id / Phoenix_Bot legacy
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_HOSTS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + "-rpc.com",
    "public-api.birdeye" + ".so",
    "pro-api.birdeye" + ".so",
    "birdeye" + ".so",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com",
    "yellowstone" + ".chainstack",
    "dexscreener" + ".com",
    "ws" + "s://",
    "ws" + "://",
)


def test_runbook_carries_no_url_host_literal() -> None:
    src = _runbook_text()
    for needle in _FORBIDDEN_URL_HOSTS:
        assert needle not in src, (
            f"Stage 29.6 runbook must not carry URL host "
            f"literal {needle!r}"
        )


_FORBIDDEN_RAW_SECRET_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "s" + "k-live-",
    "s" + "k-test-",
    "p" + "k-live-",
    "p" + "k-test-",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "BIRDEYE_API" + "_KEY=",
    "CHAINSTACK_API" + "_KEY=",
)


def test_runbook_carries_no_raw_secret_literal() -> None:
    src = _runbook_text()
    for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
        assert needle not in src, (
            f"Stage 29.6 runbook must not carry raw-secret-"
            f"shaped literal {needle!r}"
        )


def test_runbook_carries_no_pump_fun_program_id() -> None:
    src = _runbook_text()
    pump_program = (
        "6EF8rrec" + "thR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    )
    assert pump_program not in src


def test_runbook_carries_no_phoenix_bot_legacy_substring() -> None:
    src = _runbook_text()
    lower = src.lower()
    assert "phoenix_bot" not in lower, (
        "Stage 29.6 runbook must not carry the "
        "'Phoenix_Bot' legacy substring"
    )


# ---------------------------------------------------------------------------
# 13. Spec-lock markdown invariants
# ---------------------------------------------------------------------------


def test_spec_lock_lists_allowed_file_inventory() -> None:
    src = _spec_lock_text()
    for name in (
        "STAGE_29_6_BOUNDED_LIVE_PROOF_RUNBOOK.md",
        "STAGE_29_6_SPEC_LOCK.md",
        "test_stage_29_6_spec_lock.py",
        "test_stage_29_6_bounded_live_proof.py",
    ):
        assert name in src, (
            f"Stage 29.6 spec-lock markdown must list allowed "
            f"file {name!r}"
        )


def test_spec_lock_lists_forbidden_production_touch_paths() -> None:
    src = _spec_lock_text()
    for forbidden in (
        "PHX2/stage27/",
        "PHX2/stage28/",
        "stage29_3_tradeable_smoke.py",
        "stage29_4_",
        "stage29_5_4_",
        "stage29_5_5_",
        "stage29_5_6_",
    ):
        assert forbidden in src, (
            f"Stage 29.6 spec-lock markdown must list forbidden "
            f"production-touch path {forbidden!r}"
        )


def test_spec_lock_carries_no_url_or_secret_literal() -> None:
    src = _spec_lock_text()
    for needle in _FORBIDDEN_URL_HOSTS:
        assert needle not in src
    for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
        assert needle not in src


def test_spec_lock_carries_no_phoenix_bot_legacy_substring() -> None:
    src = _spec_lock_text()
    lower = src.lower()
    assert "phoenix_bot" not in lower


# ---------------------------------------------------------------------------
# 14. Stage 29.6 live-call abstinence pins
# ---------------------------------------------------------------------------


_REQUIRED_ABSTINENCE_PHRASES: tuple[str, ...] = (
    (
        "Stage 29.6 implementation/tests perform ZERO live "
        "WS/gRPC/HTTP calls."
    ),
    (
        "Stage 29.6 implementation/tests perform ZERO live "
        "Discord sends."
    ),
    (
        "The Stage 29.6 live ceremony requires separate "
        "explicit operator authorization before any live "
        "WS/gRPC/HTTP call or Discord send."
    ),
    (
        "Stage 29.6 implementation/commit does not itself run "
        "the live ceremony."
    ),
)


def test_spec_lock_pins_zero_live_ws_grpc_http_calls() -> None:
    src = _spec_lock_text()
    normalized = _normalize_whitespace(src)
    needle = _normalize_whitespace(
        _REQUIRED_ABSTINENCE_PHRASES[0]
    )
    assert needle in normalized, (
        "Stage 29.6 spec-lock must explicitly pin that "
        "implementation/tests perform ZERO live WS/gRPC/HTTP "
        "calls"
    )


def test_spec_lock_pins_zero_live_discord_sends() -> None:
    src = _spec_lock_text()
    normalized = _normalize_whitespace(src)
    needle = _normalize_whitespace(
        _REQUIRED_ABSTINENCE_PHRASES[1]
    )
    assert needle in normalized, (
        "Stage 29.6 spec-lock must explicitly pin that "
        "implementation/tests perform ZERO live Discord sends"
    )


def test_spec_lock_pins_separate_operator_authorization_gate() -> None:
    src = _spec_lock_text()
    normalized = _normalize_whitespace(src)
    needle = _normalize_whitespace(
        _REQUIRED_ABSTINENCE_PHRASES[2]
    )
    assert needle in normalized, (
        "Stage 29.6 spec-lock must explicitly pin that the "
        "live ceremony requires separate explicit operator "
        "authorization before any live WS/gRPC/HTTP call or "
        "Discord send"
    )


def test_spec_lock_pins_implementation_does_not_run_ceremony() -> None:
    src = _spec_lock_text()
    normalized = _normalize_whitespace(src)
    needle = _normalize_whitespace(
        _REQUIRED_ABSTINENCE_PHRASES[3]
    )
    assert needle in normalized, (
        "Stage 29.6 spec-lock must explicitly pin that "
        "implementation/commit does not itself run the live "
        "ceremony"
    )


def test_spec_lock_carries_all_abstinence_phrases() -> None:
    """Belt-and-braces pin: every Codex-required abstinence
    phrase must appear in the spec-lock markdown.
    """
    src = _spec_lock_text()
    normalized = _normalize_whitespace(src)
    missing: list[str] = []
    for phrase in _REQUIRED_ABSTINENCE_PHRASES:
        if _normalize_whitespace(phrase) not in normalized:
            missing.append(phrase)
    assert not missing, (
        f"Stage 29.6 spec-lock missing required abstinence "
        f"phrases: {missing!r}"
    )
