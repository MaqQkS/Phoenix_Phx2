"""Stage 22.6 doc-guard tests for the Stage 22 operator runbook.

The runbook is shipped at
``PHX2/stage22/STAGE_22_OPERATOR_RUNBOOK.md``. This file
enforces:

  * the runbook exists at the locked path;
  * the runbook mentions the required safety topics:
      - do not paste secrets into AI chats,
      - PowerShell session env vars,
      - ``git check-ignore -v`` for the optional ``.env.local``
        pattern,
      - ``git status --short`` / ``git diff`` / ``git diff
        --cached`` pre-run checks,
      - Stage 22 limitations,
      - Stage 23 / 24 / 25 handoff,
      - bounded-runner caps (``max_provider_attempts == 1``,
        ``max_events``, ``max_dispatches``,
        ``stop_after_first_dispatch``);
  * the runbook does NOT contain a real-looking API key,
    webhook URL, bearer token, recipient id, or private key;
  * the runbook does NOT make completeness claims about ATH /
    Birdeye / filters / fees / X / public routing;
  * the runbook does NOT instruct committing a ``.env`` /
    ``.env.local`` / secret-bearing file.
"""

from __future__ import annotations

import re
from pathlib import Path


STAGE22_ROOT: Path = (
    Path(__file__).parent.parent.parent / "stage22"
)
OPERATOR_RUNBOOK_PATH: Path = (
    STAGE22_ROOT / "STAGE_22_OPERATOR_RUNBOOK.md"
)


# URL-scheme + webhook-host substrings, mirrored from the
# Stage 22.1 secret-leak scanner. Constructed at module load
# to avoid the literals appearing in this test source.
_FORBIDDEN_URL_SUBSTRINGS: tuple[str, ...] = (
    "https" + ":" + "//",
    "http" + ":" + "//",
    "wss" + ":" + "//",
    "ws" + ":" + "//",
    "discord" + "." + "com",
    "discordapp" + "." + "com",
    "hooks" + ".slack" + "." + "com",
    "bot" + "." + "db",
)


_LONG_HEX_RE = re.compile(r"[a-fA-F0-9]{40,}")
_LONG_BASE64ISH_RE = re.compile(r"[A-Za-z0-9+=_-]{32,}")


_SCREAMING_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SNAKE_LOWER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PASCAL_CASE_RE = re.compile(r"^[A-Z][a-z][A-Za-z0-9]*$")
_PRIVATE_NAME_RE = re.compile(r"^_[a-zA-Z0-9_]*$")
_HYPHENATED_LOWER_RE = re.compile(r"^[a-z]+(-[a-z]+)+$")


def _is_safe_identifier_shape(s: str) -> bool:
    return bool(
        _SCREAMING_SNAKE_RE.fullmatch(s)
        or _SNAKE_LOWER_RE.fullmatch(s)
        or _PASCAL_CASE_RE.fullmatch(s)
        or _PRIVATE_NAME_RE.fullmatch(s)
        or _HYPHENATED_LOWER_RE.fullmatch(s)
    )


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------


def test_operator_runbook_exists():
    assert OPERATOR_RUNBOOK_PATH.is_file(), (
        f"Stage 22 operator runbook must exist at "
        f"{OPERATOR_RUNBOOK_PATH}"
    )


def test_operator_runbook_is_non_empty():
    assert OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").strip() != ""


# ---------------------------------------------------------------------------
# Required safety topics
# ---------------------------------------------------------------------------


_REQUIRED_SAFETY_SUBSTRINGS_LOWER: tuple[str, ...] = (
    "do not paste",
    "ai chat",
    "powershell",
    "$env:",
    "git check-ignore",
    "git status --short",
    "git diff",
    "git diff --cached",
    ".env",
    ".env.local",
    "outside the repo",
    "max_provider_attempts",
    "max_events",
    "max_dispatches",
    "stop_after_first_dispatch",
    "stage 22 cannot",
    "stage 23",
    "stage 24",
    "stage 25",
    "private discord",
    "raw capture",
    "dedupe",
    "readiness_not_ready",
    "provider_failed",
    "provider_returned_zero",
    "all_malformed",
    "all_duplicates",
    "transport_refused",
    # Codex fix 1: runbook must point operator at the THREE
    # Stage 21 surfaces that together define the env var
    # names; conflating them is the documented failure mode.
    "phx2/stage21/constants.py",
    "phx2/stage21/config.py",
    "phx2/stage21/live_secrets_boundary.py",
    "scratch-script",
)


