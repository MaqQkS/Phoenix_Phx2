"""Stage 30.8.0 compact session artifact / storage-readiness spec-lock
pin tests.

Pure read-only repo inspection. No live network calls, no env reads, no
Discord traffic, no provider calls. The test does not shell out to ``git``
and does not pin any git-SHA snapshot; it asserts the Stage 30.8.0
contract via direct filesystem inspection of the three-file inventory
(spec lock markdown + manifest module + this pin test) plus substring /
line-parse / AST matches against those files, plus membership checks
against the Stage 30.0 inventory allowlist.

Pinned contract:

  * The spec doc and the manifest exist.
  * The spec doc mentions the Stage 30.7 closure / handoff / proof
    context (the closure-audit + handoff doc basenames + the final
    compact proof line).
  * The spec doc defines all closed-set compact artifact kinds.
  * The spec doc defines the required identity fields.
  * The spec doc defines the safe compact content fields, including
    ``MC`` / ``LP`` / ``Net`` / ``ATH`` / ``Mig``.
  * The spec doc forbids secrets / raw provider payloads / webhook
    destination / API-key / env value / wallet / signing material.
  * The spec doc states the default storage location is outside the repo.
  * The spec doc states no writer / DB / SQLite / zstd / live / provider /
    Discord / enforcement / trading at Stage 30.8.0.
  * The spec doc references the Stage 30.6 storage budget / soft + hard
    cap policy.
  * The spec doc defines the dedupe rules.
  * The spec doc defines the redaction rules.
  * The spec doc defines the future Stage 30.8.1+ stages.
  * The manifest is constants-only (no def / class / Call; imports only
    ``__future__`` + ``typing``; no PHX2 import).
  * The Stage 30.0 inventory allowlist admits exactly the Stage 30.8.0
    files and no Stage 30.8.1+ file.
  * No runtime file is added by Stage 30.8.0 (the production-inventory
    delta is exactly the spec doc + the manifest).
  * No Stage 30.8.0 Python file carries a forbidden runtime / Stage
    21-29 / PHX1 import or a forbidden secret / transport text needle.

Stage 30.8.0 is a spec-lock / handoff document only. This test makes no
live call, sends no Discord message, and changes no runtime behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Tuple

from PHX2.stage30.stage30_8_manifest import (
    STAGE30_8_0_MINOR_VERSION,
    STAGE30_8_0_SPEC_LOCK_BASENAME,
    STAGE30_8_0_TEST_BASENAMES,
    STAGE30_8_ALLOWED_INITIAL_FILES,
    STAGE30_8_ALLOWED_STDLIB_IMPORTS,
    STAGE30_8_ARTIFACT_KINDS,
    STAGE30_8_DISK_HARD_STOP_PERCENT,
    STAGE30_8_DISK_SOFT_ALARM_PERCENT,
    STAGE30_8_FORBIDDEN_ARTIFACT_FIELDS,
    STAGE30_8_FORBIDDEN_RUNTIME_IMPORTS,
    STAGE30_8_FORBIDDEN_SURFACES,
    STAGE30_8_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_8_FUTURE_SUBSTAGE_SEQUENCE,
    STAGE30_8_IDENTITY_FIELDS,
    STAGE30_8_MANIFEST_BASENAME,
    STAGE30_8_NEXT_RECOMMENDED_STAGE,
    STAGE30_8_REDACTION_SUBSTITUTION_TOKENS,
    STAGE30_8_SAFE_COMPACT_CONTENT_FIELDS,
    STAGE30_8_STAGE_ID,
    STAGE30_8_STAGE30_7_CLOSURE_AUDIT_BASENAME,
    STAGE30_8_STAGE30_7_COMPACT_PROOF_LINE,
    STAGE30_8_STAGE30_7_HANDOFF_BASENAME,
)

# The single source of truth for the Stage 30.0 inventory allowlist. The
# Stage 30.8.0 inventory-pin tests read these frozensets directly so the
# allowlist (not a duplicated copy) is what is asserted to admit exactly
# the Stage 30.8.0 files.
from PHX2.tests.stage30.test_stage_30_0_spec_lock import (
    _STAGE30_ALLOWED_BASENAMES,
    _TESTS_STAGE30_ALLOWED_BASENAMES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
SPEC_LOCK_PATH: Path = STAGE30_ROOT / STAGE30_8_0_SPEC_LOCK_BASENAME
MANIFEST_PATH: Path = STAGE30_ROOT / STAGE30_8_MANIFEST_BASENAME
TEST_PATH: Path = TESTS_STAGE30_ROOT / STAGE30_8_0_TEST_BASENAMES[0]


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
    """Collapse all runs of whitespace into single spaces so a phrase
    that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


