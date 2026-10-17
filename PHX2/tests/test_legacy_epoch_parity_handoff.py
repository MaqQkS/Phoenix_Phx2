"""Adopting a PRE-alert-policy closed epoch into the PHX1_PARITY deployment.

2026-08-01.  ``python main.py start`` refused with
``HANDOFF_PRIOR_DEPLOYMENT_IDENTITY_INVALID``.  The closed production epoch was
written before ``alert_policy_binding`` existed, so the handoff's legacy-fill
gate demanded ``prior_launcher_canonical`` -- which re-renders the PRIOR repo
head with the CURRENT launcher template.  The very commit that introduced the
binding also added the ``--alert-policy`` lines to that template, so for
exactly the epochs the compatibility path exists to adopt, the re-render can
never reproduce the launcher hash that deployment actually ran.  The gate was
unsatisfiable, not unsatisfied.

What authenticates a pre-binding epoch instead is the digest-chained handoff
log: it recorded that launcher as canonical for that head back when the
renderer agreed, and it recorded a ``semantic_policy_digest_after`` computed
over the PRE-binding key set.  Reproducing that digest proves both that the
identity is byte-authentic and that it genuinely predates the binding.

Nothing here opens a socket, reaches RPC, or constructs a transport.  Every
path is under ``tmp_path``; the canonical ledger is never opened for write.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import PHX2.free_tier_producer.live_epoch as epochlib
import PHX2.tests.test_closed_epoch_deployment_handoff as handoff_harness
from PHX2.free_tier_producer.launcher_contract import CANONICAL_ALERT_POLICY
from PHX2.free_tier_producer.live_epoch import LEGACY_ALERT_POLICY_BINDING

OLD_HEAD = handoff_harness.OLD_HEAD
OLD_LAUNCHER = handoff_harness.OLD_LAUNCHER
NEW_HEAD = handoff_harness.NEW_HEAD
NEW_LAUNCHER = handoff_harness.NEW_LAUNCHER
NOW = handoff_harness.NOW


# --------------------------------------------------------------------------- #
# harness: a genuinely pre-binding closed epoch + the chain that armed it
# --------------------------------------------------------------------------- #


def _pre_binding_identity(root: Path, **changes):
    """The prior identity EXACTLY as the pre-binding code wrote it."""

    identity = handoff_harness._identity(  # noqa: SLF001
        root, head=OLD_HEAD, launcher=OLD_LAUNCHER, **changes)
    identity.pop("alert_policy_binding")
    return identity


def _chain_record(
    *,
    generation: int,
    previous_digest,
    new_repository_head: str,
    new_launcher_sha256: str,
    semantic_policy_digest_after: str,
    schema_version: str = epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA,
    **overrides,
):
    """One ACCEPTED record shaped exactly like the production chain's."""

    payload = {
        "schema_version": schema_version,
        "event_type": epochlib.CLOSED_EPOCH_DEPLOYMENT_HANDOFF,
        "prior_epoch_id": f"epoch-chain-{generation}",
        "prior_epoch_generation": generation,
        "prior_epoch_document_digest": "0" * 64,
        "prior_epoch_file_sha256": "1" * 64,
        "prior_repository_head": "9" * 40,
        "prior_launcher_sha256": "9" * 64,
        "prior_closure_status": epochlib.EPOCH_CLOSED,
        "prior_closure_reason": "OPERATOR_SHUTDOWN",
        "new_repository_head": new_repository_head,
        "new_launcher_sha256": new_launcher_sha256,
        "new_policy_identity_digest": "2" * 64,
        "semantic_policy_digest_before": "3" * 64,
        "semantic_policy_digest_after": semantic_policy_digest_after,
        "state_directory_digest": "4" * 64,
        "cursor_state_directory_digest": "5" * 64,
        "canonical_ledger_path_digest": "6" * 64,
        "handoff_at_utc": NOW,
        "handoff_generation": generation,
        "previous_record_digest": previous_digest,
        "validation_outcome": "ACCEPTED",
    }
    if schema_version == epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2:
        payload.update({
            "prior_alert_policy": LEGACY_ALERT_POLICY_BINDING,
            "new_alert_policy": LEGACY_ALERT_POLICY_BINDING,
            "alert_policy_changed": False,
        })
    payload.update(overrides)
    digest = epochlib._digest(payload)  # noqa: SLF001
    return {**payload, "record_digest": digest}


