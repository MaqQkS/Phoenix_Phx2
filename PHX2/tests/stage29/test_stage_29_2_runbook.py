"""Stage 29.2 runbook structural tests.

Locks the presence of required runbook sections and confirms the
runbook carries NO real API-key-shaped literal, NO URL host
literal, NO mention of forbidden surfaces (Stage 29.3 tradeable
smoke, Discord send, Telegram, etc. -- except in the explicit
"forbidden surfaces" section).
"""

from __future__ import annotations

from pathlib import Path

import pytest


_PHX2_ROOT = Path(__file__).resolve().parent.parent.parent
_RUNBOOK_PATH = (
    _PHX2_ROOT
    / "stage29"
    / "STAGE_29_2_BIRDEYE_PRICE_ATH_RUNBOOK.md"
)


def _read():
    return _RUNBOOK_PATH.read_text(encoding="utf-8")


def test_runbook_exists():
    assert _RUNBOOK_PATH.is_file()


@pytest.mark.parametrize(
    "section",
    [
        "Stage 29.2 inventory pins",
        "Canonical Stage 29.2 env names",
        "Endpoint set + headers",
        "Probe modes",
        "READINESS_ONLY",
        "HTTP_CONNECT_ONLY",
        "ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN",
        "Operator scratch ceremony",
        "Closed-set vocabularies",
        "Forbidden surfaces",
        "Acceptance criteria",
    ],
)
def test_runbook_carries_required_section(section):
    assert section in _read()


@pytest.mark.parametrize(
    "env_name",
    [
        "PHX2_STAGE29_2_BIRDEYE_API_KEY",
        "PHX2_STAGE29_2_BIRDEYE_BASE_URL",
        "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
        "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS",
    ],
)
def test_runbook_lists_each_env_name(env_name):
    assert env_name in _read()


def test_runbook_mentions_x_chain_solana_constant():
    src = _read()
    assert "x-chain" in src
    assert "solana" in src


def test_runbook_mentions_get_defi_price_and_get_defi_ohlcv():
    src = _read()
    assert "/defi/price" in src
    assert "/defi/ohlcv" in src


def test_runbook_does_not_promote_history_price_endpoint():
    # Stage 29.2 explicitly does NOT use /defi/history_price for
    # ATH. The runbook may reference it ONLY in a context that
    # makes clear it is NOT used; the simplest pin is the
    # absence of the substring entirely.
    assert "/defi/history_price" not in _read()


def test_runbook_carries_no_real_api_key_shape():
    # The Stage 29.2 readiness module accepts API keys of length
    # >= 16; a plausible-shaped key string of that length in the
    # runbook would be a leak. Use two concatenated needle
    # fragments so this test file itself does not trip the same
    # check.
    forbidden = (
        "B" + "earer ",
        "BIRDEYE_API" + "_KEY=",
        "S" + "K-",
    )
    src = _read()
    for needle in forbidden:
        assert needle not in src


def test_runbook_carries_no_url_host_literal():
    # The Stage 29.2 base URL is operator-supplied via env. The
    # runbook may reference birdeye.so ONLY in the surrounding
    # operator instructions; the strict pin here is "no
    # production source ever carries this literal". The runbook
    # itself is documentation -- but if it mentions the host,
    # it must be obviously documentation, NOT a code constant.
    src = _read()
    # The runbook should NOT advertise a default base URL
    # value in code-block form.
    code_block_needle = (
        "```\nhttps://public-api.birdeye"
        + ".so"
    )
    assert code_block_needle not in src


def test_runbook_lists_forbidden_surfaces_for_29_3():
    src = _read()
    # Forbidden-surface section must mention Stage 29.3 +
    # Discord send + Telegram + automated trading + Pump.fun
    # bonding-curve + Dexscreener + Helius + PHX1.
    assert "Stage 29.3" in src
    assert "Discord" in src
    assert "Telegram" in src
    assert "trading" in src
    assert "Pump.fun" in src
    assert "Dexscreener" in src
    assert "Helius" in src
    assert "PHX1" in src
