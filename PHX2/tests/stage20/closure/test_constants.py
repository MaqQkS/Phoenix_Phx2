"""Stage 20.4 constants tests.

Verify that every locked E20xx / W20xx code is present, codes do
not collide with prior-stage (20.1/20.2/20.3) codes, every regex
pattern compiles, the locked artifact/event/checklist tuples
match the spec, and all tuple-typed constants are real tuples
(not lists).

These tests run against ``PHX2.stage20.closure.constants`` only.
They do not import ``PHX2.stage20.constants`` (the wider Stage
20 module) so a structural drift there would not silently affect
Stage 20.4.
"""

from __future__ import annotations

import re
from types import MappingProxyType

import pytest

from PHX2.stage20.closure import constants as c


# ---------------------------------------------------------------------------
# Identity / contract version
# ---------------------------------------------------------------------------


def test_handoff_contract_version_is_locked_string():
    assert (
        c.HANDOFF_CONTRACT_VERSION
        == "stage20_to_stage21_private_preview_handoff_v0"
    )


def test_stage20_4_minor_version_is_20_4():
    assert c.STAGE20_4_MINOR_VERSION == "20.4"


# ---------------------------------------------------------------------------
# Hardcoded safety flags
# ---------------------------------------------------------------------------


def test_safe_for_live_dispatch_constant_is_false():
    """SAFE_FOR_LIVE_DISPATCH must be the literal Python False."""
    assert c.SAFE_FOR_LIVE_DISPATCH is False


def test_live_dispatch_ready_constant_is_false():
    """LIVE_DISPATCH_READY must be the literal Python False."""
    assert c.LIVE_DISPATCH_READY is False


# ---------------------------------------------------------------------------
# Closure status (closed two-value set)
# ---------------------------------------------------------------------------


def test_closure_status_values_are_only_two():
    assert c.CLOSURE_STATUS_VALUES == (
        "closed_pending_operator_review",
        "closure_blocked",
    )


def test_closure_status_constants_match_tuple_members():
    assert (
        c.CLOSURE_STATUS_CLOSED_PENDING_OPERATOR_REVIEW
        == "closed_pending_operator_review"
    )
    assert c.CLOSURE_STATUS_BLOCKED == "closure_blocked"


# ---------------------------------------------------------------------------
# Error / warning codes
# ---------------------------------------------------------------------------


EXPECTED_ERROR_CODES = (
    "E2030", "E2031", "E2032", "E2033", "E2034",
    "E2035", "E2036", "E2037", "E2038", "E2039",
    "E2040", "E2041", "E2042", "E2043", "E2044",
    "E2045", "E2046", "E2047", "E2048",
)

EXPECTED_WARNING_CODES = (
    "W2020", "W2021", "W2022", "W2024", "W2025",
)


def test_error_codes_tuple_matches_expected():
    assert c.ERROR_CODES == EXPECTED_ERROR_CODES


def test_warning_codes_tuple_matches_expected():
    assert c.WARNING_CODES == EXPECTED_WARNING_CODES


def test_error_codes_no_duplicates():
    assert len(c.ERROR_CODES) == len(set(c.ERROR_CODES))


def test_warning_codes_no_duplicates():
    assert len(c.WARNING_CODES) == len(set(c.WARNING_CODES))


def test_e2049_not_defined_in_stage_20_4():
    """E2049 is explicitly NOT defined in Stage 20.4 v0."""
    assert "E2049" not in c.ERROR_CODES
    assert "E2049" not in c.ERROR_CODE_NAMES


def test_w2023_not_defined_in_stage_20_4():
    """W2023 is explicitly NOT defined in Stage 20.4 (no git invocation)."""
    assert "W2023" not in c.WARNING_CODES
    assert "W2023" not in c.WARNING_CODE_NAMES


def test_every_error_code_has_a_name():
    for code in c.ERROR_CODES:
        assert code in c.ERROR_CODE_NAMES, code
        assert isinstance(c.ERROR_CODE_NAMES[code], str)
        assert c.ERROR_CODE_NAMES[code], code


