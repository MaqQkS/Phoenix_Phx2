"""Stage 20.4 locked constants.

All E20xx / W20xx codes used by closure, the handoff contract
version, hardcoded safety flags, forbidden-import module lists
(inner + outer scope), forbidden / warning token regex patterns,
expected upstream artifact filenames, the closure output filename
set, the run-log event sequence, the run-id format, and the
locked checklist row order live in this module.

Hand-duplicated upstream values:

  * Stage 20.2 manifest field name(s) Stage 20.4 reads
    (``safe_for_live_dispatch``).
  * Stage 20.3 manifest field names Stage 20.4 reads
    (``safe_for_live_dispatch``, ``live_dispatch_ready``,
    ``stage20_2_lineage`` block, individual lineage hash field
    names).
  * Stage 20.2 / Stage 20.3 artifact filenames.

This follows the 20.1 cross-stage hygiene precedent: closure
production code does NOT import constants from
``PHX2.stage20.constants``; the duplication IS the contract. A
drift in any upstream schema yields a loud Stage 20.4 error
rather than a silent re-aliasing.

Phoenix1 departure note: this module imports no Phoenix1 code
and references Phoenix1 only as a forbidden-module list entry.

What Stage 20.4 will NOT do (relevant here):

  * No constants that flip ``SAFE_FOR_LIVE_DISPATCH`` or
    ``LIVE_DISPATCH_READY`` to True; both are hardcoded False
    and are not operator-overridable.
  * No constants for any Stage 21 surface; Stage 21 is out of
    scope.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


# ---------------------------------------------------------------------------
# Stage 20.4 identity / contract version
# ---------------------------------------------------------------------------


STAGE20_4_MINOR_VERSION: str = "20.4"
HANDOFF_CONTRACT_VERSION: str = (
    "stage20_to_stage21_private_preview_handoff_v0"
)


# ---------------------------------------------------------------------------
# Hardcoded safety flags (always False; never operator-overridable)
# ---------------------------------------------------------------------------


SAFE_FOR_LIVE_DISPATCH: bool = False
LIVE_DISPATCH_READY: bool = False


# ---------------------------------------------------------------------------
# Closure status values (closed set; only these two)
# ---------------------------------------------------------------------------


CLOSURE_STATUS_CLOSED_PENDING_OPERATOR_REVIEW: str = (
    "closed_pending_operator_review"
)
CLOSURE_STATUS_BLOCKED: str = "closure_blocked"

CLOSURE_STATUS_VALUES: tuple[str, ...] = (
    CLOSURE_STATUS_CLOSED_PENDING_OPERATOR_REVIEW,
    CLOSURE_STATUS_BLOCKED,
)


# ---------------------------------------------------------------------------
# Stage 20.4 error codes (closed set; every hit blocks closure)
# ---------------------------------------------------------------------------
#
# E2049 is intentionally NOT defined in Stage 20.4 v0.


ERROR_CODES: tuple[str, ...] = (
    "E2030",
    "E2031",
    "E2032",
    "E2033",
    "E2034",
    "E2035",
    "E2036",
    "E2037",
    "E2038",
    "E2039",
    "E2040",
    "E2041",
    "E2042",
    "E2043",
    "E2044",
    "E2045",
    "E2046",
    "E2047",
    "E2048",
)


ERROR_CODE_NAMES: Mapping[str, str] = MappingProxyType({
    "E2030": "STAGE20_2_RUN_DIR_MISSING_OR_NOT_DIR",
    "E2031": "STAGE20_3_RUN_DIR_MISSING_OR_NOT_DIR",
    "E2032": "STAGE20_2_MANIFEST_MISSING_OR_INVALID_JSON",
    "E2033": "STAGE20_3_MANIFEST_MISSING_OR_INVALID_JSON",
    "E2034": "STAGE20_2_REQUIRED_ARTIFACT_MISSING",
    "E2035": "STAGE20_3_REQUIRED_ARTIFACT_MISSING",
    "E2036": "STAGE20_3_LINEAGE_HASH_MISMATCH_VS_STAGE20_2",
    "E2037": "FORBIDDEN_NETWORK_IMPORT_FOUND",
    "E2038": "FORBIDDEN_PHOENIX1_IMPORT_FOUND",
    "E2039": "CROSS_STAGE_IMPORT_VIOLATION",
    "E2040": "FORBIDDEN_BLOCKING_TOKEN_FOUND_IN_SOURCE",
    "E2041": "STAGE20_2_SAFE_FOR_LIVE_DISPATCH_NOT_FALSE",
    "E2042": "STAGE20_3_LIVE_DISPATCH_READY_NOT_FALSE",
    "E2043": "OPERATOR_TEST_RESULTS_INCONSISTENT_OR_RED",
    "E2044": "COMMIT_SHA_INVALID_FORMAT",
    "E2045": "REPO_ROOT_NOT_FOUND_OR_NOT_PHX2_REPO",
    "E2046": "STAGE20_4_RUN_DIR_ALREADY_EXISTS",
    "E2047": "STAGE20_3_FILTER_REGISTRY_NOT_EMPTY",
    "E2048": "STAGE20_3_FILTER_RESULTS_NOT_EMPTY",
})


# ---------------------------------------------------------------------------
# Stage 20.4 warning codes (closed set; non-blocking)
# ---------------------------------------------------------------------------
#
# W2020 is reserved for a possible future single-run-results mode.
# In v0 both runs are required and missing fields trigger E2043,
# so W2020 is defined but never emitted by v0 code paths.
#
# W2023 is intentionally NOT defined in Stage 20.4 (no git
# invocation means no untracked-paths concept).


WARNING_CODES: tuple[str, ...] = (
    "W2020",
    "W2021",
    "W2022",
    "W2024",
    "W2025",
)


WARNING_CODE_NAMES: Mapping[str, str] = MappingProxyType({
    "W2020": "RESERVED_UNUSED_V0",
    "W2021": "STAGE20_2_README_MISSING",
    "W2022": "STAGE20_3_README_MISSING",
    "W2024": "STAGE20_4_PRIOR_CLOSURE_RUN_DETECTED",
    "W2025": "PROVIDER_NAME_OR_SECRET_TOKEN_PRESENT",
})


# ---------------------------------------------------------------------------
# Forbidden import module lists
# ---------------------------------------------------------------------------
#
# Inner scope walks every .py file under PHX2/stage20/closure/.
# Outer scope walks every .py file under PHX2/stage20/ EXCLUDING
# any path containing "/closure/" or "\\closure\\".


# Network / IO client modules forbidden anywhere in PHX2/stage20/
# (both inner and outer scope). All hits map to E2037.
FORBIDDEN_NETWORK_MODULES: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpclib",
    "discord",
    "telegram",
    "telethon",
    "pyrogram",
)


# Modules forbidden ONLY in inner scope (PHX2/stage20/closure/).
# These have legitimate uses elsewhere in the wider repo (tests
# may patch subprocess; other stages may store sqlite state) but
# closure production code must not touch them. All hits map to
# E2037 with a ``reason`` field describing the category.
FORBIDDEN_INNER_ONLY_MODULES: tuple[str, ...] = (
    "dotenv",
    "python_dotenv",
    "sqlite3",
    "aiosqlite",
    "subprocess",
    "git",
    "pygit2",
    "dulwich",
)


# Phoenix1 import prefixes forbidden inner + outer. E2038.
FORBIDDEN_PHOENIX1_MODULES: tuple[str, ...] = (
    "phoenix1",
    "Phoenix1",
    "phx1",
)


# Cross-stage prefixes forbidden in OUTER scope (matched by dotted
# prefix on ast.ImportFrom.module). The closure inner scope does
# not need this list because the closure subtree imports nothing
# from PHX2.stage20.* at all. E2039.
FORBIDDEN_CROSS_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
)


# ---------------------------------------------------------------------------
# Forbidden / warning token regex patterns (string source-level scan)
# ---------------------------------------------------------------------------
#
# Scope: PHX2/stage20/ source files (.py only) EXCLUDING the
# closure/templates/ subdirectory. Each pattern is compiled with
# re.MULTILINE in the auditor; each match records the file path,
# 1-based line number, the matched substring, and ~80 chars of
# surrounding context.
#
# Blocking patterns are case-insensitive ((?i)) on both the field
# name and the boolean literal so uppercase / lowercase / mixed-case
# safety flags all trigger. The identifier pattern covers three
# forms in one regex:
#
#   * direct assignment:         name = True
#   * dict-like colon form:      name: True
#   * type-annotated assignment: name: bool = True
#
# The ``[^=\n]*`` in the colon-then-equals branch lets a single-line
# type annotation (e.g. ``: bool``, ``: Final[bool]``) sit between
# the colon and the equals without letting the regex leap across a
# newline.
#
# Self-match note: the regex pattern strings themselves, as they
# appear literally in this source file, are designed NOT to trip
# any of the patterns. The word-boundary ``\b`` immediately before
# the field name fails to match when the preceding char is the
# backslash of ``\s`` or ``\b`` (which is a word character), and
# the quoted-form patterns are preceded by ``\b`` (backslash-b) in
# source rather than an actual quote, so the literal quote-prefix
# match also fails.


BLOCKING_TOKEN_REGEXES: tuple[str, ...] = (
    # Identifier form (case-insensitive name + True/true).
    r'(?i)\bsafe_for_live_dispatch\b\s*(?:=|:[^=\n]*=|:)\s*\btrue\b',
    r'(?i)\blive_dispatch_ready\b\s*(?:=|:[^=\n]*=|:)\s*\btrue\b',
    # Quoted-key form (JSON / dict-with-string-key), double quotes.
    r'(?i)"safe_for_live_dispatch"\s*:\s*\btrue\b',
    r'(?i)"live_dispatch_ready"\s*:\s*\btrue\b',
    # Quoted-key form, single quotes.
    r"(?i)'safe_for_live_dispatch'\s*:\s*\btrue\b",
    r"(?i)'live_dispatch_ready'\s*:\s*\btrue\b",
)


WARNING_TOKEN_REGEXES: tuple[str, ...] = (
    r'\bwebhook_url\b',
    r'\bapi_key\b',
    r'\bprivate_key\b',
    r'\bHELIUS\b',
    r'\bBIRDEYE\b',
)


# ---------------------------------------------------------------------------
# Expected upstream artifact filenames (hand-duplicated)
# ---------------------------------------------------------------------------


# Stage 20.2 artifact filenames (in <stage20_2_run_dir>/).
STAGE20_2_MANIFEST_FILENAME: str = "manifest.json"
STAGE20_2_PREVIEW_CANDIDATES_CSV_FILENAME: str = "preview_candidates.csv"
STAGE20_2_ALERT_ELIGIBILITY_DECISIONS_CSV_FILENAME: str = (
    "alert_eligibility_decisions.csv"
)
STAGE20_2_README_FILENAME: str = "README.md"
STAGE20_2_RUN_LOG_FILENAME: str = "stage20_run.log"

STAGE20_2_REQUIRED_ARTIFACT_FILENAMES: tuple[str, ...] = (
    STAGE20_2_MANIFEST_FILENAME,
    STAGE20_2_PREVIEW_CANDIDATES_CSV_FILENAME,
    STAGE20_2_ALERT_ELIGIBILITY_DECISIONS_CSV_FILENAME,
    STAGE20_2_RUN_LOG_FILENAME,
)
STAGE20_2_OPTIONAL_ARTIFACT_FILENAMES: tuple[str, ...] = (
    STAGE20_2_README_FILENAME,
)


# Stage 20.3 artifact filenames (in <stage20_3_run_dir>/).
STAGE20_3_MANIFEST_FILENAME: str = "stage20_3_manifest.json"
STAGE20_3_FILTER_INTERFACE_REGISTRY_CSV_FILENAME: str = (
    "filter_interface_registry.csv"
)
STAGE20_3_FILTER_INTERFACE_RESULTS_CSV_FILENAME: str = (
    "filter_interface_results.csv"
)
STAGE20_3_README_FILENAME: str = "README.md"
STAGE20_3_RUN_LOG_FILENAME: str = "stage20_3_run.log"

STAGE20_3_REQUIRED_ARTIFACT_FILENAMES: tuple[str, ...] = (
    STAGE20_3_MANIFEST_FILENAME,
    STAGE20_3_FILTER_INTERFACE_REGISTRY_CSV_FILENAME,
    STAGE20_3_FILTER_INTERFACE_RESULTS_CSV_FILENAME,
    STAGE20_3_RUN_LOG_FILENAME,
)
STAGE20_3_OPTIONAL_ARTIFACT_FILENAMES: tuple[str, ...] = (
    STAGE20_3_README_FILENAME,
)


# ---------------------------------------------------------------------------
# Upstream manifest field names that Stage 20.4 reads
# ---------------------------------------------------------------------------


# Stage 20.2 manifest top-level field that must be the literal False.
STAGE20_2_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH: str = (
    "safe_for_live_dispatch"
)


# Stage 20.3 manifest top-level fields that must be the literal False.
STAGE20_3_MANIFEST_FIELD_LIVE_DISPATCH_READY: str = "live_dispatch_ready"
STAGE20_3_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH: str = (
    "safe_for_live_dispatch"
)


# Stage 20.3 manifest top-level key whose value is the nested block
# carrying Stage 20.2 lineage hashes Stage 20.4 cross-checks.
STAGE20_3_MANIFEST_FIELD_STAGE20_2_LINEAGE: str = "stage20_2_lineage"


# Field names INSIDE the stage20_2_lineage block carrying Stage 20.2
# artifact SHA-256 values. Each maps to the Stage 20.2 artifact
# filename whose actual bytes Stage 20.4 will hash for the
# lineage crosscheck.
STAGE20_2_LINEAGE_HASH_FIELDS: Mapping[str, str] = MappingProxyType({
    "manifest_json_sha256": STAGE20_2_MANIFEST_FILENAME,
    "preview_candidates_csv_sha256":
        STAGE20_2_PREVIEW_CANDIDATES_CSV_FILENAME,
    "alert_eligibility_decisions_csv_sha256":
        STAGE20_2_ALERT_ELIGIBILITY_DECISIONS_CSV_FILENAME,
    "readme_md_sha256": STAGE20_2_README_FILENAME,
    "stage20_run_log_sha256": STAGE20_2_RUN_LOG_FILENAME,
})


# ---------------------------------------------------------------------------
# Closure output (8 files) -- locked filenames + locked write order
# ---------------------------------------------------------------------------


CLOSURE_OUTPUT_DIR_NAME: str = "stage20_closure_runs"


CLOSURE_MANIFEST_FILENAME: str = "stage20_closure_manifest.json"
CLOSURE_CHECKLIST_FILENAME: str = "stage20_closure_checklist.csv"
CODEBASE_AUDIT_REPORT_FILENAME: str = "codebase_audit_report.json"
STAGE20_2_LINEAGE_FILENAME: str = "stage20_2_lineage.json"
STAGE20_3_LINEAGE_FILENAME: str = "stage20_3_lineage.json"
CLOSURE_RUN_LOG_FILENAME: str = "stage20_4_run.log"
STAGE21_HANDOFF_FILENAME: str = "stage21_handoff.md"
CLOSURE_README_FILENAME: str = "README.md"


# Deterministic write order; the orchestrator iterates this tuple
# and the run log's ``artifacts_written`` event records this list.
CLOSURE_OUTPUT_ARTIFACT_FILENAMES: tuple[str, ...] = (
    CLOSURE_MANIFEST_FILENAME,
    CLOSURE_CHECKLIST_FILENAME,
    CODEBASE_AUDIT_REPORT_FILENAME,
    STAGE20_2_LINEAGE_FILENAME,
    STAGE20_3_LINEAGE_FILENAME,
    CLOSURE_RUN_LOG_FILENAME,
    STAGE21_HANDOFF_FILENAME,
    CLOSURE_README_FILENAME,
)


# ---------------------------------------------------------------------------
# Run-log event sequence (locked; 17 events in this exact order)
# ---------------------------------------------------------------------------


CLOSURE_RUN_LOG_EVENT_SEQUENCE: tuple[str, ...] = (
    "input_loaded",
    "codebase_audit_inner_started",
    "codebase_audit_inner_completed",
    "codebase_audit_outer_started",
    "codebase_audit_outer_completed",
    "forbidden_token_scan_started",
    "forbidden_token_scan_completed",
    "artifact_validation_stage20_2_started",
    "artifact_validation_stage20_2_completed",
    "artifact_validation_stage20_3_started",
    "artifact_validation_stage20_3_completed",
    "lineage_crosscheck_started",
    "lineage_crosscheck_completed",
    "operator_test_results_validated",
    "checklist_built",
    "closure_status_decided",
    "artifacts_written",
)


# ---------------------------------------------------------------------------
# Run-ID format
# ---------------------------------------------------------------------------


# strftime format -> YYYYMMDDTHHMMSSZ (e.g. 20260516T123456Z).
RUN_ID_UTC_COMPACT_FORMAT: str = "%Y%m%dT%H%M%SZ"

# Number of hex chars of sha256(canonical_json(config)) carried in run_id.
RUN_ID_CONFIG_SHA_LENGTH: int = 8

# Template: stage20_4_<utc_compact>_<config_sha8>.
RUN_ID_TEMPLATE: str = "stage20_4_{utc_compact}_{config_sha8}"


# ---------------------------------------------------------------------------
# Checklist row order (locked; 28 rows; stable order)
# ---------------------------------------------------------------------------
#
# Each entry: (code, description, severity). Status and detail are
# decided per-row by the checklist builder at run time.


CHECKLIST_ROW_ORDER: tuple[tuple[str, str, str], ...] = (
    ("C20_4_01", "Stage 20.1 commit SHA format valid", "error"),
    ("C20_4_02", "Stage 20.2 commit SHA format valid", "error"),
    ("C20_4_03", "Stage 20.3 commit SHA format valid", "error"),
    ("C20_4_04", "Stage 20.2 run directory exists", "error"),
    ("C20_4_05", "Stage 20.3 run directory exists", "error"),
    ("C20_4_06", "Stage 20.2 manifest valid JSON", "error"),
    ("C20_4_07", "Stage 20.3 manifest valid JSON", "error"),
    ("C20_4_08",
     "Stage 20.2 safe_for_live_dispatch is false", "error"),
    ("C20_4_09",
     "Stage 20.3 live_dispatch_ready is false", "error"),
    ("C20_4_10", "Stage 20.2 required artifacts present", "error"),
    ("C20_4_11", "Stage 20.3 required artifacts present", "error"),
    ("C20_4_12", "Stage 20.2 README present", "warning"),
    ("C20_4_13", "Stage 20.3 README present", "warning"),
    ("C20_4_14",
     "Stage 20.3 filter_interface_registry headers-only", "error"),
    ("C20_4_15",
     "Stage 20.3 filter_interface_results headers-only", "error"),
    ("C20_4_16",
     "Stage 20.3 -> Stage 20.2 lineage hashes match", "error"),
    ("C20_4_17",
     "No forbidden network imports in PHX2/stage20/", "error"),
    ("C20_4_18", "No Phoenix1 imports in PHX2/stage20/", "error"),
    ("C20_4_19",
     "No cross-stage imports (stage17/18/19) in PHX2/stage20/",
     "error"),
    ("C20_4_20",
     "No subprocess/git/sqlite3/env reads in closure/", "error"),
    ("C20_4_21",
     "No blocking forbidden tokens in PHX2/stage20/ source",
     "error"),
    ("C20_4_22", "Warning tokens reviewed (informational)", "warning"),
    ("C20_4_23",
     "Operator test results consistent and green", "error"),
    ("C20_4_24",
     "Stage 20.4 run directory is fresh (no overwrite)", "error"),
    ("C20_4_25",
     "safe_for_live_dispatch in closure manifest is false", "error"),
    ("C20_4_26",
     "live_dispatch_ready in closure manifest is false", "error"),
    ("C20_4_27",
     "Handoff contract version present in manifest and md", "error"),
    ("C20_4_28",
     "No prior closure run in same output_root (informational)",
     "warning"),
)


# Locked CSV column order for stage20_closure_checklist.csv.
# Differs intentionally from the ChecklistItem NamedTuple field
# order (writer reorders explicitly).
CHECKLIST_CSV_COLUMNS: tuple[str, ...] = (
    "code",
    "description",
    "status",
    "severity",
    "detail",
)

CHECKLIST_STATUS_VALUES: tuple[str, ...] = (
    "pass",
    "fail",
    "warning",
    "n/a",
)


# ---------------------------------------------------------------------------
# Commit SHA validation pattern (40 lowercase hex chars)
# ---------------------------------------------------------------------------


COMMIT_SHA_REGEX: str = r"^[0-9a-f]{40}$"


__all__ = [
    "BLOCKING_TOKEN_REGEXES",
    "CHECKLIST_CSV_COLUMNS",
    "CHECKLIST_ROW_ORDER",
    "CHECKLIST_STATUS_VALUES",
    "CLOSURE_CHECKLIST_FILENAME",
    "CLOSURE_MANIFEST_FILENAME",
    "CLOSURE_OUTPUT_ARTIFACT_FILENAMES",
    "CLOSURE_OUTPUT_DIR_NAME",
    "CLOSURE_README_FILENAME",
    "CLOSURE_RUN_LOG_EVENT_SEQUENCE",
    "CLOSURE_RUN_LOG_FILENAME",
    "CLOSURE_STATUS_BLOCKED",
    "CLOSURE_STATUS_CLOSED_PENDING_OPERATOR_REVIEW",
    "CLOSURE_STATUS_VALUES",
    "CODEBASE_AUDIT_REPORT_FILENAME",
    "COMMIT_SHA_REGEX",
    "ERROR_CODES",
    "ERROR_CODE_NAMES",
    "FORBIDDEN_CROSS_STAGE_PREFIXES",
    "FORBIDDEN_INNER_ONLY_MODULES",
    "FORBIDDEN_NETWORK_MODULES",
    "FORBIDDEN_PHOENIX1_MODULES",
    "HANDOFF_CONTRACT_VERSION",
    "LIVE_DISPATCH_READY",
    "RUN_ID_CONFIG_SHA_LENGTH",
    "RUN_ID_TEMPLATE",
    "RUN_ID_UTC_COMPACT_FORMAT",
    "SAFE_FOR_LIVE_DISPATCH",
    "STAGE20_2_ALERT_ELIGIBILITY_DECISIONS_CSV_FILENAME",
    "STAGE20_2_LINEAGE_FILENAME",
    "STAGE20_2_LINEAGE_HASH_FIELDS",
    "STAGE20_2_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH",
    "STAGE20_2_MANIFEST_FILENAME",
    "STAGE20_2_OPTIONAL_ARTIFACT_FILENAMES",
    "STAGE20_2_PREVIEW_CANDIDATES_CSV_FILENAME",
    "STAGE20_2_README_FILENAME",
    "STAGE20_2_REQUIRED_ARTIFACT_FILENAMES",
    "STAGE20_2_RUN_LOG_FILENAME",
    "STAGE20_3_FILTER_INTERFACE_REGISTRY_CSV_FILENAME",
    "STAGE20_3_FILTER_INTERFACE_RESULTS_CSV_FILENAME",
    "STAGE20_3_LINEAGE_FILENAME",
    "STAGE20_3_MANIFEST_FIELD_LIVE_DISPATCH_READY",
    "STAGE20_3_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH",
    "STAGE20_3_MANIFEST_FIELD_STAGE20_2_LINEAGE",
    "STAGE20_3_MANIFEST_FILENAME",
    "STAGE20_3_OPTIONAL_ARTIFACT_FILENAMES",
    "STAGE20_3_README_FILENAME",
    "STAGE20_3_REQUIRED_ARTIFACT_FILENAMES",
    "STAGE20_3_RUN_LOG_FILENAME",
    "STAGE20_4_MINOR_VERSION",
    "STAGE21_HANDOFF_FILENAME",
    "WARNING_CODES",
    "WARNING_CODE_NAMES",
    "WARNING_TOKEN_REGEXES",
]
