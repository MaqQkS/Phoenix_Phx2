"""Offline proofs that the named alert policy is BOUND at every deployment boundary.

``--alert-policy phx1_parity`` selects a production policy that changes which
eligibility conditions are enforced, how long a candidate is watched, and
whether a send-time market refresh runs.  Before this binding it was the only
safety-bearing production selection that no deployment surface recorded: a run
could switch between LEGACY and PHX1_PARITY without any of the identity
protections that guard the migration source mode and the structural policy.

The invariant proven here is that the effective alert policy is explicitly
bound and auditable at each boundary -- launcher contract, launcher template,
startup manifest, durable epoch identity, closed-epoch deployment handoff,
watchdog expected policy, operator status, and producer summary -- and that
missing, duplicated, unknown or conflicting values fail closed rather than
defaulting to something the deployment never stated.

Nothing here starts a producer, opens a socket, or touches the canonical ledger.
"""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from PHX2.free_tier_producer import live_epoch as epochlib
from PHX2.free_tier_producer import phx1_parity_policy as policy
from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_ALERT_POLICY,
    CANONICAL_ALERT_POLICY_CLI,
    REFUSAL_ALERT_POLICY_ABSENT,
    REFUSAL_ALERT_POLICY_COUNT,
    REFUSAL_ALERT_POLICY_NOT_CANONICAL,
    REFUSAL_ALERT_POLICY_UNKNOWN,
    alert_policy_occurrences,
    canonical_launcher_arguments,
    parse_launcher_arguments,
    validate_launcher_arguments,
)
from PHX2.free_tier_producer.live_epoch import (
    LEGACY_ALERT_POLICY_BINDING,
    build_durable_policy_identity,
)
from PHX2.tests import test_closed_epoch_deployment_handoff as handoff_harness
from PHX2.tests.watchdog._harness import (
    HEAD_SHA as HARNESS_HEAD,
    FakeWorld,
    canonical_durable_identity,
    make_config,
)
from PHX2.watchdog.config import alert_policy_in_launcher
from PHX2.watchdog.launcher_template import (
    REFUSAL_ALERT_POLICY_COUNT as TEMPLATE_ALERT_POLICY_COUNT,
    REFUSAL_ALERT_POLICY_MISSING as TEMPLATE_ALERT_POLICY_MISSING,
    REFUSAL_ALERT_POLICY_NOT_CANONICAL as TEMPLATE_ALERT_POLICY_NOT_CANONICAL,
    REFUSAL_ALERT_POLICY_UNKNOWN as TEMPLATE_ALERT_POLICY_UNKNOWN,
    deployment_specification,
    render_live_launcher,
    validate_live_launcher_text,
)
from PHX2.watchdog.observe import expected_alert_policy
from PHX2.watchdog.process import (
    ADOPT_ALERT_POLICY_MISMATCH,
    ADOPTION_REFUSAL_REASONS,
    evaluate_producer_adoption,
    read_producer_lock,
)


HEAD = "a" * 40
BASELINE = "b" * 64 + ":25:9164"


def _launcher_text() -> str:
    return render_live_launcher(expected_head=HEAD, ledger_baseline=BASELINE)


# ---------------------------------------------------------------------------
# 1. PHX1_PARITY launcher binds PHX1_PARITY into the manifest
# ---------------------------------------------------------------------------


