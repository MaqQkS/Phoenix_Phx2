"""Stage 26.7 closure-audit + Stage 27 handoff doc tests.

Pins:

  * ``PHX2/stage26/STAGE_26_CLOSURE_AUDIT.md`` exists and carries
    every Stage 26 substage name, every Stage 26 commit SHA (full
    + short), the calibration / candidate-policy-evidence-only
    scope statement, the forbidden-surface list (enforcement /
    dispatch / live routing / Discord / Telegram / X / social /
    Axiom / Stage 24 fees / Stage 27 implementation), the truth-
    preservation invariants, and the candidate-policy safety flags.
  * ``PHX2/stage26/STAGE_27_HANDOFF.md`` exists and pins Stage 27
    as the PHX1-parity private live tradeable ping runner, the
    first real private Discord ping stage; explicitly states
    Stage 27 is NOT X / social; includes the SOL / USDC / UNKNOWN
    pair-awareness vocabulary; pins the USDC observe-only
    discipline; pins the SOL / USDC calibration-universe separation;
    pins the Stage 28 / Stage 29 / Stage 30+ roadmap.
  * ``PHX2/stage27/`` does NOT exist (no Stage 27 scaffold ships
    at Stage 26.7).
  * No Stage 27 implementation file ships under ``PHX2/stage26/``
    (no runner / CLI / dispatcher / live-router / Discord /
    Telegram / X-social / Axiom / approval / enforcement basename
    is present).
  * The Stage 25.7 closure-audit allowlist admits exactly the
    Stage 26.7 docs (`STAGE_26_CLOSURE_AUDIT.md` /
    `STAGE_27_HANDOFF.md`) and still blocks Stage 27 implementation.
  * The new Stage 26.7 documents carry no URL literal, no webhook
    host literal, no API-key literal, and no approval-leak marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE26_ROOT: Path = PHX2_ROOT / "stage26"
TESTS_STAGE25_ROOT: Path = PHX2_ROOT / "tests" / "stage25"


CLOSURE_AUDIT_PATH: Path = STAGE26_ROOT / "STAGE_26_CLOSURE_AUDIT.md"
STAGE27_HANDOFF_PATH: Path = STAGE26_ROOT / "STAGE_27_HANDOFF.md"
STAGE_25_7_CLOSURE_TEST_PATH: Path = (
    TESTS_STAGE25_ROOT / "test_stage_25_7_closure_audit.py"
)


def _closure_audit_text() -> str:
    return CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")


def _stage27_handoff_text() -> str:
    return STAGE27_HANDOFF_PATH.read_text(encoding="utf-8")


def _stage_25_7_closure_test_text() -> str:
    return STAGE_25_7_CLOSURE_TEST_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace (including markdown line wraps)
    into single spaces so a phrase that wraps across a line still
    matches.
    """
    return " ".join(text.split())


def _stage_25_7_allowlist_body() -> str:
    """Return only the body of the Stage 25.7 ``_STAGE_26_7_ALLOWED_ENTRIES``
    frozenset literal so the allowlist-narrowness check does not
    falsely match Stage 25 production filenames that legitimately
    appear elsewhere in the closure-audit test file (e.g. Stage 25's
    own ``runner.py`` module in ``_EXPECTED_STAGE25_PRODUCTION_PY``).
    """
    text = _stage_25_7_closure_test_text()
    marker = "_STAGE_26_7_ALLOWED_ENTRIES: frozenset[str] = frozenset("
    start = text.find(marker)
    assert start >= 0, (
        "Stage 25.7 closure-audit test must declare "
        "_STAGE_26_7_ALLOWED_ENTRIES; the Stage 26.7 narrow "
        "amendment is missing"
    )
    end = text.find(")", start)
    assert end > start, "could not locate end of allowlist literal"
    return text[start:end + 1]


# ---------------------------------------------------------------------------
# 1-2. Documents exist
# ---------------------------------------------------------------------------


