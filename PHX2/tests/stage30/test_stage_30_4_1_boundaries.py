"""Stage 30.4.1 production-file boundary tests.

Scans the five Stage 30.4.1 production .py files (models,
formatter, source protocol, adapter, artifact writer) for:

  * forbidden runtime imports,
  * forbidden text needles (URL hosts, inbound-hook hosts, bearer
    tokens, API keys, RPC providers),
  * forbidden Stage 21-29 production imports,
  * forbidden Stage 30.1 / 30.2 / 30.3 runtime-mutation imports,
  * presence of the Stage 30.4.2 orchestrator file (must NOT
    exist),
  * no operator-channel transport construction,
  * no Discord transport construction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PHX2.stage30.stage30_4_manifest import (
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_ADAPTER_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_WRITER_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_FORMATTER_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_MODELS_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_SOURCE_PROTOCOL_BASENAME,
    STAGE30_4_1_TEST_BASENAMES,
    STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_1,
    STAGE30_4_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _production_files() -> Dict[str, str]:
    files: Dict[str, str] = {}
    for basename in STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_1:
        path = STAGE30_ROOT / basename
        files[basename] = path.read_text(encoding="utf-8")
    return files


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


def _extract_imported_module(line: str) -> str:
    stripped = line.strip()
    tokens = stripped.split()
    if len(tokens) < 2:
        return ""
    if tokens[0] in ("import", "from"):
        return tokens[1]
    return ""


# ---------------------------------------------------------------------------
# 1. All five production files exist
# ---------------------------------------------------------------------------


def test_all_five_production_files_exist() -> None:
    for basename in STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_1:
        path = STAGE30_ROOT / basename
        assert path.is_file(), (
            f"Stage 30.4.1 requires {path}"
        )


def test_all_production_basenames_are_pinned() -> None:
    expected = (
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_MODELS_BASENAME,
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_FORMATTER_BASENAME,
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_SOURCE_PROTOCOL_BASENAME,
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_ADAPTER_BASENAME,
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_WRITER_BASENAME,
    )
    assert STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_1 == expected


# ---------------------------------------------------------------------------
# 2. All seven test files exist
# ---------------------------------------------------------------------------


def test_all_seven_test_basenames_pinned() -> None:
    expected = (
        "test_stage_30_4_1_models.py",
        "test_stage_30_4_1_formatter.py",
        "test_stage_30_4_1_adapter_unknown_path.py",
        "test_stage_30_4_1_adapter_present_path_with_fake_source.py",
        "test_stage_30_4_1_adapter_error_stale_paths.py",
        "test_stage_30_4_1_artifact_writer.py",
        "test_stage_30_4_1_boundaries.py",
    )
    assert STAGE30_4_1_TEST_BASENAMES == expected
    for basename in STAGE30_4_1_TEST_BASENAMES:
        path = TESTS_STAGE30_ROOT / basename
        assert path.is_file(), (
            f"Stage 30.4.1 requires test {path}"
        )


# ---------------------------------------------------------------------------
# 3. Forbidden runtime imports (os, requests, httpx, aiohttp,
#    urllib, socket, grpc, keyring, dotenv)
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
    "asyncio",
    "websocket",
    "websockets",
    "http",
)


def test_no_forbidden_runtime_imports_in_30_4_1_files() -> None:
    py_files = _production_files()
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
                    f"Stage 30.4.1 file {filename!r} imports "
                    f"forbidden module {module!r} on line "
                    f"{line.rstrip()!r}"
                )


# ---------------------------------------------------------------------------
# 4. No Stage 21-29 production imports
# ---------------------------------------------------------------------------


def test_no_stage21_29_imports_in_30_4_1_files() -> None:
    py_files = _production_files()
    for filename, text in py_files.items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for stage_n in range(21, 30):
                forbidden_prefix = f"PHX2.stage{stage_n}"
                assert not module.startswith(forbidden_prefix), (
                    f"Stage 30.4.1 file {filename!r} imports "
                    f"forbidden Stage 21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.4.1 file {filename!r} imports forbidden "
                f"PHX1 module {module!r}"
            )


# ---------------------------------------------------------------------------
# 5. No Stage 30.1 / 30.2 / 30.3 runtime-mutation imports
# ---------------------------------------------------------------------------
#
# Stage 30.4.1 must not import Stage 30.1 / 30.2 / 30.3 runtime
# modules. Stage 30.4.1 sits "below" Stage 30.1 / 30.2 / 30.3 in
# the import graph; it is consumed by a future Stage 30.4.2
# orchestrator, but never consumes Stage 30.1 / 30.2 / 30.3 itself.


_FORBIDDEN_STAGE30_OTHER_MODULE_PREFIXES: Tuple[str, ...] = (
    "PHX2.stage30.tier_decision_models",
    "PHX2.stage30.tier_decision_projector",
    "PHX2.stage30.tier_decision_artifact_writer",
    "PHX2.stage30.compact_ping_models",
    "PHX2.stage30.compact_ping_renderer",
    "PHX2.stage30.compact_ping_artifact_writer",
    "PHX2.stage30.stage30_1_manifest",
    "PHX2.stage30.stage30_2_manifest",
    "PHX2.stage30.stage30_3_compact_runtime_models",
    "PHX2.stage30.stage30_3_compact_candidate_projection",
    "PHX2.stage30.stage30_3_compact_candidate_context_recorder",
    "PHX2.stage30.stage30_3_compact_body_transport_wrapper",
    "PHX2.stage30.stage30_3_runtime_wiring_artifact_writer",
    "PHX2.stage30.stage30_3_compact_runtime_session_orchestrator",
    "PHX2.stage30.stage30_3_manifest",
)


def test_no_stage30_other_substage_imports_in_30_4_1_files() -> None:
    py_files = _production_files()
    for filename, text in py_files.items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for forbidden in _FORBIDDEN_STAGE30_OTHER_MODULE_PREFIXES:
                assert not module.startswith(forbidden), (
                    f"Stage 30.4.1 file {filename!r} imports "
                    f"forbidden other Stage 30 substage module "
                    f"{module!r}"
                )


# ---------------------------------------------------------------------------
# 6. No forbidden text needles
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles_in_30_4_1_production_files() -> None:
    py_files = _production_files()
    for filename, text in py_files.items():
        lower = text.lower()
        for needle in STAGE30_4_FORBIDDEN_TEXT_NEEDLES:
            needle_lower = needle.lower()
            assert needle_lower not in lower, (
                f"Stage 30.4.1 file {filename!r} carries "
                f"forbidden text needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 7. Stage 30.4.3 / later live source adapter must NOT exist
# ---------------------------------------------------------------------------
#
# Stage 30.4.2 widened the orchestrator-file pin: the Stage 30.4.2
# parallel orchestrator file is now permitted. Stage 30.4.3 widened
# the source pin: the offline Birdeye token-overview source bridge
# (basename ``stage30_4_3_market_context_birdeye_source.py``) is now
# authorized, so the ``birdeye_token_overview`` basename ban is
# dropped here. The Dexscreener cross-check, on-chain supply, and any
# ``live_token_overview`` source families remain deferred and forbidden.


def test_no_live_token_overview_source_adapter_file_exists() -> None:
    """No Dexscreener cross-check, on-chain supply, or generic
    ``live_token_overview`` source-adapter file may ship; those
    families remain deferred. The authorized Stage 30.4.3 Birdeye
    source bridge basename is intentionally NOT matched by these
    substrings.
    """
    forbidden_basename_substrings = (
        "live_token_overview",
        "dex" + "screener_cross_check",
        "on_chain_supply",
    )
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__":
            continue
        for forbidden in forbidden_basename_substrings:
            assert forbidden not in entry.name, (
                "Stage 30.4.1 / 30.4.2 must not ship a real live "
                f"source adapter file: unexpected {entry.name!r}"
            )


# ---------------------------------------------------------------------------
# 8. Stage 30.4.3 test files must NOT exist
# ---------------------------------------------------------------------------


def test_no_premature_stage30_4_3_test_file_exists() -> None:
    """Stage 30.4.3 is now separately authorized, so its
    ``test_stage_30_4_3`` test files are admitted. Any Stage
    30.4.4+ / live-proof test file would remain forbidden until its
    own authorization; none is pinned here yet.
    """
    forbidden_substrings: Tuple[str, ...] = ()
    for entry in TESTS_STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__":
            continue
        for forbidden in forbidden_substrings:
            assert forbidden not in entry.name, (
                "Stage 30.4.1 / 30.4.2 must not ship a Stage "
                f"30.4.4+ test file: unexpected {entry.name!r}"
            )


# ---------------------------------------------------------------------------
# 9. No transport-construction surface (raw operator-channel
#    transport, inbound-hook factory)
# ---------------------------------------------------------------------------


def test_no_transport_construction_substrings_in_30_4_1_files() -> None:
    """Defensive: split-literal substrings that would indicate a
    raw transport / hook / fetch construction surface must not
    appear in the Stage 30.4.1 production source text.
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
        "send_one_audited_post",
        "compact_body_transport",
        "compact_runtime_session_orchestrator",
    )
    py_files = _production_files()
    for filename, text in py_files.items():
        lower = text.lower()
        for needle in needles:
            assert needle.lower() not in lower, (
                f"Stage 30.4.1 file {filename!r} carries transport-"
                f"construction needle {needle!r}"
            )


