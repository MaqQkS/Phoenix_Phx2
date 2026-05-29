"""Stage 30.5.0 migration-context spec-lock pins.

Pure read-only repo inspection. No live network calls, no env
reads, no Discord traffic, no provider calls. This test only reads
the Stage 30.5.0 spec-lock markdown
(``STAGE_30_5_0_MIGRATION_CONTEXT_SPEC_LOCK.md``) and asserts the
Stage 30.5.0 contract via substring matches.

Pinned contract:

  * The spec doc exists.
  * It carries the required section headings (scope, starting
    point, target display options, source contract, rendering rule,
    Stage 29.5 handoff, substage sequence, ATH handoff, secret
    hygiene), in order.
  * Stage 30.5 scope is migration-context-only: no ATH, no Net, no
    live, no Discord, no provider calls, no candidate scan, no
    enforcement, no public / subscriber routing, no trading, no
    Telegram / X / social.
  * Stage 30.5.0 is spec lock and tests only (not live runtime, not
    Discord, not ATH, not a tag / closure).
  * The current starting body line with ``Mig: Unknown`` is
    documented and Stage 30.5 owns only the ``Mig`` token.
  * The migration display statuses are a closed set
    (``Mig: Known`` / ``Mig: Unverified`` / ``Mig: Unknown``) and
    Fresh / Stale are explicitly deferred.
  * The closed-set ``migration_basis`` tokens are documented.
  * The Stage-30-owned source contract fields are documented.
  * The rendering rule says replace only the ``Mig`` token and keep
    the same compact line shape (no verbose block; missing /
    ambiguous renders ``Mig: Unknown``).
  * The Stage 29.5 handoff is documented, including the hard
    must-NOT-import boundary on the Stage 29.5.5 private Discord
    side-channel renderer.
  * The Stage 30.5 substage sequence (30.5.0 .. 30.5.5) is
    documented.
  * The ATH handoff to Stage 30.6 (or later) is documented.
  * The doc carries NONE of the forbidden secret / header /
    URL-scheme / raw-payload substrings (split-literal needles so
    this test's own source carries none of them either).
  * No public / enforcement / trading / social scope is introduced
    (each is declared out of scope).

Stage 30.5.0 ships no manifest module (it ships zero production
code); the Stage-30-owned migration context models / source
protocol / manifest land at Stage 30.5.1 under separately
authorized scope. This test therefore pins the doc contract only.

Stage 30.5.0 is a spec-lock / handoff document only. This test
makes no live call, sends no Discord message, and changes no
runtime behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
SPEC_DOC_PATH: Path = (
    STAGE30_ROOT / "STAGE_30_5_0_MIGRATION_CONTEXT_SPEC_LOCK.md"
)
SPEC_DOC_BASENAME: str = (
    "STAGE_30_5_0_MIGRATION_CONTEXT_SPEC_LOCK.md"
)
TEST_BASENAME: str = (
    "test_stage_30_5_0_migration_context_spec_lock.py"
)


def _doc_text() -> str:
    return SPEC_DOC_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. The spec doc exists.
# ---------------------------------------------------------------------------


def test_spec_doc_exists() -> None:
    assert SPEC_DOC_PATH.is_file(), (
        f"Stage 30.5.0 requires the spec-lock doc {SPEC_DOC_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Required section headings exist, in order.
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: Tuple[str, ...] = (
    "# PHX2 Stage 30.5.0",
    "## 1. Stage 30.5 scope",
    "## 2. Starting point",
    "## 3. Target compact display options",
    "## 4. Source contract",
    "## 5. Rendering rule",
    "## 6. Stage 29.5 handoff",
    "## 7. Proposed substage sequence",
    "## 8. Handoff to ATH",
    "## 9. Forbidden terms and secret hygiene",
)


def test_spec_doc_contains_required_section_headings() -> None:
    text = _doc_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30.5.0 spec doc missing required section "
            f"heading: {heading!r}"
        )


def test_spec_doc_section_headings_appear_in_order() -> None:
    text = _doc_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30.5.0 spec doc section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


# ---------------------------------------------------------------------------
# 3. Stage 30.5 scope is migration-context only.
# ---------------------------------------------------------------------------


_REQUIRED_SCOPE_PHRASES: Tuple[str, ...] = (
    "migration context into compact private pings only",
    "Stage 30.5 is migration context only",
)


def test_spec_doc_scope_is_migration_only() -> None:
    normalized = _normalized_whitespace(_doc_text())
    for phrase in _REQUIRED_SCOPE_PHRASES:
        assert phrase in normalized, (
            "Stage 30.5.0 spec doc must pin migration-only scope; "
            f"missing {phrase!r}"
        )


_REQUIRED_NO_SCOPE_PHRASES: Tuple[str, ...] = (
    "NO ATH",
    "NO Net",
    "NO live",
    "NO Discord",
    "NO provider calls",
    "NO candidate scan",
    "NO enforcement",
    "NO public or subscriber routing",
    "NO trading",
    "NO Telegram",
)


def test_spec_doc_declares_no_live_no_discord_no_provider_no_scan() -> None:
    text = _doc_text()
    for phrase in _REQUIRED_NO_SCOPE_PHRASES:
        assert phrase in text, (
            "Stage 30.5.0 spec doc must declare the out-of-scope "
            f"surface; missing {phrase!r}"
        )


def test_spec_doc_pins_stage_30_5_0_is_spec_lock_only() -> None:
    normalized = _normalized_whitespace(_doc_text())
    required = (
        "Stage 30.5.0 is spec lock and tests only",
        "is NOT live runtime implementation",
        "is NOT ATH",
        "is NOT a tag or a closure",
    )
    for phrase in required:
        assert phrase in normalized, (
            "Stage 30.5.0 spec doc must pin the spec-lock-only "
            f"stance; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 4. No ATH implementation in Stage 30.5.0; ATH handoff to 30.6+.
# ---------------------------------------------------------------------------


def test_spec_doc_pins_no_ath_implementation() -> None:
    normalized = _normalized_whitespace(_doc_text())
    required = (
        "ATH is not part of Stage 30.5",
        "Stage 30.5.0 does not wire ATH",
        "Do not mix ATH into Stage 30.5.0",
    )
    for phrase in required:
        assert phrase in normalized, (
            "Stage 30.5.0 spec doc must pin that ATH is not "
            f"implemented here; missing {phrase!r}"
        )


def test_spec_doc_records_ath_handoff_to_stage_30_6() -> None:
    normalized = _normalized_whitespace(_doc_text())
    assert "Stage 30.6" in normalized, (
        "Stage 30.5.0 spec doc must hand ATH context off to Stage "
        "30.6 (or a later 30.5.x)"
    )
    assert "ATH context remains Stage 30.6" in normalized, (
        "Stage 30.5.0 spec doc must pin the ATH-context handoff to "
        "Stage 30.6 verbatim"
    )


# ---------------------------------------------------------------------------
# 5. Starting body line with Mig Unknown is documented.
# ---------------------------------------------------------------------------


def test_spec_doc_documents_starting_body_line() -> None:
    text = _doc_text()
    starting_line = "MC: $7.4k | ATH: Unknown | Mig: Unknown"
    assert starting_line in text, (
        "Stage 30.5.0 spec doc must document the current starting "
        f"compact body line: missing {starting_line!r}"
    )


def test_spec_doc_pins_stage_30_5_owns_only_mig_token() -> None:
    normalized = _normalized_whitespace(_doc_text())
    assert "Stage 30.5 only owns the `Mig` token" in normalized, (
        "Stage 30.5.0 spec doc must pin that Stage 30.5 owns only "
        "the Mig token"
    )


# ---------------------------------------------------------------------------
# 6. Migration display statuses are a closed set.
# ---------------------------------------------------------------------------


_REQUIRED_STATUS_TOKENS: Tuple[str, ...] = (
    "Mig: Known",
    "Mig: Unverified",
    "Mig: Unknown",
)


def test_spec_doc_declares_closed_set_status_tokens() -> None:
    text = _doc_text()
    for token in _REQUIRED_STATUS_TOKENS:
        assert token in text, (
            "Stage 30.5.0 spec doc must declare the closed-set "
            f"migration display token: missing {token!r}"
        )
    normalized = _normalized_whitespace(text)
    assert "closed set" in normalized, (
        "Stage 30.5.0 spec doc must declare the migration display "
        "statuses as a closed set"
    )


def test_spec_doc_defers_fresh_and_stale_tokens() -> None:
    normalized = _normalized_whitespace(_doc_text())
    for token in ("Fresh", "Stale"):
        assert token in normalized, (
            "Stage 30.5.0 spec doc must name the deferred "
            f"display token: missing {token!r}"
        )
    assert "NOT in the active closed set" in normalized, (
        "Stage 30.5.0 spec doc must pin that Fresh / Stale are NOT "
        "in the active closed set"
    )
    assert "deferred" in normalized, (
        "Stage 30.5.0 spec doc must pin Fresh / Stale as deferred"
    )


def test_spec_doc_declares_closed_set_migration_basis() -> None:
    text = _doc_text()
    for token in (
        "ON_CHAIN_EVENT",
        "EVIDENCE_PARTIAL",
        "`NONE`",
    ):
        assert token in text, (
            "Stage 30.5.0 spec doc must declare the closed-set "
            f"migration_basis token: missing {token!r}"
        )


# ---------------------------------------------------------------------------
# 7. Stage-30-owned source contract fields are documented.
# ---------------------------------------------------------------------------


_REQUIRED_CONTRACT_FIELDS: Tuple[str, ...] = (
    "token_mint",
    "migration_status",
    "migration_basis",
    "migration_event_time",
    "migration_age_seconds",
    "source_label",
    "source_status",
    "source_reason",
    "runtime_consumable",
)


def test_spec_doc_documents_source_contract_fields() -> None:
    text = _doc_text()
    for field in _REQUIRED_CONTRACT_FIELDS:
        assert field in text, (
            "Stage 30.5.0 spec doc must document the source "
            f"contract field: missing {field!r}"
        )


def test_spec_doc_documents_runtime_consumable_semantics() -> None:
    normalized = _normalized_whitespace(_doc_text())
    assert "hard-locked `False`" in normalized, (
        "Stage 30.5.0 spec doc must pin runtime_consumable "
        "hard-locked False for the offline record"
    )


# ---------------------------------------------------------------------------
# 8. Rendering rule: replace only Mig, keep compact line shape.
# ---------------------------------------------------------------------------


_REQUIRED_RENDERING_PHRASES: Tuple[str, ...] = (
    "Replace only the `Mig` token",
    "same compact line shape",
    "Do not expand into a verbose block",
    "render `Mig: Unknown`",
    "missing or ambiguous",
)


def test_spec_doc_pins_rendering_rule() -> None:
    normalized = _normalized_whitespace(_doc_text())
    for phrase in _REQUIRED_RENDERING_PHRASES:
        assert phrase in normalized, (
            "Stage 30.5.0 spec doc must pin the rendering rule; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 9. Stage 29.5 handoff documented (incl. must-not-import boundary).
# ---------------------------------------------------------------------------


_REQUIRED_HANDOFF_PHRASES: Tuple[str, ...] = (
    "Stage 29.5.4 migration context source adapter",
    "Stage29_5PrivatePingMigrationContext",
    (
        "must NOT import the Stage 29.5.5 private Discord "
        "side-channel renderer"
    ),
)


def test_spec_doc_documents_stage_29_5_handoff() -> None:
    normalized = _normalized_whitespace(_doc_text())
    for phrase in _REQUIRED_HANDOFF_PHRASES:
        assert phrase in normalized, (
            "Stage 30.5.0 spec doc must document the Stage 29.5 "
            f"handoff; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 10. Stage 30.5 substage sequence documented (30.5.0 .. 30.5.5).
# ---------------------------------------------------------------------------


def test_spec_doc_documents_substage_sequence() -> None:
    text = _doc_text()
    for substage in (
        "Stage 30.5.0",
        "Stage 30.5.1",
        "Stage 30.5.2",
        "Stage 30.5.3",
        "Stage 30.5.4",
        "Stage 30.5.5",
    ):
        assert substage in text, (
            "Stage 30.5.0 spec doc must document the full Stage "
            f"30.5 substage sequence; missing {substage!r}"
        )


# ---------------------------------------------------------------------------
# 11. No public / enforcement / trading / social scope introduced.
# ---------------------------------------------------------------------------


_REQUIRED_OUT_OF_SCOPE_PHRASES: Tuple[str, ...] = (
    "NO enforcement",
    "NO public or subscriber routing",
    "NO trading",
    "NO Telegram",
    "social surface",
)


def test_spec_doc_introduces_no_public_enforcement_trading_social() -> None:
    text = _doc_text()
    for phrase in _REQUIRED_OUT_OF_SCOPE_PHRASES:
        assert phrase in text, (
            "Stage 30.5.0 spec doc must keep public / enforcement "
            f"/ trading / social out of scope; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 12. Forbidden secret / header / URL-scheme / raw-payload substrings
#     must be absent.
# ---------------------------------------------------------------------------
#
# Every needle below is assembled from split literals so this test's
# own source does NOT carry the bare forbidden substring. The values
# are already lowercase; the scan lowercases the document text.


_FORBIDDEN_SUBSTRING_NEEDLES: Tuple[str, ...] = (
    "api" + " key",
    "web" + "hook url",
    "discord web" + "hook url",
    "endpoint" + " url",
    "http" + "://",
    "https" + "://",
    "raw" + "_body",
    "response" + "_body",
    "endpoint" + "_secret",
    "head" + "ers",
    "author" + "ization",
    "x-api-" + "key",
    "b" + "earer",
)


def test_spec_doc_carries_no_forbidden_secret_substring() -> None:
    lowered = _doc_text().lower()
    for needle in _FORBIDDEN_SUBSTRING_NEEDLES:
        assert needle not in lowered, (
            "Stage 30.5.0 spec doc must NOT carry forbidden "
            f"secret / header / URL / raw-payload substring "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# 13. Defensive: the doc names itself + its test (self-consistency).
# ---------------------------------------------------------------------------


def test_spec_doc_basename_matches_this_file_target() -> None:
    assert SPEC_DOC_PATH.name == SPEC_DOC_BASENAME
    assert Path(__file__).name == TEST_BASENAME