def test_stage_26_closure_audit_doc_exists():
    assert CLOSURE_AUDIT_PATH.is_file(), (
        f"Stage 26.7 requires {CLOSURE_AUDIT_PATH}"
    )


def test_stage_27_handoff_doc_exists():
    assert STAGE27_HANDOFF_PATH.is_file(), (
        f"Stage 26.7 requires {STAGE27_HANDOFF_PATH}"
    )


# ---------------------------------------------------------------------------
# 3. Closure audit doc names every Stage 26 substage
# ---------------------------------------------------------------------------


_STAGE_26_SUBSTAGE_NAMES: tuple[str, ...] = (
    "26.0",
    "26.1",
    "26.2",
    "26.3",
    "26.4",
    "26.5",
    "26.6",
    "26.7",
)


@pytest.mark.parametrize("substage", _STAGE_26_SUBSTAGE_NAMES)
def test_closure_audit_doc_names_each_substage(substage):
    text = _closure_audit_text()
    assert substage in text, (
        f"closure-audit doc missing Stage {substage} substage label"
    )


_STAGE_26_SUBSTAGE_SCOPE_PHRASES: tuple[str, ...] = (
    "spec-lock",
    "calibration input contracts",
    "denominator",
    "outcome-eligibility",
    "cohort builder",
    "threshold candidate generator",
    "policy candidate",
    "operator review packet",
    "approval handoff",
    "closure audit",
    "Stage 27 handoff",
)