def _all_30_8_0_files() -> Dict[str, str]:
    return {
        "spec": _spec_text(),
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _python_30_8_0_files() -> Dict[str, str]:
    return {
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _is_real_import_line(line: str) -> bool:
    """Return True iff ``line`` is an actual Python import statement (not a
    comment, not a string-literal line inside a tuple).
    """
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if stripped.startswith("\"") or stripped.startswith("'"):
        return False
    return stripped.startswith("import ") or stripped.startswith("from ")


def _extract_imported_module(line: str) -> str:
    """Return the module token from an ``import X`` or ``from X import Y``
    line. Empty string on malformed.
    """
    stripped = line.strip()
    tokens = stripped.split()
    if len(tokens) < 2:
        return ""
    if tokens[0] in ("import", "from"):
        return tokens[1]
    return ""


# ---------------------------------------------------------------------------
# 1. (Test req 1 + 2) files exist
# ---------------------------------------------------------------------------


def test_spec_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 30.8.0 requires the spec-lock document {SPEC_LOCK_PATH}"
    )


def test_manifest_exists() -> None:
    assert MANIFEST_PATH.is_file(), (
        f"Stage 30.8.0 requires the manifest module {MANIFEST_PATH}"
    )


def test_pin_test_file_exists() -> None:
    assert TEST_PATH.is_file(), (
        f"Stage 30.8.0 requires the pin test {TEST_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Version + basename + stage id pins
# ---------------------------------------------------------------------------


def test_stage_id_and_minor_version_pinned() -> None:
    assert STAGE30_8_STAGE_ID == "30.8"
    assert STAGE30_8_0_MINOR_VERSION == "30.8.0"


def test_basenames_pinned() -> None:
    assert STAGE30_8_0_SPEC_LOCK_BASENAME == (
        "STAGE_30_8_0_COMPACT_SESSION_STORAGE_SPEC_LOCK.md"
    )
    assert STAGE30_8_MANIFEST_BASENAME == "stage30_8_manifest.py"
    assert STAGE30_8_0_TEST_BASENAMES == (
        "test_stage_30_8_0_storage_spec_lock.py",
    )


def test_next_recommended_stage_is_30_8_1() -> None:
    assert STAGE30_8_NEXT_RECOMMENDED_STAGE == "30.8.1"


def test_spec_lock_only_stance_pinned_in_doc() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30.8.0 is spec lock and tests only",
        "ZERO production `.py` file beyond the manifest",
    ):
        assert phrase in normalized, (
            f"Stage 30.8.0 spec doc must pin the spec-lock-only stance; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 3. Required section headings, in order
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: Tuple[str, ...] = (
    "# PHX2 Stage 30.8.0",
    "## 1. Stage purpose",
    "## 2. Non-goals",
    "## 3. Compact artifact types",
    "## 4. Required identity fields",
    "## 5. Required compact content fields",
    "## 6. Forbidden fields",
    "## 7. Storage location policy",
    "## 8. Retention and rolling policy",
    "## 9. Dedupe policy",
    "## 10. Redaction policy",
    "## 11. Future implementation stages",
    "## 12. Prior context and proof handoff",
    "## 13. Forbidden terms and secret hygiene",
)


def test_spec_contains_all_required_section_headings() -> None:
    text = _spec_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30.8.0 spec lock missing required section heading: "
            f"{heading!r}"
        )


def test_spec_section_headings_appear_in_order() -> None:
    text = _spec_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30.8.0 spec lock section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


# ---------------------------------------------------------------------------
# 4. (Test req 3) Stage 30.7 closure / handoff / proof context
# ---------------------------------------------------------------------------


def test_spec_mentions_stage_30_7_closure_and_proof() -> None:
    text = _spec_text()
    assert "Stage 30.7" in text, (
        "Stage 30.8.0 spec lock must reference Stage 30.7"
    )
    assert STAGE30_8_STAGE30_7_CLOSURE_AUDIT_BASENAME in text, (
        "Stage 30.8.0 spec lock must reference the Stage 30.7 closure "
        f"audit doc {STAGE30_8_STAGE30_7_CLOSURE_AUDIT_BASENAME!r}"
    )
    assert STAGE30_8_STAGE30_7_HANDOFF_BASENAME in text, (
        "Stage 30.8.0 spec lock must reference the Stage 30.7 handoff "
        f"doc {STAGE30_8_STAGE30_7_HANDOFF_BASENAME!r}"
    )
    assert STAGE30_8_STAGE30_7_COMPACT_PROOF_LINE in text, (
        "Stage 30.8.0 spec lock must carry the Stage 30.7 final compact "
        f"proof line {STAGE30_8_STAGE30_7_COMPACT_PROOF_LINE!r}"
    )


# ---------------------------------------------------------------------------
# 5. (Test req 4) all compact artifact kinds defined
# ---------------------------------------------------------------------------


def test_artifact_kinds_pinned_in_manifest() -> None:
    assert STAGE30_8_ARTIFACT_KINDS == (
        "compact_session_summary",
        "compact_ping_artifact",
        "compact_dispatch_attempt_artifact",
        "compact_error_artifact",
        "compact_storage_budget_snapshot",
    )


def test_spec_defines_all_artifact_kinds() -> None:
    text = _spec_text()
    for kind in STAGE30_8_ARTIFACT_KINDS:
        assert kind in text, (
            "Stage 30.8.0 spec lock must define the compact artifact "
            f"kind {kind!r}"
        )


# ---------------------------------------------------------------------------
# 6. (Test req 5) identity fields defined
# ---------------------------------------------------------------------------


def test_identity_fields_cover_required_axes() -> None:
    for field in (
        "stage_id",
        "run_id",
        "session_id",
        "ping_id",
        "token_mint",
        "normalized_event_id",
        "observed_at_utc",
        "artifact_created_at_utc",
        "artifact_schema_version",
        "artifact_kind",
        "dedupe_key",
        "compact_ping_schema_version",
    ):
        assert field in STAGE30_8_IDENTITY_FIELDS, (
            f"Stage 30.8 identity fields must include {field!r}"
        )


def test_spec_defines_identity_fields() -> None:
    text = _spec_text()
    for field in STAGE30_8_IDENTITY_FIELDS:
        assert field in text, (
            "Stage 30.8.0 spec lock must define the identity field "
            f"{field!r}"
        )


# ---------------------------------------------------------------------------
# 7. (Test req 6) safe compact content fields incl MC / LP / Net / ATH / Mig
# ---------------------------------------------------------------------------


def test_spec_defines_safe_compact_content_fields() -> None:
    text = _spec_text()
    assert "compact_body_text" in STAGE30_8_SAFE_COMPACT_CONTENT_FIELDS
    for field in STAGE30_8_SAFE_COMPACT_CONTENT_FIELDS:
        assert field in text, (
            "Stage 30.8.0 spec lock must define the safe compact content "
            f"field {field!r}"
        )


def test_spec_defines_mc_lp_net_ath_mig_display_tokens() -> None:
    text = _spec_text()
    for token in ("MC", "LP", "Net", "ATH", "Mig"):
        assert token in text, (
            "Stage 30.8.0 spec lock must name the compact display token "
            f"{token!r}"
        )


# ---------------------------------------------------------------------------
# 8. (Test req 7) forbidden fields: secrets / raw payloads / webhook /
#    API-key / env / wallet / signing material
# ---------------------------------------------------------------------------


def test_spec_forbids_secret_and_raw_payload_fields() -> None:
    text = _spec_text()
    for field in STAGE30_8_FORBIDDEN_ARTIFACT_FIELDS:
        assert field in text, (
            "Stage 30.8.0 spec lock must forbid the artifact field class "
            f"{field!r}"
        )


def test_forbidden_artifact_fields_cover_required_classes() -> None:
    joined = " | ".join(STAGE30_8_FORBIDDEN_ARTIFACT_FIELDS)
    for token in (
        "webhook",
        "API-key",
        "auth-metadata",
        "environment variable value",
        "raw provider payload",
        "wallet private key",
        "signing material",
        "user secret",
    ):
        assert token in joined, (
            f"Stage 30.8 forbidden artifact fields must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 9. (Test req 8) default storage outside the repo
# ---------------------------------------------------------------------------


def test_spec_states_default_storage_outside_repo() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "outside the repository" in lowered, (
        "Stage 30.8.0 spec lock must state the default storage location "
        "is outside the repository"
    )
    assert "test fixtures" in lowered and "temporary directories" in lowered, (
        "Stage 30.8.0 spec lock must restrict test fixtures to temporary "
        "directories"
    )


# ---------------------------------------------------------------------------
# 10. (Test req 9) no writer / DB / zstd / live / provider / Discord /
#     enforcement / trading at Stage 30.8.0
# ---------------------------------------------------------------------------


def test_spec_states_no_writer_db_zstd_live_provider_discord() -> None:
    lowered = _normalized(_spec_text()).lower()
    for phrase in (
        "no writer",
        "no database",
        "no sqlite",
        "no zstd",
        "no live run",
        "no provider call",
        "no discord send",
        "no enforcement",
        "no trading",
    ):
        assert phrase in lowered, (
            "Stage 30.8.0 spec lock must state the non-goal; missing "
            f"{phrase!r}"
        )


# ---------------------------------------------------------------------------
# 11. (Test req 10) Stage 30.6 storage budget / soft + hard cap reference
# ---------------------------------------------------------------------------


def test_disk_budget_thresholds_pinned_in_manifest() -> None:
    assert STAGE30_8_DISK_SOFT_ALARM_PERCENT == 65
    assert STAGE30_8_DISK_HARD_STOP_PERCENT == 90


def test_spec_references_stage_30_6_storage_budget_policy() -> None:
    normalized = _normalized(_spec_text())
    lowered = normalized.lower()
    assert "Stage 30.6" in normalized, (
        "Stage 30.8.0 spec lock must reference Stage 30.6"
    )
    assert "storage budget" in lowered, (
        "Stage 30.8.0 spec lock must reference the Stage 30.6 storage "
        "budget policy"
    )
    assert "soft cap" in lowered and "hard cap" in lowered, (
        "Stage 30.8.0 spec lock must reference the soft + hard cap policy"
    )
    assert "65%" in normalized and "90%" in normalized, (
        "Stage 30.8.0 spec lock must reference the Stage 30.6 soft 65% / "
        "hard 90% disk caps"
    )


# ---------------------------------------------------------------------------
# 12. (Test req 11) dedupe rules
# ---------------------------------------------------------------------------


def test_spec_defines_dedupe_rules() -> None:
    normalized = _normalized(_spec_text())
    lowered = normalized.lower()
    assert "dedupe" in lowered, (
        "Stage 30.8.0 spec lock must define the dedupe rules"
    )
    assert "dedupe_key" in normalized, (
        "Stage 30.8.0 spec lock must name the dedupe_key identity"
    )
    assert "exactly one terminal" in lowered, (
        "Stage 30.8.0 spec lock must pin exactly one terminal ping "
        "artifact per dedupe identity"
    )
    assert (
        "provider retry attempts are recorded as separate" in lowered
    ), (
        "Stage 30.8.0 spec lock must pin retry attempts as separate "
        "attempt artifacts"
    )


# ---------------------------------------------------------------------------
# 13. (Test req 12) redaction rules
# ---------------------------------------------------------------------------


def test_spec_defines_redaction_rules() -> None:
    normalized = _normalized(_spec_text())
    lowered = normalized.lower()
    assert "redaction" in lowered, (
        "Stage 30.8.0 spec lock must define the redaction rules"
    )
    assert "fail closed" in lowered, (
        "Stage 30.8.0 spec lock must pin the fail-closed redaction rule"
    )
    for token in STAGE30_8_REDACTION_SUBSTITUTION_TOKENS:
        assert token in normalized, (
            "Stage 30.8.0 spec lock must name the redaction substitution "
            f"token {token!r}"
        )


# ---------------------------------------------------------------------------
# 14. (Test req 13) future Stage 30.8.1+ stages
# ---------------------------------------------------------------------------


def test_future_substage_sequence_pinned_in_manifest() -> None:
    assert STAGE30_8_FUTURE_SUBSTAGE_SEQUENCE == (
        "30.8.0",
        "30.8.1",
        "30.8.2",
        "30.8.3",
        "30.8.4",
    )


def test_spec_defines_future_stages() -> None:
    text = _spec_text()
    for substage in ("Stage 30.8.1", "Stage 30.8.2", "Stage 30.8.3", "Stage 30.8.4"):
        assert substage in text, (
            "Stage 30.8.0 spec lock must define the future stage; missing "
            f"{substage!r}"
        )


# ---------------------------------------------------------------------------
# 15. (Test req 14) manifest is constants-only
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only() -> None:
    """AST proof: the manifest contains no function / class definition and
    no Call node anywhere (constants-only; the split-literal needle
    concatenations use ``+`` BinOps, never Calls), and imports only
    ``__future__`` + ``typing`` (no PHX2 import).
    """
    tree = ast.parse(_manifest_text())

    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), "Stage 30.8.0 manifest must be constants-only (no def / class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.8.0 manifest must be constants-only (no Call -- no "
            "implicit I/O at import time)"
        )

    allowed_import_roots = set(STAGE30_8_ALLOWED_STDLIB_IMPORTS)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.8.0 manifest may only import __future__ / "
                f"typing; saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.8.0 manifest may only import __future__ / "
                    f"typing; saw {alias.name!r}"
                )