def test_error_code_names_no_extra_keys():
    assert set(c.ERROR_CODE_NAMES.keys()) == set(c.ERROR_CODES)


def test_every_warning_code_has_a_name():
    for code in c.WARNING_CODES:
        assert code in c.WARNING_CODE_NAMES, code
        assert isinstance(c.WARNING_CODE_NAMES[code], str)
        assert c.WARNING_CODE_NAMES[code], code


def test_warning_code_names_no_extra_keys():
    assert set(c.WARNING_CODE_NAMES.keys()) == set(c.WARNING_CODES)


def test_specific_error_code_names_locked():
    """Spot-check the locked spelling of high-value E-codes."""
    assert (
        c.ERROR_CODE_NAMES["E2030"]
        == "STAGE20_2_RUN_DIR_MISSING_OR_NOT_DIR"
    )
    assert (
        c.ERROR_CODE_NAMES["E2036"]
        == "STAGE20_3_LINEAGE_HASH_MISMATCH_VS_STAGE20_2"
    )
    assert (
        c.ERROR_CODE_NAMES["E2040"]
        == "FORBIDDEN_BLOCKING_TOKEN_FOUND_IN_SOURCE"
    )
    assert (
        c.ERROR_CODE_NAMES["E2046"]
        == "STAGE20_4_RUN_DIR_ALREADY_EXISTS"
    )
    assert (
        c.ERROR_CODE_NAMES["E2047"]
        == "STAGE20_3_FILTER_REGISTRY_NOT_EMPTY"
    )
    assert (
        c.ERROR_CODE_NAMES["E2048"]
        == "STAGE20_3_FILTER_RESULTS_NOT_EMPTY"
    )


def test_w2020_name_is_reserved_unused_v0():
    assert c.WARNING_CODE_NAMES["W2020"] == "RESERVED_UNUSED_V0"


def test_w2024_name_is_prior_closure_run_detected():
    assert (
        c.WARNING_CODE_NAMES["W2024"]
        == "STAGE20_4_PRIOR_CLOSURE_RUN_DETECTED"
    )


# ---------------------------------------------------------------------------
# No collision with prior-stage (20.1 / 20.2 / 20.3) codes
# ---------------------------------------------------------------------------


def test_error_codes_do_not_collide_with_prior_stage_codes():
    """E2030..E2048 must not overlap with any pre-existing Stage 20.x code."""
    prior_stage_codes = {
        "E2001", "E2002", "E2003", "E2004", "E2005", "E2006",
        "E2007", "E2008", "E2009", "E2010", "E2011", "E2012",
        "E2013", "E2014", "E2015", "E2016", "E2017", "E2020",
        "E2021", "E2022", "E2023", "E2024", "E2025", "E2027",
        "E2028", "E2029",
    }
    assert not (set(c.ERROR_CODES) & prior_stage_codes)


def test_warning_codes_do_not_collide_with_prior_stage_codes():
    prior_stage_warnings = {
        "W2001", "W2002", "W2003", "W2004", "W2005", "W2006", "W2007",
    }
    assert not (set(c.WARNING_CODES) & prior_stage_warnings)


# ---------------------------------------------------------------------------
# Forbidden module lists
# ---------------------------------------------------------------------------


def test_forbidden_network_modules_is_nonempty_tuple_of_strs():
    assert isinstance(c.FORBIDDEN_NETWORK_MODULES, tuple)
    assert c.FORBIDDEN_NETWORK_MODULES
    for m in c.FORBIDDEN_NETWORK_MODULES:
        assert isinstance(m, str) and m


def test_forbidden_network_modules_contains_canonical_clients():
    expected_subset = {
        "requests", "httpx", "aiohttp", "urllib3", "websockets",
        "grpc", "grpclib",
        "discord", "telegram", "telethon", "pyrogram",
    }
    assert expected_subset.issubset(set(c.FORBIDDEN_NETWORK_MODULES))