@pytest.mark.parametrize("phrase", _STAGE_26_SUBSTAGE_SCOPE_PHRASES)
def test_closure_audit_doc_carries_substage_scope_phrase(phrase):
    """The closure-audit doc carries the locked Stage 26 substage
    scope phrases. The match is case-insensitive and whitespace-
    normalized so the markdown line-wrap convention does not break
    a multi-word phrase match.
    """
    normalized = _normalized_whitespace(_closure_audit_text()).lower()
    assert phrase.lower() in normalized, (
        f"closure-audit doc missing Stage 26 scope phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 4. Closure audit doc names every Stage 26 commit SHA (full + short)
# ---------------------------------------------------------------------------


_STAGE_26_COMMITS: tuple[tuple[str, str, str], ...] = (
    (
        "fea479b9f4816ffd87fb2756b40f7f2edb12f96c",
        "fea479b",
        "phx2 stage 26.0: lock calibration architecture charter",
    ),
    (
        "d5ab2b9f5bf7bf9eb49c07f690670a483118d05f",
        "d5ab2b9",
        "phx2 stage 25: expose manifest self-entry sentinels",
    ),
    (
        "2bdf02585f97ed46a1c4e23f19a4134224aeb0bc",
        "2bdf025",
        "phx2 stage 26.1: calibration input readers and contracts",
    ),
    (
        "7fb2138472cf46cdfc7c1f0b89e8bf7bc402d070",
        "7fb2138",
        "phx2 stage 26.2: denominator eligibility semantics",
    ),
    (
        "ef5c47dbbfe4d6e649dfb5bec03a0b96304a1272",
        "ef5c47d",
        "phx2 stage 26.3: calibration cohort builder",
    ),
    (
        "c54743d70a8a2f8fff0a5875df44be13c41bdbbc",
        "c54743d",
        "phx2 stage 26.4: threshold candidate generator",
    ),
    (
        "9fd2113136850121d7b8397128030ac2113b5684",
        "9fd2113",
        "phx2 stage 26.5: observe-only policy candidate artifacts",
    ),
    (
        "49476695860e9a9897114ed9724919d4852c5240",
        "4947669",
        "phx2 stage 26.6: operator review packet handoff",
    ),
)


@pytest.mark.parametrize(
    "full_sha,short_sha,subject", _STAGE_26_COMMITS
)
def test_closure_audit_doc_contains_each_commit(
    full_sha, short_sha, subject
):
    text = _closure_audit_text()
    assert full_sha in text, (
        f"closure-audit doc missing full SHA {full_sha!r}"
    )
    assert short_sha in text, (
        f"closure-audit doc missing short SHA {short_sha!r}"
    )
    assert subject in text, (
        f"closure-audit doc missing commit subject {subject!r}"
    )


# ---------------------------------------------------------------------------
# 5. Closure audit doc states Stage 26 is calibration/candidate-policy only
# ---------------------------------------------------------------------------


def test_closure_audit_doc_states_calibration_candidate_only_scope():
    text = _closure_audit_text()
    assert (
        "Stage 26 is calibration / candidate-policy evidence only."
        in text
    )


def test_closure_audit_doc_states_no_live_policy_activation():
    normalized = _normalized_whitespace(_closure_audit_text()).lower()
    assert "does not activate any live policy" in normalized, (
        "closure-audit doc must state that Stage 26 does not "
        "activate any live policy"
    )


# ---------------------------------------------------------------------------
# 6. Closure audit doc forbids enforcement/dispatch/live routing/social/Axiom
# ---------------------------------------------------------------------------


_REQUIRED_CLOSURE_AUDIT_FORBIDDEN_PHRASES: tuple[str, ...] = (
    # No enforcement.
    "enforce",
    # No dispatch.
    "dispatch",
    # No live runner / live alert path.
    "live runner",
    # No Discord / Telegram dispatch.
    "Discord",
    "Telegram",
    # No X / social.
    "X / social",
    # No Axiom / global-fee reopening.
    "Axiom",
    "global-fee",
    "execution-fee",
    # No Stage 27 implementation here.
    "Stage 27",
    # No approval granted.
    "approve any policy candidate",
    # No runtime-consumable / enforcement-enabled.
    "runtime-consumable",
    "enforcement-enabled",
)


@pytest.mark.parametrize(
    "phrase", _REQUIRED_CLOSURE_AUDIT_FORBIDDEN_PHRASES
)
def test_closure_audit_doc_names_forbidden_surface(phrase):
    text = _closure_audit_text()
    assert phrase in text, (
        f"closure-audit doc missing forbidden-surface phrase "
        f"{phrase!r}"
    )


# ---------------------------------------------------------------------------
# 7. Closure audit doc preserves safety flags + truth invariants
# ---------------------------------------------------------------------------


_REQUIRED_CLOSURE_AUDIT_SAFETY_PHRASES: tuple[str, ...] = (
    "candidate_only=True",
    "observe_only=True",
    "review_only=True",
    "operator_approved=False",
    "runtime_consumable=False",
    "enforcement_enabled=False",
    "PENDING_OPERATOR_REVIEW",
)


@pytest.mark.parametrize(
    "phrase", _REQUIRED_CLOSURE_AUDIT_SAFETY_PHRASES
)
def test_closure_audit_doc_pins_each_safety_flag(phrase):
    text = _closure_audit_text()
    assert phrase in text, (
        f"closure-audit doc missing safety-flag phrase {phrase!r}"
    )


_REQUIRED_CLOSURE_AUDIT_TRUTH_PHRASES: tuple[str, ...] = (
    "no fake ATH when source data is missing",
    "no fake migration timestamp when migration evidence is "
    "ambiguous",
    "no `0` price as a missing sentinel",
    "no `0` ATH as a missing sentinel",
    "MEASURED",
    "PARTIAL",
    "SOURCE_CONFLICT",
    "AMBIGUOUS",
    "MISSING",
    "UNSUPPORTED",
    "REJECTED",
    "NOT_APPLICABLE",
)


@pytest.mark.parametrize(
    "phrase", _REQUIRED_CLOSURE_AUDIT_TRUTH_PHRASES
)
def test_closure_audit_doc_carries_each_truth_invariant(phrase):
    text = _closure_audit_text()
    assert phrase in text, (
        f"closure-audit doc missing truth invariant {phrase!r}"
    )


def test_closure_audit_doc_forbids_truth_upgrades():
    text = _closure_audit_text()
    assert (
        "NEVER upgraded into" in text
        or "NEVER upgrades them" in text
    )


# ---------------------------------------------------------------------------
# 7b. Closure audit doc pins writer safety
# ---------------------------------------------------------------------------


_REQUIRED_CLOSURE_AUDIT_WRITER_PHRASES: tuple[str, ...] = (
    "deterministic offline",
    "redaction sweep",
    "self-entry sentinel",
    "Path.write_bytes",
)


@pytest.mark.parametrize(
    "phrase", _REQUIRED_CLOSURE_AUDIT_WRITER_PHRASES
)
def test_closure_audit_doc_pins_writer_safety(phrase):
    text = _closure_audit_text()
    assert phrase in text, (
        f"closure-audit doc missing writer-safety phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 8-10. Stage 27 handoff doc: charter, Discord, NOT X/social
# ---------------------------------------------------------------------------


def test_stage27_handoff_doc_names_phx1_parity_private_live_ping_runner():
    text = _stage27_handoff_text()
    assert (
        "PHX1-parity private live tradeable ping runner" in text
    )


def test_stage27_handoff_doc_says_first_real_private_discord_ping_stage():
    text = _stage27_handoff_text()
    assert "first PHX2 stage" in text
    assert "real private Discord pings" in text
    assert "manual trading" in text


def test_stage27_handoff_doc_explicitly_says_not_x_social():
    text = _stage27_handoff_text()
    assert "Stage 27 is not the X / social stage" in text
    assert "deferred to" in text
    assert "Stage 30+" in text


# ---------------------------------------------------------------------------
# 11. Pump pair-awareness vocabulary
# ---------------------------------------------------------------------------


_STAGE_27_QUOTE_ASSETS: tuple[str, ...] = ("SOL", "USDC", "UNKNOWN")
_STAGE_27_PAIR_TYPES: tuple[str, ...] = (
    "PUMP_SOL",
    "PUMP_USDC",
    "UNKNOWN",
)
_STAGE_27_BONDING_CURVE_VERSIONS: tuple[str, ...] = (
    "SOL_LEGACY",
    "USDC_FIXED",
    "UNKNOWN",
)


@pytest.mark.parametrize("token", _STAGE_27_QUOTE_ASSETS)
def test_stage27_handoff_doc_names_quote_asset_token(token):
    text = _stage27_handoff_text()
    assert token in text, (
        f"Stage 27 handoff missing quote_asset token {token!r}"
    )


@pytest.mark.parametrize("token", _STAGE_27_PAIR_TYPES)
def test_stage27_handoff_doc_names_pair_type_token(token):
    text = _stage27_handoff_text()
    assert token in text, (
        f"Stage 27 handoff missing pair_type token {token!r}"
    )


@pytest.mark.parametrize(
    "token", _STAGE_27_BONDING_CURVE_VERSIONS
)
def test_stage27_handoff_doc_names_bonding_curve_version_token(
    token,
):
    text = _stage27_handoff_text()
    assert token in text, (
        f"Stage 27 handoff missing bonding_curve_version token "
        f"{token!r}"
    )


def test_stage27_handoff_doc_names_pair_awareness_vocabulary():
    text = _stage27_handoff_text()
    assert "quote_asset" in text
    assert "pair_type" in text
    assert "bonding_curve_version" in text


# ---------------------------------------------------------------------------
# 12. USDC observe-only discipline
# ---------------------------------------------------------------------------


def test_stage27_handoff_doc_says_usdc_pings_observe_only_until_data_exists():
    text = _stage27_handoff_text()
    assert "USDC-pair pings" in text
    assert "observe-only" in text.lower()
    assert (
        "until PHX2 has" in text
        or "until enough PHX2 data" in text
        or "until PHX2 has accumulated" in text
    )


# ---------------------------------------------------------------------------
# 13. SOL / USDC universe separation
# ---------------------------------------------------------------------------


def test_stage27_handoff_doc_says_sol_and_usdc_universes_must_stay_separate():
    text = _stage27_handoff_text()
    assert "MUST stay separate" in text
    assert "SOL-pair" in text
    assert "USDC-pair" in text


def test_stage27_handoff_doc_forbids_silent_merge_of_sol_and_usdc():
    text = _stage27_handoff_text()
    assert "silently merging" in text or "silent merging" in text
    assert "denominator" in text


# ---------------------------------------------------------------------------
# 14. Stage 28 / 29 / 30+ roadmap
# ---------------------------------------------------------------------------


def test_stage27_handoff_doc_pins_stage_28_hardening():
    text = _stage27_handoff_text()
    assert "Stage 28" in text
    assert "hardening" in text


def test_stage27_handoff_doc_pins_stage_29_approved_enforcement():
    text = _stage27_handoff_text()
    assert "Stage 29" in text
    assert "Approved enforcement" in text or "approved enforcement" in text
    assert "live gating" in text


def test_stage27_handoff_doc_pins_stage_30_x_social_sidecar():
    text = _stage27_handoff_text()
    assert "Stage 30+" in text
    assert "X / social sidecar" in text


# ---------------------------------------------------------------------------
# 14b. Stage 27 required surfaces
# ---------------------------------------------------------------------------


_STAGE_27_REQUIRED_SURFACE_PHRASES: tuple[str, ...] = (
    ".env",
    "API key",
    "Helius",
    "gRPC",
    "Birdeye",
    "migration",
    "Discord ping",
    "dedupe",
    "bounded continuous runner",
    "runbook",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_27_REQUIRED_SURFACE_PHRASES
)
def test_stage27_handoff_doc_names_required_surface_phrase(phrase):
    text = _stage27_handoff_text()
    assert phrase in text, (
        f"Stage 27 handoff missing required-surface phrase "
        f"{phrase!r}"
    )


def test_stage27_handoff_doc_includes_stage23_24_observe_only_labels():
    text = _stage27_handoff_text()
    assert "Stage 23" in text
    assert "Stage 24" in text
    assert "observe-only" in text


def test_stage27_handoff_doc_includes_stage25_measurement_aware_context():
    text = _stage27_handoff_text()
    assert "Stage 25 measurement-aware" in text


# ---------------------------------------------------------------------------
# 15-17. No Stage 27 implementation
# ---------------------------------------------------------------------------


# Stage 27.0 / 27.1 narrow amendment: ``PHX2/stage27/`` is
# materialized at Stage 27.0 with the scaffold and extended at
# Stage 27.1 with the operator-config / secrets-readiness / run-
# identity / config-errors / config-models production surface
# (no provider client, no Discord sender, no ping renderer, no
# bounded runner, no dedupe, no pair classifier, no enforcement).
# The narrow allowlist admits exactly the Stage 27.0 + 27.1 file
# set; every Stage 27.2+ implementation surface remains blocked.
_STAGE_27_0_NARROW_ALLOWED_ENTRIES: frozenset[str] = frozenset(
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


def test_stage27_implementation_tree_does_not_exist():
    """Stage 27.0 narrow amendment to the legacy Stage 27 tree check.

    Stage 26.7 originally asserted ``PHX2/stage27/`` did not exist.
    Stage 27.0 ships a scaffold-only Stage 27 package (the package
    marker + the spec-lock document), so this assertion has been
    narrowed: if ``PHX2/stage27/`` exists, every top-level entry
    must be inside the locked Stage 27.0 narrow allowlist
    (``__init__.py`` + ``STAGE_27_0_SPEC_LOCK.md``). The
    interpreter's ``__pycache__`` directory is build noise and is
    excluded. Every Stage 27.1+ implementation file remains
    forbidden at Stage 27.0 closure.
    """
    stage27 = PHX2_ROOT / "stage27"
    if not stage27.exists():
        return
    assert stage27.is_dir(), (
        f"PHX2/stage27 must be a directory if it exists: {stage27}"
    )
    actual: set[str] = set()
    for entry in stage27.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = actual - _STAGE_27_0_NARROW_ALLOWED_ENTRIES
    assert not forbidden, (
        f"PHX2/stage27 admits only the Stage 27.0 + 27.1 file set "
        f"({sorted(_STAGE_27_0_NARROW_ALLOWED_ENTRIES)!r}); Stage "
        f"27.2+ implementation files (runner / classifier / "
        f"Discord sender / dedupe / provider client / price "
        f"reader / candidate assembler) remain blocked. "
        f"Forbidden entries found: {sorted(forbidden)!r}"
    )


_FORBIDDEN_STAGE_27_BASENAMES: tuple[str, ...] = (
    "runner.py",
    "live_runner.py",
    "cli.py",
    "main.py",
    "scheduler.py",
    "daemon.py",
    "dispatch.py",
    "dispatcher.py",
    "discord.py",
    "telegram.py",
    "x_api.py",
    "social.py",
    "enforcement.py",
    "approval.py",
    "axiom.py",
    "global_fee.py",
    "live_router.py",
    "subscriber_router.py",
    "stage27_handoff.py",
)


@pytest.mark.parametrize(
    "basename", _FORBIDDEN_STAGE_27_BASENAMES
)
def test_no_stage_27_implementation_basename_under_stage26(basename):
    assert not (STAGE26_ROOT / basename).exists(), (
        f"PHX2/stage26 must not ship Stage 27 implementation "
        f"basename {basename!r} during Stage 26.7"
    )


def test_no_stage_27_python_module_under_stage26():
    """No new Stage 26 production .py module ships during Stage 26.7.

    Stage 26.7 is a docs-and-tests-only pass; the Stage 26 .py
    inventory remains the locked Stage 26.6 set.
    """
    locked_stage_26_py = frozenset(
        {
            "__init__.py",
            "constants.py",
            "errors.py",
            "models.py",
            "stage25_schema_whitelist.py",
            "stage25_artifact_reader.py",
            "stage25_artifact_validation.py",
            "calibration_input_contracts.py",
            "eligibility_constants.py",
            "eligibility_models.py",
            "eligibility_classifier.py",
            "cohort_constants.py",
            "cohort_models.py",
            "cohort_builder.py",
            "threshold_constants.py",
            "threshold_models.py",
            "threshold_candidate_generator.py",
            "policy_candidate_constants.py",
            "policy_candidate_models.py",
            "policy_candidate_builder.py",
            "policy_candidate_writer.py",
            "review_packet_constants.py",
            "review_packet_models.py",
            "review_packet_builder.py",
            "review_packet_writer.py",
        }
    )
    actual_py = {
        p.name
        for p in STAGE26_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    unexpected = actual_py - locked_stage_26_py
    assert not unexpected, (
        f"Stage 26.7 must not add a new Stage 26 production .py "
        f"module; unexpected files: {sorted(unexpected)}"
    )


# ---------------------------------------------------------------------------
# 18. Stage 25.7 closure-audit allowlist admits only Stage 26.7 docs
# ---------------------------------------------------------------------------


def test_stage_25_7_allowlist_admits_closure_audit_doc():
    text = _stage_25_7_closure_test_text()
    assert "\"STAGE_26_CLOSURE_AUDIT.md\"" in text


def test_stage_25_7_allowlist_admits_stage27_handoff_doc():
    text = _stage_25_7_closure_test_text()
    assert "\"STAGE_27_HANDOFF.md\"" in text


def test_stage_25_7_allowlist_still_forbids_stage27_implementation_tree():
    text = _stage_25_7_closure_test_text()
    assert "test_stage27_implementation_tree_does_not_exist" in text
    assert "stage27 = PHX2_ROOT / \"stage27\"" in text


def test_stage_25_7_allowlist_does_not_admit_runner_or_cli_basenames():
    """The Stage 26.7 narrow allowlist amendment must not have been
    broadly relaxed.

    Stage 26.7's amendment admits exactly the two closure markdown
    documents (``STAGE_26_CLOSURE_AUDIT.md`` /
    ``STAGE_27_HANDOFF.md``) and nothing else; the
    ``_STAGE_26_7_ALLOWED_ENTRIES`` set must not now admit a
    runner / CLI / dispatch / live-router / Discord / Telegram
    basename. The check is scoped to the allowlist literal body
    only so that legitimate Stage 25 production filenames declared
    elsewhere in the closure-audit test (e.g. Stage 25's own
    ``runner.py`` in ``_EXPECTED_STAGE25_PRODUCTION_PY``) do not
    false-trip the check.
    """
    body = _stage_25_7_allowlist_body()
    forbidden_in_allowlist = (
        "\"runner.py\"",
        "\"live_runner.py\"",
        "\"cli.py\"",
        "\"main.py\"",
        "\"dispatcher.py\"",
        "\"dispatch.py\"",
        "\"discord.py\"",
        "\"telegram.py\"",
        "\"x_api.py\"",
        "\"social.py\"",
        "\"enforcement.py\"",
        "\"approval.py\"",
        "\"axiom.py\"",
        "\"global_fee.py\"",
        "\"live_router.py\"",
        "\"subscriber_router.py\"",
    )
    for fragment in forbidden_in_allowlist:
        assert fragment not in body, (
            f"Stage 25.7 closure-audit allowlist must not admit "
            f"Stage 27 implementation basename {fragment!r}; the "
            "Stage 26.7 amendment must remain narrow"
        )


# ---------------------------------------------------------------------------
# Closure docs carry no URL / secret / approval-leak literal
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
    "doc_path", [CLOSURE_AUDIT_PATH, STAGE27_HANDOFF_PATH]
)
def test_stage_26_7_doc_has_no_url_literal(doc_path):
    text = doc_path.read_text(encoding="utf-8")
    for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
        assert needle not in text, (
            f"{doc_path.name}: forbidden URL literal {needle!r}"
        )


_FORBIDDEN_LEAK_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "operator_approved=true",
    "operator_approved=True",
    "runtime_consumable=true",
    "runtime_consumable=True",
    "enforcement_enabled=true",
    "enforcement_enabled=True",
)


@pytest.mark.parametrize(
    "doc_path", [CLOSURE_AUDIT_PATH, STAGE27_HANDOFF_PATH]
)
def test_stage_26_7_doc_has_no_leak_marker_literal(doc_path):
    text = doc_path.read_text(encoding="utf-8")
    for needle in _FORBIDDEN_LEAK_LITERAL_SUBSTRINGS:
        assert needle not in text, (
            f"{doc_path.name}: forbidden leak-marker literal "
            f"{needle!r}"
        )


@pytest.mark.parametrize(
    "doc_path", [CLOSURE_AUDIT_PATH, STAGE27_HANDOFF_PATH]
)
def test_stage_26_7_doc_does_not_emit_approved_token(doc_path):
    """The closure docs must never expose an APPROVED / AUTO_APPROVED
    token as a closed-set value; Stage 26 only emits the
    PENDING_OPERATOR_REVIEW handoff state.
    """
    text = doc_path.read_text(encoding="utf-8")
    assert "\"AUTO_APPROVED\"" not in text
    # ``"APPROVED"`` (with literal quotes) would only appear if a
    # closed-set value tried to expose an approved outcome; the
    # closure docs deliberately do not.
    assert "\"APPROVED\"" not in text


# ---------------------------------------------------------------------------
# Stage 26.7 doc cross-references
# ---------------------------------------------------------------------------


def test_closure_audit_doc_points_at_stage27_handoff():
    text = _closure_audit_text()
    assert "STAGE_27_HANDOFF.md" in text


def test_stage27_handoff_doc_points_at_stage26_closure_audit():
    text = _stage27_handoff_text()
    assert "STAGE_26_CLOSURE_AUDIT.md" in text


def test_closure_audit_doc_disclaims_tag_creation():
    text = _closure_audit_text()
    assert "no tag" in text.lower()
    assert "stage-26-closed" in text


def test_stage_26_7_is_docs_and_tests_only():
    text = _closure_audit_text()
    assert "docs and tests only" in text.lower() or (
        "docs / tests only" in text.lower()
    )