def test_manifest_imports_no_phx2_module() -> None:
    for line in _manifest_text().split("\n"):
        if not _is_real_import_line(line):
            continue
        module = _extract_imported_module(line)
        assert not module.startswith("PHX2"), (
            "Stage 30.8.0 manifest must import no PHX2 module; saw "
            f"{module!r}"
        )


# ---------------------------------------------------------------------------
# 16. (Test req 15 + 16) Stage 30.0 inventory allowlist admits exactly the
#     30.8.0 files; no Stage 30.8.1+ file is admitted.
# ---------------------------------------------------------------------------


def test_allowed_initial_files_are_exactly_spec_and_manifest() -> None:
    assert STAGE30_8_ALLOWED_INITIAL_FILES == (
        STAGE30_8_0_SPEC_LOCK_BASENAME,
        STAGE30_8_MANIFEST_BASENAME,
    )


def test_stage30_0_allowlist_admits_the_30_8_0_files() -> None:
    """The Stage 30.0 inventory allowlist (the single source of truth)
    must admit exactly the Stage 30.8.0 spec doc + manifest + pin test.
    """
    assert STAGE30_8_0_SPEC_LOCK_BASENAME in _STAGE30_ALLOWED_BASENAMES
    assert STAGE30_8_MANIFEST_BASENAME in _STAGE30_ALLOWED_BASENAMES
    assert (
        STAGE30_8_0_TEST_BASENAMES[0] in _TESTS_STAGE30_ALLOWED_BASENAMES
    )
    # And they exist on disk.
    assert SPEC_LOCK_PATH.is_file()
    assert MANIFEST_PATH.is_file()
    assert TEST_PATH.is_file()


