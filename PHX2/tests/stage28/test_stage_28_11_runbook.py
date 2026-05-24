"""Stage 28.11 runbook content tests.

Pins:

  * Runbook file exists at the locked path.
  * Stage 28.11 is declared as a real-gRPC-client substage with
    three modes; not a Discord-send stage; not a Stage 28.9
    wrapper invocation.
  * Pinned proto source: ``rpcpool/yellowstone-grpc``, tag
    ``v13.1.0+solana.4.0.0``, commit SHA
    ``62893fb7644b1ceafd2f8d840f8e3997f44a483f``.
  * Pinned proto files: ``geyser.proto`` + ``solana-storage.proto``.
  * Pinned dependency versions: ``grpcio==1.66.2``,
    ``grpcio-tools==1.66.2``, ``protobuf==5.28.3``.
  * Pinned generation command, proto source path, generated stub
    path.
  * Locked env-name surface listed in the runbook.
  * Live order (readiness-only -> connect-only -> dry run ->
    Stage 28.12 after explicit authorization) pinned.
  * No-Discord / no-Stage-29 / no-public / no-Telegram /
    no-X-social / no-wallet / no-trade discipline pinned.
  * Price staleness + UNKNOWN / DISAGREE / USDC observe-only
    suppression discipline carried forward from Stage 28.10.
"""

from __future__ import annotations

import re
from pathlib import Path


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
RUNBOOK_PATH: Path = (
    PHX2_ROOT
    / "stage28"
    / "STAGE_28_11_CHAINSTACK_GRPC_RUNBOOK.md"
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalized_runbook_text() -> str:
    """Collapse whitespace runs to a single space so substring
    checks on multi-word sentences are not foiled by markdown
    soft-wrap inserting newlines mid-sentence."""
    return re.sub(r"\s+", " ", _runbook_text())


# ---------------------------------------------------------------------------
# 1. Existence + scope marker
# ---------------------------------------------------------------------------


def test_runbook_exists():
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 28.11 requires runbook {RUNBOOK_PATH}"
    )


def test_runbook_scope_marker_three_modes_no_dispatch():
    text = _runbook_text().lower()
    assert "real grpc client path" in text
    assert "three modes" in text
    assert "no dispatch" in text


def test_runbook_says_not_discord_send_stage():
    text = _runbook_text()
    assert "Stage 28.11 is NOT a Discord-send stage." in text


def test_runbook_says_not_stage_28_9_wrapper():
    text = _normalized_runbook_text()
    assert (
        "Stage 28.11 does NOT invoke the Stage 28.9 wrapper."
        in text
    )


def test_runbook_says_not_stage_29():
    text = _normalized_runbook_text()
    assert "Stage 28.11 is NOT Stage 29 enforcement." in text


# ---------------------------------------------------------------------------
# 2. Pinned proto source
# ---------------------------------------------------------------------------


def test_runbook_pins_proto_repo():
    text = _runbook_text()
    assert "rpcpool/yellowstone-grpc" in text


def test_runbook_pins_proto_tag():
    text = _runbook_text()
    assert "v13.1.0+solana.4.0.0" in text


def test_runbook_pins_proto_commit_sha():
    text = _runbook_text()
    assert (
        "62893fb7644b1ceafd2f8d840f8e3997f44a483f" in text
    )


def test_runbook_pins_proto_files():
    text = _runbook_text()
    assert "geyser.proto" in text
    assert "solana-storage.proto" in text


def test_runbook_pins_proto_source_path():
    text = _runbook_text()
    assert "PHX2/proto/stage28_11/source" in text


def test_runbook_pins_generated_stub_path():
    text = _runbook_text()
    assert "PHX2/proto/stage28_11/_generated" in text


# ---------------------------------------------------------------------------
# 3. Pinned dependency versions
# ---------------------------------------------------------------------------


def test_runbook_pins_grpcio_version():
    text = _runbook_text()
    assert "grpcio==1.66.2" in text


def test_runbook_pins_grpcio_tools_version():
    text = _runbook_text()
    assert "grpcio-tools==1.66.2" in text


def test_runbook_pins_protobuf_version():
    text = _runbook_text()
    assert "protobuf==5.28.3" in text


def test_runbook_pins_requirements_file_path():
    text = _runbook_text()
    assert (
        "PHX2/stage28/stage28_11_requirements.txt" in text
    )


# ---------------------------------------------------------------------------
# 4. Pinned generation command
# ---------------------------------------------------------------------------