def test_forbidden_inner_only_modules_locked_set():
    expected = {
        "dotenv", "python_dotenv",
        "sqlite3", "aiosqlite",
        "subprocess",
        "git", "pygit2", "dulwich",
    }
    assert set(c.FORBIDDEN_INNER_ONLY_MODULES) == expected


def test_forbidden_phoenix1_modules_locked():
    assert set(c.FORBIDDEN_PHOENIX1_MODULES) == {
        "phoenix1", "Phoenix1", "phx1",
    }


def test_forbidden_cross_stage_prefixes_locked():
    assert c.FORBIDDEN_CROSS_STAGE_PREFIXES == (
        "PHX2.stage17",
        "PHX2.stage18",
        "PHX2.stage19",
    )


def test_inner_only_and_network_module_lists_do_not_overlap():
    """Inner-only modules must not duplicate entries in the shared
    network list (otherwise the auditor would double-count)."""
    overlap = (
        set(c.FORBIDDEN_INNER_ONLY_MODULES)
        & set(c.FORBIDDEN_NETWORK_MODULES)
    )
    assert overlap == set()


# ---------------------------------------------------------------------------
# Forbidden / warning token regex patterns
# ---------------------------------------------------------------------------


def test_blocking_token_regexes_all_compile():
    for pattern in c.BLOCKING_TOKEN_REGEXES:
        re.compile(pattern, re.MULTILINE)


def test_warning_token_regexes_all_compile():
    for pattern in c.WARNING_TOKEN_REGEXES:
        re.compile(pattern, re.MULTILINE)


def test_blocking_token_regex_catches_python_true_assignment():
    """A canonical violation (lowercase field = True) must match
    exactly one of the locked blocking patterns."""
    src = "safe_for_live_dispatch = True\n"
    matched = [
        re.search(pat, src, re.MULTILINE)
        for pat in c.BLOCKING_TOKEN_REGEXES
    ]
    hits = [m for m in matched if m]
    assert len(hits) == 1


def test_blocking_token_regex_catches_uppercase_python_true_assignment():
    """Per operator patch: ``SAFE_FOR_LIVE_DISPATCH = True`` (uppercase)
    must trigger E2040 via the case-insensitive identifier pattern."""
    src = "SAFE_FOR_LIVE_DISPATCH = True\n"
    hits = [
        m for m in (
            re.search(pat, src, re.MULTILINE)
            for pat in c.BLOCKING_TOKEN_REGEXES
        )
        if m
    ]
    assert len(hits) == 1


def test_blocking_token_regex_catches_typed_lowercase_true_assignment():
    """Per operator patch: ``safe_for_live_dispatch: bool = True``
    (type-annotated lowercase) must trigger E2040."""
    src = "safe_for_live_dispatch: bool = True\n"
    hits = [
        m for m in (
            re.search(pat, src, re.MULTILINE)
            for pat in c.BLOCKING_TOKEN_REGEXES
        )
        if m
    ]
    assert len(hits) == 1


def test_blocking_token_regex_catches_typed_uppercase_true_assignment():
    """Per operator patch: ``SAFE_FOR_LIVE_DISPATCH: bool = True``
    (type-annotated uppercase) must trigger E2040 -- previously a
    documented gap, now closed."""
    src = "SAFE_FOR_LIVE_DISPATCH: bool = True\n"
    hits = [
        m for m in (
            re.search(pat, src, re.MULTILINE)
            for pat in c.BLOCKING_TOKEN_REGEXES
        )
        if m
    ]
    assert len(hits) == 1


def test_blocking_token_regex_catches_typed_live_dispatch_ready_true():
    src = "LIVE_DISPATCH_READY: bool = True\n"
    hits = [
        m for m in (
            re.search(pat, src, re.MULTILINE)
            for pat in c.BLOCKING_TOKEN_REGEXES
        )
        if m
    ]
    assert len(hits) == 1