def _write_chain(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = b"".join(
        epochlib._canonical(record) + b"\n"  # noqa: SLF001
        for record in records)
    path.write_bytes(body)


def _legacy_deployment(
    root: Path,
    *,
    identity=None,
    attested_launcher: str = OLD_LAUNCHER,
    attested_head: str = OLD_HEAD,
    attested_digest=None,
):
    """A closed pre-binding epoch plus the chain record that armed it."""

    prior_identity = identity if identity is not None else (
        _pre_binding_identity(root))
    state = root / "state"
    manager = epochlib.LiveEpochManager(
        state_dir=state,
        now_fn=lambda: NOW,
        id_fn=lambda: "epoch-legacy-prior",
        durable_policy_identity=prior_identity,
        run_instance_identity={
            "identity_schema": epochlib.LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
            "runtime_nonce": "prior"},
    )
    assert manager.observe_confirmed_slot(435_500_000)
    manager.close("OPERATOR_SHUTDOWN")
    epoch_path = state / epochlib.LIVE_EPOCH_BASENAME

    digest_after = (
        attested_digest if attested_digest is not None
        else epochlib.pre_alert_policy_semantic_digest(prior_identity))
    chain_path = epoch_path.with_name(
        epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME)
    first = _chain_record(
        generation=1, previous_digest=None,
        new_repository_head="8" * 40, new_launcher_sha256="8" * 64,
        semantic_policy_digest_after="7" * 64)
    second = _chain_record(
        generation=2, previous_digest=first["record_digest"],
        new_repository_head=attested_head,
        new_launcher_sha256=attested_launcher,
        semantic_policy_digest_after=digest_after)
    _write_chain(chain_path, [first, second])
    return epoch_path, chain_path, prior_identity


def _parity_current(root: Path, **changes):
    return handoff_harness._current(  # noqa: SLF001
        root, alert_policy_binding=CANONICAL_ALERT_POLICY, **changes)


def _legacy_context(root: Path, **changes):
    # The whole point: a genuinely pre-binding launcher CANNOT re-render, so
    # every test here runs with prior_launcher_canonical False.
    return handoff_harness._context(  # noqa: SLF001
        root, prior_launcher_canonical=False, **changes)


def _validate(root: Path, *, prior=None, current=None, context=None,
              **deployment):
    """``prior`` is the stored pre-binding identity; ``current`` the new."""

    epoch_path, chain_path, prior_identity = _legacy_deployment(
        root, identity=prior, **deployment)
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=(
            current if current is not None else _parity_current(root)),
        context=context or _legacy_context(root),
        handoff_path=chain_path,
    )
    return verdict, epoch_path, chain_path, prior_identity


# --------------------------------------------------------------------------- #
# 1 + 2.  The pre-binding epoch projects LEGACY and its identity validates
# --------------------------------------------------------------------------- #


def test_1_authentic_pre_binding_epoch_projects_legacy(tmp_path):
    identity = _pre_binding_identity(tmp_path)
    assert "alert_policy_binding" not in identity

    projection = epochlib._semantic_policy_projection(identity)  # noqa: SLF001
    assert projection["alert_policy_binding"] == LEGACY_ALERT_POLICY_BINDING

    verdict, _path, _chain, _identity = _validate(tmp_path)
    assert verdict.checks["prior_alert_policy"] == LEGACY_ALERT_POLICY_BINDING
    assert verdict.checks["current_alert_policy"] == CANONICAL_ALERT_POLICY