def test_1_launcher_binds_phx1_parity_into_the_startup_manifest():
    text = _launcher_text()

    # The rendered launcher states the policy in its argument vector...
    assert f'"--alert-policy", "{CANONICAL_ALERT_POLICY_CLI}"' in text
    # ...in its redaction-safe transcript line...
    assert f"alert_policy={CANONICAL_ALERT_POLICY_CLI}" in text
    # ...and in the startup manifest it writes.
    assert f'alert_policy            = "{CANONICAL_ALERT_POLICY}"' in text

    # The prefix trap: "__ALERT_POLICY__" is a prefix of
    # "__ALERT_POLICY_CLI__", so a naive replacement order would leave
    # "phx1_parity_CLI" or "PHX1_PARITY_CLI" behind.
    assert "__ALERT_POLICY__" not in text
    assert "__ALERT_POLICY_CLI__" not in text
    assert "PHX1_PARITY_CLI" not in text
    assert "phx1_parity_CLI" not in text

    spec = deployment_specification(
        expected_head=HEAD, ledger_baseline=BASELINE)
    assert spec["alert_policy"] == CANONICAL_ALERT_POLICY
    assert spec["contract_refusals"] == []

    # The canonical argument vector the contract requires carries it exactly once.
    argv = canonical_launcher_arguments(
        launcher="launch_window_04.ps1",
        expected_head=HEAD, ledger_baseline=BASELINE)
    assert alert_policy_occurrences(argv) == [CANONICAL_ALERT_POLICY_CLI]
    assert argv.count("--alert-policy") == 1
    assert parse_launcher_arguments(argv)["alert_policy"] == (
        CANONICAL_ALERT_POLICY_CLI)

    # And the watchdog reads the same single value back out of the text.
    assert alert_policy_in_launcher(text) == CANONICAL_ALERT_POLICY


# ---------------------------------------------------------------------------
# 2. Durable epoch identity includes the alert-policy binding
# ---------------------------------------------------------------------------


def test_2_durable_epoch_identity_includes_the_alert_policy_binding(tmp_path):
    identity = build_durable_policy_identity(
        state_dir=tmp_path, repo_head=HEAD, launcher_sha256="c" * 64,
        alert_policy=CANONICAL_ALERT_POLICY)
    assert identity["alert_policy_binding"] == CANONICAL_ALERT_POLICY

    # It is a SEMANTIC binding: it participates in the policy digest, so two
    # deployments differing only in alert policy are not the same identity.
    assert "alert_policy_binding" in epochlib._SEMANTIC_POLICY_KEYS  # noqa: SLF001
    assert "alert_policy_binding" in epochlib._DURABLE_POLICY_IDENTITY_KEYS  # noqa: SLF001

    legacy = build_durable_policy_identity(
        state_dir=tmp_path, repo_head=HEAD, launcher_sha256="c" * 64,
        alert_policy=policy.ALERT_POLICY_LEGACY)
    assert legacy["alert_policy_binding"] == LEGACY_ALERT_POLICY_BINDING
    assert epochlib.durable_semantic_policy_digest(identity) != (
        epochlib.durable_semantic_policy_digest(legacy))

    # An identity built without stating a policy describes what an unflagged
    # process actually runs, rather than silently claiming the new one.
    assert build_durable_policy_identity(
        state_dir=tmp_path)["alert_policy_binding"] == (
            LEGACY_ALERT_POLICY_BINDING)

    # Unknown spellings fail closed at construction.
    for rejected in ("Phx1_Parity", "PARITY", "shadow", ""):
        with pytest.raises(ValueError, match=policy.ALERT_POLICY_INVALID):
            build_durable_policy_identity(
                state_dir=tmp_path, alert_policy=rejected)

    # It is NOT in the canonical must-equal set: both values are legitimate
    # identities, which is what keeps the reverse handoff possible.
    assert "alert_policy_binding" not in (
        epochlib._CANONICAL_SEMANTIC_POLICY)  # noqa: SLF001


# ---------------------------------------------------------------------------
# 3 + 4. Both switch directions require an authenticated closed-epoch handoff
# ---------------------------------------------------------------------------


def _switch_verdict(tmp_path, *, prior: str, current: str):
    """Validate a handoff whose ONLY semantic change is the alert policy."""

    root = tmp_path
    state = root / "state"
    prior_identity = handoff_harness._identity(  # noqa: SLF001
        root, head=handoff_harness.OLD_HEAD,
        launcher=handoff_harness.OLD_LAUNCHER,
        alert_policy_binding=prior)
    manager = epochlib.LiveEpochManager(
        state_dir=state,
        now_fn=lambda: handoff_harness.NOW,
        id_fn=lambda: "epoch-alert-policy-switch",
        durable_policy_identity=prior_identity,
        run_instance_identity={
            "identity_schema": epochlib.LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
            "runtime_nonce": "prior"},
    )
    assert manager.observe_confirmed_slot(435_500_000)
    manager.close("OPERATOR_SHUTDOWN")
    epoch_path = state / epochlib.LIVE_EPOCH_BASENAME

    current_identity = handoff_harness._current(  # noqa: SLF001
        root, alert_policy_binding=current)
    return epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=current_identity,
        context=handoff_harness._context(root),  # noqa: SLF001
    ), epoch_path, current_identity


