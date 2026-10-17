"""Ownership isolation and redaction.

Covers required offline tests 29-32, 43 and 45.

The isolation claims are proven STRUCTURALLY (the watchdog package contains no
import of, or call into, any transport / producer / ledger-writer) and
BEHAVIOURALLY (a full supervision run leaves producer-owned state byte-identical).
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from PHX2.tests.watchdog._harness import FakeWorld, make_config, make_watchdog
from PHX2.watchdog.config import (
    CLOSED_ARMED_ROUTES,
    REFUSAL_BACKOFF_NOT_ASCENDING,
    REFUSAL_BACKOFF_OUT_OF_RANGE,
    REFUSAL_CIRCUIT_MAX_RESTARTS,
    REFUSAL_EXPECTED_HEAD,
    REFUSAL_HEARTBEAT_BELOW_CADENCE,
    REFUSAL_POLL_INTERVAL,
    REFUSAL_STATE_ROOT_INSIDE_PRODUCER_STATE,
    WATCHDOG_CONFIG_REFUSAL_REASONS,
    pinned_head_in_launcher,
    resolve_repo_head,
    validate_watchdog_config,
)
from PHX2.watchdog.state import (
    REDACTION_POSITIVE_CONTROL,
    RedactionViolation,
    append_jsonl,
    positive_control_ok,
    scan_payload,
    write_json_atomic,
)

WATCHDOG_DIR = Path(__file__).resolve().parents[2] / "watchdog"
WATCHDOG_SOURCES = sorted(WATCHDOG_DIR.glob("*.py"))


def _imported_modules(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


# --- 29 / 30. the watchdog cannot construct a transport ----------------- #

def test_watchdog_imports_no_delivery_module():
    banned = ("PHX2.delivery", "telegram", "discord", "requests",
              "http.client", "urllib.request", "socket", "grpc")
    for path in WATCHDOG_SOURCES:
        for module in _imported_modules(path):
            lowered = module.lower()
            for needle in banned:
                assert needle not in lowered, (
                    f"{path.name} imports {module}, which could construct or "
                    f"reach a delivery transport")


def test_watchdog_names_no_transport_constructor():
    """No identifier in the package may be a transport/adapter/config class."""

    banned_identifiers = {
        "TelegramTransport", "TelegramDeliveryAdapter", "TelegramConfig",
        "DiscordTransport", "DiscordWebhook", "send_message", "post_webhook",
    }
    for path in WATCHDOG_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            if name in banned_identifiers:
                pytest.fail(f"{path.name} references {name}")


def test_watchdog_does_not_import_the_producer_or_the_closed_route():
    for path in WATCHDOG_SOURCES:
        modules = _imported_modules(path)
        assert not any(m.endswith("free_tier_session") for m in modules), (
            f"{path.name} imports the armed producer module")
        for closed in CLOSED_ARMED_ROUTES:
            assert closed not in modules, (
                f"{path.name} imports the deliberately closed route {closed}")


def test_closed_route_is_named_only_as_inert_data():
    """The docstrings/refusal data MAY name the closed route; code may not."""

    text = (WATCHDOG_DIR / "config.py").read_text(encoding="utf-8")
    assert "production_supervisor" in text, (
        "the closed route should still be documented as closed")
    assert "import" not in text.split("CLOSED_ARMED_ROUTES")[1][:400]


# --- 31. the watchdog cannot open the canonical ledger writable --------- #

def test_no_write_mode_open_of_any_producer_owned_path():
    """Every `open()` in the package is read-only, or targets watchdog state."""

    write_modes = {"w", "a", "x", "w+", "a+", "r+", "wb", "ab", "xb"}
    for path in WATCHDOG_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "open"):
                continue
            mode = None
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value,
                                                        ast.Constant):
                    mode = keyword.value.value
            if mode in write_modes:
                # Only the watchdog's own state files may be opened for writing,
                # and those go through state.write_json_atomic / append_jsonl.
                assert path.name == "state.py", (
                    f"{path.name}:{node.lineno} opens a file for writing "
                    f"outside the watchdog state writer")


def test_ledger_identity_reader_never_creates_or_modifies(tmp_path):
    from PHX2.watchdog.state import ledger_identity

    ledger = tmp_path / "ping_dedupe.jsonl"
    ledger.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    before = ledger.read_bytes()

    identity = ledger_identity(ledger)

    assert identity["lines"] == 2
    assert identity["parse_ok"] is True
    assert identity["truncated_final_line"] is False
    assert identity["sha256"] == hashlib.sha256(before).hexdigest()
    assert ledger.read_bytes() == before

    missing = tmp_path / "absent.jsonl"
    assert ledger_identity(missing)["sha256"] is None
    assert not missing.exists(), "reading a missing ledger created it"


def test_truncated_and_unparseable_ledgers_are_detected(tmp_path):
    from PHX2.watchdog.state import ledger_identity

    truncated = tmp_path / "t.jsonl"
    truncated.write_text('{"a":1}\n{"b":2}', encoding="utf-8")
    assert ledger_identity(truncated)["truncated_final_line"] is True

    broken = tmp_path / "b.jsonl"
    broken.write_text('{"a":1}\nnot-json\n', encoding="utf-8")
    assert ledger_identity(broken)["parse_ok"] is False


# --- 32. the watchdog cannot mutate cursor / recovery state ------------- #

def test_full_supervision_run_leaves_producer_state_byte_identical(tmp_path):
    config = make_config(tmp_path)
    state_dir = Path(config.cursor_state_dir)
    (state_dir / "grpc_stream_cursor.json").write_text(
        '{"envelope_version":"x"}', encoding="utf-8")
    (state_dir / "rpc_gap_recovery.json").write_text(
        '{"envelope_version":"x"}', encoding="utf-8")

    def snapshot() -> dict:
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(state_dir.iterdir()) if p.is_file()}

    ledger = Path(config.ledger_path)
    before_state = snapshot()
    before_ledger = ledger.read_bytes()

    world = FakeWorld(config)
    make_watchdog(config, world).run(max_cycles=4)

    after_state = snapshot()
    # The fake producer legitimately creates/removes its OWN runtime lock; every
    # other durable document must be untouched.
    for name, digest in before_state.items():
        assert after_state.get(name) == digest, (
            f"the watchdog modified producer state {name}")
    assert ledger.read_bytes() == before_ledger, (
        "the watchdog modified the canonical ledger")


def test_watchdog_state_root_may_not_live_inside_producer_state(tmp_path):
    config = make_config(tmp_path)
    bad = replace(config, state_root=str(
        Path(config.cursor_state_dir) / "watchdog"))
    verdict = validate_watchdog_config(bad)
    assert not verdict.valid
    assert REFUSAL_STATE_ROOT_INSIDE_PRODUCER_STATE in verdict.refusals


# --- 43. invalid configuration fails closed ---------------------------- #

@pytest.mark.parametrize("overrides,reason", [
    ({"poll_interval_seconds": 0.0}, REFUSAL_POLL_INTERVAL),
    ({"poll_interval_seconds": 10_000.0}, REFUSAL_POLL_INTERVAL),
    ({"expected_head": "nope"}, REFUSAL_EXPECTED_HEAD),
    ({"heartbeat_max_age_seconds": 60.0,
      "producer_heartbeat_cadence_seconds": 45.0},
     REFUSAL_HEARTBEAT_BELOW_CADENCE),
    ({"restart_backoff_seconds": (30.0, 10.0)},
     REFUSAL_BACKOFF_NOT_ASCENDING),
    ({"restart_backoff_seconds": (0.5, 10.0)}, REFUSAL_BACKOFF_OUT_OF_RANGE),
    ({"restart_backoff_seconds": ()}, "WATCHDOG_CONFIG_BACKOFF_EMPTY"),
    ({"circuit_max_restarts": 0}, REFUSAL_CIRCUIT_MAX_RESTARTS),
    ({"circuit_max_restarts": 1_000}, REFUSAL_CIRCUIT_MAX_RESTARTS),
])
def test_invalid_configuration_is_refused(tmp_path, overrides, reason):
    config = replace(make_config(tmp_path), **overrides)
    verdict = validate_watchdog_config(config)
    assert not verdict.valid
    assert reason in verdict.refusals
    assert all(r in WATCHDOG_CONFIG_REFUSAL_REASONS for r in verdict.refusals)


def test_nan_backoff_is_refused(tmp_path):
    config = replace(make_config(tmp_path),
                     restart_backoff_seconds=(float("nan"), 10.0))
    verdict = validate_watchdog_config(config)
    assert not verdict.valid
    assert REFUSAL_BACKOFF_OUT_OF_RANGE in verdict.refusals


def test_invalid_configuration_refuses_the_daemon_before_any_launch(tmp_path):
    config = replace(make_config(tmp_path), poll_interval_seconds=0.0)
    world = FakeWorld(config)
    result = make_watchdog(config, world).run(max_cycles=2)

    assert result.exit_code == 2
    assert result.outcome == "CONFIG_REFUSED"
    assert world.spawns == []


def test_launcher_head_pin_must_be_unique_and_match_repo_head(tmp_path):
    config = make_config(tmp_path)
    # Two different pinned commits: ambiguous, so refuse.
    Path(config.launcher_path).write_text(
        'a' * 40 + "\n" + 'b' * 40 + "\n", encoding="utf-8")
    assert pinned_head_in_launcher(
        Path(config.launcher_path).read_text(encoding="utf-8")) is None

    world = FakeWorld(config)
    result = make_watchdog(config, world).run(max_cycles=1)
    assert result.exit_code == 2
    assert result.outcome == "LAUNCHER_HEAD_PIN_NOT_UNIQUE"
    assert world.spawns == []


def test_launcher_pinning_a_different_commit_is_refused(tmp_path):
    config = make_config(tmp_path)
    Path(config.launcher_path).write_text("f" * 40 + "\n", encoding="utf-8")
    world = FakeWorld(config)
    result = make_watchdog(config, world).run(max_cycles=1)
    assert result.exit_code == 2
    assert result.outcome == "LAUNCHER_HEAD_PIN_MISMATCH"
    assert world.spawns == []


def test_missing_launcher_is_refused(tmp_path):
    config = make_config(tmp_path)
    Path(config.launcher_path).unlink()
    world = FakeWorld(config)
    result = make_watchdog(config, world).run(max_cycles=1)
    assert result.outcome == "LAUNCHER_NOT_DEPLOYED"
    assert world.spawns == []


def test_repo_head_resolution_handles_ref_and_detached(tmp_path):
    detached = tmp_path / "d"
    (detached / ".git").mkdir(parents=True)
    (detached / ".git" / "HEAD").write_text("a" * 40 + "\n", encoding="utf-8")
    assert resolve_repo_head(detached) == "a" * 40

    attached = tmp_path / "a"
    (attached / ".git" / "refs" / "heads").mkdir(parents=True)
    (attached / ".git" / "HEAD").write_text(
        "ref: refs/heads/master\n", encoding="utf-8")
    (attached / ".git" / "refs" / "heads" / "master").write_text(
        "b" * 40 + "\n", encoding="utf-8")
    assert resolve_repo_head(attached) == "b" * 40

    packed = tmp_path / "p"
    (packed / ".git").mkdir(parents=True)
    (packed / ".git" / "HEAD").write_text(
        "ref: refs/heads/main\n", encoding="utf-8")
    (packed / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled\n" + "c" * 40 + " refs/heads/main\n",
        encoding="utf-8")
    assert resolve_repo_head(packed) == "c" * 40

    assert resolve_repo_head(tmp_path / "missing") is None


# --- 45. redaction positive controls ----------------------------------- #

def test_positive_control_is_flagged():
    assert positive_control_ok() is True
    assert scan_payload({"probe": REDACTION_POSITIVE_CONTROL})


@pytest.mark.parametrize("payload,label", [
    ({"x": "123456789:AAEEbbCCddEEffGGhhIIjjKKllMMnnOOppQQrr"},
     "VALUE:TELEGRAM_BOT_TOKEN"),
    ({"x": "https://api.telegram.org/bot123/sendMessage"},
     "VALUE:TELEGRAM_API_URL"),
    ({"x": "https://discord.com/api/webhooks/1/abc"},
     "VALUE:DISCORD_WEBHOOK_URL"),
    ({"x": "https://mainnet.example-provider.com/?key=abc"}, "VALUE:ANY_URL"),
    ({"x": "@PHOENIXOperatorChannel"}, "VALUE:TELEGRAM_HANDLE"),
    ({"x": r"C:\Users\BalaC\phx2_paid_primary_runtime\state"},
     "VALUE:ABSOLUTE_WINDOWS_PATH"),
    ({"x": "4k6K1MTNvnqVdeRtNN6UiTQS31aEnt4oQhQYopALLwEjPArfJaFcHYrQNg1K3bEan9ituKckfWUw4SG4dURFpNvS"},
     "VALUE:RAW_BASE58_SIGNATURE"),
    ({"telegram_bot_token": "anything-at-all"}, "BANNED_KEY:telegram_bot_token"),
    ({"nested": [{"webhook_url": "value"}]}, "BANNED_KEY:webhook_url"),
])
def test_every_redaction_rule_fires(payload, label):
    assert label in scan_payload(payload)


def test_boolean_flags_under_banned_key_names_are_allowed():
    """`telegram_token_configured: true` carries no secret."""

    assert scan_payload({"telegram_token_configured": True,
                         "telegram_chat_configured": True,
                         "discord_enabled": False}) == []


def test_unsafe_payload_is_refused_by_the_writers(tmp_path):
    target = tmp_path / "unsafe.json"
    with pytest.raises(RedactionViolation):
        write_json_atomic(target, {"token": REDACTION_POSITIVE_CONTROL})
    assert not target.exists(), "an unsafe payload was partially written"

    with pytest.raises(RedactionViolation):
        append_jsonl(tmp_path / "unsafe.jsonl",
                     {"webhook": "https://discord.com/api/webhooks/1/x"})


def test_no_watchdog_artifact_contains_a_path_or_secret(tmp_path):
    """A full run's artifacts are scanned with the same rules."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    make_watchdog(config, world).run(max_cycles=3)

    for name in ("watchdog_status.json", "watchdog_heartbeat.json",
                 "current_child.json", "circuit_state.json"):
        path = config.state_root_path / name
        if not path.exists():
            continue
        hits = scan_payload(json.loads(path.read_text(encoding="utf-8")))
        assert hits == [], f"{name} leaked: {hits}"

    for name in ("watchdog_events.jsonl", "restart_history.jsonl"):
        path = config.state_root_path / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            hits = scan_payload(json.loads(line))
            assert hits == [], f"{name} leaked: {hits}"