def test_2_pre_binding_prior_identity_validates(tmp_path):
    """The exact predicate that refused on 2026-08-01 now holds."""

    verdict, _path, _chain, _identity = _validate(tmp_path)
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID not in verdict.refusals
    assert verdict.checks["prior_predates_alert_policy_binding"] is True
    # ...and it holds WITHOUT the unsatisfiable re-render ever succeeding.
    assert verdict.checks["prior_launcher_canonical"] is False


# --------------------------------------------------------------------------- #
# 3 + 4 + 5.  One authenticated LEGACY -> PHX1_PARITY handoff
# --------------------------------------------------------------------------- #


def test_3_legacy_to_parity_requires_and_receives_the_handoff(tmp_path):
    verdict, epoch_path, chain_path, _identity = _validate(tmp_path)
    current = _parity_current(tmp_path)

    # Seen as a real semantic change, and permitted.
    assert verdict.checks["semantic_policy_equal"] is False
    assert verdict.checks["alert_policy_changed"] is True
    assert verdict.allowed is True
    assert verdict.refusals == []

    # ...but not AUTHORIZED until the handoff is actually recorded.
    assert epochlib.closed_epoch_deployment_handoff_is_valid(
        epoch_path=epoch_path, current_policy_identity=current,
        handoff_path=chain_path) is False
    recorded = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=epoch_path, current_policy_identity=current,
        context=_legacy_context(tmp_path), handoff_path=chain_path)
    assert recorded.allowed is True
    assert epochlib.closed_epoch_deployment_handoff_is_valid(
        epoch_path=epoch_path, current_policy_identity=current,
        handoff_path=chain_path) is True


def test_4_the_recorded_handoff_states_alert_policy_changed(tmp_path):
    verdict, epoch_path, chain_path, _identity = _validate(tmp_path)
    assert verdict.audit_payload["alert_policy_changed"] is True
    assert verdict.audit_payload["prior_alert_policy"] == (
        LEGACY_ALERT_POLICY_BINDING)
    assert verdict.audit_payload["new_alert_policy"] == CANONICAL_ALERT_POLICY

    epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=_parity_current(tmp_path),
        context=_legacy_context(tmp_path), handoff_path=chain_path)
    written = json.loads(
        chain_path.read_text(encoding="utf-8").splitlines()[-1])
    assert written["schema_version"] == (
        epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2)
    assert written["alert_policy_changed"] is True
    assert written["prior_alert_policy"] == LEGACY_ALERT_POLICY_BINDING
    assert written["new_alert_policy"] == CANONICAL_ALERT_POLICY
    # The v1 records it was appended to stay valid and unrewritten.
    state, records, _ = epochlib.classify_deployment_handoff_log(chain_path)
    assert state == "VALID"
    assert [item["schema_version"] for item in records] == [
        epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA,
        epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA,
        epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2,
    ]


def test_5_the_new_durable_identity_binds_phx1_parity(tmp_path):
    _verdict, epoch_path, chain_path, _identity = _validate(tmp_path)
    current = _parity_current(tmp_path)
    epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=epoch_path, current_policy_identity=current,
        context=_legacy_context(tmp_path), handoff_path=chain_path)

    manager = epochlib.LiveEpochManager(
        state_dir=epoch_path.parent,
        now_fn=lambda: NOW,
        id_fn=lambda: "epoch-parity-armed",
        durable_policy_identity=current,
        run_instance_identity={
            "identity_schema": epochlib.LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
            "runtime_nonce": "new"},
    )
    snapshot = manager.snapshot()
    assert snapshot["durable_policy_identity"]["alert_policy_binding"] == (
        CANONICAL_ALERT_POLICY)
    assert snapshot["deployment_handoff"]["schema_version"] == (
        epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2)