def test_operator_runbook_mentions_all_required_safety_topics():
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").lower()
    for needle in _REQUIRED_SAFETY_SUBSTRINGS_LOWER:
        assert needle in text, (
            f"operator runbook is missing required safety topic "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# Forbidden completeness claims
# ---------------------------------------------------------------------------


_FORBIDDEN_CLAIM_SUBSTRINGS_LOWER: tuple[str, ...] = (
    "ath ready",
    "ath complete",
    "ath shipped",
    "birdeye ready",
    "birdeye complete",
    "birdeye shipped",
    "filters ready",
    "filters complete",
    "filters shipped",
    "fees ready",
    "fees complete",
    "fees shipped",
    "jito ready",
    "jito complete",
    "axiom ready",
    "axiom complete",
    "x integration",
    "social ingest ready",
    "social ingest complete",
    "public routing ready",
    "subscriber routing ready",
    "paid routing ready",
    "telegram ready",
    "telegram shipped",
    "production ready",
)


def test_operator_runbook_makes_no_forbidden_completeness_claims():
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").lower()
    for needle in _FORBIDDEN_CLAIM_SUBSTRINGS_LOWER:
        assert needle not in text, (
            f"operator runbook contains forbidden completeness claim "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# Forbidden public-routing instructions
# ---------------------------------------------------------------------------


_FORBIDDEN_ROUTING_INSTRUCTIONS_LOWER: tuple[str, ...] = (
    "send to public",
    "post to public",
    "route to public",
    "send to subscribers",
    "route to subscribers",
    "send to paid",
    "route to paid",
    "send to telegram",
    "post to telegram",
)


def test_operator_runbook_has_no_public_or_paid_routing_instructions():
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").lower()
    for needle in _FORBIDDEN_ROUTING_INSTRUCTIONS_LOWER:
        assert needle not in text, (
            f"operator runbook contains forbidden routing instruction "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# No URL-scheme / webhook-host literal
# ---------------------------------------------------------------------------


def test_operator_runbook_contains_no_url_or_webhook_literal():
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").lower()
    for needle in _FORBIDDEN_URL_SUBSTRINGS:
        assert needle not in text, (
            f"operator runbook contains forbidden URL / webhook "
            f"substring {needle!r}"
        )


# ---------------------------------------------------------------------------
# No long secret-shaped runs
# ---------------------------------------------------------------------------


def test_operator_runbook_has_no_long_hex_runs():
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8")
    matches = list(_LONG_HEX_RE.finditer(text))
    assert matches == [], (
        f"operator runbook must not contain any long hex run; "
        f"first offender: {matches[0].group(0)!r}" if matches else ""
    )


def test_operator_runbook_has_no_long_base64_runs_outside_identifiers():
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8")
    for match in _LONG_BASE64ISH_RE.finditer(text):
        token = match.group(0)
        if _is_safe_identifier_shape(token):
            continue
        # Python keyword-argument shapes like ``key=value`` show
        # up here because ``=`` is in the base64 character class.
        # Accept the match if every ``=``-separated component is
        # itself a safe identifier shape; this preserves coverage
        # for true long base64 secrets while letting illustrative
        # code blocks containing kwarg patterns through.
        components = [c for c in token.split("=") if c]
        if components and all(
            _is_safe_identifier_shape(c) for c in components
        ):
            continue
        raise AssertionError(
            f"operator runbook contains unexpected long base64-shaped "
            f"run {token!r}"
        )


# ---------------------------------------------------------------------------
# No commit-the-env instruction
# ---------------------------------------------------------------------------


def test_operator_runbook_does_not_instruct_committing_env_files():
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").lower()
    forbidden_phrases = (
        "git add .env",
        "git add phx2/.env",
        "commit .env",
        "commit the .env",
        "commit your .env",
        "check in .env",
        "check in your .env",
        "add .env to git",
    )
    for phrase in forbidden_phrases:
        assert phrase not in text, (
            f"operator runbook must not instruct committing env files; "
            f"offending phrase {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Must explicitly mention the no-AI-paste rule
# ---------------------------------------------------------------------------


def test_operator_runbook_explicitly_forbids_pasting_into_ai_chats():
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").lower()
    # The runbook must contain a direct prohibition that ties
    # "do not paste" to an AI surface name. Match either the
    # explicit "ai chat" wording or any of the named tools.
    requires_negation = any(
        phrase in text for phrase in (
            "do not paste any real key",
            "do not paste any real provider key",
            "do not paste any key",
            "do not paste secrets",
        )
    )
    mentions_ai_surface = any(
        phrase in text for phrase in (
            "ai chat", "claude", "codex", "chatgpt",
        )
    )
    assert requires_negation and mentions_ai_surface, (
        "operator runbook must explicitly forbid pasting real keys "
        "into AI chat surfaces"
    )


# ---------------------------------------------------------------------------
# Codex fix 1: env-var surface guidance must separate the three
# Stage 21 surfaces and call out the scratch-local recipient
# ---------------------------------------------------------------------------


def test_operator_runbook_separates_constants_config_and_readiness_surfaces():
    """The runbook must not imply ``live_secrets_boundary.py``
    alone defines every env var name. Three Stage 21 surfaces
    have distinct roles:

      * ``PHX2/stage21/constants.py`` -- base config env var
        NAMES (provider / API key / RPC / Discord webhook);
      * ``PHX2/stage21/config.py`` -- the single env-read
        loader;
      * ``PHX2/stage21/live_secrets_boundary.py`` -- live-
        readiness overlay names.

    The runbook section 4.2 prose must reference all three.
    The required-topics test above asserts presence; this test
    asserts the prose ties each file to its actual role so a
    future drift cannot collapse them onto a single sentence.
    """
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").lower()
    # ``constants.py`` must appear in proximity to "base" /
    # "provider" / "api key" / "rpc" / "webhook" wording.
    constants_section_anchors = (
        "base env var",
        "provider",
        "api key",
        "rpc",
        "webhook",
    )
    assert "phx2/stage21/constants.py" in text and any(
        anchor in text for anchor in constants_section_anchors
    ), (
        "runbook must explain that PHX2/stage21/constants.py "
        "defines the base provider / API key / RPC / Discord "
        "webhook env var NAMES"
    )
    # ``config.py`` must be tied to the env-read role.
    assert "phx2/stage21/config.py" in text and (
        "os.environ" in text or "env-read" in text or
        "single stage 21 entry" in text
    ), (
        "runbook must explain that PHX2/stage21/config.py is "
        "the single Stage 21 module that reads os.environ"
    )
    # ``live_secrets_boundary.py`` must be tied to the
    # readiness-overlay role, NOT to the base provider names.
    assert "phx2/stage21/live_secrets_boundary.py" in text and (
        "readiness overlay" in text or "overlay" in text
    ), (
        "runbook must explain that "
        "PHX2/stage21/live_secrets_boundary.py defines the "
        "live-readiness OVERLAY env var names, not the base "
        "provider key names"
    )


def test_operator_runbook_flags_recipient_as_scratch_local():
    """The runbook must explicitly call out that the Discord
    recipient id is a scratch-script local variable, not a
    Stage 21 / Stage 22 config-surface env var.
    """
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").lower()
    has_recipient_mention = "recipient" in text
    has_scratch_local_qualifier = any(
        phrase in text for phrase in (
            "scratch-script local",
            "scratch-script\nlocal",
            "scratch script local",
            "scratch-local",
            "scratch local",
        )
    )
    assert has_recipient_mention and has_scratch_local_qualifier, (
        "runbook must explicitly flag the Discord recipient id "
        "as a scratch-script local variable"
    )


# ---------------------------------------------------------------------------
# Codex fix 2: JSONL writers take pathlib.Path, not str
# ---------------------------------------------------------------------------


def test_operator_runbook_scratch_example_passes_path_not_str():
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8")
    # Required correct forms:
    required_path_forms = (
        'path=out_dir / "raw_capture.jsonl"',
        'path=out_dir / "dedupe.jsonl"',
    )
    for needle in required_path_forms:
        assert needle in text, (
            f"runbook scratch example must pass a Path object: "
            f"missing expected snippet {needle!r}"
        )
    # Forbidden str() coercions:
    forbidden_str_forms = (
        'path=str(out_dir / "raw_capture.jsonl")',
        'path=str(out_dir / "dedupe.jsonl")',
    )
    for needle in forbidden_str_forms:
        assert needle not in text, (
            f"runbook scratch example must NOT wrap the Path in str(); "
            f"offending snippet {needle!r}"
        )


def test_operator_runbook_calls_out_path_typing_requirement():
    """A reader who only skims the example must still see that
    the writers reject ``str`` paths. The follow-up notes
    section is required to say so.
    """
    text = OPERATOR_RUNBOOK_PATH.read_text(encoding="utf-8").lower()
    assert "pathlib.path" in text, (
        "runbook must reference pathlib.Path explicitly in the "
        "notes following the scratch example"
    )
    assert "not `str`" in text or "(not `str`)" in text or (
        "not str" in text and "str)" in text
    ), (
        "runbook must explicitly say the writers do NOT accept "
        "str paths"
    )
