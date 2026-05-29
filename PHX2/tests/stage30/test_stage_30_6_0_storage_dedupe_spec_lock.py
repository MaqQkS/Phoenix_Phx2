"""Stage 30.6.0 storage + dedupe spec-lock pin tests.

Pure read-only repo inspection. No live network calls, no env
reads, no Discord traffic, no provider calls. The test does not
shell out to ``git`` and does not pin any git-SHA snapshot; it
asserts the Stage 30.6.0 contract via direct filesystem inspection
of the three-file inventory (spec lock markdown + manifest module +
this pin test) plus substring / line-parse / AST matches against
those files.

Pinned contract:

  * The spec doc, the manifest, and this pin test exist.
  * The spec doc carries the twelve required section headings in
    order.
  * The spec references all four storage lifecycle tiers (Tier 0
    WAL buffer / Tier 1 hot raw / Tier 2 durable token summary /
    Tier 3 sealed archive), by human label and by closed-set token.
  * The spec requires dedupe / session persistence with a restart-
    safe seen-state, the closed-set re-alert triggers, and the
    dedupe-key components.
  * The spec requires soft (around 65%) and hard (around 90%) disk
    budget guardrails that fail closed, with prune not the first
    line of defense.
  * The spec requires day rolling and zstd / archive compression,
    and forbids a single giant forever-growing file.
  * The spec requires that the raw stream is not kept forever.
  * The spec requires main-database anti-bloat.
  * The spec requires a per-run storage summary plus a pre-archive
    redaction scan and operator-visible warnings.
  * The spec declares the Stage 30.6.0 non-goals.
  * The spec declares the future slices (30.6.1 .. 30.6.5 + 30.7).
  * The spec forbids ATH implementation in this stage and hands ATH
    off to Stage 30.7.
  * The spec forbids live / provider / Discord / runtime changes.
  * The Stage 30.6.0 inventory delta admits only the spec doc plus
    the manifest (no Stage 30.6.1+ implementation file); the only
    Stage 30.6 files present are the spec doc and the manifest.
  * The manifest is constants-only (no Call, no def / class, only
    ``__future__`` + ``typing`` imports).
  * No Stage 30.6.0 Python file carries a forbidden runtime import
    or a forbidden Stage 21-29 / PHX1 import.
  * No Stage 30.6.0 file carries a forbidden secret / transport /
    URL-scheme / raw-payload text needle (split-literal needles so
    this test's own source carries none of them either).

Stage 30.6.0 is a spec-lock / handoff document only. This test
makes no live call, sends no Discord message, and changes no
runtime behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Tuple

from PHX2.stage30.stage30_6_manifest import (
    STAGE30_6_0_MINOR_VERSION,
    STAGE30_6_0_TEST_BASENAMES,
    STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_0,
    STAGE30_6_ATH_HANDOFF_SUBSTAGE,
    STAGE30_6_DEDUPE_KEY_COMPONENTS,
    STAGE30_6_DISK_HARD_STOP_PERCENT,
    STAGE30_6_DISK_SOFT_ALARM_PERCENT,
    STAGE30_6_FORBIDDEN_RUNTIME_IMPORTS,
    STAGE30_6_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_6_MANIFEST_BASENAME,
    STAGE30_6_MINOR_VERSION,
    STAGE30_6_REALERT_TRIGGER_NAMES,
    STAGE30_6_SPEC_BASENAME,
    STAGE30_6_STORAGE_SUMMARY_FIELD_NAMES,
    STAGE30_6_STORAGE_TIER_LABELS,
    STAGE30_6_STORAGE_TIER_NAMES,
    STAGE30_6_SUBSTAGE_SEQUENCE,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
SPEC_LOCK_PATH: Path = STAGE30_ROOT / STAGE30_6_SPEC_BASENAME
MANIFEST_PATH: Path = STAGE30_ROOT / STAGE30_6_MANIFEST_BASENAME
TEST_PATH: Path = (
    TESTS_STAGE30_ROOT / "test_stage_30_6_0_storage_dedupe_spec_lock.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


def _test_text() -> str:
    return TEST_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


def _all_30_6_0_files() -> Dict[str, str]:
    return {
        "spec": _spec_text(),
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _python_30_6_0_files() -> Dict[str, str]:
    return {
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _is_real_import_line(line: str) -> bool:
    """Return True iff ``line`` is an actual Python import statement
    (not a comment, not a string-literal line inside a tuple).
    """
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if stripped.startswith("\"") or stripped.startswith("'"):
        return False
    return (
        stripped.startswith("import ")
        or stripped.startswith("from ")
    )


def _extract_imported_module(line: str) -> str:
    """Return the module token from an ``import X`` or ``from X
    import Y`` line. Empty string on malformed.
    """
    stripped = line.strip()
    tokens = stripped.split()
    if len(tokens) < 2:
        return ""
    if tokens[0] in ("import", "from"):
        return tokens[1]
    return ""


# ---------------------------------------------------------------------------
# 1. Files exist
# ---------------------------------------------------------------------------


def test_spec_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 30.6.0 requires the spec-lock document "
        f"{SPEC_LOCK_PATH}"
    )


def test_manifest_exists() -> None:
    assert MANIFEST_PATH.is_file(), (
        f"Stage 30.6.0 requires the manifest module {MANIFEST_PATH}"
    )


def test_pin_test_file_exists() -> None:
    assert TEST_PATH.is_file(), (
        f"Stage 30.6.0 requires the pin test {TEST_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Minor version + basename pins
# ---------------------------------------------------------------------------


def test_minor_versions_pinned() -> None:
    assert STAGE30_6_MINOR_VERSION == "30.6"
    assert STAGE30_6_0_MINOR_VERSION == "30.6.0"


def test_spec_basename_pinned() -> None:
    assert STAGE30_6_SPEC_BASENAME == (
        "STAGE_30_6_0_STORAGE_DEDUPE_SPEC_LOCK.md"
    )


def test_manifest_basename_pinned() -> None:
    assert STAGE30_6_MANIFEST_BASENAME == "stage30_6_manifest.py"


def test_test_basenames_pinned() -> None:
    assert STAGE30_6_0_TEST_BASENAMES == (
        "test_stage_30_6_0_storage_dedupe_spec_lock.py",
    )


def test_spec_lock_only_stance_pinned_in_doc() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30.6.0 is spec lock and tests only",
        "ZERO production `.py` file beyond the manifest",
    ):
        assert phrase in normalized, (
            f"Stage 30.6.0 spec doc must pin the spec-lock-only "
            f"stance; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 3. Required section headings, in order
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: Tuple[str, ...] = (
    "# PHX2 Stage 30.6.0",
    "## 1. Stage 30.6 scope and stance",
    "## 2. 24/7 readiness definition",
    "## 3. Storage lifecycle tiers",
    "## 4. Dedupe and session persistence",
    "## 5. Disk budget guardrails",
    "## 6. Day rolling and archive compression",
    "## 7. Database anti-bloat",
    "## 8. Observability and per-run storage summary",
    "## 9. Prior art and reuse",
    "## 10. Non-goals",
    "## 11. Future slices",
    "## 12. Forbidden terms and secret hygiene",
)


def test_spec_contains_all_required_section_headings() -> None:
    text = _spec_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30.6.0 spec lock missing required section "
            f"heading: {heading!r}"
        )


def test_spec_section_headings_appear_in_order() -> None:
    text = _spec_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30.6.0 spec lock section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


# ---------------------------------------------------------------------------
# 4. (Test req 15) 24/7 readiness definition
# ---------------------------------------------------------------------------


_REQUIRED_READINESS_PHRASES: Tuple[str, ...] = (
    "controlled private soak mode",
    "bounded write growth",
    "dedupe / session persistence",
    "restart-safe seen-state",
    "disk budget guardrails",
    "no public routing",
    "no enforcement by default",
    "filters observe-only unless later promoted",
    "operator kill switch",
)


def test_spec_pins_24_7_readiness_definition() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_READINESS_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must pin the 24/7 readiness "
            f"definition clause; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 5. (Test req 2) all required storage lifecycle tiers
# ---------------------------------------------------------------------------


def test_spec_references_all_storage_tier_labels() -> None:
    text = _spec_text()
    for label in STAGE30_6_STORAGE_TIER_LABELS:
        assert label in text, (
            "Stage 30.6.0 spec lock must reference the storage "
            f"lifecycle tier label; missing {label!r}"
        )


def test_spec_references_all_storage_tier_tokens() -> None:
    text = _spec_text()
    for token in STAGE30_6_STORAGE_TIER_NAMES:
        assert token in text, (
            "Stage 30.6.0 spec lock must reference the closed-set "
            f"storage tier token; missing {token!r}"
        )


_REQUIRED_TIER_DETAIL_PHRASES: Tuple[str, ...] = (
    # Tier 0 / WAL buffer
    "short-lived rotating raw buffer",
    "safe to delete",
    "crash / replay / debug only",
    # Tier 1 / Hot raw
    "retention target around 24-48h",
    "day-rolled or mint-scoped chunks",
    # Tier 2 / Durable token summary
    "one evolving aggregate per mint / session",
    "durable but compact",
    "carries no raw provider payloads",
    # Tier 3 / Sealed archive
    "immutable compact summary",
    "eligible for deletion after seal",
    "daily archive files are preferred",
)


def test_spec_pins_per_tier_detail() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_TIER_DETAIL_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must pin the per-tier detail; "
            f"missing {phrase!r}"
        )


def test_spec_pins_lifecycle_not_time_only() -> None:
    normalized = _normalized(_spec_text())
    assert (
        "lifecycle-tier storage model, NOT a simple time-only "
        "storage model"
    ) in normalized, (
        "Stage 30.6.0 spec lock must pin lifecycle-tier (not "
        "time-only) storage"
    )


# ---------------------------------------------------------------------------
# 6. (Test req 3) dedupe / session persistence
# ---------------------------------------------------------------------------


_REQUIRED_DEDUPE_PHRASES: Tuple[str, ...] = (
    "no repeated first ping for the same mint in the same session",
    "no repeated same tier for the same mint",
    "ping again only on a meaningful state change",
    "restart-safe",
)


def test_spec_pins_dedupe_session_persistence() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_DEDUPE_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must pin the dedupe / session "
            f"persistence rule; missing {phrase!r}"
        )


def test_spec_pins_all_realert_triggers() -> None:
    text = _spec_text()
    for trigger in STAGE30_6_REALERT_TRIGGER_NAMES:
        assert trigger in text, (
            "Stage 30.6.0 spec lock must pin the closed-set "
            f"re-alert trigger; missing {trigger!r}"
        )


def test_spec_pins_dedupe_key_components() -> None:
    normalized = _normalized(_spec_text())
    # The dedupe key must include mint + alert/tier/state class +
    # policy-version / session-scope axis.
    assert (
        "must include the mint plus an alert / tier / state class "
        "plus a policy-version / session-scope axis"
    ) in normalized, (
        "Stage 30.6.0 spec lock must pin the dedupe-key composition"
    )
    for component in STAGE30_6_DEDUPE_KEY_COMPONENTS:
        assert component in _manifest_text(), (
            "Stage 30.6.0 manifest must pin the dedupe-key "
            f"component {component!r}"
        )


def test_spec_pins_restart_safe_before_24h_soak() -> None:
    normalized = _normalized(_spec_text())
    assert "restart-safe before any 24h soak" in normalized, (
        "Stage 30.6.0 spec lock must pin restart-safe seen-state "
        "before a 24h soak"
    )


# ---------------------------------------------------------------------------
# 7. (Test req 4) soft / hard disk budget guardrails
# ---------------------------------------------------------------------------


def test_disk_budget_thresholds_pinned_in_manifest() -> None:
    assert STAGE30_6_DISK_SOFT_ALARM_PERCENT == 65
    assert STAGE30_6_DISK_HARD_STOP_PERCENT == 90


_REQUIRED_DISK_PHRASES: Tuple[str, ...] = (
    "soft disk alarm around 65%",
    "hard stop around 90%",
    "fail closed",
    "prune is not the first line of defense",
    "a full disk never produces a weird crash",
    "storage budget is visible in the per-run storage summary",
)


def test_spec_pins_disk_budget_guardrails() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_DISK_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must pin the disk-budget "
            f"guardrail; missing {phrase!r}"
        )


def test_spec_disk_percentages_present() -> None:
    text = _spec_text()
    assert "65%" in text
    assert "90%" in text


# ---------------------------------------------------------------------------
# 8. (Test req 5) day rolling + zstd / archive compression
# ---------------------------------------------------------------------------


_REQUIRED_ROLLING_PHRASES: Tuple[str, ...] = (
    "day-rolling files for artifacts and logs",
    "zstd compression for older archives where applicable",
    "no single giant forever-growing file",
    "archives are compressed or deleted by date or by lifecycle "
    "seal",
)


def test_spec_pins_day_rolling_and_compression() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_ROLLING_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must pin day-rolling / archive "
            f"compression; missing {phrase!r}"
        )


def test_spec_names_zstd_as_doc_target_only() -> None:
    normalized = _normalized(_spec_text())
    assert "zstd" in normalized, (
        "Stage 30.6.0 spec lock must name zstd as a design target"
    )
    assert (
        "adds no zstd dependency and no zstd implementation"
    ) in normalized, (
        "Stage 30.6.0 spec lock must pin that zstd is doc-only at "
        "this stage"
    )


# ---------------------------------------------------------------------------
# 9. (Test req 6) raw stream not kept forever
# ---------------------------------------------------------------------------


def test_spec_pins_raw_stream_not_kept_forever() -> None:
    normalized = _normalized(_spec_text())
    assert "the raw stream is not kept forever" in normalized, (
        "Stage 30.6.0 spec lock must pin that the raw stream is not "
        "kept forever"
    )


# ---------------------------------------------------------------------------
# 10. (Test req 7) main database anti-bloat
# ---------------------------------------------------------------------------


_REQUIRED_DB_PHRASES: Tuple[str, ...] = (
    "no raw per-trade / per-event rows are kept forever in the "
    "main database",
    "the main database stores only compact durable summaries, "
    "dedupe state, the ping ledger, and sealed lifecycle summaries",
    "raw event payloads belong in short-lived files or compressed "
    "archives, not in unbounded database tables",
    "future migrations must include size / retention expectations",
)


def test_spec_pins_database_anti_bloat() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_DB_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must pin the database "
            f"anti-bloat rule; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 11. (Test req 8) per-run storage summary + redaction + warnings
# ---------------------------------------------------------------------------


_REQUIRED_OBSERVABILITY_PHRASES: Tuple[str, ...] = (
    "per-run storage summary",
    "raw bytes written",
    "durable rows written",
    "archived / compressed bytes",
    "dropped / pruned / sealed counts",
    "dedupe suppressed counts",
    "disk usage before and after",
    "a redaction scan runs before any archive proof is considered "
    "safe",
    "operator-visible warnings",
)


def test_spec_pins_per_run_storage_summary() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_OBSERVABILITY_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must pin the observability / "
            f"per-run storage summary; missing {phrase!r}"
        )


def test_storage_summary_field_names_pinned_in_manifest() -> None:
    assert STAGE30_6_STORAGE_SUMMARY_FIELD_NAMES == (
        "raw_bytes_written",
        "durable_rows_written",
        "archived_compressed_bytes",
        "dropped_count",
        "pruned_count",
        "sealed_count",
        "dedupe_suppressed_count",
        "disk_usage_percent_before",
        "disk_usage_percent_after",
    )


# ---------------------------------------------------------------------------
# 12. (Test req 9) Stage 30.6.0 non-goals declared
# ---------------------------------------------------------------------------


_REQUIRED_NON_GOAL_PHRASES: Tuple[str, ...] = (
    "implement a storage writer",
    "implement a dedupe engine",
    "run live",
    "send Discord",
    "add ATH",
    "add filters",
    "add enforcement",
    "add public routing",
    "add trading / wallet logic",
    "add a zstd dependency",
)


def test_spec_declares_non_goals() -> None:
    normalized = _normalized(_spec_text())
    assert "Stage 30.6.0 explicitly does NOT" in normalized, (
        "Stage 30.6.0 spec lock must declare an explicit non-goals "
        "list"
    )
    for phrase in _REQUIRED_NON_GOAL_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must declare the non-goal; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 13. (Test req 10) future slices declared
# ---------------------------------------------------------------------------


def test_substage_sequence_pinned_in_manifest() -> None:
    assert STAGE30_6_SUBSTAGE_SEQUENCE == (
        "30.6.0",
        "30.6.1",
        "30.6.2",
        "30.6.3",
        "30.6.4",
        "30.6.5",
    )
    assert STAGE30_6_ATH_HANDOFF_SUBSTAGE == "30.7"


_REQUIRED_FUTURE_SLICE_PHRASES: Tuple[str, ...] = (
    "Stage 30.6.1 — storage budget models + pure policy evaluator",
    "Stage 30.6.2 — rotating WAL / day-rolled artifact writer "
    "scaffold",
    "Stage 30.6.3 — dedupe / session ledger scaffold",
    "Stage 30.6.4 — lifecycle seal aggregate contract",
    "Stage 30.6.5 — storage / dedupe offline integration proof",
    "Stage 30.7 — ATH context bridge",
)


def test_spec_declares_future_slices() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_FUTURE_SLICE_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must declare the future slice; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 14. (Test req 11) ATH forbidden in this stage; handed to 30.7
# ---------------------------------------------------------------------------


def test_spec_forbids_ath_implementation_here() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30.6.0 does not implement ATH",
        "ATH context is Stage 30.7",
        "No ATH mapping, no ATH basis, and no ATH storage column "
        "ships in any Stage 30.6 storage slice",
    ):
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must forbid ATH implementation "
            f"in this stage; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 15. (Test req 12) live / provider / Discord / runtime forbidden
# ---------------------------------------------------------------------------


_REQUIRED_NO_LIVE_PHRASES: Tuple[str, ...] = (
    "There is no live provider call during Stage 30.6.0 "
    "implementation.",
    "There is no Discord send during Stage 30.6.0 implementation.",
    "There is no runtime logic change and no Stage 27 / 28 / 29 "
    "production change at Stage 30.6.0.",
    "There is no Stage 30.1 / 30.2 / 30.3 / 30.4 / 30.5 runtime "
    "change at Stage 30.6.0.",
    "There is no storage writer, no dedupe engine, no database "
    "migration, and no filesystem writer at Stage 30.6.0.",
    "There is no zstd dependency and no zstd implementation added "
    "at Stage 30.6.0.",
)


def test_spec_forbids_live_provider_discord_runtime() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_NO_LIVE_PHRASES:
        assert phrase in normalized, (
            "Stage 30.6.0 spec lock must forbid live / provider / "
            f"Discord / runtime changes; missing {phrase!r}"
        )


def test_spec_forbids_commit_tag_push() -> None:
    normalized = _normalized(_spec_text())
    assert (
        "There is no commit, no tag, and no push performed by "
        "Stage 30.6.0 implementation."
    ) in normalized, (
        "Stage 30.6.0 spec lock must pin no commit / tag / push"
    )


# ---------------------------------------------------------------------------
# 16. (Test req 13 + 15) inventory allowlist admits only 30.6.0 files;
#     no Stage 30.6.1+ implementation file; no runtime file changed.
# ---------------------------------------------------------------------------


def test_allowed_basenames_are_only_spec_and_manifest() -> None:
    """The Stage 30.6.0 production-inventory delta is exactly the
    new spec lock plus the new manifest. Stage 30.6.0 modifies NO
    Stage 30.1 / 30.2 / 30.3 / 30.4 / 30.5 runtime file.
    """
    assert STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_0 == (
        STAGE30_6_SPEC_BASENAME,
        STAGE30_6_MANIFEST_BASENAME,
    )
    for basename in STAGE30_6_ALLOWED_STAGE30_BASENAMES_FOR_30_6_0:
        assert (STAGE30_ROOT / basename).is_file()


def test_only_stage30_6_production_files_are_spec_and_manifest() -> None:
    """The Stage 30.6.0 production-inventory delta is the spec doc +
    the manifest. Stage 30.6.1 additionally ships the storage budget
    models + evaluator (a pure offline policy brain). Every Stage 30.6
    entry under ``PHX2/stage30/`` must be exactly one of those four
    files; NO Stage 30.6.2+ production file (a WAL / day-rolled writer,
    a dedupe ledger, a seal aggregate, a database migration) may exist
    yet.
    """
    observed = {
        entry.name
        for entry in STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and (
            entry.name.startswith("stage30_6")
            or entry.name.startswith("STAGE_30_6")
        )
    }
    allowed = {
        STAGE30_6_SPEC_BASENAME,
        STAGE30_6_MANIFEST_BASENAME,
        # Stage 30.6.1 storage budget models + pure policy evaluator
        # (narrow authorized relaxation; no Stage 30.6.2+ file).
        "stage30_6_storage_budget_models.py",
        "stage30_6_storage_budget_evaluator.py",
    }
    assert observed == allowed, (
        "Stage 30.6 production entries must be exactly the spec lock + "
        "manifest (30.6.0) plus the storage budget models + evaluator "
        f"(30.6.1); unexpected entries: {sorted(observed - allowed)}"
    )


def test_only_stage30_6_test_file_is_the_pin_test() -> None:
    """Stage 30.6.0 ships the pin test; Stage 30.6.1 additionally ships
    its four storage budget tests (models, evaluator, boundaries,
    manifest). NO Stage 30.6.2+ test file may exist yet.
    """
    observed = {
        entry.name
        for entry in TESTS_STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and entry.name.startswith("test_stage_30_6")
    }
    allowed = {
        "test_stage_30_6_0_storage_dedupe_spec_lock.py",
        # Stage 30.6.1 storage budget tests (narrow authorized
        # relaxation; no Stage 30.6.2+ test file).
        "test_stage_30_6_1_storage_budget_models.py",
        "test_stage_30_6_1_storage_budget_evaluator.py",
        "test_stage_30_6_1_boundaries.py",
        "test_stage_30_6_1_manifest.py",
    }
    assert observed == allowed, (
        "Stage 30.6 test entries must be exactly the 30.6.0 pin test "
        "plus the four 30.6.1 storage budget tests; unexpected "
        f"entries: {sorted(observed - allowed)}"
    )


# ---------------------------------------------------------------------------
# 17. (Test req 14) manifest is constants-only
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only() -> None:
    """AST proof: the manifest contains no function / class
    definition and no Call node anywhere (constants-only; the
    split-literal needle concatenations use ``+`` BinOps, never
    Calls), and imports only ``__future__`` + ``typing``.
    """
    tree = ast.parse(_manifest_text())

    # No def / class anywhere.
    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), (
            "Stage 30.6.0 manifest must be constants-only "
            "(no def / class)"
        )
        assert not isinstance(node, ast.Call), (
            "Stage 30.6.0 manifest must be constants-only "
            "(no Call -- no implicit I/O at import time)"
        )

    # Only __future__ + typing imports at module level.
    allowed_import_roots = {"__future__", "typing"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.6.0 manifest may only import "
                f"__future__ / typing; saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.6.0 manifest may only import "
                    f"__future__ / typing; saw {alias.name!r}"
                )


# ---------------------------------------------------------------------------
# 18. No forbidden runtime / Stage 21-29 / PHX1 imports in 30.6.0 files
# ---------------------------------------------------------------------------


_FORBIDDEN_MODULE_PREFIXES: Tuple[str, ...] = (
    "os",
    "dotenv",
    "keyring",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "grpc",
    "sqlite3",
    "zstandard",
    "zstd",
)


def test_no_forbidden_runtime_imports_in_30_6_0_files() -> None:
    py_files = _python_30_6_0_files()
    for filename, text in py_files.items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for prefix in _FORBIDDEN_MODULE_PREFIXES:
                assert not (
                    module == prefix
                    or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.6.0 file {filename!r} imports "
                    f"forbidden module {module!r} on line "
                    f"{line.rstrip()!r}"
                )


def test_no_stage21_29_or_phx1_imports_in_30_6_0_files() -> None:
    py_files = _python_30_6_0_files()
    for filename, text in py_files.items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for stage_n in range(21, 30):
                forbidden_prefix = f"PHX2.stage{stage_n}"
                assert not module.startswith(forbidden_prefix), (
                    f"Stage 30.6.0 file {filename!r} imports "
                    f"forbidden Stage 21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.6.0 file {filename!r} imports forbidden "
                f"PHX1 module {module!r}"
            )


def test_forbidden_runtime_imports_tuple_is_non_empty() -> None:
    assert len(STAGE30_6_FORBIDDEN_RUNTIME_IMPORTS) >= 20, (
        "STAGE30_6_FORBIDDEN_RUNTIME_IMPORTS must enumerate the "
        "forbidden runtime import surfaces"
    )


# ---------------------------------------------------------------------------
# 19. No forbidden secret / transport / URL / raw-payload text needle
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles_in_30_6_0_files() -> None:
    """Case-insensitive substring scan over the spec lock, the
    manifest, and this test file. The manifest's
    ``STAGE30_6_FORBIDDEN_TEXT_NEEDLES`` tuple uses split-literal
    forms so the manifest source itself does not carry the bare
    needles; this test imports the values at runtime and scans
    every Stage 30.6.0 file.
    """
    files = _all_30_6_0_files()
    for filename, text in files.items():
        lower = text.lower()
        for needle in STAGE30_6_FORBIDDEN_TEXT_NEEDLES:
            needle_lower = needle.lower()
            assert needle_lower not in lower, (
                f"Stage 30.6.0 file {filename!r} carries forbidden "
                f"text needle {needle!r}"
            )


def test_forbidden_text_needles_tuple_is_non_empty() -> None:
    assert len(STAGE30_6_FORBIDDEN_TEXT_NEEDLES) >= 12, (
        "STAGE30_6_FORBIDDEN_TEXT_NEEDLES must enumerate the "
        "forbidden text needles"
    )