def test_blocking_token_regex_catches_json_true_value():
    """JSON-style ``"safe_for_live_dispatch": true`` must match."""
    src = '"safe_for_live_dispatch": true\n'
    hits = [
        m for m in (
            re.search(pat, src, re.MULTILINE)
            for pat in c.BLOCKING_TOKEN_REGEXES
        )
        if m
    ]
    assert len(hits) == 1


def test_blocking_token_regex_catches_uppercase_json_true_value():
    """Case-insensitive name match catches uppercase JSON keys too."""
    src = '"SAFE_FOR_LIVE_DISPATCH": true\n'
    hits = [
        m for m in (
            re.search(pat, src, re.MULTILINE)
            for pat in c.BLOCKING_TOKEN_REGEXES
        )
        if m
    ]
    assert len(hits) == 1


def test_blocking_token_regex_catches_live_dispatch_ready_true():
    src = "live_dispatch_ready = True\n"
    hits = [
        m for m in (
            re.search(pat, src, re.MULTILINE)
            for pat in c.BLOCKING_TOKEN_REGEXES
        )
        if m
    ]
    assert len(hits) == 1


def test_blocking_token_regex_catches_dict_python_dict_form():
    """``safe_for_live_dispatch: True`` (dict literal entry without
    quoted key) must trigger via the colon-only branch of the
    identifier pattern."""
    src = "x = {safe_for_live_dispatch: True}\n"
    hits = [
        m for m in (
            re.search(pat, src, re.MULTILINE)
            for pat in c.BLOCKING_TOKEN_REGEXES
        )
        if m
    ]
    assert len(hits) == 1


def test_blocking_token_regex_does_not_match_false_literal():
    """Lowercase field = False must NOT trip any blocking pattern."""
    src = "safe_for_live_dispatch = False\n"
    for pat in c.BLOCKING_TOKEN_REGEXES:
        assert re.search(pat, src, re.MULTILINE) is None


def test_blocking_token_regex_ignores_safe_for_live_dispatch_not_false():
    """The literal substring ``safe_for_live_dispatch_not_false`` (used as
    an E2022 code name in PHX2.stage20.constants) must NOT trigger any
    blocking pattern -- the ``=`` is missing and the ``_`` after the
    field name breaks the word boundary."""
    src = 'NAMES = {"E2022": "safe_for_live_dispatch_not_false"}\n'
    for pat in c.BLOCKING_TOKEN_REGEXES:
        assert re.search(pat, src, re.MULTILINE) is None


def test_warning_token_regex_catches_provider_name():
    src = 'BIRDEYE = "x"\n'
    matched_any = any(
        re.search(pat, src, re.MULTILINE)
        for pat in c.WARNING_TOKEN_REGEXES
    )
    assert matched_any


def test_warning_token_regex_catches_api_key_assignment():
    src = "api_key = 'x'\n"
    matched_any = any(
        re.search(pat, src, re.MULTILINE)
        for pat in c.WARNING_TOKEN_REGEXES
    )
    assert matched_any


def test_blocking_token_regexes_do_not_self_match_regex_source_text():
    """The regex pattern strings, treated as source content, must not
    trip any of the patterns. Word-boundary checks fail because of the
    leading backslash in ``\\s*``."""
    for pat in c.BLOCKING_TOKEN_REGEXES:
        for other in c.BLOCKING_TOKEN_REGEXES:
            assert re.search(other, pat, re.MULTILINE) is None


def test_warning_token_regexes_do_not_self_match_regex_source_text():
    for pat in c.WARNING_TOKEN_REGEXES:
        for other in c.WARNING_TOKEN_REGEXES:
            assert re.search(other, pat, re.MULTILINE) is None


# ---------------------------------------------------------------------------
# Upstream artifact filenames (hand-duplicated)
# ---------------------------------------------------------------------------


def test_stage20_2_required_artifact_filenames_locked():
    assert c.STAGE20_2_REQUIRED_ARTIFACT_FILENAMES == (
        "manifest.json",
        "preview_candidates.csv",
        "alert_eligibility_decisions.csv",
        "stage20_run.log",
    )