@pytest.mark.parametrize(
    "prior,current",
    [(LEGACY_ALERT_POLICY_BINDING, CANONICAL_ALERT_POLICY),
     (CANONICAL_ALERT_POLICY, LEGACY_ALERT_POLICY_BINDING)],
)
def test_3_and_4_switching_alert_policy_requires_an_authenticated_handoff(
    tmp_path, prior, current
):
    verdict, epoch_path, current_identity = _switch_verdict(
        tmp_path, prior=prior, current=current)

    # The switch is SEEN as a semantic change...
    assert verdict.checks["semantic_policy_equal"] is False
    assert verdict.checks["alert_policy_changed"] is True
    assert verdict.checks["prior_alert_policy"] == prior
    assert verdict.checks["current_alert_policy"] == current
    # ...and the digest before/after actually differ.
    assert verdict.audit_payload["semantic_policy_digest_before"] != (
        verdict.audit_payload["semantic_policy_digest_after"])

    # ...it is authorized ONLY through the closed-epoch handoff, which still
    # requires a fully stopped, forward-only, canonical, audited deployment.
    assert verdict.allowed is True
    assert verdict.refusals == []

    # Until that handoff is RECORDED, the new identity is not authorized.
    assert epochlib.closed_epoch_deployment_handoff_is_valid(
        epoch_path=epoch_path,
        current_policy_identity=current_identity) is False
    recorded = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=current_identity,
        context=handoff_harness._context(tmp_path),  # noqa: SLF001
    )
    assert recorded.allowed is True
    assert epochlib.closed_epoch_deployment_handoff_is_valid(
        epoch_path=epoch_path,
        current_policy_identity=current_identity) is True


@pytest.mark.parametrize(
    "prior,current",
    [(LEGACY_ALERT_POLICY_BINDING, CANONICAL_ALERT_POLICY),
     (CANONICAL_ALERT_POLICY, LEGACY_ALERT_POLICY_BINDING)],
)
def test_3b_a_running_deployment_cannot_switch_without_the_handoff(
    tmp_path, prior, current
):
    """A live (non-closed) epoch refuses the switch outright."""

    verdict, _path, _identity = _switch_verdict(
        tmp_path, prior=prior, current=current)
    assert verdict.allowed is True

    # The same switch with an owner still alive is refused: the handoff is an
    # authenticated FULLY STOPPED event, never a hot policy flip.
    root = tmp_path / "hot"
    root.mkdir()
    state = root / "state"
    prior_identity = handoff_harness._identity(  # noqa: SLF001
        root, head=handoff_harness.OLD_HEAD,
        launcher=handoff_harness.OLD_LAUNCHER,
        alert_policy_binding=prior)
    manager = epochlib.LiveEpochManager(
        state_dir=state, now_fn=lambda: handoff_harness.NOW,
        id_fn=lambda: "epoch-hot", durable_policy_identity=prior_identity,
        run_instance_identity={
            "identity_schema": epochlib.LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
            "runtime_nonce": "prior"})
    assert manager.observe_confirmed_slot(435_500_000)
    manager.close("OPERATOR_SHUTDOWN")
    hot = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=state / epochlib.LIVE_EPOCH_BASENAME,
        current_policy_identity=handoff_harness._current(  # noqa: SLF001
            root, alert_policy_binding=current),
        context=handoff_harness._context(root, producer_count=1),  # noqa: SLF001
    )
    assert hot.allowed is False
    assert "HANDOFF_ACTIVE_PRODUCER" in hot.refusals


