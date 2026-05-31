"""Stage 30.8.2 temp-dir artifact writer closure-audit document tests.

Asserts the Stage 30.8.2 closure-audit markdown
(``STAGE_30_8_2_TEMP_ARTIFACT_WRITER_CLOSURE_AUDIT.md``) exists and
contains the mandated closure content:

  * all three Stage 30.8 commit SHAs (30.8.0..30.8.2) + their substage
    labels,
  * the audited Stage 30.8.2 commit metadata (full SHA, short SHA, exact
    subject, exact parent SHA, no-tag-created + no-push-performed status),
  * the final compact proof line a ``compact_ping_artifact`` captures,
  * the writer entry point + bundle carrier + final write data path,
  * the Stage 30.8.2 safety invariants,
  * the fail-closed write invariants (validate-first, exact-type gate,
    path containment, atomic stage-and-promote, whole-directory swap),
  * the determinism / no-leak invariants (sorted keys, trailing newline,
    no absolute path, no wall-clock, field-projected serialization),
  * the explicit "did NOT solve" list,
  * the Stage 30.8.3 next-stage recommendation,
  * the Codex review history: the initial FAIL finding phrases, the
    remediation phrases, the re-audit verdict (PASS WITH MINOR NOTES /
    Critical: none / Major: none / safe-to-commit), and the final pass
    counts (62 / 172 / 47 / 2186 passed),
  * a closure stance with no commit / tag / push and no Stage 30.8.3,
  * a redaction-safe (forbidden-needle-free) body, AND
  * NO un-negated false-positive closure claim ("tag created", "pushed",
    "Stage 30.8.3 started", ...) -- a doc that falsely claimed a tag /
    push / live run / Stage 30.8.3 start would FAIL.

This is a self-contained closure-audit test: the closure-specific
expectations (the commit SHAs / subject, the data-path hops, the safety /
fail-closed / determinism phrases, the deferred-item list, the Codex
review-history phrases and pass counts) are pinned locally; only the
already-published Stage 30.8 manifest constants that the audit
cross-references (the proof line, the bundle schema version, the
write-status closed set, the writer basename, the next recommended stage,
and the forbidden-needle vocabulary) are imported.

Doc only. No live call, no env read, no provider, no Discord, no
actual-disk write.
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage30.stage30_8_manifest import (
    STAGE30_8_2_BUNDLE_SCHEMA_VERSION,
    STAGE30_8_2_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_2_NEXT_RECOMMENDED_STAGE_TITLE,
    STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME,
    STAGE30_8_2_WRITE_STATUS_VALUES,
    STAGE30_8_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_8_STAGE30_7_COMPACT_PROOF_LINE,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"

CLOSURE_AUDIT_BASENAME: str = (
    "STAGE_30_8_2_TEMP_ARTIFACT_WRITER_CLOSURE_AUDIT.md"
)
AUDIT_PATH: Path = STAGE30_ROOT / CLOSURE_AUDIT_BASENAME


# The three Stage 30.8 substage commit SHAs the closure audit records, as
# immutable historical facts (the inventory pins do not shell out to git;
# the closure audit is a point-in-time documentation record of the chain).
STAGE30_8_0_COMMIT: str = "1c2bf4ddf73577fa97f575bd62c49bc031add9a2"
STAGE30_8_1_COMMIT: str = "5f00b8cf5de0a2333ce2bb470abec21b5b128ee0"
STAGE30_8_2_COMMIT: str = "115a72343de1573698378e22aa12c257a42d79c3"

# Explicit Stage 30.8.2 commit metadata the closure audit must record.
STAGE30_8_2_SHORT_SHA: str = "115a723"
STAGE30_8_2_SUBJECT: str = "phx2 stage 30.8.2: temp artifact writer"
# The Stage 30.8.2 parent is the Stage 30.8.1 commit.
STAGE30_8_2_PARENT_SHA: str = STAGE30_8_1_COMMIT


WRITER_ENTRY_POINT: str = "write_compact_session_artifact_bundle"
BUNDLE_CARRIER: str = "Stage30_8CompactSessionArtifactBundle"


# Distinctive hops the final write data path must name.
_DATA_PATH_HOPS = (
    BUNDLE_CARRIER,
    WRITER_ENTRY_POINT,
    "hidden staging directory",
    "whole-directory rename",
)


# The Stage 30.8.2 safety invariants the closure audit restates verbatim.
_SAFETY_INVARIANTS = (
    "offline / temp-dir only",
    "no live provider / Discord call",
    "no env read",
    "no database / SQLite",
    "no zstd / compression",
    "no network module",
    "caller-provided output directory only",
    "no default storage root / real bot artifact directory",
    "no enforcement / public routing / trading / wallet / social",
    "no drawdown / tier recomputation",
    "no Stage 25 / 27 / 28 / 29 production import",
    "no Stage 29.5 production import",
    "renderer / compact models / orchestrator untouched",
)


# Fail-closed write invariants the closure audit must state.
_FAIL_CLOSED_PHRASES = (
    "BEFORE any byte is written",
    "type(x) is Model",
    "whole-directory swap",
    "stale member file",
    "EMPTY_BUNDLE",
    "INVALID_ARTIFACT_TYPE",
    "PATH_ESCAPE",
)


# Determinism / no-leak invariants the closure audit must state.
_DETERMINISM_PHRASES = (
    "sorted keys",
    "trailing newline",
    "no absolute path",
    "reads no clock",
    "dataclasses.asdict",
    "canonical fields enumerated from the BASE",
)


# The explicit deferred-item list.
_NOT_SOLVED_ITEMS = (
    "live capture / controlled session proof",
    "dedupe / session index integration",
    "write-time storage-budget enforcement",
    "day-partitioned rolling",
    "zstd compression",
    "default storage location / real collection root",
    "drawdown from ATH",
    "tier dip",
    "enforcement",
    "public routing",
    "wallet/trading",
)


# The initial Codex FAIL finding phrases the closure audit must record.
_INITIAL_CODEX_FINDINGS = (
    "direct writes into final session dir",
    "stale manifest",
    "partial rewrite",
    "shrinking rewrite",
    "isinstance",
    "asdict",
    "future-stage guard only checked 30_8_3 and 30_8_4",
    "whitespace-only session IDs",
)


# The remediation phrases the closure audit must record.
_REMEDIATION_PHRASES = (
    "staging directory under output_dir",
    "manifest.json last",
    "validation_result.json",
    "staging verification",
    "final→previous",
    "staging→final",
    "rollback",
    "whole-directory replacement",
    "exact top-level type gates",
    "strict base-model field projection",
    "regex guard",
    "stage30_8_<N>=3",
)


# The Codex re-audit verdict lines the closure audit must record.
_REAUDIT_VERDICT_PHRASES = (
    "PASS WITH MINOR NOTES",
    "Critical: none",
    "Major: none",
    "Safe to commit after final tests: yes",
)


# The Codex re-audit final pass counts the closure audit must record.
_FINAL_PASS_COUNTS = (
    "62 passed",
    "172 passed",
    "47 passed",
    "2186 passed",
)


# ---------------------------------------------------------------------------
# False-positive closure-claim guards (Major 3).
#
# Phrases that, if present UN-negated, would be a false closure claim. Each
# may legitimately appear only when immediately preceded by a negator
# (e.g. "no tag created" / "no push performed"); an un-negated occurrence
# fails the test.
# ---------------------------------------------------------------------------


_NEGATABLE_FALSE_CLAIMS = (
    "tag created",
    "push performed",
)


# Phrases that must never appear in any form (no legitimate negated use in
# this closure record).
_ABSOLUTE_FALSE_CLAIMS = (
    "tag was created",
    "created tag",
    "was pushed",
    "pushed",
    "stage 30.8.3 started",
    "stage 30.8.3 was started",
    "began stage 30.8.3",
    "live run occurred",
    "discord send occurred",
    "env reads occurred",
    "db/sqlite used",
    "zstd used",
    "dedupe/session index implemented",
    "runtime integration implemented",
)


_NEGATORS = frozenset({"no", "not", "never", "zero"})


# Safe negated claims that MUST be present (so the negative scan above is
# guarding a doc that actually makes the safe negative statements, not a
# doc that simply omits them).
_REQUIRED_SAFE_NEGATIONS = (
    "no tag created",
    "no push performed",
    "does NOT begin Stage 30.8.3",
)


def _audit_text() -> str:
    return AUDIT_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    """Collapse runs of whitespace so a phrase that wraps across a
    markdown line still matches.
    """
    return " ".join(text.split())


def _word_before(text_lower: str, idx: int) -> str:
    """Return the whitespace-delimited word immediately before ``idx``."""
    words = text_lower[:idx].split()
    return words[-1] if words else ""


def _unnegated_hits(text_lower: str, phrase: str) -> list:
    """Return offsets of ``phrase`` NOT immediately preceded by a negator."""
    hits = []
    start = 0
    while True:
        idx = text_lower.find(phrase, start)
        if idx == -1:
            break
        if _word_before(text_lower, idx) not in _NEGATORS:
            hits.append(idx)
        start = idx + len(phrase)
    return hits


# ---------------------------------------------------------------------------
# 1. Doc exists
# ---------------------------------------------------------------------------


def test_closure_audit_doc_exists() -> None:
    assert AUDIT_PATH.is_file(), (
        f"Stage 30.8.2 closure requires {CLOSURE_AUDIT_BASENAME}"
    )
    assert _audit_text().strip() != ""


def test_closure_audit_title_names_the_writer_slice() -> None:
    normalized = _normalized(_audit_text())
    assert (
        "PHX2 Stage 30.8.2 — Temp-Dir Compact Session Artifact Writer "
        "Closure Audit" in normalized
    ), "closure audit must carry the Stage 30.8.2 writer-slice title"


# ---------------------------------------------------------------------------
# 2. All three commit SHAs + substage labels
# ---------------------------------------------------------------------------


def test_audit_mentions_all_three_commit_shas() -> None:
    text = _audit_text()
    for sha in (STAGE30_8_0_COMMIT, STAGE30_8_1_COMMIT, STAGE30_8_2_COMMIT):
        assert sha in text, f"closure audit must cite commit SHA {sha!r}"


def test_audit_labels_the_commit_chain_substages() -> None:
    text = _audit_text()
    for substage in ("30.8.0", "30.8.1", "30.8.2"):
        assert substage in text, (
            f"closure audit must label substage {substage!r}"
        )


# ---------------------------------------------------------------------------
# 2b. Explicit Stage 30.8.2 commit metadata (full / short SHA, subject,
#     parent, no-tag, no-push)
# ---------------------------------------------------------------------------


def test_audit_records_commit_metadata() -> None:
    text = _audit_text()
    normalized = _normalized(text)
    assert STAGE30_8_2_COMMIT in text, (
        "closure audit must record the full Stage 30.8.2 SHA"
    )
    assert STAGE30_8_2_SHORT_SHA in text, (
        f"closure audit must record the short SHA "
        f"{STAGE30_8_2_SHORT_SHA!r}"
    )
    assert STAGE30_8_2_SUBJECT in text, (
        f"closure audit must record the exact subject "
        f"{STAGE30_8_2_SUBJECT!r}"
    )
    assert STAGE30_8_2_PARENT_SHA in text, (
        "closure audit must record the exact parent SHA "
        f"{STAGE30_8_2_PARENT_SHA!r}"
    )
    assert "Parent SHA" in normalized, (
        "closure audit must label the parent SHA explicitly"
    )
    assert "no tag created" in normalized, (
        "closure audit must record tag status: no tag created"
    )
    assert "no push performed" in normalized, (
        "closure audit must record push status: no push performed"
    )


# ---------------------------------------------------------------------------
# 3. Final proof line + bundle schema version + write statuses
# ---------------------------------------------------------------------------


def test_audit_contains_final_proof_line() -> None:
    assert STAGE30_8_STAGE30_7_COMPACT_PROOF_LINE in _audit_text(), (
        "closure audit must contain the final compact proof line "
        f"{STAGE30_8_STAGE30_7_COMPACT_PROOF_LINE!r}"
    )


def test_audit_contains_bundle_schema_version() -> None:
    assert STAGE30_8_2_BUNDLE_SCHEMA_VERSION in _audit_text(), (
        "closure audit must name the bundle schema version "
        f"{STAGE30_8_2_BUNDLE_SCHEMA_VERSION!r}"
    )


def test_audit_contains_write_status_closed_set() -> None:
    text = _audit_text()
    for status in STAGE30_8_2_WRITE_STATUS_VALUES:
        assert status in text, (
            f"closure audit must name the write status {status!r}"
        )


# ---------------------------------------------------------------------------
# 4. Writer basename + entry point + bundle carrier + final data path
# ---------------------------------------------------------------------------


def test_audit_names_writer_basename_and_entry_point() -> None:
    text = _audit_text()
    assert STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME in text, (
        "closure audit must name the writer basename "
        f"{STAGE30_8_2_TEMP_ARTIFACT_WRITER_BASENAME!r}"
    )
    assert WRITER_ENTRY_POINT in text, (
        f"closure audit must name the entry point {WRITER_ENTRY_POINT!r}"
    )


def test_audit_contains_final_data_path() -> None:
    text = _audit_text()
    for hop in _DATA_PATH_HOPS:
        assert hop in text, (
            f"closure audit must contain data-path hop {hop!r}"
        )


# ---------------------------------------------------------------------------
# 5. Safety invariants
# ---------------------------------------------------------------------------


def test_audit_contains_safety_invariants() -> None:
    normalized = _normalized(_audit_text())
    for invariant in _SAFETY_INVARIANTS:
        assert invariant in normalized, (
            f"closure audit must state safety invariant {invariant!r}"
        )


# ---------------------------------------------------------------------------
# 6. Fail-closed write invariants
# ---------------------------------------------------------------------------


def test_audit_contains_fail_closed_write_invariants() -> None:
    text = _audit_text()
    normalized = _normalized(text)
    assert "fail closed" in normalized.lower() or "fails closed" in (
        normalized.lower()
    ), "closure audit must state the fail-closed stance"
    for phrase in _FAIL_CLOSED_PHRASES:
        assert phrase in normalized, (
            f"closure audit must state fail-closed invariant {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 7. Determinism / no-leak invariants
# ---------------------------------------------------------------------------


def test_audit_contains_determinism_and_no_leak_invariants() -> None:
    normalized = _normalized(_audit_text())
    for phrase in _DETERMINISM_PHRASES:
        assert phrase in normalized, (
            f"closure audit must state determinism / no-leak invariant "
            f"{phrase!r}"
        )


# ---------------------------------------------------------------------------
# 8. What Stage 30.8.2 did NOT solve
# ---------------------------------------------------------------------------


def test_audit_lists_what_was_not_solved() -> None:
    normalized = _normalized(_audit_text())
    for item in _NOT_SOLVED_ITEMS:
        assert item in normalized, (
            f"closure audit must list deferred item {item!r}"
        )


# ---------------------------------------------------------------------------
# 9. Stage 30.8.3 recommendation
# ---------------------------------------------------------------------------


def test_audit_recommends_stage_30_8_3() -> None:
    normalized = _normalized(_audit_text())
    assert "Stage 30.8.3" in normalized, (
        "closure audit must recommend Stage 30.8.3"
    )
    assert STAGE30_8_2_NEXT_RECOMMENDED_STAGE == "30.8.3"
    assert STAGE30_8_2_NEXT_RECOMMENDED_STAGE_TITLE in normalized, (
        "closure audit must state the Stage 30.8.3 recommendation title "
        f"{STAGE30_8_2_NEXT_RECOMMENDED_STAGE_TITLE!r}"
    )


# ---------------------------------------------------------------------------
# 10. Codex review history: initial FAIL findings + remediations
# ---------------------------------------------------------------------------


def test_audit_records_initial_codex_fail_findings() -> None:
    normalized = _normalized(_audit_text())
    for phrase in _INITIAL_CODEX_FINDINGS:
        assert phrase in normalized, (
            f"closure audit must record initial Codex finding {phrase!r}"
        )


def test_audit_records_remediation_phrases() -> None:
    normalized = _normalized(_audit_text())
    lowered = normalized.lower()
    for phrase in _REMEDIATION_PHRASES:
        # ``manifest.json last`` is matched case-insensitively (the doc
        # also spells it ``manifest.json LAST`` in the fail-closed section);
        # every other remediation phrase matches verbatim.
        haystack = lowered if phrase == "manifest.json last" else normalized
        needle = phrase if phrase != "manifest.json last" else phrase.lower()
        assert needle in haystack, (
            f"closure audit must record remediation phrase {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 11. Codex re-audit verdict + final pass counts
# ---------------------------------------------------------------------------


def test_audit_records_reaudit_verdict() -> None:
    normalized = _normalized(_audit_text())
    for phrase in _REAUDIT_VERDICT_PHRASES:
        assert phrase in normalized, (
            f"closure audit must record re-audit verdict line {phrase!r}"
        )


def test_audit_records_final_pass_counts() -> None:
    normalized = _normalized(_audit_text())
    for phrase in _FINAL_PASS_COUNTS:
        assert phrase in normalized, (
            f"closure audit must record final pass count {phrase!r}"
        )
    assert "git diff --check" in normalized, (
        "closure audit must record the git diff --check result"
    )


# ---------------------------------------------------------------------------
# 12. Closure stance: no commit / tag / push, no Stage 30.8.3 begun, no
#     production / manifest change
# ---------------------------------------------------------------------------


def test_audit_states_closure_stance() -> None:
    normalized = _normalized(_audit_text())
    lowered = normalized.lower()
    for phrase in ("no commit", "no tag", "no push"):
        assert phrase in lowered, (
            f"closure audit must state the {phrase!r} stance"
        )
    assert "does NOT begin Stage 30.8.3" in normalized, (
        "closure audit must state it does not begin Stage 30.8.3"
    )
    assert "ZERO production code" in normalized, (
        "closure audit must state it adds zero production code"
    )
    assert "ZERO manifest change" in normalized, (
        "closure audit must state it makes zero manifest change"
    )


# ---------------------------------------------------------------------------
# 13. Negative false-claim scan (Major 3): the doc must NOT falsely claim a
#     tag / push / live run / Stage 30.8.3 start, even alongside safe text.
# ---------------------------------------------------------------------------


def test_audit_safe_negations_are_present() -> None:
    normalized = _normalized(_audit_text())
    for phrase in _REQUIRED_SAFE_NEGATIONS:
        assert phrase in normalized, (
            f"closure audit must make the safe negated claim {phrase!r}"
        )


def test_audit_has_no_unnegated_false_positive_claims() -> None:
    lowered = _normalized(_audit_text()).lower()
    for phrase in _NEGATABLE_FALSE_CLAIMS:
        hits = _unnegated_hits(lowered, phrase)
        assert not hits, (
            f"closure audit makes an un-negated false claim {phrase!r} "
            f"at offsets {hits} (only a negated form such as "
            f"'no {phrase}' is allowed)"
        )
    for phrase in _ABSOLUTE_FALSE_CLAIMS:
        assert phrase not in lowered, (
            f"closure audit carries forbidden false claim {phrase!r}"
        )


def test_negative_scan_helper_rejects_a_false_claim() -> None:
    """The negative scan must actually catch an un-negated false claim and
    pass a safely-negated one (so the guard is not vacuous).
    """
    assert _unnegated_hits("the tag created here", "tag created")
    assert not _unnegated_hits("no tag created here", "tag created")
    assert not _unnegated_hits("never push performed", "push performed")


# ---------------------------------------------------------------------------
# 14. Redaction hygiene: the audit + this test carry no forbidden needle
# ---------------------------------------------------------------------------


def test_audit_and_test_carry_no_forbidden_text_needles() -> None:
    """Case-insensitive substring scan over the closure-audit doc and this
    test file against the Stage 30.8 forbidden-needle vocabulary (imported
    as runtime-concatenated split-literals, so neither file carries the
    bare needle even inside a negative claim).
    """
    sources = {
        CLOSURE_AUDIT_BASENAME: _audit_text(),
        Path(__file__).name: Path(__file__).read_text(encoding="utf-8"),
    }
    for filename, text in sources.items():
        lowered = text.lower()
        for needle in STAGE30_8_FORBIDDEN_TEXT_NEEDLES:
            assert needle.lower() not in lowered, (
                f"Stage 30.8.2 closure file {filename!r} carries forbidden "
                f"text needle {needle!r}"
            )
