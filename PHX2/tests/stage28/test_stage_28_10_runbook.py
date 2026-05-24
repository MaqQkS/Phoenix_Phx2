"""Stage 28.10 Chainstack Yellowstone runbook tests.

Pin:

  * the doc exists at the locked path,
  * required ceremony phrases are present,
  * no real provider calls in unit tests is stated,
  * the proto / dependency source must be pinned before a live
    client is wired,
  * the first live provider flow is connect-only + one-event
    decode + Stage 28.9 wrapper,
  * real pings require fresh price + missing / stale price
    suppresses,
  * Stage 29 enforcement pending is stated,
  * forbidden surfaces (public / subscriber / paid / Telegram /
    X-social / automated trading / wallet / private-key /
    position sizing / trade execution / dashboard / daemon) are
    re-stated,
  * no URL host literal / raw secret literal / executable Python
    invocation appears.

No network. No env reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
RUNBOOK_PATH: Path = (
    STAGE28_ROOT
    / "STAGE_28_10_CHAINSTACK_YELLOWSTONE_RUNBOOK.md"
)


def _read_runbook() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalized_runbook_text() -> str:
    raw = _read_runbook().lower()
    return " ".join(raw.split())


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------


def test_runbook_file_exists():
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 28.10 runbook required at {RUNBOOK_PATH}"
    )


def test_runbook_is_nonempty():
    text = _read_runbook()
    assert len(text) > 500, (
        "Stage 28.10 runbook must be a substantial operator doc"
    )


# ---------------------------------------------------------------------------
# Required ceremony phrases
# ---------------------------------------------------------------------------


_REQUIRED_PHRASES: tuple[str, ...] = (
    "Stage 28.10",
    "chainstack yellowstone",
    "protocol / fake",
    "no real provider calls",
    "pinned proto",
    "pinned version",
    "pinned generation command",
    "readiness-only validation",
    "provider-connect-only probe",
    "one-event decode",
    "Stage 28.9 wrapper",
    "max_events",
    "real pings",
    "fresh price",
    "missing price",
    "stale price",
    "Stage 29 enforcement pending",
    "operator must manually interpret",
    "explicit operator authorization",
)


@pytest.mark.parametrize("phrase", _REQUIRED_PHRASES)
def test_runbook_contains_required_phrase(phrase: str):
    text = _normalized_runbook_text()
    needle = phrase.lower()
    assert needle in text, (
        f"Stage 28.10 runbook must contain phrase {phrase!r}"
    )


def test_runbook_states_no_real_provider_calls_in_unit_tests():
    text = _normalized_runbook_text()
    assert "no real provider calls in unit tests" in text


def test_runbook_states_proto_must_be_pinned_before_live_client():
    text = _normalized_runbook_text()
    assert "pinned proto source" in text
    assert "before any" in text or "before a live" in text


def test_runbook_states_first_live_flow_is_connect_only_then_one_event_then_wrapper():
    text = _normalized_runbook_text()
    assert "provider-connect-only probe" in text
    assert "one-event decode" in text
    # The Stage 28.9 wrapper invocation is the fourth step.
    assert "stage 28.9 wrapper" in text


def test_runbook_states_real_pings_require_fresh_price():
    text = _normalized_runbook_text()
    assert "real pings" in text
    assert "fresh price" in text or "present fresh price" in text


def test_runbook_states_missing_or_stale_price_suppresses():
    text = _normalized_runbook_text()
    assert "missing price suppresses" in text
    assert "stale price suppresses" in text


def test_runbook_states_stage_29_enforcement_pending():
    text = _normalized_runbook_text()
    assert "stage 29 enforcement pending" in text


# ---------------------------------------------------------------------------
# Forbidden-surface re-statement
# ---------------------------------------------------------------------------


_FORBIDDEN_SURFACE_PHRASES: tuple[str, ...] = (
    "stage 29 enforcement",
    "public routing",
    "subscriber routing",
    "paid",  # paid tiers
    "telegram",
    "x / social",
    "automated trading",
    "wallet",
    "private-key",
    "position sizing",
    "trade execution",
    "dashboard",
    "daemon",
    "grpc / grpcio / protobuf imports",
    "generated pb2",
    "real chainstack network calls",
    "real discord sends",
)


@pytest.mark.parametrize("phrase", _FORBIDDEN_SURFACE_PHRASES)
def test_runbook_restates_forbidden_surface(phrase: str):
    text = _normalized_runbook_text()
    assert phrase in text, (
        f"Stage 28.10 runbook must explicitly state forbidden "
        f"surface {phrase!r}"
    )


# ---------------------------------------------------------------------------
# No URL host literal / no raw secret literal / no executable Python
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_HOST_SUBSTRINGS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + ".rpc.com",
    "public-api.birdeye" + ".so",
    "birdeye" + ".so/v1",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com/",
    "yellowstone" + ".chainstack",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_URL_HOST_SUBSTRINGS,
)
def test_runbook_carries_no_url_host_literal(needle: str):
    text = _read_runbook()
    assert needle not in text, (
        f"Stage 28.10 runbook must not contain URL host literal "
        f"{needle!r}"
    )


def test_runbook_carries_no_url_scheme_literal():
    text = _read_runbook()
    for scheme in (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
    ):
        assert scheme not in text, (
            f"Stage 28.10 runbook must not contain URL scheme "
            f"literal {scheme!r}"
        )


_FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "x-a" + "pi-key",
    "X-A" + "pi-Key",
    "s" + "k-",
    "p" + "k-",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
    "CHAINSTACK_API" + "_KEY=",
    "CHAINSTACK_XTOKEN" + "=",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES,
)
def test_runbook_carries_no_raw_secret_literal(needle: str):
    text = _read_runbook()
    assert needle not in text, (
        f"Stage 28.10 runbook must not contain raw-secret-"
        f"looking literal {needle!r}"
    )


_FORBIDDEN_EXECUTABLE_PYTHON_TOKENS: tuple[str, ...] = (
    "subprocess.run",
    "subprocess.Popen",
    "os.system",
    "os.popen",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_EXECUTABLE_PYTHON_TOKENS,
)
def test_runbook_carries_no_executable_python_token(
    needle: str,
):
    text = _read_runbook()
    assert needle not in text, (
        f"Stage 28.10 runbook must not contain executable Python "
        f"invocation {needle!r}"
    )
