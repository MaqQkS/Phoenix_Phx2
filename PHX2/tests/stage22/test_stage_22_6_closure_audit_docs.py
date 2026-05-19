"""Stage 22.6 doc-guard tests for the Stage 22 closure audit
doc.

The closure audit doc is shipped at
``PHX2/stage22/STAGE_22_CLOSURE_AUDIT.md``. This file enforces:

  * the doc exists at the locked path;
  * the doc mentions the required closure-audit topics
    (stage21-closed tag, no stage21 modifications, no
    stage-22 tag yet, test suite snapshot, pre-existing
    untracked paths, Stage 23 / 24 / 25 handoff);
  * the doc does NOT contain a URL-scheme literal, a Discord
    webhook host literal, or any long secret-shaped run other
    than the known stage-21-closed commit SHA;
  * the doc does NOT make completeness claims about ATH /
    Birdeye / filters / fees / X / public routing.
"""

from __future__ import annotations

import re
from pathlib import Path


STAGE22_ROOT: Path = (
    Path(__file__).parent.parent.parent / "stage22"
)
CLOSURE_AUDIT_PATH: Path = STAGE22_ROOT / "STAGE_22_CLOSURE_AUDIT.md"


# Stage-21-closed commit SHA, allowed verbatim in this doc only.
_KNOWN_SAFE_HEX_LITERALS: tuple[str, ...] = (
    "67e5453d2b4e7d9f59af4bd50fbc4718de35b0cc",
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


# Long-token leak-shape regexes, mirrored from the Stage 22.1
# secret-leak scanner.
_LONG_HEX_RE = re.compile(r"[a-fA-F0-9]{40,}")
_LONG_BASE64ISH_RE = re.compile(r"[A-Za-z0-9+=_-]{32,}")


# Identifier safety regexes, also mirrored from the secret-leak
# scanner.
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


def test_closure_audit_doc_exists():
    assert CLOSURE_AUDIT_PATH.is_file(), (
        f"Stage 22 closure audit doc must exist at {CLOSURE_AUDIT_PATH}"
    )


def test_closure_audit_doc_is_non_empty():
    assert CLOSURE_AUDIT_PATH.read_text(encoding="utf-8").strip() != ""


# ---------------------------------------------------------------------------
# Required topics
# ---------------------------------------------------------------------------


_REQUIRED_TOPIC_SUBSTRINGS: tuple[str, ...] = (
    "stage-21-closed",
    "67e5453d2b4e7d9f59af4bd50fbc4718de35b0cc",
    "stage-22-closed",
    "PHX2/stage21",
    "PHX2/stage22",
    "PHX2/.stage_17_inputs/",
    "PHX2/docs/",
    "ROADMAP.md",
    # Codex fix 3: closure audit must record the final
    # reproduced counts directly. The first 22.6 pass landed
    # 28 new tests; the Codex-driven fix pass added 7 more,
    # finalising Stage 22 at 847 (812 + 35) and the full PHX2
    # suite at 5513 (5506 + 7). "812" survives as the pre-22.6
    # Stage 22 baseline.
    "812",
    "847",
    "1032",
    "5513",
    "Stage 23",
    "Stage 24",
    "Stage 25",
    "bounded_live_runner",
    "live_composition",
)


def test_closure_audit_mentions_all_required_topics():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")
    for needle in _REQUIRED_TOPIC_SUBSTRINGS:
        assert needle in text, (
            f"closure audit doc is missing required topic {needle!r}"
        )


# ---------------------------------------------------------------------------
# Forbidden scope claims (must NOT claim ATH / Birdeye / filters /
# fees / X are complete)
# ---------------------------------------------------------------------------


_FORBIDDEN_CLAIM_SUBSTRINGS_LOWER: tuple[str, ...] = (
    "ath ready",
    "ath complete",
    "ath shipped",
    "ath done",
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
    "production monetized",
)


def test_closure_audit_makes_no_forbidden_completeness_claims():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8").lower()
    for needle in _FORBIDDEN_CLAIM_SUBSTRINGS_LOWER:
        assert needle not in text, (
            f"closure audit doc contains forbidden completeness claim "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# No URL-scheme literal / webhook-host literal
# ---------------------------------------------------------------------------


def test_closure_audit_contains_no_url_or_webhook_literal():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8").lower()
    for needle in _FORBIDDEN_URL_SUBSTRINGS:
        assert needle not in text, (
            f"closure audit doc contains forbidden URL / webhook "
            f"substring {needle!r}"
        )


# ---------------------------------------------------------------------------
# No long secret-shaped runs other than the known stage-21-closed SHA
# ---------------------------------------------------------------------------


def test_closure_audit_has_no_unexpected_long_hex_runs():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")
    for match in _LONG_HEX_RE.finditer(text):
        token = match.group(0)
        assert token in _KNOWN_SAFE_HEX_LITERALS, (
            f"closure audit doc contains unexpected long hex run "
            f"{token!r}; only the known stage-21-closed SHA is allowed"
        )


def test_closure_audit_has_no_unexpected_long_base64_runs():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")
    for match in _LONG_BASE64ISH_RE.finditer(text):
        token = match.group(0)
        if token in _KNOWN_SAFE_HEX_LITERALS:
            continue
        if _is_safe_identifier_shape(token):
            continue
        raise AssertionError(
            f"closure audit doc contains unexpected long base64-shaped "
            f"run {token!r}"
        )


# ---------------------------------------------------------------------------
# Tag-policy text: doc must NOT claim stage-22-closed exists
# ---------------------------------------------------------------------------


def test_closure_audit_does_not_claim_stage_22_tag_already_exists():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8").lower()
    forbidden_phrases = (
        "stage-22-closed has been created",
        "stage-22-closed was created",
        "stage 22 has been tagged",
        "stage 22 is tagged",
        "stage-22-closed tag exists",
    )
    for phrase in forbidden_phrases:
        assert phrase not in text, (
            f"closure audit doc must not claim the stage-22-closed tag "
            f"already exists; offending phrase {phrase!r}"
        )


# ---------------------------------------------------------------------------
# No instruction to commit a secret-bearing file
# ---------------------------------------------------------------------------


def test_closure_audit_does_not_instruct_committing_secrets():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8").lower()
    forbidden_phrases = (
        "git add .env",
        "git add pHX2/.env",
        "commit .env",
        "commit your .env",
        "commit the .env",
        "check in your keys",
        "check in keys",
        "add your keys to git",
    )
    for phrase in forbidden_phrases:
        assert phrase not in text.lower(), (
            f"closure audit doc must not instruct committing secrets; "
            f"offending phrase {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Codex fix 3: closure audit records the final test counts directly
# ---------------------------------------------------------------------------


def test_closure_audit_records_final_stage22_count_directly():
    """The closure audit must record ``847 passed`` as the
    final reproduced Stage 22 count after the Codex fix pass.
    ``812 + delta`` wording alone is not sufficient: Codex
    must be able to read the closure number off the doc
    without arithmetic.
    """
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")
    assert "847 passed" in text, (
        "closure audit must record the final Stage 22 count as "
        "'847 passed' directly"
    )


def test_closure_audit_records_final_stage21_count_directly():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")
    assert "1032 passed" in text, (
        "closure audit must record the final Stage 21 count as "
        "'1032 passed' directly"
    )


def test_closure_audit_records_full_suite_count_directly():
    text = CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")
    assert "5513 passed" in text, (
        "closure audit must record the full PHX2 suite count as "
        "'5513 passed' directly"
    )
    assert "3 skipped" in text, (
        "closure audit must record the 3-skipped delta on the "
        "full PHX2 suite directly"
    )