def test_runbook_pins_protoc_generation_command():
    text = _runbook_text()
    assert "grpc_tools.protoc" in text
    assert "--python_out" in text
    assert "--grpc_python_out" in text


def test_runbook_documents_import_rewrite_step():
    """The generated stubs use sibling imports
    (``import solana_storage_pb2``); the Stage 28.11 vendor
    step rewrites those to absolute imports. The runbook must
    document the rewrite so re-generation stays reproducible.
    """
    text = _runbook_text()
    assert (
        "import solana_storage_pb2 as solana__storage__pb2"
        in text
    )
    assert (
        "PHX2.proto.stage28_11._generated" in text
    )


# ---------------------------------------------------------------------------
# 5. Env-name surface
# ---------------------------------------------------------------------------


def test_runbook_lists_endpoint_env_name():
    text = _runbook_text()
    assert (
        "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT" in text
    )


def test_runbook_lists_x_token_env_name():
    text = _runbook_text()
    assert "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN" in text


def test_runbook_lists_live_gate_env_name():
    text = _runbook_text()
    assert "PHX2_STAGE28_11_ALLOW_LIVE_GRPC" in text


def test_runbook_lists_timeout_env_name():
    text = _runbook_text()
    assert "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS" in text


# ---------------------------------------------------------------------------
# 6. Live order
# ---------------------------------------------------------------------------


def test_runbook_live_order_readiness_only_first():
    text = _runbook_text()
    assert "Readiness-only" in text


def test_runbook_live_order_provider_connect_only_second():
    text = _runbook_text()
    assert "Provider-connect-only" in text


def test_runbook_live_order_one_event_decode_dry_run_third():
    text = _runbook_text()
    assert "One-event decode dry run" in text


def test_runbook_says_stage_28_12_after_explicit_authorization():
    text = _runbook_text().lower()
    assert "stage 28.12" in text
    assert (
        "max_events=1" in text
        and "max_dispatches=1" in text
    )


# ---------------------------------------------------------------------------
# 7. No-Discord / no-Stage-29 / no-public discipline
# ---------------------------------------------------------------------------


def test_runbook_pins_no_discord_send_in_stage_28_11():
    text = _runbook_text()
    assert "**No Discord.**" in text


def test_runbook_pins_no_stage_28_9_wrapper_invocation():
    text = _normalized_runbook_text()
    assert "**No Stage 28.9 wrapper.**" in text


def test_runbook_pins_no_stage_29_enforcement():
    text = _runbook_text()
    assert "**No Stage 29 enforcement.**" in text


def test_runbook_pins_no_public_subscriber_paid():
    text = _runbook_text().lower()
    assert "no public" in text
    assert "subscriber" in text
    assert "paid tier" in text


def test_runbook_pins_no_telegram_x_social():
    text = _runbook_text().lower()
    assert "no telegram" in text
    assert "x / social" in text


def test_runbook_pins_no_automated_trading_wallet():
    text = _runbook_text().lower()
    assert "no automated trading" in text
    assert "wallet" in text
    assert "private-key" in text


def test_runbook_pins_no_position_sizing_no_trade_execution():
    text = _normalized_runbook_text().lower()
    assert "no position sizing" in text
    assert "trade execution" in text


# ---------------------------------------------------------------------------
# 8. Price + UNKNOWN / DISAGREE / USDC discipline carried over
# ---------------------------------------------------------------------------


def test_runbook_pins_missing_price_suppresses():
    text = _runbook_text()
    assert "**A missing price suppresses.**" in text


def test_runbook_pins_stale_price_suppresses():
    text = _runbook_text()
    assert "**A stale price suppresses.**" in text


def test_runbook_pins_no_sol_invention():
    text = _normalized_runbook_text()
    assert "Stage 28.11 NEVER invents a SOL hint." in text


def test_runbook_pins_no_usdc_invention():
    text = _normalized_runbook_text()
    assert "Stage 28.11 NEVER invents a USDC hint." in text


def test_runbook_pins_unknown_disagree_usdc_remain():
    text = _runbook_text()
    assert (
        "UNKNOWN / DISAGREE / USDC observe-only suppressions remain"
        in text
    )


# ---------------------------------------------------------------------------
# 9. Stage 28.11 closure language
# ---------------------------------------------------------------------------


def test_runbook_says_no_stage_28_closed_tag_movement():
    text = _runbook_text().lower()
    assert "no `stage-28-closed` tag" in text


def test_runbook_says_no_stage_28_11_closed_tag_in_this_substage():
    text = _runbook_text().lower()
    assert (
        "stage 28.11 does not introduce a `stage-28-11-closed` tag"
        in text
    )
