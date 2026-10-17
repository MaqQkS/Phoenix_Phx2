from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from PHX2.paper_trading.config import default_config
from PHX2.scripts import phx2_paper_preflight as preflight


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("offline preflight attempted network access")
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(socket, "getaddrinfo", fail)


@pytest.fixture
def local_plan(tmp_path):
    source = tmp_path / "producer-run"
    source.mkdir()
    config = default_config().to_dict()
    for strategy in config["strategies"]:
        strategy["max_open_positions"] = 1
    config_path = tmp_path / "paper.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    args = preflight.build_parser().parse_args([
        "--repo", str(tmp_path), "--config", str(config_path),
        "--source-root", str(source), "--out-root", str(tmp_path / "paper-output"),
        "--run-id", "paper_canary_01", "--reviewed-head", "a" * 40,
        "--reviewed-source-sha256", "b" * 64, "--tail-capacity", "32",
        "--max-runtime-seconds", "600", "--max-market-requests", "100",
        "--helius-max-raw-bytes", "1000000", "--max-discovery-messages", "0",
        "--max-paper-messages", "0",
    ])
    identity = {"head": "a" * 40, "source_sha256": "b" * 64, "source_dirty": True}
    return args, identity


def run(local_plan):
    args, identity = local_plan
    return preflight.build_plan(args, identity=identity)


def test_valid_plan_stays_inactive_and_writes_nothing(local_plan):
    args, _ = local_plan
    before = sorted(str(p) for p in Path(args.repo).rglob("*"))
    plan = run(local_plan)
    assert plan["status"] == "LOCAL_PLAN_VALID_AWAITING_LIVE_AUTHORIZATION"
    assert not plan["activation_authorized"]
    assert not plan["network_allowed"]
    assert not plan["telegram_enabled"]
    assert not plan["credentials_loaded"]
    assert plan["processes_started"] == 0
    assert plan["inputs"]["empty_before_producer_start"]
    assert plan["paper_policy"]["initials_recovery_multiple"] == 1.35
    assert plan["ownership"]["telegram_default"] == "DURABLE_OUTBOX_ONLY"
    assert sorted(str(p) for p in Path(args.repo).rglob("*")) == before


@pytest.mark.parametrize("field,value,reason", [
    ("reviewed_head", None, "REVIEWED_HEAD_REQUIRED_OR_MISMATCH"),
    ("reviewed_head", "c" * 40, "REVIEWED_HEAD_REQUIRED_OR_MISMATCH"),
    ("reviewed_source_sha256", "c" * 64, "REVIEWED_SOURCE_DIGEST_REQUIRED_OR_MISMATCH"),
    ("run_id", "../escape", "STABLE_RUN_ID_INVALID"),
    ("run_id", "a/b", "STABLE_RUN_ID_INVALID"),
    ("run_id", "CON", "STABLE_RUN_ID_INVALID"),
    ("tail_capacity", 1, "PAPER_EXPOSURE_EXCEEDS_TAIL_CAPACITY"),
    ("tail_capacity", 0, "TAIL_CAPACITY_REQUIRED"),
    ("max_runtime_seconds", 0, "CANARY_RUNTIME_BUDGET_REQUIRED_1_TO_3600_SECONDS"),
    ("max_runtime_seconds", 3601, "CANARY_RUNTIME_BUDGET_REQUIRED_1_TO_3600_SECONDS"),
    ("max_market_requests", None, "MARKET_REQUEST_BUDGET_REQUIRED_1_TO_10000"),
    ("helius_max_raw_bytes", None, "HELIUS_BYTE_BUDGET_REQUIRED_1_TO_100000000"),
    ("max_paper_messages", 21, "SEPARATE_MESSAGE_BUDGETS_REQUIRED_DISCOVERY_0_TO_100_PAPER_0_TO_20"),
    ("max_discovery_messages", 1, "REVIEWED_PRIVATE_DESTINATION_ALIAS_REQUIRED"),
    ("destination_alias", "https://secret.example/key", "DESTINATION_ALIAS_INVALID"),
])
def test_missing_or_unsafe_decisions_fail_closed(local_plan, field, value, reason):
    setattr(local_plan[0], field, value)
    plan = run(local_plan)
    assert plan["status"] == "BLOCKED"
    assert reason in plan["reasons"]


def test_positive_message_plan_still_does_not_enable_delivery(local_plan):
    local_plan[0].max_paper_messages = 3
    local_plan[0].destination_alias = "private_reviewed_destination"
    plan = run(local_plan)
    assert not plan["reasons"]
    assert not plan["telegram_enabled"]
    assert plan["proposed_budgets"]["approval_state"] == "PENDING_SEPARATE_LIVE_AUTHORIZATION"
    assert not plan["inactive_runtime_option_map"]["paper"]["--enable-paper-telegram"]
    assert plan["inactive_runtime_option_map"]["paper"]["--max-paper-messages"] == 0
    assert "--max-sends-per-run" not in plan["inactive_runtime_option_map"]["producer"]