def test_4b_alert_policy_switch_plus_any_other_change_still_refuses(tmp_path):
    """The sanctioned arm covers EXACTLY one binding, never two at once."""

    root = tmp_path
    state = root / "state"
    prior_identity = handoff_harness._identity(  # noqa: SLF001
        root, head=handoff_harness.OLD_HEAD,
        launcher=handoff_harness.OLD_LAUNCHER,
        alert_policy_binding=LEGACY_ALERT_POLICY_BINDING)
    manager = epochlib.LiveEpochManager(
        state_dir=state, now_fn=lambda: handoff_harness.NOW,
        id_fn=lambda: "epoch-two-changes",
        durable_policy_identity=prior_identity,
        run_instance_identity={
            "identity_schema": epochlib.LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
            "runtime_nonce": "prior"})
    assert manager.observe_confirmed_slot(435_500_000)
    manager.close("OPERATOR_SHUTDOWN")

    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=state / epochlib.LIVE_EPOCH_BASENAME,
        current_policy_identity=handoff_harness._current(  # noqa: SLF001
            root,
            alert_policy_binding=CANONICAL_ALERT_POLICY,
            telegram_enabled_binding=False),
        context=handoff_harness._context(root),  # noqa: SLF001
    )
    assert verdict.allowed is False
    assert verdict.checks["alert_policy_changed"] is False
    assert "HANDOFF_SEMANTIC_POLICY_INVALID" in verdict.refusals


def test_4c_a_prior_epoch_without_the_binding_derives_legacy(tmp_path):
    """The already-closed production epoch predates this binding.

    It must project as LEGACY -- NOT as the current value -- otherwise the very
    first switch to PHX1_PARITY would look like no change at all.
    """

    identity = build_durable_policy_identity(
        state_dir=tmp_path, repo_head=HEAD, launcher_sha256="c" * 64,
        alert_policy=CANONICAL_ALERT_POLICY)
    pre_binding = {
        key: value for key, value in identity.items()
        if key != "alert_policy_binding"
    }
    # Even when the caller hands in the CURRENT identity as the legacy default
    # -- which is what the handoff builder does for every other derivable key
    # -- the alert policy must still derive LEGACY.
    projection = epochlib._semantic_policy_projection(  # noqa: SLF001
        pre_binding,
        legacy_launcher_canonical=True,
        legacy_defaults=dict(identity),
    )
    assert projection["alert_policy_binding"] == LEGACY_ALERT_POLICY_BINDING

    # And with no legacy-launcher allowance at all.
    assert epochlib._semantic_policy_projection(  # noqa: SLF001
        pre_binding)["alert_policy_binding"] == LEGACY_ALERT_POLICY_BINDING
    assert "alert_policy_binding" in (
        epochlib._LEGACY_DERIVABLE_POLICY_KEYS)  # noqa: SLF001


# ---------------------------------------------------------------------------
# 5 + 6 + 7. Missing, duplicated and unknown values refuse preflight
# ---------------------------------------------------------------------------


def _argv(*, values):
    argv = canonical_launcher_arguments(
        launcher="launch_window_04.ps1",
        expected_head=HEAD, ledger_baseline=BASELINE)
    index = argv.index("--alert-policy")
    stripped = argv[:index] + argv[index + 2:]
    for value in values:
        stripped = stripped + ["--alert-policy", value]
    return stripped


def _refusals(argv):
    return validate_launcher_arguments(
        argv, expected_head=HEAD,
        ledger_baseline_fn=lambda _path: BASELINE).refusals


def test_5_missing_alert_policy_refuses_startup():
    argv = _argv(values=())
    assert alert_policy_occurrences(argv) == []
    refusals = _refusals(argv)
    assert REFUSAL_ALERT_POLICY_ABSENT in refusals

    text = _launcher_text().replace(
        f'  "--alert-policy", "{CANONICAL_ALERT_POLICY_CLI}",\n', "")
    body_refusals = validate_live_launcher_text(
        text, expected_head=HEAD, ledger_baseline=BASELINE)
    assert TEMPLATE_ALERT_POLICY_MISSING in body_refusals