def test_stage20_2_optional_artifact_filenames_locked():
    assert c.STAGE20_2_OPTIONAL_ARTIFACT_FILENAMES == ("README.md",)


def test_stage20_3_required_artifact_filenames_locked():
    assert c.STAGE20_3_REQUIRED_ARTIFACT_FILENAMES == (
        "stage20_3_manifest.json",
        "filter_interface_registry.csv",
        "filter_interface_results.csv",
        "stage20_3_run.log",
    )


def test_stage20_3_optional_artifact_filenames_locked():
    assert c.STAGE20_3_OPTIONAL_ARTIFACT_FILENAMES == ("README.md",)


# ---------------------------------------------------------------------------
# Upstream manifest field names + lineage hash field map
# ---------------------------------------------------------------------------


def test_stage20_2_manifest_safe_for_live_dispatch_field_name_locked():
    assert (
        c.STAGE20_2_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH
        == "safe_for_live_dispatch"
    )


def test_stage20_3_manifest_live_dispatch_ready_field_name_locked():
    assert (
        c.STAGE20_3_MANIFEST_FIELD_LIVE_DISPATCH_READY
        == "live_dispatch_ready"
    )


def test_stage20_3_manifest_safe_for_live_dispatch_field_name_locked():
    assert (
        c.STAGE20_3_MANIFEST_FIELD_SAFE_FOR_LIVE_DISPATCH
        == "safe_for_live_dispatch"
    )


def test_stage20_3_manifest_lineage_block_key_locked():
    assert (
        c.STAGE20_3_MANIFEST_FIELD_STAGE20_2_LINEAGE == "stage20_2_lineage"
    )


def test_stage20_2_lineage_hash_fields_locked():
    """Each lineage hash field in the Stage 20.3 manifest's
    stage20_2_lineage block must map to the corresponding Stage 20.2
    artifact filename."""
    assert set(c.STAGE20_2_LINEAGE_HASH_FIELDS.keys()) == {
        "manifest_json_sha256",
        "preview_candidates_csv_sha256",
        "alert_eligibility_decisions_csv_sha256",
        "readme_md_sha256",
        "stage20_run_log_sha256",
    }
    assert (
        c.STAGE20_2_LINEAGE_HASH_FIELDS["manifest_json_sha256"]
        == "manifest.json"
    )
    assert (
        c.STAGE20_2_LINEAGE_HASH_FIELDS["preview_candidates_csv_sha256"]
        == "preview_candidates.csv"
    )
    assert (
        c.STAGE20_2_LINEAGE_HASH_FIELDS[
            "alert_eligibility_decisions_csv_sha256"
        ]
        == "alert_eligibility_decisions.csv"
    )
    assert (
        c.STAGE20_2_LINEAGE_HASH_FIELDS["readme_md_sha256"]
        == "README.md"
    )
    assert (
        c.STAGE20_2_LINEAGE_HASH_FIELDS["stage20_run_log_sha256"]
        == "stage20_run.log"
    )


# ---------------------------------------------------------------------------
# Closure output (8 files)
# ---------------------------------------------------------------------------


def test_closure_output_artifact_filenames_is_eight():
    assert len(c.CLOSURE_OUTPUT_ARTIFACT_FILENAMES) == 8


def test_closure_output_artifact_filenames_set_locked():
    assert set(c.CLOSURE_OUTPUT_ARTIFACT_FILENAMES) == {
        "stage20_closure_manifest.json",
        "stage20_closure_checklist.csv",
        "codebase_audit_report.json",
        "stage20_2_lineage.json",
        "stage20_3_lineage.json",
        "stage20_4_run.log",
        "stage21_handoff.md",
        "README.md",
    }


def test_closure_output_artifact_filenames_no_duplicates():
    assert (
        len(c.CLOSURE_OUTPUT_ARTIFACT_FILENAMES)
        == len(set(c.CLOSURE_OUTPUT_ARTIFACT_FILENAMES))
    )