def test_6_parity_back_to_legacy_is_still_handoff_gated(tmp_path):
    """The reverse direction stays a semantic change, never a silent flip."""

    root = tmp_path
    state = root / "state"
    prior = handoff_harness._identity(  # noqa: SLF001
        root, head=OLD_HEAD, launcher=OLD_LAUNCHER,
        alert_policy_binding=CANONICAL_ALERT_POLICY)
    manager = epochlib.LiveEpochManager(
        state_dir=state, now_fn=lambda: NOW,
        id_fn=lambda: "epoch-parity-prior",
        durable_policy_identity=prior,
        run_instance_identity={
            "identity_schema": epochlib.LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
            "runtime_nonce": "prior"})
    assert manager.observe_confirmed_slot(435_500_000)
    manager.close("OPERATOR_SHUTDOWN")

    reverse = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=state / epochlib.LIVE_EPOCH_BASENAME,
        current_policy_identity=handoff_harness._current(  # noqa: SLF001
            root, alert_policy_binding=LEGACY_ALERT_POLICY_BINDING),
        context=handoff_harness._context(root),  # noqa: SLF001
    )
    assert reverse.checks["alert_policy_changed"] is True
    assert reverse.checks["semantic_policy_equal"] is False
    assert reverse.allowed is True
    assert reverse.audit_payload["prior_alert_policy"] == (
        CANONICAL_ALERT_POLICY)
    assert reverse.audit_payload["new_alert_policy"] == (
        LEGACY_ALERT_POLICY_BINDING)
    assert reverse.audit_payload["alert_policy_changed"] is True

    # A LIVE owner still refuses it outright.
    hot = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=state / epochlib.LIVE_EPOCH_BASENAME,
        current_policy_identity=handoff_harness._current(  # noqa: SLF001
            root, alert_policy_binding=LEGACY_ALERT_POLICY_BINDING),
        context=handoff_harness._context(  # noqa: SLF001
            root, producer_count=1),
    )
    assert hot.allowed is False
    assert epochlib.HANDOFF_ACTIVE_PRODUCER in hot.refusals


# --------------------------------------------------------------------------- #
# 7 - 12.  Forged, corrupt and modern prior identities all still refuse
# --------------------------------------------------------------------------- #


def test_7_missing_prior_head_still_refuses(tmp_path):
    identity = _pre_binding_identity(tmp_path)
    identity["repo_head_binding"] = None
    verdict, _p, _c, _i = _validate(tmp_path, prior=identity)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals
    assert verdict.checks["prior_predates_alert_policy_binding"] is False


def test_8_incorrect_prior_launcher_hash_still_refuses(tmp_path):
    """The chain attests ONE launcher per head; a different one refuses."""

    verdict, _p, _c, _i = _validate(
        tmp_path, attested_launcher="d" * 64)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals
    assert verdict.checks["prior_predates_alert_policy_binding"] is False


def test_8b_a_newer_record_for_the_same_head_wins(tmp_path):
    """Most-recent-wins: an old record cannot re-authorize a re-armed head."""

    epoch_path, chain_path, prior_identity = _legacy_deployment(tmp_path)
    state, records, _ = epochlib.classify_deployment_handoff_log(chain_path)
    assert state == "VALID"
    superseding = _chain_record(
        generation=3, previous_digest=records[-1]["record_digest"],
        new_repository_head=OLD_HEAD, new_launcher_sha256="e" * 64,
        semantic_policy_digest_after="f" * 64)
    _write_chain(chain_path, [*records, superseding])

    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=_parity_current(tmp_path),
        context=_legacy_context(tmp_path), handoff_path=chain_path)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals


def test_9_altered_prior_chain_manifest_still_refuses(tmp_path):
    """Editing the attested record without re-digesting breaks the chain."""

    epoch_path, chain_path, _identity = _legacy_deployment(tmp_path)
    lines = chain_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[-1])
    tampered["new_launcher_sha256"] = "d" * 64
    lines[-1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    chain_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert epochlib.classify_deployment_handoff_log(chain_path)[0] == "INVALID"
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=_parity_current(tmp_path),
        context=_legacy_context(tmp_path), handoff_path=chain_path)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_AUDIT_LOG_INVALID in verdict.refusals
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals


def test_9b_altered_prior_epoch_document_still_refuses(tmp_path):
    epoch_path, chain_path, _identity = _legacy_deployment(tmp_path)
    document = json.loads(epoch_path.read_text(encoding="utf-8"))
    document["epoch_start_slot"] = 1
    epoch_path.write_text(json.dumps(document), encoding="utf-8")
    epoch_path.with_name(
        epoch_path.name + epochlib.LIVE_EPOCH_BACKUP_SUFFIX).unlink(
            missing_ok=True)

    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=_parity_current(tmp_path),
        context=_legacy_context(tmp_path), handoff_path=chain_path)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_DOCUMENT_INVALID in verdict.refusals


def test_10_corrupt_prior_semantic_digest_still_refuses(tmp_path):
    """A semantic field that no longer reproduces the attested digest."""

    verdict, _p, _c, _i = _validate(tmp_path, attested_digest="a" * 64)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals
    assert verdict.checks["prior_predates_alert_policy_binding"] is False


def test_10b_a_tampered_semantic_field_breaks_the_attestation(tmp_path):
    identity = _pre_binding_identity(tmp_path)
    attested = epochlib.pre_alert_policy_semantic_digest(identity)
    identity["telegram_enabled_binding"] = False
    verdict, _p, _c, _i = _validate(
        tmp_path, prior=identity, attested_digest=attested)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals


def test_11_unknown_prior_policy_remains_refused(tmp_path):
    """An identity STATING a policy outside the closed set is not legacy."""

    identity = handoff_harness._identity(  # noqa: SLF001
        tmp_path, head=OLD_HEAD, launcher=OLD_LAUNCHER,
        alert_policy_binding="PHX1_PARITY_RELAXED")
    verdict, _p, _c, _i = _validate(tmp_path, prior=identity)
    assert verdict.allowed is False
    assert verdict.checks["alert_policy_changed"] is False
    assert epochlib.HANDOFF_SEMANTIC_POLICY_CHANGED in verdict.refusals
    # It is NOT laundered through the pre-binding path either.
    assert verdict.checks["prior_predates_alert_policy_binding"] is False


def test_11b_an_unknown_policy_in_a_v2_chain_record_is_refused(tmp_path):
    epoch_path, chain_path, _identity = _legacy_deployment(tmp_path)
    forged = _chain_record(
        generation=2, previous_digest=json.loads(
            chain_path.read_text(encoding="utf-8").splitlines()[0]
        )["record_digest"],
        new_repository_head=OLD_HEAD, new_launcher_sha256=OLD_LAUNCHER,
        semantic_policy_digest_after="b" * 64,
        schema_version=epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2,
        prior_alert_policy="NOT_A_POLICY", new_alert_policy="LEGACY",
        alert_policy_changed=True)
    lines = chain_path.read_text(encoding="utf-8").splitlines()
    chain_path.write_bytes(
        lines[0].encode("utf-8") + b"\n"
        + epochlib._canonical(forged) + b"\n")  # noqa: SLF001
    assert epochlib.classify_deployment_handoff_log(chain_path)[0] == "INVALID"


def test_11c_a_v2_record_cannot_claim_no_change_between_two_policies(tmp_path):
    _epoch, chain_path, _identity = _legacy_deployment(tmp_path)
    lying = _chain_record(
        generation=1, previous_digest=None,
        new_repository_head=OLD_HEAD, new_launcher_sha256=OLD_LAUNCHER,
        semantic_policy_digest_after="b" * 64,
        schema_version=epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_SCHEMA_V2,
        prior_alert_policy=LEGACY_ALERT_POLICY_BINDING,
        new_alert_policy=CANONICAL_ALERT_POLICY,
        alert_policy_changed=False)
    _write_chain(chain_path, [lying])
    assert epochlib.classify_deployment_handoff_log(chain_path)[0] == "INVALID"