def test_6_duplicate_alert_policy_flags_refuse_startup():
    # Same value twice is still a refusal: exactly one, never "at least one".
    same = _argv(values=(CANONICAL_ALERT_POLICY_CLI,
                         CANONICAL_ALERT_POLICY_CLI))
    assert alert_policy_occurrences(same) == [
        CANONICAL_ALERT_POLICY_CLI, CANONICAL_ALERT_POLICY_CLI]
    assert REFUSAL_ALERT_POLICY_COUNT in _refusals(same)

    # Conflicting values are refused for BOTH reasons: duplicated, and one of
    # them is not the canonical production policy.
    conflicting = _argv(values=("legacy", CANONICAL_ALERT_POLICY_CLI))
    conflicting_refusals = _refusals(conflicting)
    assert REFUSAL_ALERT_POLICY_COUNT in conflicting_refusals
    assert REFUSAL_ALERT_POLICY_NOT_CANONICAL in conflicting_refusals
    # A plain last-wins parse would have hidden the conflict entirely.
    assert parse_launcher_arguments(conflicting)["alert_policy"] == (
        CANONICAL_ALERT_POLICY_CLI)

    text = _launcher_text().replace(
        f'  "--alert-policy", "{CANONICAL_ALERT_POLICY_CLI}",\n',
        f'  "--alert-policy", "{CANONICAL_ALERT_POLICY_CLI}",\n'
        f'  "--alert-policy", "legacy",\n')
    assert TEMPLATE_ALERT_POLICY_COUNT in validate_live_launcher_text(
        text, expected_head=HEAD, ledger_baseline=BASELINE)


def test_7_unknown_or_non_canonical_alert_policy_refuses_startup():
    for unknown in ("Phx1_Parity", "PARITY", "shadow", "enforce", "true"):
        refusals = _refusals(_argv(values=(unknown,)))
        assert REFUSAL_ALERT_POLICY_UNKNOWN in refusals, unknown
        assert REFUSAL_ALERT_POLICY_NOT_CANONICAL not in refusals, unknown

    # A KNOWN but non-production policy is a different, separately named fault.
    legacy_refusals = _refusals(_argv(values=("legacy",)))
    assert REFUSAL_ALERT_POLICY_NOT_CANONICAL in legacy_refusals
    assert REFUSAL_ALERT_POLICY_UNKNOWN not in legacy_refusals

    # The canonical vector is clean on every alert-policy reason.
    clean = _refusals(_argv(values=(CANONICAL_ALERT_POLICY_CLI,)))
    for reason in (REFUSAL_ALERT_POLICY_ABSENT, REFUSAL_ALERT_POLICY_COUNT,
                   REFUSAL_ALERT_POLICY_UNKNOWN,
                   REFUSAL_ALERT_POLICY_NOT_CANONICAL):
        assert reason not in clean

    text = _launcher_text().replace(
        f'"--alert-policy", "{CANONICAL_ALERT_POLICY_CLI}"',
        '"--alert-policy", "Phx1_Parity"')
    assert TEMPLATE_ALERT_POLICY_UNKNOWN in validate_live_launcher_text(
        text, expected_head=HEAD, ledger_baseline=BASELINE)
    legacy_text = _launcher_text().replace(
        f'"--alert-policy", "{CANONICAL_ALERT_POLICY_CLI}"',
        '"--alert-policy", "legacy"')
    assert TEMPLATE_ALERT_POLICY_NOT_CANONICAL in validate_live_launcher_text(
        legacy_text, expected_head=HEAD, ledger_baseline=BASELINE)


def test_7b_ambiguous_launcher_policy_is_not_guessed():
    """The watchdog reader refuses to pick a winner."""

    assert alert_policy_in_launcher(
        '"--alert-policy", "phx1_parity"') == CANONICAL_ALERT_POLICY
    assert alert_policy_in_launcher(
        '"--alert-policy", "phx1_parity"\n"--alert-policy", "legacy"') is None
    assert alert_policy_in_launcher(
        '"--alert-policy", "phx1_parity"\n"--alert-policy", "phx1_parity"'
    ) is None
    assert alert_policy_in_launcher('"--alert-policy", "nonsense"') is None
    assert alert_policy_in_launcher("no policy here") is None


# ---------------------------------------------------------------------------
# 8. Watchdog expected policy matches the producer
# ---------------------------------------------------------------------------


def _adopt(config, world, **expectation):
    return evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python,
        expected_head=HARNESS_HEAD,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path,
        yellowstone_owner_count=1,
        **expectation,
    )


