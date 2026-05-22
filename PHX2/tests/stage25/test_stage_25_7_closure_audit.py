"""Stage 25.7 closure-audit + Stage 26 handoff tests.

Pins:

  * The Stage 25 closure audit document carries every Stage 25
    substage commit (full SHA, short SHA, subject).
  * The closure docs state the tag is operator-created only.
  * The closed Stage 25 production + test inventories include the
    Stage 25.7 closure docs and the closure-audit test file.
  * Locked artifact filenames are exposed by ``constants.py`` and
    match the closure doc's documented set.
  * Manifest self-entry sentinels exist and are documented.
  * Measurement-truth invariants are documented verbatim.
  * Stage 26 handoff doc carries the locked consume / must-not /
    deferral language.
  * Stage 25 production source carries no Stage 21-24 imports, no
    network / DB / dispatch / CLI surfaces, no env reads, no URL
    literals.
  * ``PHX2/stage26/`` carries only the approved Stage 26.0 spec-
    lock scaffold + the approved Stage 26.1 calibration-input
    contract + Stage 25 artifact reader / validator surface + the
    approved Stage 26.2 denominator / outcome-eligibility surface +
    the approved Stage 26.3 calibration cohort builder surface +
    the approved Stage 26.4 threshold candidate generator surface +
    the approved Stage 26.5 observe-only policy candidate artifact
    builder + writer surface + the approved Stage 26.6 operator
    review packet / approval handoff builder + writer surface +
    the approved Stage 26.7 closure-audit + Stage 27 handoff docs.
    Stage 26.7 admits: ``__init__.py`` + ``STAGE_26_0_SPEC_LOCK.md``
    + ``constants.py`` + ``errors.py`` + ``models.py`` +
    ``stage25_schema_whitelist.py`` + ``stage25_artifact_reader.py``
    + ``stage25_artifact_validation.py`` +
    ``calibration_input_contracts.py`` + ``eligibility_constants.py``
    + ``eligibility_models.py`` + ``eligibility_classifier.py`` +
    ``cohort_constants.py`` + ``cohort_models.py`` +
    ``cohort_builder.py`` + ``threshold_constants.py`` +
    ``threshold_models.py`` + ``threshold_candidate_generator.py`` +
    ``policy_candidate_constants.py`` + ``policy_candidate_models.py``
    + ``policy_candidate_builder.py`` +
    ``policy_candidate_writer.py`` + ``review_packet_constants.py``
    + ``review_packet_models.py`` + ``review_packet_builder.py`` +
    ``review_packet_writer.py`` + ``STAGE_26_CLOSURE_AUDIT.md`` +
    ``STAGE_27_HANDOFF.md``. Any other entry is treated as Stage 27
    implementation and is rejected (Stage 27 surfaces -- runner /
    CLI / dispatch / live router / Discord / Telegram / X / social
    / Axiom / approval / enforcement -- remain blocked).
  * ``PHX2/stage27/`` does NOT exist (no Stage 27 scaffold is
    admitted at Stage 25.7 / Stage 26.0 / Stage 26.1 / Stage 26.2 /
    Stage 26.3 / Stage 26.4 / Stage 26.5 / Stage 26.6 / Stage 26.7).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


REPO_ROOT: Path = Path(__file__).parent.parent.parent.parent
PHX2_ROOT: Path = Path(__file__).parent.parent.parent
STAGE25_ROOT: Path = PHX2_ROOT / "stage25"
TESTS_STAGE25_ROOT: Path = PHX2_ROOT / "tests" / "stage25"


CLOSURE_AUDIT_PATH: Path = STAGE25_ROOT / "STAGE_25_CLOSURE_AUDIT.md"
STAGE26_HANDOFF_PATH: Path = STAGE25_ROOT / "STAGE_26_HANDOFF.md"
CLOSURE_TEST_PATH: Path = (
    TESTS_STAGE25_ROOT / "test_stage_25_7_closure_audit.py"
)


STAGE25_COMMITS: tuple[tuple[str, str, str], ...] = (
    (
        "2a9ba710aa1728af486e8b7b582542d1db3d6a50",
        "2a9ba71",
        "phx2 stage 25.1: measurement contracts and input scaffolding",
    ),
    (
        "76a7051382d46540de4763e7da96c674f0924242",
        "76a7051",
        "phx2 stage 25.2: migration measurement scaffold",
    ),
    (
        "dd4990abde77b726dc54879d2230d7a4a961ae33",
        "dd4990a",
        "phx2 stage 25.3: price observation window scaffold",
    ),
    (
        "a3bd7645f50cf30198d537e71bfe44eee3504554",
        "a3bd764",
        "phx2 stage 25.4: ath candidate builder from source windows",
    ),
    (
        "16a6129530760a91ca56e2e2abceb158205ac47b",
        "16a6129",
        "phx2 stage 25.5: source reconciliation and confidence labeling",
    ),
    (
        "18c20db27de757e67fd9fc1f6dc8a14e318d5097",
        "18c20db",
        "phx2 stage 25.6: runner writer and deterministic measurement "
        "artifacts",
    ),
)


def _closure_audit_text() -> str:
    return CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")


def _stage26_handoff_text() -> str:
    return STAGE26_HANDOFF_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Category 1: Commit inventory
# ---------------------------------------------------------------------------


def test_closure_audit_exists():
    assert CLOSURE_AUDIT_PATH.is_file(), (
        f"Stage 25.7 requires {CLOSURE_AUDIT_PATH}"
    )


def test_stage26_handoff_exists():
    assert STAGE26_HANDOFF_PATH.is_file(), (
        f"Stage 25.7 requires {STAGE26_HANDOFF_PATH}"
    )


@pytest.mark.parametrize("full_sha,short_sha,subject", STAGE25_COMMITS)
def test_closure_audit_contains_each_commit(full_sha, short_sha, subject):
    text = _closure_audit_text()
    assert full_sha in text, f"missing full SHA {full_sha!r}"
    assert short_sha in text, f"missing short SHA {short_sha!r}"
    assert subject in text, f"missing commit subject {subject!r}"


def test_closure_audit_states_tag_is_operator_created():
    text = _closure_audit_text().lower()
    assert "operator" in text
    assert "stage-25-closed" in text
    assert "explicit authorization" in text


def test_closure_audit_states_no_implementation_creates_tag():
    text = _closure_audit_text().lower()
    # The closure doc must explicitly disclaim auto-tag behaviour.
    assert "no" in text
    assert "tag" in text
    assert "does not" in text or "must not" in text


# ---------------------------------------------------------------------------
# Category 2: File inventory
# ---------------------------------------------------------------------------


_EXPECTED_STAGE25_PRODUCTION_PY: frozenset[str] = frozenset(
    {
        "__init__.py",
        "constants.py",
        "errors.py",
        "models.py",
        "measurement_contracts.py",
        "input_reader.py",
        "stage25_manifest.py",
        "migration_observation.py",
        "migration_measurement.py",
        "price_observation.py",
        "price_window.py",
        "ath_candidate.py",
        "source_reconciliation.py",
        "runner.py",
        "artifact_writer.py",
        "summary.py",
    }
)


_EXPECTED_STAGE25_PRODUCTION_MD: frozenset[str] = frozenset(
    {
        "STAGE_25_CLOSURE_AUDIT.md",
        "STAGE_26_HANDOFF.md",
    }
)


def test_stage25_production_py_inventory_complete():
    files = {
        p.name
        for p in STAGE25_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    missing = _EXPECTED_STAGE25_PRODUCTION_PY - files
    extra = files - _EXPECTED_STAGE25_PRODUCTION_PY
    assert not missing, f"Stage 25 production .py missing: {sorted(missing)}"
    assert not extra, f"Stage 25 production .py unexpected: {sorted(extra)}"


def test_stage25_production_md_inventory_complete():
    files = {
        p.name
        for p in STAGE25_ROOT.iterdir()
        if p.is_file() and p.suffix == ".md"
    }
    missing = _EXPECTED_STAGE25_PRODUCTION_MD - files
    assert not missing, (
        f"Stage 25 production .md missing at closure: {sorted(missing)}"
    )


def test_stage25_test_inventory_includes_closure_audit_test():
    test_files = {
        p.name
        for p in TESTS_STAGE25_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    expected_present = {
        "test_stage_25_1_boundaries.py",
        "test_stage_25_1_constants.py",
        "test_stage_25_1_input_reader.py",
        "test_stage_25_1_manifest.py",
        "test_stage_25_1_models.py",
        "test_stage_25_2_boundaries.py",
        "test_stage_25_2_migration_measurement.py",
        "test_stage_25_2_migration_observation.py",
        "test_stage_25_3_boundaries.py",
        "test_stage_25_3_price_observation.py",
        "test_stage_25_3_price_window.py",
        "test_stage_25_4_ath_candidate.py",
        "test_stage_25_4_boundaries.py",
        "test_stage_25_5_boundaries.py",
        "test_stage_25_5_source_reconciliation.py",
        "test_stage_25_6_artifact_writer.py",
        "test_stage_25_6_boundaries.py",
        "test_stage_25_6_runner.py",
        "test_stage_25_6_summary.py",
        "test_stage_25_7_closure_audit.py",
    }
    missing = expected_present - test_files
    assert not missing, f"Stage 25 test inventory missing: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Category 3: Artifact filename locks
# ---------------------------------------------------------------------------


def test_artifact_filename_constants_are_exposed():
    from PHX2.stage25 import constants as c

    expected_names = {
        "STAGE25_MIGRATION_OBSERVATIONS_FILENAME",
        "STAGE25_MIGRATION_MEASUREMENTS_FILENAME",
        "STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME",
        "STAGE25_ATH_CANDIDATES_FILENAME",
        "STAGE25_SOURCE_RECONCILIATIONS_FILENAME",
        "STAGE25_ATH_MEASUREMENTS_FILENAME",
        "STAGE25_MEASUREMENT_REJECTIONS_FILENAME",
        "STAGE25_SUMMARY_FILENAME",
        "STAGE25_MANIFEST_FILENAME",
        "STAGE25_ARTIFACT_FILENAMES",
        "STAGE25_EMITS_SOURCE_COVERAGE_CSV",
    }
    for name in expected_names:
        assert hasattr(c, name), f"constants missing {name}"


def test_artifact_filenames_tuple_equals_nine_locked_basenames():
    from PHX2.stage25 import constants as c

    expected: tuple[str, ...] = (
        "stage25_migration_observations.jsonl",
        "stage25_migration_measurements.jsonl",
        "stage25_price_window_observations.jsonl",
        "stage25_ath_candidates.jsonl",
        "stage25_source_reconciliations.jsonl",
        "stage25_ath_measurements.jsonl",
        "stage25_measurement_rejections.jsonl",
        "stage25_summary.json",
        "stage25_manifest.json",
    )
    assert set(c.STAGE25_ARTIFACT_FILENAMES) == set(expected)
    assert len(c.STAGE25_ARTIFACT_FILENAMES) == 9


def test_csv_emission_flag_is_locked_false():
    from PHX2.stage25 import constants as c

    assert c.STAGE25_EMITS_SOURCE_COVERAGE_CSV is False


def test_closure_audit_documents_each_locked_artifact_basename():
    text = _closure_audit_text()
    for basename in (
        "stage25_migration_observations.jsonl",
        "stage25_migration_measurements.jsonl",
        "stage25_price_window_observations.jsonl",
        "stage25_ath_candidates.jsonl",
        "stage25_source_reconciliations.jsonl",
        "stage25_ath_measurements.jsonl",
        "stage25_measurement_rejections.jsonl",
        "stage25_summary.json",
        "stage25_manifest.json",
    ):
        assert basename in text, f"closure audit missing {basename!r}"


def test_closure_audit_documents_csv_emission_flag_locked_false():
    text = _closure_audit_text()
    assert "STAGE25_EMITS_SOURCE_COVERAGE_CSV" in text
    assert "False" in text


# ---------------------------------------------------------------------------
# Category 4: Manifest self-entry locks
# ---------------------------------------------------------------------------


def test_self_referential_manifest_sha256_exists():
    from PHX2.stage25.stage25_manifest import (
        SELF_REFERENTIAL_MANIFEST_SHA256,
    )

    assert isinstance(SELF_REFERENTIAL_MANIFEST_SHA256, str)
    assert SELF_REFERENTIAL_MANIFEST_SHA256 != ""


def test_self_referential_manifest_sha256_is_not_64_char_lowercase_hex():
    """The sentinel must NOT look like a legitimate sha256 digest so
    downstream readers cannot mistake it for evidence.
    """
    from PHX2.stage25.stage25_manifest import (
        SELF_REFERENTIAL_MANIFEST_SHA256,
    )

    sentinel = SELF_REFERENTIAL_MANIFEST_SHA256
    is_64_lowercase_hex = (
        len(sentinel) == 64
        and all(ch in "0123456789abcdef" for ch in sentinel)
    )
    assert not is_64_lowercase_hex, (
        "manifest self-entry sentinel must not look like a 64-char "
        f"lowercase hex digest; got {sentinel!r}"
    )


def test_self_referential_manifest_byte_count_is_minus_one():
    from PHX2.stage25.stage25_manifest import (
        SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    )

    assert SELF_REFERENTIAL_MANIFEST_BYTE_COUNT == -1


def test_self_referential_manifest_row_count_is_minus_one():
    from PHX2.stage25.stage25_manifest import (
        SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    )

    assert SELF_REFERENTIAL_MANIFEST_ROW_COUNT == -1


def test_closure_audit_documents_self_referential_manifest_convention():
    text = _closure_audit_text()
    assert "SELF_REFERENTIAL_MANIFEST_SHA256" in text
    # Document the row/byte sentinel convention.
    assert "-1" in text


def test_handoff_doc_documents_self_referential_manifest_convention():
    text = _stage26_handoff_text()
    assert "SELF_REFERENTIAL_MANIFEST_SHA256" in text


# ---------------------------------------------------------------------------
# Category 5: Measurement-truth docs
# ---------------------------------------------------------------------------


_REQUIRED_CLOSURE_AUDIT_INVARIANTS: tuple[str, ...] = (
    # No fake ATH when source data is missing.
    "no fake ATH when source data is missing",
    # No fake migration timestamp when migration evidence is ambiguous.
    "no fake migration timestamp when migration evidence is ambiguous",
    # No 0 price/ATH missing sentinel.
    "no `0` price as a missing sentinel",
    "no `0` ATH as a missing sentinel",
    # Ambiguous migration cannot produce measured ATH.
    "ambiguous migration cannot produce a measured ATH",
    # UNKNOWN_WINDOW cannot become ATH eligible.
    "UNKNOWN_WINDOW",
    "ATH-eligible",
    # AMBIGUOUS candidate poisons reconciliation.
    "AMBIGUOUS",
    "poisons",
    # Distinct source families required for AGREED/MEASURED.
    "two distinct contributing source families",
    "AGREED",
    # SINGLE_SOURCE remains PARTIAL.
    "SINGLE_SOURCE",
    "PARTIAL",
    # DISAGREED_MAJOR/SOURCE_CONFLICT.
    "DISAGREED_MAJOR",
    "SOURCE_CONFLICT",
    # Non-MEASURED cannot fake peak fields.
    "non-`MEASURED` ATH measurement cannot carry fake peak fields",
)


@pytest.mark.parametrize("phrase", _REQUIRED_CLOSURE_AUDIT_INVARIANTS)
def test_closure_audit_documents_each_truth_invariant(phrase):
    text = _closure_audit_text()
    assert phrase in text, (
        f"closure audit missing required invariant phrase: {phrase!r}"
    )


def test_closure_audit_lists_each_status_token():
    text = _closure_audit_text()
    for token in (
        "MEASURED",
        "PARTIAL",
        "AMBIGUOUS",
        "SOURCE_CONFLICT",
        "MISSING",
        "UNSUPPORTED",
        "REJECTED",
        "NOT_APPLICABLE",
    ):
        assert token in text, f"closure audit missing status token {token!r}"


# ---------------------------------------------------------------------------
# Category 6: Stage 26 handoff docs
# ---------------------------------------------------------------------------


_REQUIRED_HANDOFF_PHRASES: tuple[str, ...] = (
    # Stage 26 consumes Stage 25 artifacts.
    "consumes",
    "Stage 25",
    # Must not mutate Stage 25 artifacts.
    "mutate any Stage 25 artifact",
    # Must not rewrite ATH/migration truth.
    "rewrite migration or ATH truth",
    # Stage 26.1 is calibration input contracts + artifact readers.
    "Stage 26.1",
    "calibration input contracts",
    "artifact readers",
    # Not enforcement yet.
    "Stage 26.1 does NOT yet ship",
    "enforcement of any threshold",
    # Defers Stage 27 X/social.
    "Stage 27",
    "X / social",
    # Defers routing/dispatch.
    "routing",
    "Discord / Telegram",
    # Defers confirmed Axiom/global-fee decoder unless separately reopened.
    "Axiom",
    "global-fee",
    "Sanitized real fixtures",
    "proof",
)


@pytest.mark.parametrize("phrase", _REQUIRED_HANDOFF_PHRASES)
def test_stage26_handoff_doc_contains_phrase(phrase):
    text = _stage26_handoff_text()
    assert phrase in text, (
        f"Stage 26 handoff doc missing required phrase: {phrase!r}"
    )


def test_stage26_handoff_says_no_x_social():
    text = _stage26_handoff_text()
    # Stage 26 must NOT implement X / social.
    assert "Stage 27" in text
    assert "X / social" in text or "X/social" in text


def test_stage26_handoff_says_no_routing_or_dispatch():
    text = _stage26_handoff_text()
    assert "routing" in text
    assert "dispatch" in text or "Dispatch" in text or "Discord" in text


def test_stage26_handoff_says_observe_only_first():
    text = _stage26_handoff_text()
    assert "observe-only" in text


def test_stage26_handoff_says_stage26_1_first():
    text = _stage26_handoff_text()
    assert "Stage 26.1" in text
    assert (
        "calibration input contracts + artifact readers" in text
    ) or (
        "calibration input contracts" in text
        and "artifact readers" in text
    )


# ---------------------------------------------------------------------------
# Category 7: Boundary scan
# ---------------------------------------------------------------------------


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
)


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    "helius",
    "jupiter",
    "discord",
    "telegram",
    "telethon",
    "webhook",
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "daemon",
    "sqlalchemy",
    "sqlite3",
    "dotenv",
    "keyring",
)


def _iter_stage25_production_py() -> list[Path]:
    return [
        p
        for p in STAGE25_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
    ]


def _collect_full_import_targets(source: str) -> set[str]:
    tree = ast.parse(source)
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                targets.add(mod)
                for alias in node.names:
                    targets.add(f"{mod}.{alias.name}")
    return targets


def test_no_stage25_production_imports_prior_stage():
    for path in _iter_stage25_production_py():
        targets = _collect_full_import_targets(
            path.read_text(encoding="utf-8")
        )
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import {target!r}"
                )


def test_no_stage25_production_imports_runtime_module_patterns():
    for path in _iter_stage25_production_py():
        targets = _collect_full_import_targets(
            path.read_text(encoding="utf-8")
        )
        for target in targets:
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern {pattern!r} "
                    f"in {target!r}"
                )


def test_no_stage25_production_reads_environ():
    env_attr_names = {"environ", "getenv", "environb"}
    for path in _iter_stage25_production_py():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        os_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        os_aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "os":
                    for alias in node.names:
                        assert alias.name not in env_attr_names, (
                            f"{path}: forbidden env-read import "
                            f"{alias.name!r}"
                        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id in os_aliases
                ):
                    assert node.attr not in env_attr_names, (
                        f"{path}: forbidden env-read pattern "
                        f"os.{node.attr}"
                    )


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
)


def test_no_url_literal_in_stage25_production_source():
    for path in _iter_stage25_production_py():
        source = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL literal {needle!r}"
            )


def test_no_url_literal_in_closure_docs():
    for path in (CLOSURE_AUDIT_PATH, STAGE26_HANDOFF_PATH):
        source = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL literal {needle!r}"
            )


_STAGE_26_7_ALLOWED_ENTRIES: frozenset[str] = frozenset(
    {
        # Stage 26.0 spec-lock scaffold.
        "__init__.py",
        "STAGE_26_0_SPEC_LOCK.md",
        # Stage 26.1 calibration-input contract + Stage 25 artifact
        # reader / validator surface.
        "constants.py",
        "errors.py",
        "models.py",
        "stage25_schema_whitelist.py",
        "stage25_artifact_reader.py",
        "stage25_artifact_validation.py",
        "calibration_input_contracts.py",
        # Stage 26.2 denominator / outcome-eligibility surface.
        "eligibility_constants.py",
        "eligibility_models.py",
        "eligibility_classifier.py",
        # Stage 26.3 calibration cohort builder surface.
        "cohort_constants.py",
        "cohort_models.py",
        "cohort_builder.py",
        # Stage 26.4 threshold candidate generator surface.
        "threshold_constants.py",
        "threshold_models.py",
        "threshold_candidate_generator.py",
        # Stage 26.5 observe-only policy candidate artifact builder
        # + writer surface.
        "policy_candidate_constants.py",
        "policy_candidate_models.py",
        "policy_candidate_builder.py",
        "policy_candidate_writer.py",
        # Stage 26.6 operator review packet / approval handoff
        # builder + writer surface.
        "review_packet_constants.py",
        "review_packet_models.py",
        "review_packet_builder.py",
        "review_packet_writer.py",
        # Stage 26.7 closure audit + Stage 27 handoff (docs only).
        # The Stage 27 implementation tree (``PHX2/stage27/``) and
        # every Stage 27 production file (runner / CLI / dispatcher
        # / Discord / Telegram / X-social / Axiom / approval /
        # enforcement) remain forbidden -- only these two closure
        # markdown documents are admitted.
        "STAGE_26_CLOSURE_AUDIT.md",
        "STAGE_27_HANDOFF.md",
    }
)


def test_stage26_tree_is_only_stage26_7_approved_files():
    """``PHX2/stage26/`` carries only the approved Stage 26.0-26.7 surface.

    Stage 25.7 originally asserted ``PHX2/stage26/`` did not exist.
    Stage 26.0 materialized the directory with a spec-lock-only
    scaffold. Stage 26.1 added the calibration-input contract +
    Stage 25 artifact reader / validator surface. Stage 26.2 added
    the denominator / outcome-eligibility surface. Stage 26.3 added
    the calibration cohort builder surface. Stage 26.4 added the
    threshold candidate generator surface. Stage 26.5 added the
    observe-only policy candidate artifact builder + writer
    surface. Stage 26.6 added the operator review packet /
    approval handoff builder + writer surface. Stage 26.7 added the
    Stage 26 closure-audit doc and the Stage 27 handoff doc (no
    Stage 26 production code was added in 26.7); this test was
    narrowly extended to admit exactly that locked file set:

      * ``__init__.py``                          -- Stage 26 package
                                                    marker.
      * ``STAGE_26_0_SPEC_LOCK.md``              -- Stage 26.0 spec-
                                                    lock document.
      * ``constants.py``                         -- Stage 26.1 closed-
                                                    set vocabularies.
      * ``errors.py``                            -- Stage 26.1 / 26.2 /
                                                    26.3 / 26.4 / 26.5
                                                    / 26.6 typed
                                                    errors.
      * ``models.py``                            -- Stage 26.1 immutable
                                                    input record
                                                    NamedTuples.
      * ``stage25_schema_whitelist.py``          -- locked Stage 25
                                                    schema / vocabulary
                                                    import surface.
      * ``stage25_artifact_reader.py``           -- pure per-row
                                                    projector reader.
      * ``stage25_artifact_validation.py``       -- structured per-file
                                                    validator.
      * ``calibration_input_contracts.py``       -- high-level Stage
                                                    26.1 orchestrator.
      * ``eligibility_constants.py``             -- Stage 26.2 closed-
                                                    set denominator /
                                                    outcome-eligibility
                                                    vocabularies.
      * ``eligibility_models.py``                -- Stage 26.2 immutable
                                                    eligibility record
                                                    NamedTuples.
      * ``eligibility_classifier.py``            -- pure deterministic
                                                    Stage 26.2 classifier.
      * ``cohort_constants.py``                  -- Stage 26.3 closed-
                                                    set cohort
                                                    vocabularies.
      * ``cohort_models.py``                     -- Stage 26.3 immutable
                                                    cohort record
                                                    NamedTuples.
      * ``cohort_builder.py``                    -- pure deterministic
                                                    Stage 26.3 cohort
                                                    builder.
      * ``threshold_constants.py``               -- Stage 26.4 closed-
                                                    set threshold
                                                    candidate
                                                    vocabularies.
      * ``threshold_models.py``                  -- Stage 26.4 immutable
                                                    threshold candidate
                                                    record NamedTuples.
      * ``threshold_candidate_generator.py``     -- pure deterministic
                                                    Stage 26.4 threshold
                                                    candidate generator.
      * ``policy_candidate_constants.py``        -- Stage 26.5 closed-
                                                    set policy candidate
                                                    vocabularies.
      * ``policy_candidate_models.py``           -- Stage 26.5 immutable
                                                    observe-only policy
                                                    candidate record
                                                    NamedTuples.
      * ``policy_candidate_builder.py``          -- pure deterministic
                                                    Stage 26.5
                                                    observe-only policy
                                                    candidate builder.
      * ``policy_candidate_writer.py``           -- deterministic Stage
                                                    26.5 offline
                                                    observe-only
                                                    artifact writer.
      * ``review_packet_constants.py``           -- Stage 26.6 closed-
                                                    set operator review
                                                    packet / approval
                                                    handoff vocabularies.
      * ``review_packet_models.py``              -- Stage 26.6 immutable
                                                    review packet record
                                                    NamedTuples.
      * ``review_packet_builder.py``             -- pure deterministic
                                                    Stage 26.6 operator
                                                    review packet
                                                    builder.
      * ``review_packet_writer.py``              -- deterministic Stage
                                                    26.6 offline
                                                    review-only operator
                                                    review packet
                                                    artifact writer.
      * ``STAGE_26_CLOSURE_AUDIT.md``            -- Stage 26.7 closure-
                                                    audit document
                                                    (docs only).
      * ``STAGE_27_HANDOFF.md``                  -- Stage 26.7 Stage 27
                                                    handoff document
                                                    (docs only).

    Any other top-level entry under ``PHX2/stage26/`` -- a runner /
    CLI / dispatcher / live-router / Discord / Telegram / X-social
    / Axiom / approval / enforcement module, or a subdirectory
    other than the interpreter's ``__pycache__`` -- is treated as
    Stage 27 implementation and is forbidden. Stage 27
    implementation (and ``PHX2/stage27/``) remains blocked until
    Stage 27 is operator-authorized.
    """
    stage26 = PHX2_ROOT / "stage26"
    if not stage26.exists():
        return
    assert stage26.is_dir(), (
        f"PHX2/stage26 must be a directory if it exists: {stage26}"
    )
    actual: set[str] = set()
    for entry in stage26.iterdir():
        # The interpreter's bytecode cache directory is build noise,
        # not Stage 26 source surface; the rejection check is on
        # Stage 26 source entries only.
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = actual - _STAGE_26_7_ALLOWED_ENTRIES
    assert not forbidden, (
        f"PHX2/stage26 admits only the locked Stage 26.0 + Stage 26.1 "
        f"+ Stage 26.2 + Stage 26.3 + Stage 26.4 + Stage 26.5 + Stage "
        f"26.6 + Stage 26.7 file set ("
        f"{sorted(_STAGE_26_7_ALLOWED_ENTRIES)!r}). Stage 27 "
        f"implementation (runner / CLI / dispatcher / live router / "
        f"Discord / Telegram / X-social / Axiom / approval / "
        f"enforcement) remains blocked until Stage 27 is operator-"
        f"authorized. Forbidden entries found: {sorted(forbidden)!r}"
    )


def test_stage27_implementation_tree_does_not_exist():
    stage27 = PHX2_ROOT / "stage27"
    assert not stage27.exists(), (
        f"Stage 25.7 must not ship a Stage 27 implementation tree: "
        f"{stage27}"
    )


_FORBIDDEN_DOMAIN_SUBSTRINGS_STAGE_25_7: tuple[str, ...] = (
    "calibration",
    "enforcement",
    "enforcer",
    "ratchet",
    "tweet",
    "twitter",
    "subscriber_tier",
    "dispatcher",
)


def _extract_all_identifiers(source: str) -> set[str]:
    tree = ast.parse(source)
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
        elif isinstance(node, ast.alias):
            idents.add(node.name)
            if node.asname:
                idents.add(node.asname)
    return idents


def test_no_stage25_production_identifier_implements_calibration_or_dispatch():
    """No Stage 25 production identifier implements Stage 26
    calibration / enforcement / Stage 27 X-social / routing /
    dispatch logic.
    """
    for path in _iter_stage25_production_py():
        idents = _extract_all_identifiers(
            path.read_text(encoding="utf-8")
        )
        for ident in idents:
            lower = ident.lower()
            for forbidden in _FORBIDDEN_DOMAIN_SUBSTRINGS_STAGE_25_7:
                assert forbidden not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden Stage 26+/27+ substring {forbidden!r}"
                )


# ---------------------------------------------------------------------------
# Category 8: No tag / push behavior
# ---------------------------------------------------------------------------


def test_closure_audit_disclaims_tag_creation_by_implementation():
    text = _closure_audit_text().lower()
    # The doc must state that no tag is created by the
    # implementation pass itself.
    assert "no tag" in text or "does not create any tag" in text


def test_closure_audit_explicitly_says_operator_creates_tag():
    text = _closure_audit_text().lower()
    assert "operator" in text
    assert "stage-25-closed" in text
    assert "authorization" in text


def test_closure_audit_lists_pre_closure_test_count():
    """The audit documents the focused Stage 25 suite pass count just
    before 25.7."""
    text = _closure_audit_text()
    assert "801" in text


def test_stage26_handoff_says_stage_26_must_not_mutate_artifacts():
    text = _stage26_handoff_text()
    assert (
        "mutate any Stage 25 artifact" in text
        or "read-only ingestion" in text
    )


def test_stage26_handoff_says_stage_26_must_not_rewrite_truth():
    text = _stage26_handoff_text()
    assert "rewrite migration or ATH truth" in text


def test_stage26_handoff_documents_single_source_partial_default():
    text = _stage26_handoff_text()
    assert "Single-source evidence defaults to" in text
    assert "PARTIAL" in text


def test_closure_audit_documents_observe_only_posture():
    text = _closure_audit_text()
    assert "observe-only" in text or "observe_only" in text


def test_closure_audit_documents_redaction_token():
    text = _closure_audit_text()
    assert "REDACTION_CONFIRMED_TOKEN" in text
    assert "stage25_redaction_confirmed" in text


def test_closure_audit_documents_stage24_pin_basename_only():
    text = _closure_audit_text()
    assert "Stage 24" in text
    assert "basename" in text
    assert "sha256" in text


def test_closure_audit_filename_lock_includes_all_substring_searches():
    """Sanity: every locked filename appears in the audit doc verbatim.

    Pinned via a regex so a future rename in ``constants.py`` that
    bypasses the audit doc is caught.
    """
    from PHX2.stage25 import constants as c

    text = _closure_audit_text()
    for basename in c.STAGE25_ARTIFACT_FILENAMES:
        assert re.search(re.escape(basename), text), (
            f"closure audit doc missing locked artifact filename "
            f"{basename!r}"
        )
