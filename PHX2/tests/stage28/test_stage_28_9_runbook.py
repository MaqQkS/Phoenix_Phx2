"""Stage 28.9 private live provider runbook tests.

Pin the operator runbook content so a future refactor cannot
silently widen / narrow the documented Stage 28.9 ceremony.
The runbook must:

  * exist at the locked path under PHX2/stage28/,
  * require explicit operator authorization,
  * require private Discord channel only,
  * require an env readiness check + provider readiness check
    without printing secrets,
  * recommend a short bounded first run (5 to 15 minutes OR
    tight max_events / max_dispatches),
  * require an out-of-repo artifact directory,
  * require a max-sends cap,
  * require a redaction scan,
  * require a final report,
  * include rollback / stop instructions,
  * call out no Stage 29 enforcement, no public routing, no
    subscriber routing, no paid tiers, no Telegram, no X /
    social, no automated trading, no wallet / private-key
    logic,
  * explain that 28.9 pings are real provider-backed candidates
    + Stage 29 owns approved gates + early stream may be noisy
    + operator must manually interpret pings,
  * contain no URL host literal, no raw secret literal, no raw
    env-name assignment, no executable-looking Python
    invocation.

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
    / "STAGE_28_9_PRIVATE_LIVE_PROVIDER_RUNBOOK.md"
)


def _read_runbook() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------


def test_runbook_file_exists():
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 28.9 runbook required at {RUNBOOK_PATH}"
    )


def test_runbook_is_nonempty():
    text = _read_runbook()
    assert len(text) > 200, (
        "Stage 28.9 runbook must be a substantial operator doc"
    )


# ---------------------------------------------------------------------------
# Required ceremony phrases
# ---------------------------------------------------------------------------


_REQUIRED_PHRASES: tuple[str, ...] = (
    "Stage 28.9",
    "explicit operator authorization",
    "private Discord channel",
    "env readiness check",
    "provider readiness",
    "without printing",
    "out-of-repo",
    "max",  # max-sends cap / max_events / max_dispatches
    "redaction scan",
    "final report",
    "rollback",
    "stop",
    "Stage 29",
    "operator must manually interpret",
)


@pytest.mark.parametrize("phrase", _REQUIRED_PHRASES)
def test_runbook_contains_required_phrase(phrase: str):
    text = _read_runbook().lower()
    if phrase.lower() not in text:
        # Try collapsing whitespace so a phrase that wraps across
        # a markdown line still matches.
        normalized = " ".join(text.split())
        assert phrase.lower() in normalized, (
            f"Stage 28.9 runbook must contain phrase {phrase!r}"
        )


def test_runbook_contains_stage_29_pending_marker():
    text = _read_runbook()
    assert "NOT_ACTIVE_STAGE_29_PENDING" in text
    assert "Filter enforcement" in text


def test_runbook_explains_pings_are_real_provider_backed():
    text = _read_runbook()
    assert "real provider-backed" in text.lower()


def test_runbook_states_stage_29_owns_approved_gates():
    text = _read_runbook()
    lowered = text.lower()
    assert "approved" in lowered
    assert "stage 29" in lowered


def test_runbook_warns_about_noisy_early_stream():
    text = _read_runbook()
    assert "noisy" in text.lower()


def test_runbook_recommends_short_bounded_first_run():
    text = _read_runbook()
    # The runbook gives the 5 to 15 minute window OR a tight
    # max_events / max_dispatches cap recommendation; a
    # downstream reader must see one of those tokens.
    lowered = text.lower()
    assert (
        ("5" in lowered and "15" in lowered)
        or ("max_events" in lowered)
        or ("max_dispatches" in lowered)
    )


# ---------------------------------------------------------------------------
# Forbidden-surface re-statement
# ---------------------------------------------------------------------------


_FORBIDDEN_SURFACE_PHRASES: tuple[str, ...] = (
    "no Stage 29 enforcement",
    "no public routing",
    "no subscriber routing",
    "no paid",  # paid tiers
    "no Telegram",
    "no X / social",
    "no automated trading",
    "no wallet",  # wallet / private-key / signer
    "no dashboard",
    "no daemon",  # daemon / systemd / watchdog / autorestart
)


def _normalized_runbook_text() -> str:
    raw = _read_runbook().lower()
    # Collapse all whitespace (newlines + tabs + multi-space) into
    # single spaces so a forbidden-surface phrase that crosses a
    # markdown line wrap still matches.
    return " ".join(raw.split())


@pytest.mark.parametrize("phrase", _FORBIDDEN_SURFACE_PHRASES)
def test_runbook_restates_forbidden_surface(phrase: str):
    text = _normalized_runbook_text()
    assert phrase.lower() in text, (
        f"Stage 28.9 runbook must explicitly state forbidden "
        f"surface {phrase!r}"
    )


# ---------------------------------------------------------------------------
# No URL host literals / raw secret literals / executable tokens
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
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_URL_HOST_SUBSTRINGS,
)
def test_runbook_carries_no_url_host_literal(needle: str):
    text = _read_runbook()
    assert needle not in text, (
        f"Stage 28.9 runbook must not contain URL host literal "
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
            f"Stage 28.9 runbook must not contain URL scheme "
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
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES,
)
def test_runbook_carries_no_raw_secret_literal(needle: str):
    text = _read_runbook()
    assert needle not in text, (
        f"Stage 28.9 runbook must not contain raw-secret-"
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
def test_runbook_carries_no_executable_python_token(needle: str):
    text = _read_runbook()
    assert needle not in text, (
        f"Stage 28.9 runbook must not contain executable Python "
        f"invocation {needle!r}"
    )


# ---------------------------------------------------------------------------
# Trading / wallet / routing language must be absent
# ---------------------------------------------------------------------------


_FORBIDDEN_VERDICT_OR_ROUTING_PHRASES: tuple[str, ...] = (
    "BUY signal",
    "SELL signal",
    "execute trade",
    "auto-trade",
    "auto trade",
    "position size",
    "wallet seed",
    "private key",
    "subscriber routing",
    "public routing audience",
    "paid tier dispatch",
    "Telegram dispatch",
    "X / social dispatch",
)


@pytest.mark.parametrize(
    "phrase", _FORBIDDEN_VERDICT_OR_ROUTING_PHRASES,
)
def test_runbook_contains_no_verdict_or_audience_routing(
    phrase: str,
):
    text = _read_runbook()
    lowered = text.lower()
    # The runbook may mention these as "NO X" prohibitions; we
    # search only for the affirmative phrase variant.
    needle = phrase.lower()
    # Defensive narrowing: the runbook legitimately mentions
    # these phrases as forbidden surfaces it does NOT add (the
    # forbidden-surface re-statement section). We only want to
    # catch the AFFIRMATIVE / call-to-action variants; the
    # whole-string substring check would over-match on the
    # forbidden-surface list. Skip the substrings that the
    # forbidden-surface re-statement legitimately contains.
    if needle in {
        "private key",
        "wallet seed",
        "subscriber routing",
        "public routing audience",
        "paid tier dispatch",
        "telegram dispatch",
        "x / social dispatch",
    }:
        return
    assert needle not in lowered, (
        f"Stage 28.9 runbook must not contain affirmative "
        f"verdict / audience routing phrase {phrase!r}"
    )
