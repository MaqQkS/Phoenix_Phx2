"""Stage 30.4.2 orchestrator boundary tests.

Scans the Stage 30.4.2 production .py file
(``stage30_4_compact_runtime_session_orchestrator.py``) for:

  * forbidden runtime imports (``os`` / ``dotenv`` / ``keyring`` /
    ``requests`` / ``httpx`` / ``aiohttp`` / ``urllib`` / ``socket`` /
    ``grpc`` / ``asyncio`` / ``websocket`` / ``websockets`` /
    ``http``),
  * forbidden text needles (URL hosts, inbound-hook hosts, bearer
    tokens, API keys, RPC provider names),
  * forbidden Stage 21-29 production imports (the Stage 30.4.2
    orchestrator delegates to Stage 30.3, which itself owns the
    Stage 28 import boundary; Stage 30.4.2 must NOT import any
    Stage 21-29 module by name),
  * no Discord / Telegram / Birdeye / Helius / Chainstack /
    Pump.fun / Solana provider import,
  * presence of a live Birdeye token_overview source adapter
    file (must NOT exist; the Stage 30.4.2 orchestrator is offline
    / fake-source only),
  * absence of os.environ / os.getenv / os.environb attribute
    access,
  * zero top-level Call nodes (no implicit I/O at import time),
  * the Stage 30.4.2 orchestrator's PHX2 imports are a subset of
    the documented Stage 30.4.2 read-only allowlist (Stage 30.2 /
    30.3 / 30.4.1 sibling modules only),
  * the Stage 30.1 / 30.2 / 30.3 runtime modules' public surface
    is unchanged (key callables / records / record fields still
    exist; the Stage 30.4.2 orchestrator did not silently mutate
    a sibling-module API).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Set, Tuple

from PHX2.stage30.stage30_4_manifest import (
    STAGE30_4_2_COMPACT_RUNTIME_SESSION_ORCHESTRATOR_BASENAME,
    STAGE30_4_2_TEST_BASENAMES,
    STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_2,
    STAGE30_4_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"

ORCHESTRATOR_PATH: Path = (
    STAGE30_ROOT
    / STAGE30_4_2_COMPACT_RUNTIME_SESSION_ORCHESTRATOR_BASENAME
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _orchestrator_source() -> str:
    return ORCHESTRATOR_PATH.read_text(encoding="utf-8")


def _orchestrator_ast() -> ast.Module:
    return ast.parse(_orchestrator_source())


def _orchestrator_imports() -> Set[str]:
    tree = _orchestrator_ast()
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def _is_real_import_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if stripped.startswith('"') or stripped.startswith("'"):
        return False
    return stripped.startswith("import ") or stripped.startswith(
        "from "
    )


# ---------------------------------------------------------------------------
# 1. Orchestrator file + tests exist; manifest pins are honored
# ---------------------------------------------------------------------------


def test_orchestrator_file_exists() -> None:
    assert ORCHESTRATOR_PATH.is_file(), (
        f"Stage 30.4.2 requires the orchestrator at "
        f"{ORCHESTRATOR_PATH}"
    )


def test_manifest_pins_orchestrator_basename() -> None:
    expected = "stage30_4_compact_runtime_session_orchestrator.py"
    assert (
        STAGE30_4_2_COMPACT_RUNTIME_SESSION_ORCHESTRATOR_BASENAME
        == expected
    )
    assert STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_2 == (
        expected,
    )


def test_manifest_pins_two_test_basenames() -> None:
    expected = (
        "test_stage_30_4_2_compact_runtime_integration.py",
        "test_stage_30_4_2_boundaries.py",
    )
    assert STAGE30_4_2_TEST_BASENAMES == expected
    for basename in STAGE30_4_2_TEST_BASENAMES:
        path = TESTS_STAGE30_ROOT / basename
        assert path.is_file(), (
            f"Stage 30.4.2 requires test {path}"
        )


# ---------------------------------------------------------------------------
# 2. Orchestrator module imports cleanly (smoke)
# ---------------------------------------------------------------------------


def test_orchestrator_module_imports_cleanly() -> None:
    """A fresh import of the Stage 30.4.2 orchestrator must succeed
    without opening a network connection, raising, or requiring an
    env variable.
    """
    import PHX2.stage30.stage30_4_compact_runtime_session_orchestrator  # noqa: E501,F401


# ---------------------------------------------------------------------------
# 3. No env imports / env attribute access
# ---------------------------------------------------------------------------


def test_orchestrator_does_not_import_os() -> None:
    imports = _orchestrator_imports()
    assert "os" not in imports, (
        f"orchestrator must not import os; got: {sorted(imports)!r}"
    )
    for target in imports:
        assert not target.startswith("os."), (
            f"orchestrator must not import os.*; offender: {target!r}"
        )


def test_orchestrator_does_not_import_dotenv_or_keyring() -> None:
    imports = _orchestrator_imports()
    for forbidden in ("dotenv", "keyring"):
        assert forbidden not in imports, (
            f"orchestrator must not import {forbidden!r}"
        )
        for target in imports:
            assert not target.startswith(forbidden + "."), (
                f"orchestrator must not import {forbidden}.*; "
                f"offender: {target!r}"
            )


def test_orchestrator_does_not_access_environ() -> None:
    tree = _orchestrator_ast()
    os_aliases: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    assert alias.name not in {
                        "environ",
                        "getenv",
                        "environb",
                    }, (
                        "orchestrator must not import env access "
                        f"name: {alias.name!r}"
                    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in {"environ", "getenv", "environb"}
            ):
                raise AssertionError(
                    "orchestrator must not perform os.environ / "
                    "os.getenv / os.environb attribute access"
                )


# ---------------------------------------------------------------------------
# 4. No network imports
# ---------------------------------------------------------------------------


_FORBIDDEN_NETWORK_MODULES: Tuple[str, ...] = (
    "urllib",
    "urllib.request",
    "urllib.parse",
    "urllib.error",
    "socket",
    "grpc",
    "asyncio",
    "aiohttp",
    "httpx",
    "requests",
    "websockets",
    "websocket",
    "http",
    "http.client",
    "ssl",
)


def test_orchestrator_does_not_import_network_modules() -> None:
    imports = _orchestrator_imports()
    for target in imports:
        for forbidden in _FORBIDDEN_NETWORK_MODULES:
            assert not (
                target == forbidden
                or target.startswith(forbidden + ".")
            ), (
                f"orchestrator must not import network module "
                f"{forbidden!r}; offender: {target!r}"
            )


# ---------------------------------------------------------------------------
# 5. No Discord / provider / live-source imports
# ---------------------------------------------------------------------------


_FORBIDDEN_PROVIDER_NEEDLES: Tuple[str, ...] = (
    "discord",
    "telegram",
    "birdeye",
    "hel" + "ius",
    "chain" + "stack",
    "pump",
    "solders",
    "solana",
    "web" + "hook",
    "dex" + "screener",
)


def test_orchestrator_does_not_import_provider_or_discord_modules() -> (
    None
):
    imports = _orchestrator_imports()
    for target in imports:
        if target.startswith("PHX2."):
            continue
        lower = target.lower()
        for needle in _FORBIDDEN_PROVIDER_NEEDLES:
            assert needle not in lower, (
                f"orchestrator must not import provider / Discord "
                f"surface {needle!r}; offender: {target!r}"
            )


# ---------------------------------------------------------------------------
# 6. No Stage 21-29 production imports; no PHX1 import
# ---------------------------------------------------------------------------


def test_orchestrator_does_not_import_any_stage_21_29_module() -> None:
    imports = _orchestrator_imports()
    for target in imports:
        for stage_n in range(21, 30):
            forbidden_prefix = f"PHX2.stage{stage_n}"
            assert not (
                target == forbidden_prefix
                or target.startswith(forbidden_prefix + ".")
            ), (
                f"orchestrator must not import Stage 21-29 module "
                f"{target!r}"
            )
        assert not target.startswith("PHX1"), (
            f"orchestrator must not import PHX1 module {target!r}"
        )


def test_orchestrator_text_does_not_carry_stage_21_29_module_paths() -> (
    None
):
    """Belt-and-suspenders text scan: the orchestrator source text
    must not carry any ``PHX2.stage21..PHX2.stage29`` path on a
    real import line. Mirrors the Stage 30.4.0 manifest's
    line-based scan to guard against an import wrapped in
    string-literal sleight-of-hand.
    """
    text = _orchestrator_source()
    for line in text.split("\n"):
        if not _is_real_import_line(line):
            continue
        for stage_n in range(21, 30):
            needle = f"PHX2.stage{stage_n}"
            assert needle not in line, (
                f"orchestrator import line carries Stage 21-29 "
                f"module path {needle!r}: {line.rstrip()!r}"
            )


# ---------------------------------------------------------------------------
# 7. No raw endpoint / secret / webhook text needles
# ---------------------------------------------------------------------------


def test_orchestrator_text_does_not_carry_forbidden_text_needles() -> (
    None
):
    """Case-insensitive substring scan over the orchestrator
    source. The manifest's ``STAGE30_4_FORBIDDEN_TEXT_NEEDLES``
    tuple uses split-literal forms so the manifest source itself
    does not carry the bare needles; this test imports the values
    at runtime and scans the orchestrator file.
    """
    text = _orchestrator_source().lower()
    for needle in STAGE30_4_FORBIDDEN_TEXT_NEEDLES:
        needle_lower = needle.lower()
        assert needle_lower not in text, (
            f"orchestrator carries forbidden text needle {needle!r}"
        )


def test_orchestrator_text_does_not_carry_transport_construction_needles() -> (
    None
):
    """Defensive: split-literal substrings that would indicate a
    raw transport / inbound-hook / fetch construction surface
    must not appear in the Stage 30.4.2 orchestrator source. The
    orchestrator delegates to Stage 30.3 for the actual transport
    composition and never constructs an HTTP / gRPC / WebSocket
    client itself.
    """
    needles = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "ses" + "sion.post",
        "ses" + "sion.get",
        "requests." + "post",
        "requests." + "get",
        "client." + "post",
        "client." + "get",
        "url" + "open",
    )
    text = _orchestrator_source().lower()
    for needle in needles:
        assert needle.lower() not in text, (
            f"orchestrator carries transport-construction needle "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# 8. PHX2 imports are a subset of the documented Stage 30.4.2 allowlist
# ---------------------------------------------------------------------------
#
# Stage 30.4.2 reads from Stage 30.2 / 30.3 / 30.4.1 sibling modules
# ONLY. The orchestrator does not import any Stage 30.1 module
# directly -- the Stage 30.1 tier-decision projection is reached
# transitively via ``stage30_3_compact_candidate_projection``
# (which imports ``decide_tier``). Stage 30.1's ``Stage30_1TierDecisionError``
# is imported via ``tier_decision_models`` so the orchestrator can
# catch the closed-set exception on the re-render path.


_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    # Stage 30.2 renderer + models (read-only).
    "PHX2.stage30.compact_ping_models",
    "PHX2.stage30.compact_ping_renderer",
    # Stage 30.3 sibling modules (read-only).
    "PHX2.stage30.stage30_3_compact_candidate_context_recorder",
    "PHX2.stage30.stage30_3_compact_candidate_projection",
    "PHX2.stage30.stage30_3_compact_runtime_models",
    "PHX2.stage30.stage30_3_compact_runtime_session_orchestrator",
    # Stage 30.4.1 adapter + artifact writer + models (read-only).
    "PHX2.stage30.stage30_4_compact_market_context_adapter",
    "PHX2.stage30.stage30_4_compact_market_context_artifact_writer",
    "PHX2.stage30.stage30_4_compact_market_context_models",
    # Stage 30.1 models (read-only; only for the closed-set
    # exception ``Stage30_1TierDecisionError``).
    "PHX2.stage30.tier_decision_models",
)


def test_orchestrator_phx2_imports_subset_of_allowlist() -> None:
    imports = _orchestrator_imports()
    for target in imports:
        if not target.startswith("PHX2."):
            continue
        assert target in _ALLOWED_PHX2_IMPORTS, (
            f"orchestrator PHX2 import {target!r} is not in the "
            f"documented allowlist "
            f"{sorted(_ALLOWED_PHX2_IMPORTS)!r}"
        )


# ---------------------------------------------------------------------------
# 9. No live token_overview source adapter file exists in the
# Stage 30 directory
# ---------------------------------------------------------------------------


def test_no_live_token_overview_source_adapter_file_exists() -> None:
    """Stage 30.4.2 is offline / fake-source only. A real Birdeye
    ``token_overview`` HTTP adapter (or any other live source
    adapter) requires separately authorized scope (Stage 30.4.3+)
    and must NOT ship at Stage 30.4.2.
    """
    forbidden_basename_substrings = (
        "birdeye_token_overview",
        "live_token_overview",
        "dex" + "screener_cross_check",
        "on_chain_supply",
    )
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__":
            continue
        for forbidden in forbidden_basename_substrings:
            assert forbidden not in entry.name, (
                "Stage 30.4.2 must not ship a real live source "
                f"adapter file: unexpected {entry.name!r}"
            )


# ---------------------------------------------------------------------------
# 10. Zero top-level Call nodes (no implicit I/O at import time)
# ---------------------------------------------------------------------------


def test_orchestrator_has_no_top_level_call_nodes() -> None:
    tree = _orchestrator_ast()
    hits = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(
            stmt.value, ast.Call
        ):
            hits.append(ast.dump(stmt.value))
        if isinstance(stmt, ast.Assign) and isinstance(
            stmt.value, ast.Call
        ):
            hits.append(ast.dump(stmt.value))
        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is not None and isinstance(
                stmt.value, ast.Call
            ):
                hits.append(ast.dump(stmt.value))
    assert not hits, (
        f"orchestrator must carry zero top-level Call nodes; "
        f"offenders: {hits!r}"
    )


# ---------------------------------------------------------------------------
# 11. Stage 30.1 / 30.2 / 30.3 runtime modules' public surface is
# unchanged (the Stage 30.4.2 orchestrator did not silently mutate a
# sibling-module API)
# ---------------------------------------------------------------------------


def test_stage_30_1_tier_decision_public_surface_intact() -> None:
    """The Stage 30.1 tier-decision projector / models the Stage
    30.4.2 orchestrator depends on must still expose their
    documented public callables / records / closed-set tokens.
    """
    from PHX2.stage30.tier_decision_models import (
        STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME,
        Stage30_1TierDecisionError,
        TierDecisionRecord,
    )

    assert callable(Stage30_1TierDecisionError)
    assert STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME == (
        "stage30_1_tier_decisions.jsonl"
    )
    # The TierDecisionRecord NamedTuple must still expose the
    # operator-visible fields the Stage 30.4.2 orchestrator
    # consumes via the Stage 30.3 projector.
    for field in (
        "tier_token",
        "tier_reason",
        "basis",
        "drop_positive",
        "mint",
    ):
        assert field in TierDecisionRecord._fields, (
            f"TierDecisionRecord._fields must still expose "
            f"{field!r}; got {TierDecisionRecord._fields!r}"
        )


def test_stage_30_2_compact_ping_public_surface_intact() -> None:
    """The Stage 30.2 compact ping renderer / models the Stage
    30.4.2 orchestrator depends on must still expose their
    documented public callables / records / closed-set tokens.
    """
    from PHX2.stage30.compact_ping_models import (
        STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
        CompactPingInputRecord,
        CompactPingSnapshotRecord,
        DISPLAY_UNKNOWN,
        Stage30_2CompactPingError,
    )
    from PHX2.stage30.compact_ping_renderer import (
        render_compact_ping,
    )

    assert callable(render_compact_ping)
    assert callable(Stage30_2CompactPingError)
    assert DISPLAY_UNKNOWN == "Unknown"
    assert STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME == (
        "stage30_2_compact_pings.jsonl"
    )
    # The CompactPingInputRecord must still expose the display-text
    # slots the Stage 30.4.2 orchestrator populates via _replace.
    for field in (
        "tier_decision",
        "mint",
        "current_mc_text",
        "lp_text",
        "net_flow_text",
    ):
        assert field in CompactPingInputRecord._fields, (
            f"CompactPingInputRecord._fields must still expose "
            f"{field!r}; got {CompactPingInputRecord._fields!r}"
        )
    # The CompactPingSnapshotRecord must still expose body_text.
    assert "body_text" in CompactPingSnapshotRecord._fields


def test_stage_30_3_runtime_public_surface_intact() -> None:
    """The Stage 30.3 recorder / projection / orchestrator the
    Stage 30.4.2 orchestrator depends on must still expose their
    documented public callables / records / closed-set tokens.
    """
    from PHX2.stage30.stage30_3_compact_candidate_context_recorder import (  # noqa: E501
        Stage30_3CompactCandidateContextRecorder,
    )
    from PHX2.stage30.stage30_3_compact_candidate_projection import (
        build_compact_ping_input_record,
        project_recorded_entry_to_tier_decision_record,
    )
    from PHX2.stage30.stage30_3_compact_runtime_models import (
        STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
        Stage30_3CompactRuntimeContext,
        Stage30_3CompactRuntimeError,
    )
    from PHX2.stage30.stage30_3_compact_runtime_session_orchestrator import (  # noqa: E501
        Stage30_3CompactRuntimeSessionResult,
        run_stage30_3_compact_runtime_session,
    )

    assert callable(Stage30_3CompactCandidateContextRecorder)
    assert callable(build_compact_ping_input_record)
    assert callable(project_recorded_entry_to_tier_decision_record)
    assert callable(run_stage30_3_compact_runtime_session)
    assert callable(Stage30_3CompactRuntimeError)
    assert STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME == (
        "stage30_3_runtime_wiring.jsonl"
    )
    # Stage30_3CompactRuntimeContext must still expose the fields
    # the Stage 30.4.2 orchestrator references.
    for field in (
        "session_id",
        "run_id",
        "basis",
        "output_dir",
    ):
        assert field in Stage30_3CompactRuntimeContext._fields, (
            f"Stage30_3CompactRuntimeContext._fields must still "
            f"expose {field!r}; "
            f"got {Stage30_3CompactRuntimeContext._fields!r}"
        )
    # Stage30_3CompactRuntimeSessionResult must still expose
    # session_result and the per-outcome counter fields the
    # Stage 30.4.2 result wraps.
    for field in (
        "session_result",
        "compact_renders_attempted",
        "compact_renders_succeeded",
        "compact_renders_failed",
        "compact_renders_skipped",
        "recorded_entries_count",
        "wrapper_order",
    ):
        assert (
            field
            in Stage30_3CompactRuntimeSessionResult._fields
        ), (
            f"Stage30_3CompactRuntimeSessionResult._fields must "
            f"still expose {field!r}; got "
            f"{Stage30_3CompactRuntimeSessionResult._fields!r}"
        )


# ---------------------------------------------------------------------------
# 12. Stage 30.1 / 30.2 / 30.3 runtime source files unchanged at
# the basename level (the Stage 30.4.2 orchestrator did not add a
# sibling-module file that would violate the parent Stage 30 spec-
# lock inventory)
# ---------------------------------------------------------------------------


_STAGE_30_1_2_3_RUNTIME_BASENAMES: Tuple[str, ...] = (
    # Stage 30.1 runtime source files.
    "tier_decision_models.py",
    "tier_decision_projector.py",
    "tier_decision_artifact_writer.py",
    "stage30_1_manifest.py",
    # Stage 30.2 runtime source files.
    "compact_ping_models.py",
    "compact_ping_renderer.py",
    "compact_ping_artifact_writer.py",
    "stage30_2_manifest.py",
    # Stage 30.3 runtime source files.
    "stage30_3_compact_runtime_models.py",
    "stage30_3_compact_candidate_projection.py",
    "stage30_3_compact_candidate_context_recorder.py",
    "stage30_3_compact_body_transport_wrapper.py",
    "stage30_3_runtime_wiring_artifact_writer.py",
    "stage30_3_manifest.py",
    "stage30_3_compact_runtime_session_orchestrator.py",
)


def test_stage_30_1_2_3_runtime_files_still_exist() -> None:
    """The Stage 30.4.2 orchestrator must not have renamed, moved,
    or deleted any Stage 30.1 / 30.2 / 30.3 runtime source file.
    The Stage 30.0 spec-lock inventory test pins the full Stage 30
    basename set; this test is the Stage 30.4.2-specific
    defense-in-depth pin on the 30.1 / 30.2 / 30.3 subset.
    """
    for basename in _STAGE_30_1_2_3_RUNTIME_BASENAMES:
        path = STAGE30_ROOT / basename
        assert path.is_file(), (
            f"Stage 30.4.2 must not have removed Stage 30.1 / 30.2 "
            f"/ 30.3 runtime file: missing {basename}"
        )


# ---------------------------------------------------------------------------
# 13. Orchestrator does not call run_stage28_9_live_provider_session
# directly (it must delegate via the Stage 30.3 orchestrator)
# ---------------------------------------------------------------------------


def test_orchestrator_does_not_call_or_import_stage28_9_session_runner() -> (
    None
):
    """Stage 30.4.2 must delegate the Stage 28.9 session loop via
    the Stage 30.3 orchestrator (``run_stage30_3_compact_runtime_session``).
    The Stage 30.4.2 orchestrator must NOT import or call
    ``run_stage28_9_live_provider_session`` -- a direct call /
    import would imply a Stage 28 production import.
    """
    # Import-line scan: no ``from PHX2.stage28...`` line and no
    # ``import run_stage28_9_live_provider_session`` alias.
    tree = _orchestrator_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != (
                    "run_stage28_9_live_provider_session"
                ), (
                    "orchestrator must not import "
                    "run_stage28_9_live_provider_session"
                )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != (
                    "run_stage28_9_live_provider_session"
                )

    # Call-site scan: no ``ast.Call`` whose func resolves to a
    # ``Name`` / ``Attribute`` that names
    # ``run_stage28_9_live_provider_session``.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id != (
                    "run_stage28_9_live_provider_session"
                ), (
                    "orchestrator must not call "
                    "run_stage28_9_live_provider_session "
                    "directly; delegate via "
                    "run_stage30_3_compact_runtime_session"
                )
            if isinstance(func, ast.Attribute):
                assert func.attr != (
                    "run_stage28_9_live_provider_session"
                ), (
                    "orchestrator must not call "
                    "run_stage28_9_live_provider_session via an "
                    "attribute path; delegate via "
                    "run_stage30_3_compact_runtime_session"
                )