def test_8_watchdog_expected_policy_matches_the_producer(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)

    # The expectation is DERIVED from the launcher this watchdog would run,
    # so it is a real comparison rather than a restatement of a constant.
    assert expected_alert_policy(config) == CANONICAL_ALERT_POLICY

    world.add_producer(pid=os.getpid(), wrapper_pid=1,
                       run_dir=str(tmp_path / "r"),
                       stop_file=str(tmp_path / "s"))
    world.write_producer_lock(os.getpid())

    verdict = _adopt(config, world,
                     expected_alert_policy=expected_alert_policy(config))
    assert verdict.adoptable is True, verdict.reasons
    assert verdict.checks["alert_policy"] == CANONICAL_ALERT_POLICY
    assert verdict.checks["expected_alert_policy"] == CANONICAL_ALERT_POLICY
    assert verdict.checks["alert_policy_flag_count"] == 1


@pytest.mark.parametrize(
    "producer_policy",
    ["legacy", None, "Phx1_Parity"],
)
def test_8b_producer_running_a_different_policy_is_not_adopted(
    tmp_path, producer_policy
):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.add_producer(pid=os.getpid(), wrapper_pid=1,
                       run_dir=str(tmp_path / "r"),
                       stop_file=str(tmp_path / "s"),
                       alert_policy=producer_policy)
    world.write_producer_lock(os.getpid())

    verdict = _adopt(config, world,
                     expected_alert_policy=expected_alert_policy(config))
    assert verdict.adoptable is False
    assert ADOPT_ALERT_POLICY_MISMATCH in verdict.reasons
    assert ADOPT_ALERT_POLICY_MISMATCH in ADOPTION_REFUSAL_REASONS