def test_stage30_0_allowlist_admits_no_stage_30_8_1_plus_file() -> None:
    """No Stage 30.8.1+ production / test basename is admitted by the
    Stage 30.0 allowlist yet.
    """
    future_tokens = ("30_8_1", "30_8_2", "30_8_3", "30_8_4")
    for basename in _STAGE30_ALLOWED_BASENAMES:
        for token in future_tokens:
            assert token not in basename, (
                "Stage 30.0 production allowlist must not admit a Stage "
                f"30.8.1+ file yet; saw {basename!r}"
            )
    for basename in _TESTS_STAGE30_ALLOWED_BASENAMES:
        for token in future_tokens:
            assert token not in basename, (
                "Stage 30.0 test allowlist must not admit a Stage 30.8.1+ "
                f"test file yet; saw {basename!r}"
            )


def test_only_stage30_8_production_files_are_spec_and_manifest() -> None:
    """Every Stage 30.8 entry under ``PHX2/stage30/`` must be exactly the
    spec doc or the manifest; NO Stage 30.8.1+ production file (a models
    module, a writer, a dedupe index) may exist yet.
    """
    observed = {
        entry.name
        for entry in STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and (
            entry.name.startswith("stage30_8")
            or entry.name.startswith("STAGE_30_8")
        )
    }
    allowed = {STAGE30_8_0_SPEC_LOCK_BASENAME, STAGE30_8_MANIFEST_BASENAME}
    assert observed == allowed, (
        "Stage 30.8 production entries must be exactly the spec lock + "
        f"manifest; unexpected entries: {sorted(observed - allowed)}"
    )