# ---------------------------------------------------------------------------
# 10. Module-import smoke: every Stage 30.4.1 production module
#     imports without side effects
# ---------------------------------------------------------------------------


def test_every_30_4_1_production_module_imports_cleanly() -> None:
    """A fresh import of each Stage 30.4.1 production module must
    succeed without opening a network connection, raising, or
    requiring an env variable. The smoke test runs the imports in
    the test process; pytest catches any side-effect failure.
    """
    import PHX2.stage30.stage30_4_compact_market_context_adapter  # noqa: F401
    import PHX2.stage30.stage30_4_compact_market_context_artifact_writer  # noqa: F401
    import PHX2.stage30.stage30_4_compact_market_context_formatter  # noqa: F401
    import PHX2.stage30.stage30_4_compact_market_context_models  # noqa: F401
    import PHX2.stage30.stage30_4_compact_market_context_source_protocol  # noqa: F401


# ---------------------------------------------------------------------------
# 11. Models / source-protocol module-source forbidden-attribute
#     guard exposed
# ---------------------------------------------------------------------------


def test_source_protocol_exposes_forbidden_attribute_helper() -> None:
    """Stage 30.4.1 source protocol module must export
    ``is_source_forbidden_attribute_name`` so the adapter can guard
    against a future source-protocol implementation that advertises
    a transport / secret surface.
    """
    from PHX2.stage30.stage30_4_compact_market_context_source_protocol import (  # noqa: E501
        is_source_forbidden_attribute_name,
    )

    assert callable(is_source_forbidden_attribute_name)
    # Defensive: needles built with split-literals so this test
    # source doesn't carry them bare.
    assert is_source_forbidden_attribute_name(
        "api_" + "key"
    )
    assert is_source_forbidden_attribute_name("b" + "earer_token")
    assert is_source_forbidden_attribute_name("rpc_url")
    assert not is_source_forbidden_attribute_name("read")
    assert not is_source_forbidden_attribute_name(None)
    assert not is_source_forbidden_attribute_name(b"url")


# ---------------------------------------------------------------------------
# 12. Models module exposes the forbidden-record-field-name guard
# ---------------------------------------------------------------------------


def test_models_exposes_forbidden_field_name_helper() -> None:
    from PHX2.stage30.stage30_4_compact_market_context_models import (
        FORBIDDEN_RECORD_FIELD_NAMES,
        is_forbidden_record_field_name,
    )

    assert callable(is_forbidden_record_field_name)
    assert len(FORBIDDEN_RECORD_FIELD_NAMES) >= 20
    assert is_forbidden_record_field_name(
        "raw_payload"
    )
    assert is_forbidden_record_field_name("rpc_url")
    assert not is_forbidden_record_field_name(
        "market_cap_usd_status"
    )