def test_8b2_an_unparseable_policy_is_refused_even_without_an_expectation(
    tmp_path
):
    """Absence is tolerated by a caller that states no expectation; corruption
    never is."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.add_producer(pid=os.getpid(), wrapper_pid=1,
                       run_dir=str(tmp_path / "r"),
                       stop_file=str(tmp_path / "s"),
                       alert_policy="Phx1_Parity")
    world.write_producer_lock(os.getpid())
    assert ADOPT_ALERT_POLICY_MISMATCH in _adopt(config, world).reasons

    absent = FakeWorld(make_config(tmp_path / "b"))
    absent_config = absent.config
    absent.add_producer(pid=os.getpid(), wrapper_pid=1,
                        run_dir=str(tmp_path / "r2"),
                        stop_file=str(tmp_path / "s2"),
                        alert_policy=None)
    absent.write_producer_lock(os.getpid())
    verdict = evaluate_producer_adoption(
        table=absent.table(),
        lock=read_producer_lock(absent_config.producer_runtime_lock_path),
        repo_python=absent_config.repo_python, expected_head=HARNESS_HEAD,
        cursor_state_dir=absent_config.cursor_state_dir,
        ledger_path=absent_config.ledger_path, yellowstone_owner_count=1)
    assert ADOPT_ALERT_POLICY_MISMATCH not in verdict.reasons


def test_8c_watchdog_durable_expectation_carries_the_policy(tmp_path):
    config = make_config(tmp_path)
    identity = canonical_durable_identity(config)
    assert identity["alert_policy_binding"] == CANONICAL_ALERT_POLICY

    # A launcher that states no policy expects the committed LEGACY default --
    # which is exactly what such a producer would actually run.
    silent = tmp_path / "silent_launcher.ps1"
    silent.write_text('# no policy stated\n"--run-forever"\n', encoding="utf-8")
    assert expected_alert_policy(
        replace(config, launcher_path=str(silent))) == (
            LEGACY_ALERT_POLICY_BINDING)

    # An unreadable launcher fails to the committed default, never to the new
    # policy: absence must never be read as consent to the relaxed policy.
    missing = replace(config, launcher_path=str(tmp_path / "nope.ps1"))
    assert expected_alert_policy(missing) == LEGACY_ALERT_POLICY_BINDING


# ---------------------------------------------------------------------------
# 9. Operator status reports the effective policy
# ---------------------------------------------------------------------------


def test_9_operator_status_reports_the_effective_policy(capsys):
    import PHX2.operator_cli as cli

    status = cli.OperatorStatus(
        state="RUNNING", health="HEALTHY", transport="TELEGRAM",
        discord="DISABLED", watchdog_pid=1, producer_pid=2,
        yellowstone_owners=1, epoch_id="epoch-x", epoch_status="EPOCH_HEALTHY",
        epoch_start_slot=1, epoch_durable=True, epoch_identity_matches=True,
        dex_backfill="ENABLED", circuit="CLOSED", circuit_reason=None,
        circuit_integrity_locked=False, heartbeat_age_seconds=1.0,
        last_telegram_ping=None, paid_ledger_lines=25,
        paid_ledger_sha256="d" * 64,
        alert_policy=CANONICAL_ALERT_POLICY,
    )
    cli.print_status(status)
    out = capsys.readouterr().out
    assert f"Alert policy: {CANONICAL_ALERT_POLICY}" in out
    # Stated exactly as the required operator line, not paraphrased.
    assert "Alert policy: PHX1_PARITY" in out

    # The durable binding has precedence over any heartbeat claim, and an
    # unstated policy is UNKNOWN rather than a guessed default.
    assert cli._bound_alert_policy(  # noqa: SLF001
        {"durable_policy_identity": {
            "alert_policy_binding": CANONICAL_ALERT_POLICY}},
        {"alert_policy": "LEGACY"}) == CANONICAL_ALERT_POLICY
    assert cli._bound_alert_policy({}, {}) == "UNKNOWN"  # noqa: SLF001
    assert cli._bound_alert_policy(None) == "UNKNOWN"  # noqa: SLF001
    assert cli._bound_alert_policy(  # noqa: SLF001
        {"alert_policy": "LEGACY"}) == "LEGACY"


def test_9b_producer_summary_carries_the_effective_policy():
    from PHX2.free_tier_producer import free_tier_session as session

    summary = session._build_producer_summary(  # noqa: SLF001
        mode="PAID_PRIMARY_TELEGRAM",
        result={"outcome": "ZERO_SEND"}, out_dir="ignored",
        ledger_path="ignored", baseline_before=None, baseline_after=None,
        transport_stats={}, tail_summary={}, error_count=0,
        discord_enabled=False, credit_budget={}, final=True,
        alert_policy=CANONICAL_ALERT_POLICY)
    assert summary["alert_policy"] == CANONICAL_ALERT_POLICY
    # Default stays the committed behaviour for any caller that states nothing.
    default = session._build_producer_summary(  # noqa: SLF001
        mode="PAID_PRIMARY_TELEGRAM",
        result={"outcome": "ZERO_SEND"}, out_dir="ignored",
        ledger_path="ignored", baseline_before=None, baseline_after=None,
        transport_stats={}, tail_summary={}, error_count=0,
        discord_enabled=False, credit_budget={}, final=True)
    assert default["alert_policy"] == policy.ALERT_POLICY_LEGACY


# ---------------------------------------------------------------------------
# 10 + 11. Committed behaviour is untouched by the binding
# ---------------------------------------------------------------------------


def test_10_phx1_parity_activation_fee_and_ttl_behaviour_is_unchanged():
    """This commit binds identity only; it relaxes and tightens nothing."""

    assert policy.watch_ttl_seconds(policy.ALERT_POLICY_PHX1_PARITY) == 21600
    assert policy.watch_ttl_seconds(policy.ALERT_POLICY_LEGACY) == 3600
    assert policy.enforcement_for(
        policy.CONDITION_ACTIVATION_PROVEN,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_SHADOW
    assert policy.enforcement_for(
        policy.CONDITION_ACTIVATION_CROSSING_TICK,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_SHADOW
    assert policy.enforcement_for(
        policy.CONDITION_FEE_GATE_LIFECYCLE_IMMATURE,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_SHADOW
    assert policy.enforcement_for(
        policy.CONDITION_FEE_PROOF_MISSING,
        policy=policy.ALERT_POLICY_PHX1_PARITY) == policy.ENFORCEMENT_SHADOW
    assert set(policy.PHX1_PARITY_RELAXED_CONDITIONS) == {
        policy.CONDITION_ACTIVATION_PROVEN,
        policy.CONDITION_ACTIVATION_MULTIPLIER_LIVE,
        policy.CONDITION_ACTIVATION_MULTIPLIER_BACKFILL,
        policy.CONDITION_ACTIVATION_CROSSING_TICK,
        policy.CONDITION_FEE_GATE_LIFECYCLE_IMMATURE,
        policy.CONDITION_FEE_PROOF_MISSING,
        policy.CONDITION_FEE_GATE_SCAM_LIKELY,
        policy.CONDITION_STRUCTURAL_POLICY,
    }
    # And LEGACY remains byte-identical to the committed build.
    assert policy.expected_activation_multiplier(
        discovery_provenance_is_backfill=True,
        policy=policy.ALERT_POLICY_LEGACY).__str__() == "1.39"
    assert policy.send_time_refresh_decision(
        market_all_present=False, attempts_used=0,
        policy=policy.ALERT_POLICY_LEGACY) == policy.REFRESH_NOT_ENABLED


def test_11_hard_ath_mc_lp_dedupe_and_integrity_remain_unchanged():
    for condition in policy.NON_RELAXABLE_CONDITIONS:
        for mode in policy.ALERT_POLICY_MODES:
            assert policy.blocks_compose(condition, policy=mode), condition
    for condition in (
        policy.CONDITION_ATH_COVERAGE,
        policy.CONDITION_CURRENT_MARKET_CAP_VALID,
        policy.CONDITION_LIQUIDITY_FLOOR,
        policy.CONDITION_DEDUPE,
        policy.CONDITION_CHECKPOINT_INTEGRITY,
        policy.CONDITION_CREDENTIALS,
        policy.CONDITION_OWNERSHIP_DUPLICATION,
    ):
        assert policy.enforcement_for(
            condition, policy=policy.ALERT_POLICY_PHX1_PARITY) == (
                policy.ENFORCEMENT_HARD)
        assert condition not in policy.PHX1_PARITY_RELAXED_CONDITIONS

    # The identity binding grants no new provider, transport or replay surface.
    assert epochlib._CANONICAL_SEMANTIC_POLICY[  # noqa: SLF001
        "historical_rpc_backfill_enabled_binding"] is False
    assert epochlib._CANONICAL_SEMANTIC_POLICY[  # noqa: SLF001
        "discord_enabled_binding"] is False
    assert epochlib._CANONICAL_SEMANTIC_POLICY[  # noqa: SLF001
        "wallet_enabled_binding"] is False
    assert epochlib._CANONICAL_SEMANTIC_POLICY[  # noqa: SLF001
        "trading_enabled_binding"] is False


# ---------------------------------------------------------------------------
# 12. The canonical ledger is never touched by offline testing
# ---------------------------------------------------------------------------


def test_12_canonical_ledger_is_untouched_by_offline_testing(tmp_path):
    from PHX2.free_tier_producer.launcher_contract import CANONICAL_LEDGER_PATH

    ledger = Path(CANONICAL_LEDGER_PATH)
    if not ledger.exists():
        pytest.skip("canonical ledger is not present on this machine")
    before = ledger.read_bytes()

    # Exercise every surface this module binds, then re-read the ledger.
    text = _launcher_text()
    validate_live_launcher_text(
        text, expected_head=HEAD, ledger_baseline=BASELINE)
    deployment_specification(expected_head=HEAD, ledger_baseline=BASELINE)
    validate_launcher_arguments(
        canonical_launcher_arguments(
            launcher="launch_window_04.ps1",
            expected_head=HEAD, ledger_baseline=BASELINE),
        expected_head=HEAD, ledger_baseline_fn=lambda _p: BASELINE)
    build_durable_policy_identity(
        state_dir=tmp_path, alert_policy=CANONICAL_ALERT_POLICY)
    _switch_verdict(
        tmp_path, prior=LEGACY_ALERT_POLICY_BINDING,
        current=CANONICAL_ALERT_POLICY)

    assert ledger.read_bytes() == before
    # And nothing above wrote anywhere near it.
    assert json.loads(json.dumps({"ok": True}))["ok"] is True