def test_12_a_modern_epoch_missing_the_binding_is_refused(tmp_path):
    """Stripping the field from a POST-binding epoch is tampering, not history.

    Its attested digest was computed WITH the alert policy, so the pre-binding
    recomputation cannot reproduce it and the compatibility path never opens.
    """

    modern = handoff_harness._identity(  # noqa: SLF001
        tmp_path, head=OLD_HEAD, launcher=OLD_LAUNCHER,
        alert_policy_binding=CANONICAL_ALERT_POLICY)
    modern_digest = epochlib.durable_semantic_policy_digest(modern)
    stripped = dict(modern)
    stripped.pop("alert_policy_binding")

    verdict, _p, _c, _i = _validate(
        tmp_path, prior=stripped, attested_digest=modern_digest)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals
    assert verdict.checks["prior_predates_alert_policy_binding"] is False


def test_12b_arbitrary_missing_fields_are_not_projected(tmp_path):
    """Only the EXACT pre-binding shape qualifies; extra omissions refuse."""

    identity = _pre_binding_identity(tmp_path)
    identity.pop("trading_enabled_binding")
    verdict, _p, _c, _i = _validate(tmp_path, prior=identity)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals
    assert verdict.checks["prior_predates_alert_policy_binding"] is False


def test_12c_an_unknown_extra_field_refuses(tmp_path):
    identity = _pre_binding_identity(tmp_path)
    identity["smuggled_binding"] = True
    verdict, _p, _c, _i = _validate(tmp_path, prior=identity)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals


def test_12d_a_missing_chain_cannot_attest_anything(tmp_path):
    epoch_path, chain_path, _identity = _legacy_deployment(tmp_path)
    chain_path.unlink()
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=_parity_current(tmp_path),
        context=_legacy_context(tmp_path), handoff_path=chain_path)
    assert verdict.allowed is False
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in verdict.refusals


def test_13_no_unrelated_semantic_change_is_silently_authorized(tmp_path):
    """Adoption covers EXACTLY the alert policy, never a second binding."""

    # The adoption ALONE is allowed...
    verdict, _p, _c, _i = _validate(tmp_path)
    assert verdict.allowed is True
    assert verdict.checks["alert_policy_changed"] is True

    # ...now flip one more binding alongside the adoption.
    root = tmp_path / "two_changes"
    root.mkdir()
    epoch_path, chain_path, _identity = _legacy_deployment(root)
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=_parity_current(
            root, telegram_enabled_binding=False),
        context=_legacy_context(root), handoff_path=chain_path)
    assert verdict.allowed is False
    assert verdict.checks["alert_policy_changed"] is False
    assert epochlib.HANDOFF_SEMANTIC_POLICY_INVALID in verdict.refusals


# --------------------------------------------------------------------------- #
# 14 - 16.  The operator surfaces
# --------------------------------------------------------------------------- #


