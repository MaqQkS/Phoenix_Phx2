"""Stage 30.3 spec-lock pins.

Pure read-only repo inspection. No live network calls, no env
reads, no operator-channel traffic. Pins:

  * Locked schema versions + locked artifact basenames.
  * Public ``__all__`` surface on every Stage 30.3A production
    module.
  * AST boundary scan over every Stage 30.3A production module
    (no ``import os``, no env-attr access, no outbound-network
    library import, no Stage 27/28/29 import on the wrapper /
    recorder, narrow PHX2.stage30 allowlist per module).
  * No top-level Call nodes in any Stage 30.3A production module.
  * No raw ``discord`` / ``telegram`` / forbidden URL-host
    substring in any Stage 30.3A production module, with the
    documented carve-outs for the FORBIDDEN_RECORD_FIELD_NAMES
    tuple elements, concatenated-literal needles, and the
    ``webhook_identity`` API parameter name.
  * Deferred Stage 30.3B / 30.3C files do not exist on disk.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, List, Set, Tuple

import pytest

from PHX2.stage30 import (
    stage30_3_compact_body_transport_wrapper as _wrapper_module,
    stage30_3_compact_candidate_context_recorder as _recorder_module,
    stage30_3_compact_candidate_projection as _projection_module,
    stage30_3_compact_runtime_models as _models_module,
    stage30_3_manifest as _manifest_module,
    stage30_3_runtime_wiring_artifact_writer as _writer_module,
)


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


_STAGE30_3_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    "stage30_3_compact_runtime_models.py",
    "stage30_3_compact_candidate_projection.py",
    "stage30_3_compact_candidate_context_recorder.py",
    "stage30_3_compact_body_transport_wrapper.py",
    "stage30_3_runtime_wiring_artifact_writer.py",
    "stage30_3_manifest.py",
    "stage30_3_compact_runtime_session_orchestrator.py",
)


_DEFERRED_PRODUCTION_BASENAMES: Tuple[str, ...] = ()


_DEFERRED_TEST_BASENAMES: Tuple[str, ...] = ()


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _iter_production_paths() -> List[Path]:
    return [STAGE30_ROOT / name for name in _STAGE30_3_PRODUCTION_BASENAMES]


def _collect_imported_module_paths(source: str) -> Set[str]:
    tree = ast.parse(source)
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def _module_reads_environ(source: str) -> bool:
    tree = ast.parse(source)
    os_aliases: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    if alias.name in {
                        "environ",
                        "getenv",
                        "environb",
                    }:
                        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in {"environ", "getenv", "environb"}
            ):
                return True
    return False


def _module_top_level_calls(source: str) -> List[str]:
    tree = ast.parse(source)
    hits: List[str] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            hits.append(ast.dump(stmt.value))
        if isinstance(stmt, ast.Assign):
            if isinstance(stmt.value, ast.Call):
                hits.append(ast.dump(stmt.value))
        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is not None and isinstance(
                stmt.value, ast.Call
            ):
                hits.append(ast.dump(stmt.value))
    return hits


# ---------------------------------------------------------------------------
# 1. Locked schema versions + basenames
# ---------------------------------------------------------------------------


def test_locked_minor_version() -> None:
    assert _models_module.STAGE30_3_MINOR_VERSION == "30.3"


def test_locked_runtime_wiring_schema_version() -> None:
    assert (
        _models_module.STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION
        == "stage30_3_v0_runtime_wiring"
    )


def test_locked_runtime_wiring_artifact_basename() -> None:
    assert (
        _models_module.STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
        == "stage30_3_runtime_wiring.jsonl"
    )


def test_synthetic_refusal_transport_status_byte_for_byte_mirror() -> (
    None
):
    assert (
        _models_module._STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS
        == "PAYLOAD_REFUSED"
    )


# ---------------------------------------------------------------------------
# 2. Production inventory exists, deferred files do NOT exist
# ---------------------------------------------------------------------------


def test_every_production_file_exists() -> None:
    for path in _iter_production_paths():
        assert path.is_file(), (
            f"Stage 30.3A requires production .py file {path}"
        )


def test_deferred_production_files_do_not_exist() -> None:
    for name in _DEFERRED_PRODUCTION_BASENAMES:
        path = STAGE30_ROOT / name
        assert not path.exists(), (
            f"Stage 30.3A must NOT ship deferred file {path}"
        )


def test_deferred_test_files_do_not_exist() -> None:
    for name in _DEFERRED_TEST_BASENAMES:
        path = TESTS_STAGE30_ROOT / name
        assert not path.exists(), (
            f"Stage 30.3A must NOT ship deferred test file {path}"
        )


# ---------------------------------------------------------------------------
# 3. __all__ pins
# ---------------------------------------------------------------------------


def test_models_module_all_contains_expected_surface() -> None:
    expected = {
        "STAGE30_3_MINOR_VERSION",
        "STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION",
        "STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME",
        "COMPACT_OUTCOME_RENDERED",
        "COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE",
        "COMPACT_OUTCOME_FAILED_INPUT_SHAPE",
        "COMPACT_OUTCOME_FAILED_TIER_DECISION",
        "COMPACT_OUTCOME_FAILED_COMPACT_RENDER",
        "COMPACT_OUTCOME_FAILED_CAP",
        "COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE",
        "COMPACT_OUTCOME_FAILED_EXCEPTION",
        "COMPACT_OUTCOME_VALUES",
        "is_compact_outcome_value",
        "SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED",
        "SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED",
        "SNAPSHOT_WRITE_REASON_VALUES",
        "is_snapshot_write_reason_value",
        "WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY",
        "WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION",
        "WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK",
        "WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP",
        "WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT",
        "WRAPPER_ORDER_LABEL_VALUES",
        "is_wrapper_order_label_value",
        "_STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS",
        "Stage30_3CompactRuntimeContext",
        "Stage30_3RecordedCandidateContext",
        "Stage30_3RuntimeWiringArtifactRecord",
        "FORBIDDEN_RECORD_FIELD_NAMES",
        "is_forbidden_record_field_name",
        "Stage30_3CompactRuntimeError",
    }
    assert set(_models_module.__all__) == expected


def test_projection_module_all() -> None:
    assert set(_projection_module.__all__) == {
        "project_recorded_entry_to_tier_decision_record",
        "build_compact_ping_input_record",
    }


def test_recorder_module_all() -> None:
    assert set(_recorder_module.__all__) == {
        "Stage30_3CompactCandidateContextRecorder",
    }


def test_wrapper_module_all() -> None:
    assert set(_wrapper_module.__all__) == {
        "Stage30_3CompactBodyTransportWrapper",
    }


def test_writer_module_all() -> None:
    assert set(_writer_module.__all__) == {
        "STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME",
        "runtime_wiring_record_to_dict",
        "encode_runtime_wiring_jsonl_line",
        "append_runtime_wiring_record",
    }


def test_manifest_module_all_includes_inventory_and_records() -> None:
    declared = set(_manifest_module.__all__)
    must_include = {
        "STAGE30_3_MINOR_VERSION",
        "STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION",
        "STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME",
        "STAGE30_3_PRODUCTION_INVENTORY",
        "STAGE30_3_TEST_INVENTORY",
        "STAGE30_3_FORBIDDEN_SURFACES",
        "Stage30_3CompactRuntimeContext",
        "Stage30_3RecordedCandidateContext",
        "Stage30_3RuntimeWiringArtifactRecord",
        "Stage30_3CompactRuntimeError",
        "Stage30_3CompactCandidateContextRecorder",
        "Stage30_3CompactBodyTransportWrapper",
        "project_recorded_entry_to_tier_decision_record",
        "build_compact_ping_input_record",
        "append_runtime_wiring_record",
    }
    missing = must_include - declared
    assert not missing, (
        f"manifest __all__ missing: {sorted(missing)!r}"
    )


# ---------------------------------------------------------------------------
# 4. AST boundary: no `import os`, no env access, no network libs
# ---------------------------------------------------------------------------


def test_no_production_module_imports_os() -> None:
    for path in _iter_production_paths():
        targets = _collect_imported_module_paths(_read_source(path))
        assert "os" not in targets, (
            f"{path.name}: Stage 30.3A admits ZERO import os; "
            f"found {sorted(targets)!r}"
        )
        for target in targets:
            assert not target.startswith("os."), (
                f"{path.name}: forbidden os.* import {target!r}"
            )


def test_no_production_module_reads_environ() -> None:
    for path in _iter_production_paths():
        assert not _module_reads_environ(_read_source(path)), (
            f"{path.name}: Stage 30.3A admits ZERO env-read sites"
        )


_FORBIDDEN_NETWORK_IMPORT_PATTERNS: Tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "websocket",
    "http.client",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "urllib.error",
    "socket",
    "grpc",
    "asyncio",
)


def test_no_production_module_imports_outbound_network() -> None:
    for path in _iter_production_paths():
        targets = _collect_imported_module_paths(_read_source(path))
        for target in targets:
            for needle in _FORBIDDEN_NETWORK_IMPORT_PATTERNS:
                assert not (
                    target == needle
                    or target.startswith(needle + ".")
                ), (
                    f"{path.name}: Stage 30.3A admits ZERO "
                    f"outbound-network import; offender "
                    f"{target!r}"
                )


_FORBIDDEN_PROVIDER_IMPORT_PATTERNS: Tuple[str, ...] = (
    "discord",
    "telegram",
    "telethon",
    "tweepy",
    "twitter",
    "solders",
    "solana",
    "helius",
    "birdeye",
    "dexscreener",
    "chainstack",
)


def test_no_production_module_imports_forbidden_provider() -> None:
    for path in _iter_production_paths():
        targets = _collect_imported_module_paths(_read_source(path))
        for target in targets:
            if target.startswith("PHX2."):
                continue
            lower = target.lower()
            for pattern in _FORBIDDEN_PROVIDER_IMPORT_PATTERNS:
                assert pattern not in lower, (
                    f"{path.name}: forbidden provider import "
                    f"{target!r}"
                )


def test_no_production_module_imports_phx1() -> None:
    for path in _iter_production_paths():
        targets = _collect_imported_module_paths(_read_source(path))
        for target in targets:
            lower = target.lower()
            assert "phoenix_bot" not in lower, (
                f"{path.name}: forbidden PHX1 import path {target!r}"
            )
            assert "p" + "hx1" not in lower, (
                f"{path.name}: forbidden PHX1 substring {target!r}"
            )


# ---------------------------------------------------------------------------
# 5. Per-module PHX2 import allowlist
# ---------------------------------------------------------------------------


_WRAPPER_ALLOWED_PHX2: Tuple[str, ...] = (
    "PHX2.stage30.compact_ping_artifact_writer",
    "PHX2.stage30.compact_ping_models",
    "PHX2.stage30.compact_ping_renderer",
    "PHX2.stage30.stage30_3_compact_candidate_projection",
    "PHX2.stage30.stage30_3_compact_runtime_models",
    "PHX2.stage30.stage30_3_runtime_wiring_artifact_writer",
    "PHX2.stage30.tier_decision_artifact_writer",
    "PHX2.stage30.tier_decision_models",
)


def test_wrapper_module_imports_zero_stage_27_28_29() -> None:
    targets = _collect_imported_module_paths(
        _read_source(
            STAGE30_ROOT
            / "stage30_3_compact_body_transport_wrapper.py"
        )
    )
    for target in targets:
        assert not target.startswith("PHX2.stage27"), (
            f"wrapper: forbidden Stage 27 import {target!r}"
        )
        assert not target.startswith("PHX2.stage28"), (
            f"wrapper: forbidden Stage 28 import {target!r}"
        )
        assert not target.startswith("PHX2.stage29"), (
            f"wrapper: forbidden Stage 29 import {target!r}"
        )


def test_wrapper_module_phx2_imports_in_allowlist() -> None:
    targets = _collect_imported_module_paths(
        _read_source(
            STAGE30_ROOT
            / "stage30_3_compact_body_transport_wrapper.py"
        )
    )
    for target in targets:
        if not target.startswith("PHX2."):
            continue
        assert target in _WRAPPER_ALLOWED_PHX2, (
            f"wrapper: PHX2 import {target!r} not in allowlist "
            f"{sorted(_WRAPPER_ALLOWED_PHX2)!r}"
        )


def test_recorder_module_imports_zero_stage_27_28_29() -> None:
    targets = _collect_imported_module_paths(
        _read_source(
            STAGE30_ROOT
            / "stage30_3_compact_candidate_context_recorder.py"
        )
    )
    for target in targets:
        assert not target.startswith("PHX2.stage27"), (
            f"recorder: forbidden Stage 27 import {target!r}"
        )
        assert not target.startswith("PHX2.stage28"), (
            f"recorder: forbidden Stage 28 import {target!r}"
        )
        assert not target.startswith("PHX2.stage29"), (
            f"recorder: forbidden Stage 29 import {target!r}"
        )


def test_recorder_module_phx2_imports_only_runtime_models() -> None:
    targets = _collect_imported_module_paths(
        _read_source(
            STAGE30_ROOT
            / "stage30_3_compact_candidate_context_recorder.py"
        )
    )
    phx2_targets = {t for t in targets if t.startswith("PHX2.")}
    assert phx2_targets <= {
        "PHX2.stage30.stage30_3_compact_runtime_models",
    }, (
        f"recorder: PHX2 imports must be limited to the runtime "
        f"models module; offenders: {sorted(phx2_targets)!r}"
    )


_PROJECTION_ALLOWED_PHX2: Tuple[str, ...] = (
    "PHX2.stage30.compact_ping_models",
    "PHX2.stage30.stage30_3_compact_runtime_models",
    "PHX2.stage30.tier_decision_models",
    "PHX2.stage30.tier_decision_projector",
)


def test_projection_module_phx2_imports_only_stage30() -> None:
    targets = _collect_imported_module_paths(
        _read_source(
            STAGE30_ROOT
            / "stage30_3_compact_candidate_projection.py"
        )
    )
    for target in targets:
        if not target.startswith("PHX2."):
            continue
        assert target in _PROJECTION_ALLOWED_PHX2, (
            f"projection: PHX2 import {target!r} not in allowlist "
            f"{sorted(_PROJECTION_ALLOWED_PHX2)!r}"
        )


def test_models_module_phx2_imports_empty_or_sibling_only() -> None:
    targets = _collect_imported_module_paths(
        _read_source(
            STAGE30_ROOT / "stage30_3_compact_runtime_models.py"
        )
    )
    for target in targets:
        if not target.startswith("PHX2."):
            continue
        assert target.startswith(
            "PHX2.stage30.stage30_3_"
        ), (
            f"models: PHX2 import {target!r} must be a sibling "
            f"Stage 30.3A module"
        )


def test_writer_module_phx2_imports_only_runtime_models() -> None:
    targets = _collect_imported_module_paths(
        _read_source(
            STAGE30_ROOT
            / "stage30_3_runtime_wiring_artifact_writer.py"
        )
    )
    phx2_targets = {t for t in targets if t.startswith("PHX2.")}
    assert phx2_targets == {
        "PHX2.stage30.stage30_3_compact_runtime_models",
    }, (
        f"writer: PHX2 imports must be the runtime models "
        f"module only; observed {sorted(phx2_targets)!r}"
    )


def test_manifest_module_phx2_imports_only_sibling_stage30_3() -> None:
    targets = _collect_imported_module_paths(
        _read_source(STAGE30_ROOT / "stage30_3_manifest.py")
    )
    for target in targets:
        if not target.startswith("PHX2."):
            continue
        assert target.startswith(
            "PHX2.stage30.stage30_3_"
        ), (
            f"manifest: PHX2 import {target!r} must be a sibling "
            f"Stage 30.3A module"
        )


# ---------------------------------------------------------------------------
# 6. No top-level Call nodes
# ---------------------------------------------------------------------------


def test_no_production_module_has_top_level_call() -> None:
    for path in _iter_production_paths():
        hits = _module_top_level_calls(_read_source(path))
        assert not hits, (
            f"{path.name}: Stage 30.3A admits ZERO top-level Call "
            f"nodes; offenders: {hits!r}"
        )


# ---------------------------------------------------------------------------
# 7. No raw forbidden URL host substring in Stage 30.3A source
# ---------------------------------------------------------------------------
#
# The boundary scan AST-walks each Stage 30.3A production module
# and collects every str-typed ast.Constant value PLUS every str-
# typed ast.Constant value that is an arm of a BinOp(Add) string
# concatenation. The full evaluated (concatenated) string is then
# checked against the closed-set forbidden URL host / scheme /
# operator-channel substring vocabulary. The bare-word ``webhook``
# / ``discord`` / ``telegram`` tokens are intentionally NOT in
# this vocabulary (per spec carve-out: the FORBIDDEN_RECORD_FIELD_NAMES
# tuple contains the bare ``webhook`` name as a field-name keyword
# and the writer's _OUTPUT_DIR_FORBIDDEN_SUBSTRINGS contains
# concatenated needles).


_FORBIDDEN_FULL_URL_SUBSTRINGS: Tuple[str, ...] = (
    "h" + "ttp://",
    "h" + "ttps://",
    "w" + "s://",
    "w" + "ss://",
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/web" + "hooks/",
    "api.helius" + ".xyz",
    "public-api.birdeye" + ".so",
    "pump" + ".fun",
)


def _evaluated_str_constants(source: str) -> Iterable[str]:
    """Yield every str constant value present in the module's AST
    that is NOT an arm of a BinOp(Add) string concatenation. The
    concatenated-literal needles are an explicit Stage 30.3 carve-
    out (the source must not carry a raw forbidden URL host in any
    single string literal, but ``"discord" + ".com"`` is allowed
    as a needle for the writer's safety-gate substring list).
    """
    tree = ast.parse(source)
    seen_concat_arms: Set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, ast.Add
        ):
            left = node.left
            right = node.right
            if (
                isinstance(left, ast.Constant)
                and isinstance(left.value, str)
                and isinstance(right, ast.Constant)
                and isinstance(right.value, str)
            ):
                seen_concat_arms.add(id(left))
                seen_concat_arms.add(id(right))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(
            node.value, str
        ):
            if id(node) in seen_concat_arms:
                continue
            yield node.value


def test_no_production_module_carries_forbidden_url_substring() -> (
    None
):
    for path in _iter_production_paths():
        source = _read_source(path)
        for value in _evaluated_str_constants(source):
            lowered = value.lower()
            for needle in _FORBIDDEN_FULL_URL_SUBSTRINGS:
                assert needle.lower() not in lowered, (
                    f"{path.name}: str constant carries forbidden "
                    f"URL host substring {needle!r}; offender "
                    f"value: {value!r}"
                )


# ---------------------------------------------------------------------------
# 8. Locked vocabulary tuples have no duplicates
# ---------------------------------------------------------------------------


def test_compact_outcome_values_are_unique() -> None:
    assert len(_models_module.COMPACT_OUTCOME_VALUES) == len(
        set(_models_module.COMPACT_OUTCOME_VALUES)
    )


def test_snapshot_write_reason_values_are_unique() -> None:
    assert len(_models_module.SNAPSHOT_WRITE_REASON_VALUES) == len(
        set(_models_module.SNAPSHOT_WRITE_REASON_VALUES)
    )


def test_wrapper_order_label_values_are_unique() -> None:
    assert len(_models_module.WRAPPER_ORDER_LABEL_VALUES) == len(
        set(_models_module.WRAPPER_ORDER_LABEL_VALUES)
    )