@pytest.mark.parametrize("layout", ["same", "output_child", "source_child"])
def test_source_output_overlap_refused(local_plan, layout):
    args = local_plan[0]
    source = Path(args.source_root)
    args.out_root = str(source if layout == "same" else source / "paper" if layout == "output_child" else source.parent)
    assert "INPUT_OUTPUT_OVERLAP" in run(local_plan)["reasons"]


def test_output_must_be_directory(local_plan):
    Path(local_plan[0].out_root).write_text("existing-file", encoding="utf-8")
    assert "PAPER_OUTPUT_MUST_BE_DIRECTORY" in run(local_plan)["reasons"]


def test_source_is_exact_allowed_direct_streams_only(local_plan):
    source = Path(local_plan[0].source_root)
    (source / "candidates").mkdir()
    (source / "candidates" / "token.jsonl").write_text("partial-record", encoding="utf-8")
    (source / "pricing_tail.jsonl").write_text("partial-record", encoding="utf-8")
    (source / "would_ping_records.jsonl").write_text("must-ignore", encoding="utf-8")
    (source / "candidates" / "nested").mkdir()
    (source / "candidates" / "nested" / "other.jsonl").write_text("must-ignore", encoding="utf-8")
    assert run(local_plan)["inputs"]["existing_stream_files"] == 2


@pytest.mark.parametrize("suffix", ["/*", "/**", "/Phoenix_Bot/data/bot.db", "/archive.db", "/.git"])
def test_unsafe_paths_fail_before_file_read(local_plan, suffix):
    local_plan[0].source_root += suffix
    plan = run(local_plan)
    assert plan["status"] == "BLOCKED"


def test_symlink_escape_refused(local_plan, monkeypatch):
    source = Path(local_plan[0].source_root)
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: True if p == source / "pricing_tail.jsonl" else original(p))
    assert "INPUT_PATH_ESCAPE" in run(local_plan)["reasons"]


@pytest.mark.parametrize("key,value", [
    ("initials_recovery_multiple", None), ("take_profit_pct", 0.35),
    ("runner_trailing_stop_pct", 0.25),
])
def test_real_config_must_match_recovery_policy(local_plan, key, value):
    path = Path(local_plan[0].config)
    config = json.loads(path.read_text(encoding="utf-8"))
    config["strategies"][0]["params"][key] = value
    path.write_text(json.dumps(config), encoding="utf-8")
    plan = run(local_plan)
    assert "BALA_RECOVERY_POLICY_MISMATCH" in plan["reasons"]
    assert not plan["paper_policy"]["policy_matches"]


def test_config_errors_never_echo_unknown_keys_values_or_paths(local_plan):
    path = Path(local_plan[0].config)
    path.write_text('{"DO_NOT_ECHO_SECRET": "NEVER_PRINT_VALUE"}', encoding="utf-8")
    output = json.dumps(run(local_plan))
    assert "PAPER_CONFIG_INVALID" in output
    assert "DO_NOT_ECHO_SECRET" not in output
    assert "NEVER_PRINT_VALUE" not in output
    assert str(path) not in output


def test_stop_file_blocks_future_plan(local_plan):
    args = local_plan[0]
    run_dir = Path(args.out_root) / args.run_id
    run_dir.mkdir(parents=True)
    (run_dir / "STOP").touch()
    assert "PAPER_STOP_FILE_PRESENT" in run(local_plan)["reasons"]


def test_digest_changes_for_untracked_source_and_deletion_but_excludes_secrets(tmp_path, monkeypatch):
    code = tmp_path / "PHX2" / "module.py"
    code.parent.mkdir()
    code.write_text("VALUE = 1\n", encoding="utf-8")
    secret = tmp_path / ".env"
    secret.write_text("must-not-be-hashed", encoding="utf-8")
    def fake_git(repo, *args):
        if args[0] == "rev-parse":
            return b"a" * 40 + b"\n"
        if args[0] == "ls-files":
            return b"PHX2/module.py\0.env\0"
        return b" M PHX2/module.py\0"
    monkeypatch.setattr(preflight, "_git", fake_git)
    first = preflight.code_identity(tmp_path)
    secret.write_text("changed-secret", encoding="utf-8")
    assert preflight.code_identity(tmp_path) == first
    code.write_text("VALUE = 2\n", encoding="utf-8")
    second = preflight.code_identity(tmp_path)
    assert first["source_sha256"] != second["source_sha256"]
    code.unlink()
    assert preflight.code_identity(tmp_path)["source_sha256"] != second["source_sha256"]