class _SafetyBackend:
    """Every OS-facing seam ``safety_check`` uses, all healthy and offline."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.verdict = None

    def git_clean_and_complete(self):
        return True, []

    def task_status(self):
        return {"task_present": True, "managed_schema_ok": True,
                "watchdog_exe_exists": True, "task_state": "Disabled"}

    def transport_valid(self):
        return True, None

    def helius_source_valid(self):
        return True, None

    def watchdog_snapshot(self):
        return {"circuit_status": "CLOSED", "status": {"observation": {}}}

    def process_table(self):
        return []

    def closed_epoch_deployment_handoff(self, *, record=False):
        return self.verdict


def _run_safety_check(tmp_path, monkeypatch, verdict):
    """``safety_check`` on a tmp config, with the handoff verdict injected."""

    import PHX2.operator_cli as cli

    backend = _SafetyBackend(tmp_path)
    backend.verdict = verdict
    monkeypatch.setattr(cli, "resolve_repo_head", lambda root: NEW_HEAD)
    # Only the epoch-identity arm is under test; every other gate is stubbed to
    # its healthy answer so a reason that DOES appear is attributable.
    monkeypatch.setattr(
        cli, "validate_watchdog_config",
        lambda config: type("V", (), {"refusals": []})())
    monkeypatch.setattr(
        cli, "ledger_identity", lambda path: {"parse_ok": True})
    monkeypatch.setattr(
        cli, "classify_cursor_checkpoint_file",
        lambda path: type("C", (), {"state": "MISSING"})())
    monkeypatch.setattr(
        cli, "classify_recovery_checkpoint_file",
        lambda path: type("R", (), {"state": "MISSING"})())
    monkeypatch.setattr(
        cli, "read_producer_lock",
        lambda path: type("L", (), {"present": False, "holder_pid": None})())
    monkeypatch.setattr(
        cli, "validate_live_launcher_text",
        lambda text, **kwargs: [])
    monkeypatch.setattr(
        cli, "render_live_launcher_bytes",
        lambda **kwargs: b"launcher")
    monkeypatch.setattr(cli, "pinned_head_in_launcher", lambda text: NEW_HEAD)
    monkeypatch.setattr(
        cli, "_pinned_ledger_baseline", lambda text: "b" * 64 + ":25:9164")

    launcher = tmp_path / "launch_live_24x7.ps1"
    launcher.write_bytes(b"launcher")
    config = type("Config", (), {
        "launcher_path": str(launcher),
        "cursor_state_dir": str(tmp_path / "state"),
        "ledger_path": str(tmp_path / "ledger" / "ping_dedupe.jsonl"),
        "live_epoch_primary_path": tmp_path / "state" / (
            epochlib.LIVE_EPOCH_BASENAME),
        "producer_runtime_lock_path": str(tmp_path / "runtime.lock"),
        "cursor_primary_path": str(tmp_path / "cursor.json"),
        "recovery_primary_path": str(tmp_path / "recovery.json"),
    })()
    monkeypatch.setattr(
        cli, "default_production_config", lambda *, expected_head: config)
    return cli.safety_check(backend)


def test_14_operator_safety_check_accepts_the_legacy_transition(
    tmp_path, monkeypatch
):
    """``safety_check`` stops adding the refusal and asks for the handoff."""

    epoch_path, chain_path, _identity = _legacy_deployment(tmp_path)
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=_parity_current(tmp_path),
        context=_legacy_context(tmp_path), handoff_path=chain_path)
    assert verdict.allowed is True

    safety = _run_safety_check(tmp_path, monkeypatch, verdict)
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID not in safety.reasons
    assert safety.reasons == []
    assert safety.safe is True
    # The transition is not waved through -- start must still RECORD it.
    assert safety.handoff_required is True


def test_14b_a_refused_handoff_still_surfaces_as_a_start_refusal(
    tmp_path, monkeypatch
):
    """The seam that now accepts the authentic case still refuses forgery."""

    verdict, _p, _c, _i = _validate(tmp_path, attested_launcher="d" * 64)
    assert verdict.allowed is False

    safety = _run_safety_check(tmp_path, monkeypatch, verdict)
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID in safety.reasons
    assert safety.safe is False
    assert safety.handoff_required is False


def test_15_operator_status_reports_parity_after_the_new_epoch_is_armed(
    tmp_path, capsys
):
    import PHX2.operator_cli as cli

    _verdict, epoch_path, chain_path, _identity = _validate(tmp_path)
    current = _parity_current(tmp_path)
    epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=epoch_path, current_policy_identity=current,
        context=_legacy_context(tmp_path), handoff_path=chain_path)
    manager = epochlib.LiveEpochManager(
        state_dir=epoch_path.parent, now_fn=lambda: NOW,
        id_fn=lambda: "epoch-parity-armed", durable_policy_identity=current,
        run_instance_identity={
            "identity_schema": epochlib.LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
            "runtime_nonce": "new"})
    armed = json.loads(epoch_path.read_text(encoding="utf-8"))
    assert manager.snapshot()["durable_policy_identity"][
        "alert_policy_binding"] == CANONICAL_ALERT_POLICY
    assert cli._bound_alert_policy(armed) == (  # noqa: SLF001
        CANONICAL_ALERT_POLICY)


def test_16_stopped_status_does_not_claim_identity_match_when_unknown(
    tmp_path,
):
    """The pre-binding epoch reports UNKNOWN, and never a false match."""

    import PHX2.operator_cli as cli

    epoch_path, _chain, prior_identity = _legacy_deployment(tmp_path)
    stopped = json.loads(epoch_path.read_text(encoding="utf-8"))
    assert "alert_policy_binding" not in stopped["durable_policy_identity"]
    assert cli._bound_alert_policy(stopped) == "UNKNOWN"  # noqa: SLF001

    # The durable identity is NOT equal to the canonical parity identity, so a
    # status that reported "identity matches" would be stating a falsehood.
    expected = epochlib.build_durable_policy_identity(
        state_dir=tmp_path / "state", cursor_state_dir=tmp_path / "state",
        canonical_ledger_path=tmp_path / "ledger" / "ping_dedupe.jsonl",
        repo_head=OLD_HEAD, launcher_sha256=OLD_LAUNCHER,
        alert_policy=CANONICAL_ALERT_POLICY)
    assert dict(prior_identity) != expected


# --------------------------------------------------------------------------- #
# 17 + 18.  Offline safety of this suite itself
# --------------------------------------------------------------------------- #


def test_17_canonical_ledger_is_untouched_by_these_tests(tmp_path):
    from PHX2.free_tier_producer.compat import build29_cap1_ledger as ledgerlib
    from PHX2.free_tier_producer.launcher_contract import CANONICAL_LEDGER_PATH

    before = ledgerlib.compute_baseline(CANONICAL_LEDGER_PATH)
    _validate(tmp_path)
    after = ledgerlib.compute_baseline(CANONICAL_LEDGER_PATH)
    assert before == after
    # Nothing this suite writes lives outside tmp_path.
    assert Path(CANONICAL_LEDGER_PATH) not in set(tmp_path.rglob("*"))


def test_18_no_socket_rpc_or_transport_is_constructed(tmp_path, monkeypatch):
    import socket

    def refuse(*args, **kwargs):
        raise AssertionError("offline test opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    verdict, _p, _c, _i = _validate(tmp_path)
    assert verdict.allowed is True


# --------------------------------------------------------------------------- #
# the exact production shape, replayed offline
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("prior_launcher_canonical", [False, True])
def test_the_2026_08_01_refusal_shape_is_accepted_either_way(
    tmp_path, prior_launcher_canonical
):
    """Adoption must not DEPEND on the re-render, nor be broken by it."""

    epoch_path, chain_path, _identity = _legacy_deployment(tmp_path)
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=_parity_current(tmp_path),
        context=handoff_harness._context(  # noqa: SLF001
            tmp_path, prior_launcher_canonical=prior_launcher_canonical),
        handoff_path=chain_path)
    assert verdict.allowed is True
    assert epochlib.HANDOFF_PRIOR_IDENTITY_INVALID not in verdict.refusals


def test_the_pre_binding_digest_is_not_the_modern_digest(tmp_path):
    """The two digests must differ, or requirement 12 would be vacuous."""

    identity = handoff_harness._identity(  # noqa: SLF001
        tmp_path, head=OLD_HEAD, launcher=OLD_LAUNCHER,
        alert_policy_binding=CANONICAL_ALERT_POLICY)
    assert epochlib.pre_alert_policy_semantic_digest(identity) != (
        epochlib.durable_semantic_policy_digest(identity))
    # And a LEGACY identity's modern digest is likewise distinct.
    legacy = dict(identity)
    legacy["alert_policy_binding"] = LEGACY_ALERT_POLICY_BINDING
    assert epochlib.pre_alert_policy_semantic_digest(legacy) != (
        epochlib.durable_semantic_policy_digest(legacy))