def test_closure_output_dir_name_locked():
    assert c.CLOSURE_OUTPUT_DIR_NAME == "stage20_closure_runs"


def test_individual_closure_artifact_filenames_locked():
    assert c.CLOSURE_MANIFEST_FILENAME == "stage20_closure_manifest.json"
    assert c.CLOSURE_CHECKLIST_FILENAME == "stage20_closure_checklist.csv"
    assert c.CODEBASE_AUDIT_REPORT_FILENAME == "codebase_audit_report.json"
    assert c.STAGE20_2_LINEAGE_FILENAME == "stage20_2_lineage.json"
    assert c.STAGE20_3_LINEAGE_FILENAME == "stage20_3_lineage.json"
    assert c.CLOSURE_RUN_LOG_FILENAME == "stage20_4_run.log"
    assert c.STAGE21_HANDOFF_FILENAME == "stage21_handoff.md"
    assert c.CLOSURE_README_FILENAME == "README.md"


# ---------------------------------------------------------------------------
# Run-log event sequence
# ---------------------------------------------------------------------------


def test_run_log_event_sequence_is_seventeen_events():
    assert len(c.CLOSURE_RUN_LOG_EVENT_SEQUENCE) == 17


def test_run_log_event_sequence_locked_order():
    assert c.CLOSURE_RUN_LOG_EVENT_SEQUENCE == (
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


def test_run_log_event_sequence_no_duplicates():
    assert (
        len(c.CLOSURE_RUN_LOG_EVENT_SEQUENCE)
        == len(set(c.CLOSURE_RUN_LOG_EVENT_SEQUENCE))
    )


# ---------------------------------------------------------------------------
# Run ID format
# ---------------------------------------------------------------------------


def test_run_id_utc_compact_format_locked():
    assert c.RUN_ID_UTC_COMPACT_FORMAT == "%Y%m%dT%H%M%SZ"


def test_run_id_config_sha_length_is_eight():
    assert c.RUN_ID_CONFIG_SHA_LENGTH == 8


def test_run_id_template_locked():
    assert c.RUN_ID_TEMPLATE == "stage20_4_{utc_compact}_{config_sha8}"


def test_run_id_template_renders_with_expected_keys():
    rendered = c.RUN_ID_TEMPLATE.format(
        utc_compact="20260516T123456Z",
        config_sha8="deadbeef",
    )
    assert rendered == "stage20_4_20260516T123456Z_deadbeef"


def test_run_id_utc_compact_format_renders_expected_string():
    """Sanity-check the strftime format produces YYYYMMDDTHHMMSSZ."""
    from datetime import datetime, timezone
    dt = datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc)
    assert dt.strftime(c.RUN_ID_UTC_COMPACT_FORMAT) == "20260516T123456Z"


# ---------------------------------------------------------------------------
# Checklist row order
# ---------------------------------------------------------------------------


def test_checklist_row_order_is_28_rows():
    assert len(c.CHECKLIST_ROW_ORDER) == 28


def test_checklist_row_order_codes_unique_and_sequential():
    codes = [row[0] for row in c.CHECKLIST_ROW_ORDER]
    assert len(codes) == len(set(codes))
    expected_codes = [f"C20_4_{i:02d}" for i in range(1, 29)]
    assert codes == expected_codes


def test_checklist_row_severities_are_in_locked_set():
    for code, _desc, severity in c.CHECKLIST_ROW_ORDER:
        assert severity in {"error", "warning", "info"}, (code, severity)


def test_checklist_row_descriptions_are_nonempty_strings():
    for code, desc, _sev in c.CHECKLIST_ROW_ORDER:
        assert isinstance(desc, str), code
        assert desc, code


def test_checklist_csv_columns_locked():
    assert c.CHECKLIST_CSV_COLUMNS == (
        "code",
        "description",
        "status",
        "severity",
        "detail",
    )