def test_live_flags_are_not_available():
    with pytest.raises(SystemExit) as error:
        preflight.build_parser().parse_args(["--enable-paper-telegram", "--launch"])
    assert error.value.code == 2


def test_main_prints_only_plan_and_returns_blocked(local_plan, monkeypatch, capsys):
    args, identity = local_plan
    args.reviewed_head = None
    monkeypatch.setattr(preflight, "code_identity", lambda _: identity)
    monkeypatch.setattr(preflight.argparse.ArgumentParser, "parse_args", lambda *_: args)
    assert preflight.main([]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def _write_canonical_resume(local_plan):
    args = local_plan[0]
    root = Path(args.source_root)
    consumed = root / "pricing_tail.jsonl"
    content = b'{"synthetic":true}\n'
    consumed.write_bytes(content)
    stat = consumed.stat()
    state = {
        "schema_version": "phx2_paper_state_v1", "mode": "LIVE_PAPER", "run_id": args.run_id,
        "config_digest": preflight.load_config(args.config).config_digest(),
        "source_checkpoint": {
            "selection": {"paths": [os.path.normcase(str(root.resolve()))],
                          "producer_streams_only": True,
                          "include_kinds": ["BUILD30_CANDIDATE_RECHECK", "FREE_TIER_PRICING_TAIL"]},
            "offsets": {str(consumed.resolve()): len(content)},
            "files": {str(consumed.resolve()): {"device": stat.st_dev, "inode": stat.st_ino,
                      "anchor_size": len(content), "anchor": hashlib.sha256(content).hexdigest()}},
        },
    }
    run_dir = Path(args.out_root) / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "paper_state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path, state, consumed


def test_bound_source_resume_is_verified_without_outputting_contents(local_plan):
    state_path, state, consumed = _write_canonical_resume(local_plan)
    before = (state_path.read_bytes(), consumed.read_bytes())
    plan = run(local_plan)
    assert not plan["reasons"]
    assert plan["resume"]["input_binding"] == "MATCHED"
    assert plan["resume"]["consumed_inputs_verified"] == 1
    assert plan["resume"]["canonical_state_max_bytes"] == 24 * 1024 * 1024
    assert "synthetic" not in json.dumps(plan)
    assert str(consumed) not in json.dumps(plan)
    assert before == (state_path.read_bytes(), consumed.read_bytes())


@pytest.mark.parametrize("explicit", [False, True])
def test_additive_rollover_requires_explicit_flag_and_retains_prior_roots(local_plan, explicit):
    _write_canonical_resume(local_plan)
    new_root = Path(local_plan[0].repo) / "next-producer-run"
    new_root.mkdir()
    local_plan[0].additional_source_root = [str(new_root)]
    local_plan[0].allow_input_rollover = explicit
    plan = run(local_plan)
    if explicit:
        assert not plan["reasons"]
        assert plan["resume"]["input_binding"] == "EXPLICIT_ADDITIVE_ROLLOVER"
        assert plan["resume"]["selected_source_roots"] == 2
        assert plan["inactive_runtime_option_map"]["paper"]["--allow-input-rollover"]
    else:
        assert "PAPER_INPUT_SELECTION_MISMATCH" in plan["reasons"]


def test_rollover_cannot_replace_prior_root(local_plan):
    _write_canonical_resume(local_plan)
    new_root = Path(local_plan[0].repo) / "replacement-run"
    new_root.mkdir()
    local_plan[0].source_root = str(new_root)
    local_plan[0].allow_input_rollover = True
    assert "PAPER_INPUT_SELECTION_MISMATCH" in run(local_plan)["reasons"]


@pytest.mark.parametrize("change,reason", [
    ("missing", "PAPER_CHECKPOINTED_INPUT_MISSING"),
    ("truncate", "PAPER_INPUT_REPLACED_OR_TRUNCATED"),
    ("replace_prefix", "PAPER_INPUT_REPLACED_OR_TRUNCATED"),
])
def test_consumed_input_loss_or_replacement_refused(local_plan, change, reason):
    _, _, consumed = _write_canonical_resume(local_plan)
    if change == "missing":
        consumed.unlink()
    elif change == "truncate":
        consumed.write_bytes(b"x")
    else:
        consumed.write_bytes(b"x" * consumed.stat().st_size)
    assert reason in run(local_plan)["reasons"]


def test_consumed_input_without_source_binding_refused(local_plan):
    path, state, _ = _write_canonical_resume(local_plan)
    del state["source_checkpoint"]["selection"]
    path.write_text(json.dumps(state), encoding="utf-8")
    assert "PAPER_INPUT_SELECTION_MISSING" in run(local_plan)["reasons"]


def test_oversized_canonical_state_is_blocked_before_read(local_plan, monkeypatch):
    path, _, _ = _write_canonical_resume(local_plan)
    monkeypatch.setattr(preflight, "MAX_STATE_BYTES", path.stat().st_size - 1)
    original_open = Path.open
    def guarded_open(target, *args, **kwargs):
        assert target != path, "oversized state must not be opened"
        return original_open(target, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded_open)
    assert "PAPER_CANONICAL_STATE_SIZE_LIMIT" in run(local_plan)["reasons"]


def test_legacy_live_book_requires_reviewed_migration_or_new_run(local_plan):
    run_dir = Path(local_plan[0].out_root) / local_plan[0].run_id
    run_dir.mkdir(parents=True)
    (run_dir / "paper_fills.jsonl").write_text("legacy-book", encoding="utf-8")
    assert "PAPER_LEGACY_STATE_REQUIRES_REVIEWED_MIGRATION" in run(local_plan)["reasons"]


@pytest.mark.parametrize("count,valid", [(16, True), (17, False)])
def test_source_root_limit(local_plan, count, valid):
    roots = []
    for index in range(count - 1):
        path = Path(local_plan[0].repo) / f"producer-{index}"
        path.mkdir()
        roots.append(str(path))
    local_plan[0].additional_source_root = roots
    plan = run(local_plan)
    assert (not plan["reasons"]) is valid
    if not valid:
        assert "PAPER_INPUT_SELECTION_INVALID" in plan["reasons"]


def test_synthetic_six_strategy_135_exposure_refused_against_32_tail_slots(local_plan):
    path = Path(local_plan[0].config)
    config = json.loads(path.read_text(encoding="utf-8"))
    assert len(config["strategies"]) == 6
    for strategy, limit in zip(config["strategies"], [25, 25, 25, 25, 25, 10]):
        strategy["max_open_positions"] = limit
    path.write_text(json.dumps(config), encoding="utf-8")
    plan = run(local_plan)
    assert plan["paper_policy"]["max_unique_open_positions_worst_case"] == 135
    assert "PAPER_EXPOSURE_EXCEEDS_TAIL_CAPACITY" in plan["reasons"]


@pytest.mark.parametrize("additional_count,valid", [(2, True), (3, False)])
def test_stream_file_limit_is_aggregate_across_roots(local_plan, monkeypatch, additional_count, valid):
    monkeypatch.setattr(preflight, "MAX_PREFLIGHT_INPUT_FILES", 4)
    first = Path(local_plan[0].source_root) / "candidates"
    second_root = Path(local_plan[0].repo) / "second-producer"
    second = second_root / "candidates"
    first.mkdir()
    second.mkdir(parents=True)
    for index in range(2):
        (first / f"first-{index}.jsonl").touch()
    for index in range(additional_count):
        (second / f"second-{index}.jsonl").touch()
    local_plan[0].additional_source_root = [str(second_root)]
    plan = run(local_plan)
    assert (not plan["reasons"]) is valid
    if valid:
        assert plan["inputs"]["existing_stream_files"] == 4
        assert plan["inputs"]["aggregate_stream_file_limit"] == 4
    else:
        assert "PAPER_INPUT_FILE_LIMIT_EXCEEDED" in plan["reasons"]


def test_stream_enumeration_is_lazy_and_stops_at_overflow(local_plan, monkeypatch):
    root = Path(local_plan[0].source_root)
    candidates = root / "candidates"
    candidates.mkdir()
    for index in range(5):
        (candidates / f"{index}.jsonl").touch()

    class LazyEntries:
        yielded = 0
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.closed = True

        def __iter__(self):
            return self

        def __next__(self):
            assert self.yielded < 4, "overflow must close enumeration immediately"
            entry = SimpleNamespace(name=f"{self.yielded}.jsonl")
            self.yielded += 1
            return entry

    entries = LazyEntries()
    monkeypatch.setattr(preflight.os, "scandir", lambda _: entries)
    monkeypatch.setattr(Path, "glob", lambda *_: pytest.fail("glob materialization forbidden"))
    monkeypatch.setattr(Path, "open", lambda *_a, **_kw: pytest.fail("source content read forbidden"))
    with pytest.raises(preflight.PreflightError, match="PAPER_INPUT_FILE_LIMIT_EXCEEDED"):
        preflight.inspect_source(root, file_budget=3)
    assert entries.yielded == 4
    assert entries.closed
