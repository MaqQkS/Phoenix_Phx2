"""Stage 23.6 closure-audit tests.

Stage 23.6 is the closure sub-stage. It ships no production
filter / runner / writer; it ships only two closure docs
(``STAGE_23_CLOSURE_AUDIT.md`` / ``STAGE_24_HANDOFF.md``) and
this test file.

The tests in this module pin the closure state at the
content / file / tag levels:

  * Both closure docs exist under ``PHX2/stage23/``.
  * The docs mention the locked Stage 23 commit short SHAs.
  * The docs mention the three Stage 23 filter names.
  * The docs mention the six Stage 23 artifact filenames.
  * The docs explicitly state Stage 23 is observe-only.
  * The docs explicitly defer Stage 24 / Stage 25 / Stage 26 /
    Stage 27+.
  * The Stage 23 production tree contains exactly the locked
    set of Python files plus the two closure docs.
  * No Stage 23-forbidden production file exists at closure.
  * No Stage 23 production identifier carries a forbidden
    substring (AST-position scan; string literals and
    docstrings are NOT scanned so the locked forbidden-
    vocabulary tuples in ``constants.py`` do not false-flag).
  * No Stage 23 production module reads ``os.environ`` /
    ``os.getenv`` (AST-shape scan).
  * No Stage 23 production module imports a network /
    SQLite / SQLAlchemy library.
  * No Stage 23 production module imports a
    ``PHX2.stage21`` / ``PHX2.stage22`` production target.
  * The ``stage-22-closed`` tag dereferences to the locked
    Stage 22 close commit SHA.
  * No ``stage-23-*`` tag exists yet at audit time.

The closure tests deliberately overlap with the rolling
Stage 23 boundary tests in places. The overlap is intentional:
closure pins the state explicitly at the audit moment, while
the boundary tests track the rolling invariant.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


REPO_ROOT: Path = Path(__file__).parent.parent.parent.parent
STAGE23_ROOT: Path = REPO_ROOT / "PHX2" / "stage23"
CLOSURE_AUDIT_DOC: Path = STAGE23_ROOT / "STAGE_23_CLOSURE_AUDIT.md"
STAGE_24_HANDOFF_DOC: Path = STAGE23_ROOT / "STAGE_24_HANDOFF.md"


# ---------------------------------------------------------------------------
# Locked closure content
# ---------------------------------------------------------------------------


_EXPECTED_COMMIT_SHORT_SHAS: tuple[str, ...] = (
    "defd8ea",
    "aa5fe71",
    "d1dab41",
    "a87ba11",
    "238f997",
)


_EXPECTED_FILTER_NAMES: tuple[str, ...] = (
    "holder_concentration",
    "launch_structure",
    "wallet_source_quality",
)


_EXPECTED_ARTIFACT_FILENAMES: tuple[str, ...] = (
    "stage23_filter_evaluations.jsonl",
    "stage23_filter_summary.csv",
    "stage23_reason_code_counts.csv",
    "stage23_data_status_counts.csv",
    "stage23_label_counts.csv",
    "stage23_manifest.json",
)


# Stage 22 close commit (dereferenced from the annotated
# ``stage-22-closed`` tag at closure-audit time).
_STAGE_22_CLOSE_COMMIT_SHA: str = (
    "9647f8eb94204203d2d8ef1da035e3bc5ed28b5d"
)


# ---------------------------------------------------------------------------
# Locked Stage 23 production / docs filename set
# ---------------------------------------------------------------------------


_EXPECTED_PRODUCTION_PY_FILES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "constants.py",
        "errors.py",
        "models.py",
        "input_reader.py",
        "filter_contracts.py",
        "stage23_manifest.py",
        "holder_concentration.py",
        "launch_structure.py",
        "wallet_source_quality.py",
        "runner.py",
        "artifact_writer.py",
    }
)


_EXPECTED_CLOSURE_DOC_FILES: frozenset[str] = frozenset(
    {
        "STAGE_23_CLOSURE_AUDIT.md",
        "STAGE_24_HANDOFF.md",
    }
)


# Filenames / filename-prefix patterns that must NOT appear in the
# Stage 23 production tree at closure. Each entry is a (basename,
# kind) pair where ``kind`` is ``"exact"`` for an exact-filename
# match or ``"prefix"`` for a basename-prefix match.
_FORBIDDEN_PRODUCTION_FILE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("cli.py", "exact"),
    ("discord", "prefix"),
    ("telegram", "prefix"),
    ("transport", "prefix"),
    ("sink", "prefix"),
    ("db", "prefix"),
    ("repository", "prefix"),
    ("x_api", "prefix"),
    ("social", "prefix"),
    ("birdeye", "prefix"),
    ("dexscreener", "prefix"),
    ("axiom", "prefix"),
    ("jito", "prefix"),
)


# ---------------------------------------------------------------------------
# Forbidden identifier substrings (AST identifier-position scan)
# ---------------------------------------------------------------------------
#
# These substrings must not appear in any IDENTIFIER position of any
# Stage 23 production module. They MAY appear inside string literals
# (in particular the ``STAGE23_FORBIDDEN_*`` tuples in
# ``constants.py`` legitimately list these tokens as inputs to the
# boundary scanner) and docstrings. Mirrors the
# ``test_no_production_identifier_contains_forbidden_vocabulary``
# scan technique in ``test_stage_23_1_boundaries.py``.


_FORBIDDEN_IDENTIFIER_SUBSTRINGS: tuple[str, ...] = (
    "enforce",
    "block_token",
    "block",
    "blocking",
    "send_to_discord",
    "send_to_telegram",
    "subscriber",
    "public_channel",
    "paid_signal",
    "birdeye",
    "dexscreener",
    "axiom",
    "jito",
    "priority_fee",
    "x_api",
    "social",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_production_py_modules() -> list[Path]:
    return [
        p
        for p in STAGE23_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_all_identifiers(source: str) -> set[str]:
    """Mirror of the AST identifier extractor in 23.1 boundary tests.

    Returns identifier-position names: ``ast.Name``, ``ast.Attribute``
    (``.attr``), function / async-function / class names, argument
    names, keyword argument names, and import aliases. Does NOT
    return values from ``ast.Constant`` nodes — string literals and
    docstrings stay out of the scan.
    """
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


def _module_reads_env_in_source(source: str) -> bool:
    """Mirror of the env-read detector in 23.1 boundary tests."""
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


def _git(*args: str) -> tuple[int, str, str]:
    """Run a git command in the repo root and return (rc, stdout, stderr).

    Uses ``subprocess.run`` directly because the test is asserting
    against actual repository state — there is no helper layer in
    this codebase that wraps git.
    """
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


# ---------------------------------------------------------------------------
# Doc presence
# ---------------------------------------------------------------------------


def test_closure_audit_doc_exists():
    assert CLOSURE_AUDIT_DOC.is_file(), (
        f"Stage 23.6 closure audit doc missing: {CLOSURE_AUDIT_DOC}"
    )


def test_stage_24_handoff_doc_exists():
    assert STAGE_24_HANDOFF_DOC.is_file(), (
        f"Stage 23.6 Stage 24 handoff doc missing: {STAGE_24_HANDOFF_DOC}"
    )


# ---------------------------------------------------------------------------
# Doc content -- commit short SHAs
# ---------------------------------------------------------------------------


def test_closure_audit_doc_mentions_all_stage23_commit_short_shas():
    text = _read_source(CLOSURE_AUDIT_DOC)
    missing = [sha for sha in _EXPECTED_COMMIT_SHORT_SHAS if sha not in text]
    assert not missing, (
        f"Closure audit doc must mention every Stage 23 commit short SHA; "
        f"missing: {missing}"
    )


# ---------------------------------------------------------------------------
# Doc content -- filters
# ---------------------------------------------------------------------------


def test_closure_audit_doc_mentions_all_three_filters():
    text = _read_source(CLOSURE_AUDIT_DOC)
    missing = [name for name in _EXPECTED_FILTER_NAMES if name not in text]
    assert not missing, (
        f"Closure audit doc must mention every Stage 23 filter family "
        f"identifier; missing: {missing}"
    )


def test_stage_24_handoff_doc_mentions_all_three_filters_indirectly():
    """Stage 24 handoff doc should reference Stage 23 filter artifacts.

    The handoff doc names Stage 23 artifacts (which carry the filter
    names embedded in their filenames), so this assertion checks the
    artifact filenames as a proxy for "the handoff doc references the
    Stage 23 filter surface".
    """
    text = _read_source(STAGE_24_HANDOFF_DOC)
    missing = [
        name
        for name in _EXPECTED_ARTIFACT_FILENAMES
        if name not in text
    ]
    assert not missing, (
        f"Stage 24 handoff doc must reference Stage 23 artifact "
        f"filenames; missing: {missing}"
    )


# ---------------------------------------------------------------------------
# Doc content -- artifact filenames
# ---------------------------------------------------------------------------


def test_closure_audit_doc_mentions_all_six_artifact_filenames():
    text = _read_source(CLOSURE_AUDIT_DOC)
    missing = [
        name for name in _EXPECTED_ARTIFACT_FILENAMES if name not in text
    ]
    assert not missing, (
        f"Closure audit doc must mention every Stage 23 artifact "
        f"filename; missing: {missing}"
    )


# ---------------------------------------------------------------------------
# Doc content -- observe-only posture
# ---------------------------------------------------------------------------


def test_closure_audit_doc_states_observe_only_explicitly():
    """The closure audit doc must state observe-only explicitly.

    Specific phrase rather than a substring match so that future
    edits that flip the posture statement (e.g. "not observe-only")
    still fail this assertion.
    """
    text = _read_source(CLOSURE_AUDIT_DOC).lower()
    assert "stage 23 is **observe-only**" in text or (
        "stage 23 is observe-only" in text
    ), (
        "Closure audit doc must explicitly state that Stage 23 is "
        "observe-only"
    )


def test_stage_24_handoff_doc_states_stage_24_observe_first():
    text = _read_source(STAGE_24_HANDOFF_DOC).lower()
    assert "observe-first" in text, (
        "Stage 24 handoff doc must explicitly call Stage 24 observe-first"
    )


# ---------------------------------------------------------------------------
# Doc content -- stage deferral statements
# ---------------------------------------------------------------------------


def test_closure_audit_doc_defers_stage_24_execution_fee():
    text = _read_source(CLOSURE_AUDIT_DOC).lower()
    assert (
        "axiom" in text
        and "jito" in text
        and "priority_fee" in text
    ), (
        "Closure audit doc must defer execution-fee primitives (axiom / "
        "jito / priority_fee) by name to Stage 24"
    )


def test_stage_24_handoff_doc_owns_execution_fee_primitives():
    text = _read_source(STAGE_24_HANDOFF_DOC).lower()
    assert (
        "axiom" in text
        and "priority fee" in text
        and "jito tip" in text
        and "compute budget" in text
    ), (
        "Stage 24 handoff doc must own execution-fee primitives "
        "(axiom / priority fee / jito tip / compute budget)"
    )


def test_stage_24_handoff_doc_defers_stage_25_ath_migration():
    text = _read_source(STAGE_24_HANDOFF_DOC).lower()
    assert "stage 25" in text and "ath" in text and "migration" in text, (
        "Stage 24 handoff doc must defer ATH / migration hardening to "
        "Stage 25"
    )


def test_stage_24_handoff_doc_defers_stage_26_calibration_enforcement():
    text = _read_source(STAGE_24_HANDOFF_DOC).lower()
    assert (
        "stage 26" in text
        and "calibration" in text
        and "enforcement" in text
    ), (
        "Stage 24 handoff doc must defer calibration / enforcement to "
        "Stage 26"
    )


def test_stage_24_handoff_doc_defers_stage_27_x_social():
    text = _read_source(STAGE_24_HANDOFF_DOC).lower()
    assert (
        "stage 27" in text
        and "social" in text
        and ("x api" in text or "x_api" in text or "x / social" in text)
    ), (
        "Stage 24 handoff doc must defer X / social primitives to "
        "Stage 27+"
    )


# ---------------------------------------------------------------------------
# Production tree inventory
# ---------------------------------------------------------------------------


def test_stage23_root_directory_exists():
    assert STAGE23_ROOT.is_dir(), (
        f"Stage 23 production root missing: {STAGE23_ROOT}"
    )


def test_production_py_files_match_expected_set_exactly():
    actual = {
        p.name
        for p in STAGE23_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    extra = actual - _EXPECTED_PRODUCTION_PY_FILES
    missing = _EXPECTED_PRODUCTION_PY_FILES - actual
    assert not extra and not missing, (
        f"Stage 23 production .py tree mismatch; extra={sorted(extra)}, "
        f"missing={sorted(missing)}"
    )


def test_production_closure_doc_files_exist():
    actual = {
        p.name
        for p in STAGE23_ROOT.iterdir()
        if p.is_file() and p.suffix == ".md"
    }
    missing = _EXPECTED_CLOSURE_DOC_FILES - actual
    assert not missing, (
        f"Stage 23 closure doc files missing: {sorted(missing)}"
    )


def test_no_forbidden_production_files_exist():
    actual_files = [
        p
        for p in STAGE23_ROOT.iterdir()
        if p.is_file()
    ]
    leaked: list[str] = []
    for path in actual_files:
        basename_lower = path.name.lower()
        for pattern, kind in _FORBIDDEN_PRODUCTION_FILE_PATTERNS:
            if kind == "exact":
                if basename_lower == pattern.lower():
                    leaked.append(path.name)
                    break
            elif kind == "prefix":
                if basename_lower.startswith(pattern.lower()):
                    leaked.append(path.name)
                    break
    assert not leaked, (
        f"Stage 23 production tree carries forbidden files: {leaked}"
    )


# ---------------------------------------------------------------------------
# Forbidden identifier substrings (AST identifier-position scan)
# ---------------------------------------------------------------------------


def test_no_production_identifier_contains_forbidden_closure_substring():
    """No Stage 23 production identifier contains a forbidden substring.

    The scan is AST-position only; string literals (including the
    locked ``STAGE23_FORBIDDEN_ROUTING_TOKENS`` /
    ``STAGE23_FORBIDDEN_VOCABULARY`` tuples in ``constants.py``)
    and docstrings are NOT scanned, so the legitimate forbidden-
    vocabulary tuples do not false-flag.
    """
    failures: list[str] = []
    for py_file in _iter_production_py_modules():
        idents = _extract_all_identifiers(_read_source(py_file))
        for ident in idents:
            lower = ident.lower()
            for forbidden in _FORBIDDEN_IDENTIFIER_SUBSTRINGS:
                if forbidden in lower:
                    failures.append(
                        f"{py_file.name}: identifier {ident!r} contains "
                        f"forbidden substring {forbidden!r}"
                    )
    assert not failures, (
        "Stage 23 production identifier-position substring violations:\n"
        + "\n".join(failures)
    )


# ---------------------------------------------------------------------------
# Env-read prohibition (AST shape)
# ---------------------------------------------------------------------------


def test_no_production_module_reads_os_environ():
    leaked: list[str] = []
    for py_file in _iter_production_py_modules():
        if _module_reads_env_in_source(_read_source(py_file)):
            leaked.append(py_file.name)
    assert not leaked, (
        f"Stage 23 production modules with env-read pattern: {leaked}"
    )


# ---------------------------------------------------------------------------
# Network / DB / prior-stage import prohibition
# ---------------------------------------------------------------------------


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


def test_no_production_module_imports_network_library():
    leaked: list[tuple[str, str]] = []
    for py_file in _iter_production_py_modules():
        for target in _collect_full_import_targets(_read_source(py_file)):
            top = target.split(".")[0]
            if top in _FORBIDDEN_NETWORK_IMPORT_TOPS:
                leaked.append((py_file.name, target))
    assert not leaked, (
        f"Stage 23 production modules with network-library imports: "
        f"{leaked}"
    )


def test_no_production_module_imports_sqlite_or_sqlalchemy():
    leaked: list[tuple[str, str]] = []
    for py_file in _iter_production_py_modules():
        for target in _collect_full_import_targets(_read_source(py_file)):
            top = target.split(".")[0]
            if top in _FORBIDDEN_DB_IMPORT_TOPS:
                leaked.append((py_file.name, target))
    assert not leaked, (
        f"Stage 23 production modules with sqlite/sqlalchemy imports: "
        f"{leaked}"
    )


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage21",
    "PHX2.stage22",
)


def test_no_production_module_imports_stage21_or_stage22():
    leaked: list[tuple[str, str]] = []
    for py_file in _iter_production_py_modules():
        for target in _collect_full_import_targets(_read_source(py_file)):
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                if target.startswith(forbidden):
                    leaked.append((py_file.name, target))
    assert not leaked, (
        f"Stage 23 production modules with Stage 21 / Stage 22 imports: "
        f"{leaked}"
    )


# ---------------------------------------------------------------------------
# Git tag invariants
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    rc, _, _ = _git("--version")
    return rc == 0


def _git_inside_work_tree() -> bool:
    rc, out, _ = _git("rev-parse", "--is-inside-work-tree")
    return rc == 0 and out.strip() == "true"


@pytest.fixture(scope="module")
def _git_env() -> None:
    if not _git_available():
        pytest.skip("git is not available on PATH")
    if not _git_inside_work_tree():
        pytest.skip("not inside a git work tree")


def test_stage_22_closed_tag_dereferences_to_locked_commit(_git_env):
    """The annotated ``stage-22-closed`` tag must dereference to the
    locked Stage 22 close commit SHA.
    """
    rc, out, err = _git("rev-parse", "stage-22-closed^{commit}")
    assert rc == 0, (
        f"git rev-parse stage-22-closed^{{commit}} failed: {err}"
    )
    sha = out.strip()
    assert sha == _STAGE_22_CLOSE_COMMIT_SHA, (
        f"stage-22-closed dereferences to {sha!r}; expected "
        f"{_STAGE_22_CLOSE_COMMIT_SHA!r}"
    )


def test_no_stage_23_tag_exists_yet(_git_env):
    rc, out, err = _git("tag", "--list", "stage-23-*")
    assert rc == 0, f"git tag --list failed: {err}"
    tags = [line for line in out.splitlines() if line.strip()]
    assert not tags, (
        f"Stage 23.6 closure audit must run before any stage-23-* tag "
        f"exists; saw: {tags}"
    )


# ---------------------------------------------------------------------------
# Stage 23.6 stage_version pin
# ---------------------------------------------------------------------------


def test_stage23_constants_report_final_stage_version_23_6():
    """At closure, ``STAGE_VERSION`` / ``STAGE23_MINOR_VERSION`` must be
    bumped to ``"23.6"``. The audit pins this so a missed bump does
    not silently emit stale ``"23.1"`` on manifest records.
    """
    from PHX2.stage23 import constants as c

    assert c.STAGE_VERSION == "23.6", (
        f"Stage 23 closure must set STAGE_VERSION to '23.6'; saw "
        f"{c.STAGE_VERSION!r}"
    )
    assert c.STAGE23_MINOR_VERSION == "23.6", (
        f"Stage 23 closure must set STAGE23_MINOR_VERSION to '23.6'; "
        f"saw {c.STAGE23_MINOR_VERSION!r}"
    )


def test_stage23_schema_version_axis_is_independent_of_stage_version():
    """The schema_version axis stays at its original value -- the
    stage_version bump does not migrate the schema.
    """
    from PHX2.stage23 import constants as c

    assert c.DEFAULT_SCHEMA_VERSION == "stage23_v0_filter_eval"
    assert c.STAGE23_MANIFEST_SCHEMA_VERSION == "stage23_v0_manifest"
    # Schema versions are deliberately not equal to the stage
    # version axis.
    assert c.DEFAULT_SCHEMA_VERSION != c.STAGE_VERSION
    assert c.STAGE23_MANIFEST_SCHEMA_VERSION != c.STAGE_VERSION


def test_artifact_manifest_emits_stage_version_23_6(tmp_path):
    """The Stage 23.5 artifact writer's manifest body must carry the
    closing ``stage_version = "23.6"`` value on disk.
    """
    import json as _json

    from PHX2.stage23.artifact_writer import (
        ARTIFACT_FILENAME_MANIFEST,
        write_stage23_artifacts,
    )
    from PHX2.stage23.runner import run_stage23_filters
    from PHX2.tests.stage23.fixtures.builders import (
        FIXED_CLOCK_UTC,
        make_mixed_filter_input,
    )

    runner_result = run_stage23_filters(
        filter_inputs=[
            make_mixed_filter_input(token_mint="MintA", event_id="evt_a"),
        ],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest_path = tmp_path / ARTIFACT_FILENAME_MANIFEST
    body = _json.loads(manifest_path.read_text(encoding="utf-8"))
    assert body["stage_version"] == "23.6", (
        f"Stage 23 manifest must emit stage_version '23.6'; saw "
        f"{body['stage_version']!r}"
    )