def test_checklist_status_values_locked():
    assert c.CHECKLIST_STATUS_VALUES == ("pass", "fail", "warning", "n/a")


# ---------------------------------------------------------------------------
# Commit SHA regex
# ---------------------------------------------------------------------------


def test_commit_sha_regex_compiles():
    re.compile(c.COMMIT_SHA_REGEX)


@pytest.mark.parametrize("sha", [
    "0" * 40,
    "a" * 40,
    "f" * 40,
    "0123456789abcdef" * 2 + "01234567",
    "c57606779c76763bdb0be6ee5f93cf44db99a29f",  # real 20.1 SHA
])
def test_commit_sha_regex_accepts_valid_40_hex(sha):
    assert re.fullmatch(c.COMMIT_SHA_REGEX, sha)


@pytest.mark.parametrize("bad_sha", [
    "",
    "a" * 39,
    "a" * 41,
    "A" * 40,                    # uppercase rejected
    "g" * 40,                    # non-hex char
    "deadbeef",                  # too short
    " " + "a" * 39,              # leading space
    "a" * 39 + " ",              # trailing space
])
def test_commit_sha_regex_rejects_invalid(bad_sha):
    assert re.fullmatch(c.COMMIT_SHA_REGEX, bad_sha) is None


# ---------------------------------------------------------------------------
# Tuple-ness sanity (no list slipping through)
# ---------------------------------------------------------------------------


_TUPLE_CONSTANT_NAMES = (
    "BLOCKING_TOKEN_REGEXES",
    "CHECKLIST_CSV_COLUMNS",
    "CHECKLIST_ROW_ORDER",
    "CHECKLIST_STATUS_VALUES",
    "CLOSURE_OUTPUT_ARTIFACT_FILENAMES",
    "CLOSURE_RUN_LOG_EVENT_SEQUENCE",
    "CLOSURE_STATUS_VALUES",
    "ERROR_CODES",
    "FORBIDDEN_CROSS_STAGE_PREFIXES",
    "FORBIDDEN_INNER_ONLY_MODULES",
    "FORBIDDEN_NETWORK_MODULES",
    "FORBIDDEN_PHOENIX1_MODULES",
    "STAGE20_2_OPTIONAL_ARTIFACT_FILENAMES",
    "STAGE20_2_REQUIRED_ARTIFACT_FILENAMES",
    "STAGE20_3_OPTIONAL_ARTIFACT_FILENAMES",
    "STAGE20_3_REQUIRED_ARTIFACT_FILENAMES",
    "WARNING_CODES",
    "WARNING_TOKEN_REGEXES",
)


@pytest.mark.parametrize("name", _TUPLE_CONSTANT_NAMES)
def test_documented_tuple_constants_are_tuples(name):
    value = getattr(c, name)
    assert isinstance(value, tuple), (
        f"{name} expected tuple, got {type(value).__name__}"
    )


def test_mapping_constants_are_mapping_proxy_types():
    """ERROR_CODE_NAMES, WARNING_CODE_NAMES, STAGE20_2_LINEAGE_HASH_FIELDS
    must be immutable MappingProxyType instances."""
    assert isinstance(c.ERROR_CODE_NAMES, MappingProxyType)
    assert isinstance(c.WARNING_CODE_NAMES, MappingProxyType)
    assert isinstance(c.STAGE20_2_LINEAGE_HASH_FIELDS, MappingProxyType)


def test_error_code_names_mapping_is_immutable():
    with pytest.raises(TypeError):
        c.ERROR_CODE_NAMES["E2030"] = "evil"  # type: ignore[index]


def test_warning_code_names_mapping_is_immutable():
    with pytest.raises(TypeError):
        c.WARNING_CODE_NAMES["W2020"] = "evil"  # type: ignore[index]


def test_stage20_2_lineage_hash_fields_mapping_is_immutable():
    with pytest.raises(TypeError):
        c.STAGE20_2_LINEAGE_HASH_FIELDS[
            "manifest_json_sha256"
        ] = "evil.json"  # type: ignore[index]