def test_only_stage30_8_test_file_is_the_pin_test() -> None:
    observed = {
        entry.name
        for entry in TESTS_STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and entry.name.startswith("test_stage_30_8")
    }
    allowed = {STAGE30_8_0_TEST_BASENAMES[0]}
    assert observed == allowed, (
        "Stage 30.8 test entries must be exactly the 30.8.0 pin test; "
        f"unexpected entries: {sorted(observed - allowed)}"
    )


# ---------------------------------------------------------------------------
# 17. (Test req 17) no runtime file added / edited by Stage 30.8.0
# ---------------------------------------------------------------------------


def test_no_runtime_file_added_by_stage_30_8_0() -> None:
    """The Stage 30.8.0 production-inventory delta is exactly the spec doc
    + the constants-only manifest. The only NEW production .py is the
    manifest (no runtime orchestrator / renderer / model / writer file is
    added). The git-level proof (no runtime file MODIFIED) is recorded in
    the closure report; this unit-level pin asserts the additive delta.
    """
    # The only scanned production .py is the manifest.
    py_additions = [
        name
        for name in STAGE30_8_ALLOWED_INITIAL_FILES
        if name.endswith(".py")
    ]
    assert py_additions == [STAGE30_8_MANIFEST_BASENAME], (
        "Stage 30.8.0 may add only the constants-only manifest as a new "
        f".py file; saw {py_additions!r}"
    )
    # No runtime orchestrator / renderer / model basename is in the delta.
    runtime_markers = (
        "orchestrator",
        "renderer",
        "compact_ping_models",
        "tier_decision",
        "writer",
    )
    for name in STAGE30_8_ALLOWED_INITIAL_FILES:
        for marker in runtime_markers:
            assert marker not in name, (
                "Stage 30.8.0 must add no runtime file; the delta names a "
                f"runtime marker {marker!r} in {name!r}"
            )


