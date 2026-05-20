"""Stage 24.7 closure-audit tests.

Stage 24.7 is the closure sub-stage. It ships no production
decoder / runner / writer; it ships only two closure docs
(``STAGE_24_CLOSURE_AUDIT.md`` / ``STAGE_25_HANDOFF.md``) and
this test file.

The tests in this module pin the closure state at the
content / file / constant level:

  * Both closure docs exist under ``PHX2/stage24/``.
  * The docs mention the seven Stage 24 commit short SHAs
    (``3957347`` / ``a0ce8d8`` / ``107fc3b`` / ``a593cf7`` /
    ``cd8d7a8`` / ``3af1ba5`` / ``5ae1709``).
  * The docs mention the eleven Stage 24 artifact filenames.
  * The docs explicitly state Stage 24 is observe-only.
  * The docs explicitly mention Stage 24.5 Path B and the
    no-confirmed-router-fee-decoder state.
  * The Stage 24.5 lock scalar constants in ``constants.py``
    remain at the locked values
    (``STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER is False`` /
    ``STAGE_24_5_REAL_FIXTURE_COUNT == 0`` /
    ``STAGE_24_5_CONFIRMED_LAYOUT_COUNT == 0``).
  * ``router_fee.py`` source still carries no
    ``DECODER_STATUS_DECODED`` reference and no confirmed
    ``FEE_SOURCE_AXIOM_GLOBAL_FEE`` reference.
  * The Stage 25 handoff doc mentions ATH / migration and
    defers calibration / enforcement to Stage 26 and
    X / social to Stage 27+.
  * The Stage 24 production tree contains exactly the locked
    set of Python files plus the three docs.
  * No Stage 24 production module imports a Stage 21 /
    Stage 22 / Stage 23 production target, a Phoenix1 target,
    a DB / network / Discord / Telegram library, ``os.environ``
    / ``os.getenv``, or a CLI library.
  * No Stage 25 / Stage 26 / Stage 27 feature files have been
    created under ``PHX2/stage24/``.

The closure tests deliberately overlap with the rolling
Stage 24 boundary tests in places. The overlap is intentional:
closure pins the state explicitly at the audit moment, while
the boundary tests track the rolling invariant.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage24 import constants as c


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


REPO_ROOT: Path = Path(__file__).parent.parent.parent.parent
STAGE24_ROOT: Path = REPO_ROOT / "PHX2" / "stage24"
CLOSURE_AUDIT_DOC: Path = STAGE24_ROOT / "STAGE_24_CLOSURE_AUDIT.md"
STAGE_25_HANDOFF_DOC: Path = STAGE24_ROOT / "STAGE_25_HANDOFF.md"
STAGE_24_5_LOCK_DOC: Path = STAGE24_ROOT / "STAGE_24_5_NO_DECODER_LOCK.md"
ROUTER_FEE_PY: Path = STAGE24_ROOT / "router_fee.py"


# ---------------------------------------------------------------------------
# Locked closure content
# ---------------------------------------------------------------------------


_EXPECTED_COMMIT_SHORT_SHAS: tuple[str, ...] = (
    "3957347",
    "a0ce8d8",
    "107fc3b",
    "a593cf7",
    "cd8d7a8",
    "3af1ba5",
    "5ae1709",
)


_EXPECTED_ARTIFACT_FILENAMES: tuple[str, ...] = (
    "stage24_manifest.json",
    "stage24_summary.json",
    "stage24_execution_primitives.jsonl",
    "stage24_compute_budget_results.jsonl",
    "stage24_priority_fee_results.jsonl",
    "stage24_jito_tip_results.jsonl",
    "stage24_router_fee_results.jsonl",
    "stage24_router_fee_candidates.jsonl",
    "stage24_execution_quality_results.jsonl",
    "stage24_decoder_coverage.csv",
    "stage24_rejections.jsonl",
)


# ---------------------------------------------------------------------------
# Locked Stage 24 production / docs filename set
# ---------------------------------------------------------------------------


_EXPECTED_PRODUCTION_PY_FILES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "constants.py",
        "errors.py",
        "models.py",
        "decoder_contracts.py",
        "input_reader.py",
        "stage24_manifest.py",
        "compute_budget.py",
        "priority_fee.py",
        "jito_tip.py",
        "router_fee.py",
        "execution_quality.py",
        "runner.py",
        "artifact_writer.py",
    }
)


_EXPECTED_PRODUCTION_MD_FILES: frozenset[str] = frozenset(
    {
        "STAGE_24_5_NO_DECODER_LOCK.md",
        "STAGE_24_CLOSURE_AUDIT.md",
        "STAGE_25_HANDOFF.md",
    }
)


# Stage 24.7 must NOT have introduced any Stage 25 / Stage 26 /
# Stage 27 feature file. The substrings below cover the canonical
# Stage 25+ vocabulary that has been deferred per
# ``PHX2/docs/STAGE_24_BRAINSTORM.md`` Section 2.
_FORBIDDEN_LATER_STAGE_FILE_PREFIXES: tuple[str, ...] = (
    "birdeye",
    "dexscreener",
    "ath",
    "migration",
    "x_api",
    "social",
    "enforce",
    "gate",
    "calibration",
    "subscriber",
    "public_channel",
    "paid_signal",
    "discord",
    "telegram",
    "scheduler",
    "daemon",
    "orchestrator",
)


# ---------------------------------------------------------------------------
# Forbidden import targets
# ---------------------------------------------------------------------------


_FORBIDDEN_PRIOR_STAGE_PRODUCTION_PREFIXES: tuple[str, ...] = (
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
)


_FORBIDDEN_NETWORK_IMPORT_TOPS: frozenset[str] = frozenset(
    {
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "urllib3",
        "websockets",
        "websocket",
        "grpc",
        "grpcio",
        "socket",
        "ssl",
        "http",
    }
)


_FORBIDDEN_DB_IMPORT_TOPS: frozenset[str] = frozenset(
    {
        "sqlite3",
        "sqlalchemy",
    }
)


_FORBIDDEN_MESSAGING_IMPORT_TOPS: frozenset[str] = frozenset(
    {
        "discord",
        "telegram",
        "telethon",
    }
)


_FORBIDDEN_CLI_IMPORT_TOPS: frozenset[str] = frozenset(
    {
        "argparse",
        "click",
        "typer",
        "fire",
        "docopt",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_production_py_modules() -> list[Path]:
    return [
        p
        for p in STAGE24_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
                if mod:
                    targets.add(f"{mod}.{alias.name}")
    return targets


def _collect_top_level_import_names(source: str) -> set[str]:
    tree = ast.parse(source)
    tops: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                tops.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                tops.add(mod.split(".")[0])
    return tops


def _module_reads_env_in_source(source: str) -> bool:
    tree = ast.parse(source)
    os_aliases: set[str] = set()
    env_call_aliases: set[str] = set()
    env_attr_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "os":
                for alias in node.names:
                    bound_name = alias.asname or alias.name
                    if alias.name in ("environ", "environb"):
                        env_attr_aliases.add(bound_name)
                    elif alias.name == "getenv":
                        env_call_aliases.add(bound_name)
            elif mod == "os.environ" or mod.startswith("os.environ."):
                return True

    if env_attr_aliases or env_call_aliases:
        return True

    env_attr_names: frozenset[str] = frozenset(
        {"environ", "getenv", "environb"}
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in env_attr_names
            ):
                return True
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in os_aliases
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value in env_attr_names
            ):
                return True
    return False


def _router_fee_identifiers() -> set[str]:
    tree = ast.parse(_read_source(ROUTER_FEE_PY))
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
        elif isinstance(node, ast.alias):
            idents.add(node.name)
            if node.asname:
                idents.add(node.asname)
    return idents


# ---------------------------------------------------------------------------
# Doc presence
# ---------------------------------------------------------------------------


def test_closure_audit_doc_exists():
    assert CLOSURE_AUDIT_DOC.is_file(), (
        f"Stage 24.7 closure audit doc missing: {CLOSURE_AUDIT_DOC}"
    )


def test_stage_25_handoff_doc_exists():
    assert STAGE_25_HANDOFF_DOC.is_file(), (
        f"Stage 24.7 Stage 25 handoff doc missing: {STAGE_25_HANDOFF_DOC}"
    )


def test_stage_24_5_lock_doc_still_exists():
    assert STAGE_24_5_LOCK_DOC.is_file(), (
        f"Stage 24.5 lock doc missing: {STAGE_24_5_LOCK_DOC}"
    )


# ---------------------------------------------------------------------------
# Doc content -- commit short SHAs
# ---------------------------------------------------------------------------


def test_closure_audit_doc_mentions_all_stage24_commit_short_shas():
    text = _read_source(CLOSURE_AUDIT_DOC)
    missing = [
        sha for sha in _EXPECTED_COMMIT_SHORT_SHAS if sha not in text
    ]
    assert not missing, (
        "Closure audit doc must mention every Stage 24 commit short "
        f"SHA; missing: {missing}"
    )


# ---------------------------------------------------------------------------
# Doc content -- artifact filenames
# ---------------------------------------------------------------------------


def test_closure_audit_doc_mentions_all_eleven_artifact_filenames():
    text = _read_source(CLOSURE_AUDIT_DOC)
    missing = [
        name
        for name in _EXPECTED_ARTIFACT_FILENAMES
        if name not in text
    ]
    assert not missing, (
        "Closure audit doc must mention every Stage 24 artifact "
        f"filename; missing: {missing}"
    )


def test_stage_25_handoff_doc_references_stage_24_artifact_filenames():
    """The Stage 25 handoff doc must reference the Stage 24 artifact
    filenames as the read-only context Stage 25 consumes.
    """
    text = _read_source(STAGE_25_HANDOFF_DOC)
    missing = [
        name
        for name in _EXPECTED_ARTIFACT_FILENAMES
        if name not in text
    ]
    assert not missing, (
        "Stage 25 handoff doc must reference Stage 24 artifact "
        f"filenames; missing: {missing}"
    )


# ---------------------------------------------------------------------------
# Doc content -- Path B / no-confirmed-router-fee-decoder
# ---------------------------------------------------------------------------


def test_closure_audit_doc_mentions_path_b():
    text = _read_source(CLOSURE_AUDIT_DOC)
    assert "Path B" in text, (
        "Closure audit doc must explicitly mention Stage 24.5 Path B"
    )


def test_closure_audit_doc_mentions_no_confirmed_router_fee_decoder():
    text = _read_source(CLOSURE_AUDIT_DOC).lower()
    assert "no confirmed" in text, (
        "Closure audit doc must state Stage 24 has no confirmed "
        "router / global-fee decoder"
    )
    assert ("router" in text) or ("global-fee" in text) or (
        "global fee" in text
    ), (
        "Closure audit doc must mention router / global-fee "
        "primitive"
    )


def test_closure_audit_doc_mentions_stage_24_5_lock_scalar_constants():
    """The closure audit doc must mention the three Stage 24.5 lock
    scalar constants verbatim so a future audit can grep for them
    without having to open ``constants.py``.
    """
    text = _read_source(CLOSURE_AUDIT_DOC)
    assert "STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER" in text
    assert "STAGE_24_5_REAL_FIXTURE_COUNT" in text
    assert "STAGE_24_5_CONFIRMED_LAYOUT_COUNT" in text


def test_closure_audit_doc_forbids_decoded_router_fee_at_audit_time():
    text = _read_source(CLOSURE_AUDIT_DOC)
    assert "DECODED" in text, (
        "Closure audit doc must mention DECODED to anchor the "
        "no-DECODED router-fee claim"
    )
    lowered = text.lower()
    assert ("router_fee" in lowered) or ("router-fee" in lowered) or (
        "router fee" in lowered
    )


def test_closure_audit_doc_forbids_non_none_router_amount_lamports():
    text = _read_source(CLOSURE_AUDIT_DOC)
    assert "amount_lamports" in text, (
        "Closure audit doc must reference amount_lamports to anchor "
        "the None-only router-amount claim"
    )
    assert "None" in text


def test_closure_audit_doc_forbids_confirmed_axiom_global_fee_source():
    text = _read_source(CLOSURE_AUDIT_DOC)
    # The doc explicitly contrasts the confirmed (no underscore-suffix)
    # variants with the candidate variants and states only the
    # candidates are emitted.
    assert "AXIOM_GLOBAL_FEE" in text
    assert "AXIOM_GLOBAL_FEE_CANDIDATE" in text


# ---------------------------------------------------------------------------
# Doc content -- observe-only posture
# ---------------------------------------------------------------------------


def test_closure_audit_doc_states_observe_only_explicitly():
    text = _read_source(CLOSURE_AUDIT_DOC).lower()
    assert "stage 24 is **observe-only**" in text or (
        "stage 24 is observe-only" in text
    ), (
        "Closure audit doc must explicitly state Stage 24 is "
        "observe-only"
    )


# ---------------------------------------------------------------------------
# Doc content -- Stage 25 handoff deferral statements
# ---------------------------------------------------------------------------


def test_stage_25_handoff_doc_mentions_ath_and_migration():
    text = _read_source(STAGE_25_HANDOFF_DOC).lower()
    assert "ath" in text, (
        "Stage 25 handoff doc must mention ATH"
    )
    assert "migration" in text, (
        "Stage 25 handoff doc must mention migration"
    )


def test_stage_25_handoff_doc_defers_stage_26_calibration_enforcement():
    text = _read_source(STAGE_25_HANDOFF_DOC).lower()
    assert "stage 26" in text and "calibration" in text and (
        "enforcement" in text
    ), (
        "Stage 25 handoff doc must defer calibration / enforcement "
        "to Stage 26"
    )


def test_stage_25_handoff_doc_defers_stage_27_x_social():
    text = _read_source(STAGE_25_HANDOFF_DOC).lower()
    assert "stage 27" in text and "social" in text and (
        "x api" in text or "x_api" in text or "x / social" in text
    ), (
        "Stage 25 handoff doc must defer X / social primitives to "
        "Stage 27+"
    )


def test_stage_25_handoff_doc_states_stage_24_does_not_solve_ath():
    text = _read_source(STAGE_25_HANDOFF_DOC).lower()
    assert "stage 24 does" in text and "ath" in text, (
        "Stage 25 handoff doc must explicitly state Stage 24 does "
        "not solve ATH"
    )


def test_stage_25_handoff_doc_forbids_confirmed_router_fee_promotion():
    """Stage 25 must not promote any Stage 24 router-fee primitive to
    DECODED; the handoff doc must state this so the next-stage
    author cannot accidentally re-open the Stage 24.5 lock.
    """
    text = _read_source(STAGE_25_HANDOFF_DOC).lower()
    assert "fixture proof" in text or "fixture-backed" in text or (
        "fixture-proven" in text
    ), (
        "Stage 25 handoff doc must reference fixture-proof "
        "requirement for any future router-fee promotion"
    )


# ---------------------------------------------------------------------------
# Stage 24.5 lock scalar constants
# ---------------------------------------------------------------------------


def test_stage_24_5_has_confirmed_router_fee_decoder_still_false():
    assert c.STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER is False


def test_stage_24_5_real_fixture_count_still_zero():
    assert c.STAGE_24_5_REAL_FIXTURE_COUNT == 0


def test_stage_24_5_confirmed_layout_count_still_zero():
    assert c.STAGE_24_5_CONFIRMED_LAYOUT_COUNT == 0


# ---------------------------------------------------------------------------
# router_fee.py source still candidate-only
# ---------------------------------------------------------------------------


def test_router_fee_source_does_not_use_decoder_status_decoded():
    assert "DECODER_STATUS_DECODED" not in _router_fee_identifiers(), (
        "router_fee.py must not reference DECODER_STATUS_DECODED at "
        "Stage 24 closure"
    )


def test_router_fee_source_does_not_use_confirmed_axiom_global_fee():
    assert "FEE_SOURCE_AXIOM_GLOBAL_FEE" not in (
        _router_fee_identifiers()
    ), (
        "router_fee.py must not reference FEE_SOURCE_AXIOM_GLOBAL_FEE "
        "at Stage 24 closure; only the _CANDIDATE variant is allowed"
    )


# ---------------------------------------------------------------------------
# Production tree inventory
# ---------------------------------------------------------------------------


def test_stage24_root_directory_exists():
    assert STAGE24_ROOT.is_dir(), (
        f"Stage 24 production root missing: {STAGE24_ROOT}"
    )


def test_production_py_files_match_expected_set_exactly():
    actual = {
        p.name
        for p in STAGE24_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    extra = actual - _EXPECTED_PRODUCTION_PY_FILES
    missing = _EXPECTED_PRODUCTION_PY_FILES - actual
    assert not extra and not missing, (
        f"Stage 24 production .py tree mismatch; "
        f"extra={sorted(extra)}, missing={sorted(missing)}"
    )


def test_production_md_files_match_expected_set_exactly():
    actual = {
        p.name
        for p in STAGE24_ROOT.iterdir()
        if p.is_file() and p.suffix == ".md"
    }
    extra = actual - _EXPECTED_PRODUCTION_MD_FILES
    missing = _EXPECTED_PRODUCTION_MD_FILES - actual
    assert not extra and not missing, (
        f"Stage 24 production .md tree mismatch; "
        f"extra={sorted(extra)}, missing={sorted(missing)}"
    )


def test_no_unexpected_file_types_under_stage24_root():
    """The Stage 24 production tree should contain only .py and .md
    files at the top level (no .json / .csv / .pyc / .toml / etc).
    """
    allowed_suffixes: frozenset[str] = frozenset({".py", ".md"})
    leaked: list[str] = []
    for p in STAGE24_ROOT.iterdir():
        if not p.is_file():
            continue
        if p.suffix not in allowed_suffixes:
            leaked.append(p.name)
    assert not leaked, (
        f"Stage 24 production tree carries unexpected file types: "
        f"{leaked}"
    )


def test_no_subdirectories_under_stage24_root():
    """Stage 24 is a flat module layout; no subdirectories live under
    ``PHX2/stage24/`` apart from ``__pycache__`` (which the test
    skips).
    """
    leaked: list[str] = []
    for p in STAGE24_ROOT.iterdir():
        if p.is_dir() and p.name != "__pycache__":
            leaked.append(p.name)
    assert not leaked, (
        f"Stage 24 production tree carries unexpected subdirectories: "
        f"{leaked}"
    )


def test_no_stage25_stage26_stage27_feature_files_created():
    """The Stage 24 production tree must not carry any feature file
    whose basename starts with a Stage 25 / Stage 26 / Stage 27
    vocabulary prefix.
    """
    leaked: list[str] = []
    for p in STAGE24_ROOT.iterdir():
        if not p.is_file():
            continue
        basename_lower = p.name.lower()
        for prefix in _FORBIDDEN_LATER_STAGE_FILE_PREFIXES:
            if basename_lower.startswith(prefix):
                leaked.append(p.name)
                break
    assert not leaked, (
        "Stage 24 production tree carries forbidden later-stage "
        f"feature files: {leaked}"
    )


# ---------------------------------------------------------------------------
# Env-read prohibition
# ---------------------------------------------------------------------------


def test_no_production_module_reads_os_environ():
    leaked: list[str] = []
    for py_file in _iter_production_py_modules():
        if _module_reads_env_in_source(_read_source(py_file)):
            leaked.append(py_file.name)
    assert not leaked, (
        f"Stage 24 production modules with env-read pattern: {leaked}"
    )


# ---------------------------------------------------------------------------
# Forbidden import prohibitions
# ---------------------------------------------------------------------------


def test_no_production_module_imports_stage21_stage22_stage23():
    leaked: list[tuple[str, str]] = []
    for py_file in _iter_production_py_modules():
        for target in _collect_full_import_targets(_read_source(py_file)):
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PRODUCTION_PREFIXES:
                if target.startswith(forbidden):
                    leaked.append((py_file.name, target))
    assert not leaked, (
        "Stage 24 production modules must not import Stage 21 / "
        f"Stage 22 / Stage 23 targets; leaked: {leaked}"
    )


def test_no_production_module_imports_phoenix1():
    leaked: list[tuple[str, str]] = []
    for py_file in _iter_production_py_modules():
        for target in _collect_full_import_targets(_read_source(py_file)):
            if target.lower().startswith("phoenix1"):
                leaked.append((py_file.name, target))
    assert not leaked, (
        f"Stage 24 production modules must not import phoenix1: "
        f"{leaked}"
    )


def test_no_production_module_imports_network_library():
    leaked: list[tuple[str, str]] = []
    for py_file in _iter_production_py_modules():
        tops = _collect_top_level_import_names(_read_source(py_file))
        for top in tops:
            if top in _FORBIDDEN_NETWORK_IMPORT_TOPS:
                leaked.append((py_file.name, top))
    assert not leaked, (
        f"Stage 24 production modules with network-library imports: "
        f"{leaked}"
    )


def test_no_production_module_imports_database_library():
    leaked: list[tuple[str, str]] = []
    for py_file in _iter_production_py_modules():
        tops = _collect_top_level_import_names(_read_source(py_file))
        for top in tops:
            if top in _FORBIDDEN_DB_IMPORT_TOPS:
                leaked.append((py_file.name, top))
    assert not leaked, (
        f"Stage 24 production modules with database imports: "
        f"{leaked}"
    )


def test_no_production_module_imports_messaging_library():
    leaked: list[tuple[str, str]] = []
    for py_file in _iter_production_py_modules():
        tops = _collect_top_level_import_names(_read_source(py_file))
        for top in tops:
            if top in _FORBIDDEN_MESSAGING_IMPORT_TOPS:
                leaked.append((py_file.name, top))
    assert not leaked, (
        f"Stage 24 production modules with messaging imports: "
        f"{leaked}"
    )


def test_no_production_module_imports_cli_library():
    leaked: list[tuple[str, str]] = []
    for py_file in _iter_production_py_modules():
        tops = _collect_top_level_import_names(_read_source(py_file))
        for top in tops:
            if top in _FORBIDDEN_CLI_IMPORT_TOPS:
                leaked.append((py_file.name, top))
    assert not leaked, (
        f"Stage 24 production modules with CLI-library imports: "
        f"{leaked}"
    )


# ---------------------------------------------------------------------------
# Constants artifact filename tuple matches the closure-pinned set
# ---------------------------------------------------------------------------


def test_constants_artifact_filename_tuple_matches_closure_pin():
    """The locked ``ALL_STAGE24_ARTIFACT_FILENAMES`` tuple in
    ``constants.py`` must contain exactly the eleven Stage 24
    artifact filenames the closure audit doc pins.
    """
    constants_set = set(c.ALL_STAGE24_ARTIFACT_FILENAMES)
    closure_set = set(_EXPECTED_ARTIFACT_FILENAMES)
    assert constants_set == closure_set, (
        f"ALL_STAGE24_ARTIFACT_FILENAMES drift from closure pin: "
        f"constants_extra={sorted(constants_set - closure_set)}, "
        f"closure_extra={sorted(closure_set - constants_set)}"
    )


def test_constants_artifact_filename_tuple_length_is_eleven():
    assert len(c.ALL_STAGE24_ARTIFACT_FILENAMES) == 11