# ---------------------------------------------------------------------------
# 18. Forbidden runtime / Stage 21-29 / PHX1 imports
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


def test_no_forbidden_runtime_imports_in_30_8_0_files() -> None:
    for filename, text in _python_30_8_0_files().items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for prefix in _FORBIDDEN_MODULE_PREFIXES:
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.8.0 file {filename!r} imports forbidden "
                    f"module {module!r} on line {line.rstrip()!r}"
                )


def test_no_stage21_29_or_phx1_imports_in_30_8_0_production() -> None:
    """The manifest imports no Stage 21-29 / Stage 29.5 / PHX1 production
    module. (This pin test legitimately imports the Stage 30.0 sibling
    TEST module to read the inventory allowlist; that is asserted to be a
    PHX2.tests import, never a PHX2 stage-21-29 production import.)
    """
    text = _manifest_text()
    for line in text.split("\n"):
        if not _is_real_import_line(line):
            continue
        module = _extract_imported_module(line)
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}"), (
                "Stage 30.8.0 manifest imports forbidden Stage 21-29 "
                f"module {module!r}"
            )
        assert not module.startswith("PHX1"), (
            f"Stage 30.8.0 manifest imports forbidden PHX1 module {module!r}"
        )


def test_forbidden_runtime_imports_tuple_is_non_empty() -> None:
    assert len(STAGE30_8_FORBIDDEN_RUNTIME_IMPORTS) >= 20, (
        "STAGE30_8_FORBIDDEN_RUNTIME_IMPORTS must enumerate the forbidden "
        "runtime import surfaces"
    )


# ---------------------------------------------------------------------------
# 19. Forbidden secret / transport / URL / raw-payload text needle scan
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles_in_30_8_0_files() -> None:
    """Case-insensitive substring scan over the spec lock, the manifest,
    and this test file. The manifest's ``STAGE30_8_FORBIDDEN_TEXT_NEEDLES``
    tuple uses split-literal forms so the manifest source itself does not
    carry the bare needles; this test imports the values at runtime and
    scans every Stage 30.8.0 file.
    """
    for filename, text in _all_30_8_0_files().items():
        lower = text.lower()
        for needle in STAGE30_8_FORBIDDEN_TEXT_NEEDLES:
            needle_lower = needle.lower()
            assert needle_lower not in lower, (
                f"Stage 30.8.0 file {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_forbidden_text_needles_tuple_is_non_empty() -> None:
    assert len(STAGE30_8_FORBIDDEN_TEXT_NEEDLES) >= 12, (
        "STAGE30_8_FORBIDDEN_TEXT_NEEDLES must enumerate the forbidden "
        "text needles"
    )


# ---------------------------------------------------------------------------
# 20. Forbidden surfaces documentation tuple covers key scopes
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_8_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_8_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_8_FORBIDDEN_SURFACES)
    for token in (
        "writer implementation",
        "database implementation",
        "SQLite implementation",
        "filesystem artifact writer implementation",
        "zstd implementation",
        "live run",
        "provider call",
        "Discord send",
        "enforcement",
        "public routing",
        "trading",
        "wallet",
        "Stage 25/27/28/29 production import",
        "Stage 29.5 production import",
        "Stage 30.7 file edit",
        "Stage 30.8.1+ implementation file",
        "commit",
        "tag",
        "push",
    ):
        assert token in joined, (
            f"Stage 30.8 forbidden surfaces must name {token!r}"
        )
