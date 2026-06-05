"""Stage 28.11 boundary scan.

Pins:

  * Every Stage 28.11 production .py / dep / doc / test file
    exists at the locked path.
  * Stage 28.11 production .py modules other than the client /
    decode modules must NOT import ``grpc`` / generated
    ``_pb2`` / ``_pb2_grpc`` modules.
  * Stage 28.11 production .py modules other than the readiness
    module must NOT read ``os.environ`` / ``os.getenv`` /
    ``os.environb``.
  * Stage 28.11 production .py modules must NOT import any
    Stage 21-27 module.
  * Stage 28.11 production .py modules must NOT import the
    Stage 28.9 adapter / transport / models / Stage 28.6
    bounded private session runner / Stage 28.4 audited
    transport. Stage 28.11 is bounded to readiness / connect /
    decode; the Stage 28.9 dispatch surface is Stage 28.12.
  * Stage 28.11 production .py modules must NOT import Stage 29
    modules.
  * Stage 28.11 production .py modules must NOT import any
    forbidden runtime library (Discord / Telegram / X / social
    / wallet / trade / SQL / dotenv / keyring / etc.) beyond
    the narrow ``grpc`` / generated-stub admission for the
    client + decode modules.
  * Stage 28.11 production source carries no URL host literal
    and no raw-secret-looking literal.
  * Stage 28.11 production identifiers never implement a Stage
    29+ enforcement surface, public router, subscriber router,
    paid tier, Telegram, X / social, automated trading, wallet
    / private-key / signer logic, position sizing, trade
    execution, dashboard / control server, or daemon /
    watchdog / autorestart service.
  * The Stage 28.10 ban on generated ``*_pb2.py`` /
    ``*_pb2_grpc.py`` stubs under ``PHX2/stage28/`` is still
    in force; the Stage 28.11 stubs live under
    ``PHX2/proto/stage28_11/_generated/``.
  * No Stage 29 implementation tree exists.
  * Vendored proto sources match the pinned files set.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
REPO_ROOT: Path = PHX2_ROOT.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE28_ROOT: Path = PHX2_ROOT / "tests" / "stage28"
PROTO_ROOT: Path = PHX2_ROOT / "proto" / "stage28_11"
PROTO_SOURCE_ROOT: Path = PROTO_ROOT / "source"
PROTO_GENERATED_ROOT: Path = PROTO_ROOT / "_generated"


_STAGE_28_11_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "chainstack_yellowstone_grpc_models.py",
    "chainstack_yellowstone_grpc_readiness.py",
    "chainstack_yellowstone_grpc_decode.py",
    "chainstack_yellowstone_grpc_client.py",
    "chainstack_yellowstone_grpc_probe.py",
    "stage28_11_manifest.py",
)


_STAGE_28_11_DEPENDENCY_BASENAMES: tuple[str, ...] = (
    "stage28_11_requirements.txt",
)


_STAGE_28_11_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_11_CHAINSTACK_GRPC_RUNBOOK.md",
)


_STAGE_28_11_TEST_BASENAMES: tuple[str, ...] = (
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_models.py"
    ),
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_readiness.py"
    ),
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_decode.py"
    ),
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_client.py"
    ),
    (
        "test_stage_28_11_"
        "chainstack_yellowstone_grpc_probe.py"
    ),
    "test_stage_28_11_runbook.py",
    "test_stage_28_11_boundaries.py",
)


# Stage 28.11 admits ``grpc`` / generated stubs ONLY in these
# modules. Every other Stage 28.11 production .py file must NOT
# import them.
_STAGE_28_11_GRPC_ADMITTED_BASENAMES: tuple[str, ...] = (
    "chainstack_yellowstone_grpc_client.py",
    "chainstack_yellowstone_grpc_decode.py",
)


# Stage 28.11 admits ``os.environ`` / ``os.getenv`` /
# ``os.environb`` reads ONLY in this module.
_STAGE_28_11_ENV_READ_ADMITTED_BASENAME: str = (
    "chainstack_yellowstone_grpc_readiness.py"
)


# Locked Stage 28.10 / Stage 28.11 sibling imports that every
# Stage 28.11 production .py module is free to use.
_STAGE_28_10_SIBLING_PREFIXES: tuple[str, ...] = (
    "PHX2.stage28.chainstack_yellowstone_models",
    "PHX2.stage28.chainstack_yellowstone_contracts",
    "PHX2.stage28.chainstack_yellowstone_event_source",
    "PHX2.stage28.chainstack_yellowstone_candidate_assembler",
    "PHX2.stage28.stage28_10_manifest",
)


_STAGE_28_11_SIBLING_PREFIXES: tuple[str, ...] = (
    "PHX2.stage28.chainstack_yellowstone_grpc_models",
    "PHX2.stage28.chainstack_yellowstone_grpc_readiness",
    "PHX2.stage28.chainstack_yellowstone_grpc_decode",
    "PHX2.stage28.chainstack_yellowstone_grpc_client",
    "PHX2.stage28.chainstack_yellowstone_grpc_probe",
    "PHX2.stage28.stage28_11_manifest",
)


# Locked generated-stub package prefix; Stage 28.11 client +
# decode modules import from this exact path.
_STAGE_28_11_GENERATED_PREFIX: str = (
    "PHX2.proto.stage28_11._generated"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_stage28_11_production_py_files() -> list[Path]:
    return [
        STAGE28_ROOT / name
        for name in _STAGE_28_11_PRODUCTION_PY_BASENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_imported_module_paths(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
    return modules


# ---------------------------------------------------------------------------
# 1. Inventory existence
# ---------------------------------------------------------------------------


def test_every_stage_28_11_production_py_file_exists():
    for name in _STAGE_28_11_PRODUCTION_PY_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.11 requires production .py file {path}"
        )


def test_every_stage_28_11_dependency_file_exists():
    for name in _STAGE_28_11_DEPENDENCY_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.11 requires dependency file {path}"
        )


def test_every_stage_28_11_doc_file_exists():
    for name in _STAGE_28_11_DOC_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.11 requires operator doc {path}"
        )


def test_every_stage_28_11_test_file_exists():
    for name in _STAGE_28_11_TEST_BASENAMES:
        path = TESTS_STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.11 requires test file {path}"
        )


def test_proto_source_dir_contains_pinned_files():
    assert PROTO_SOURCE_ROOT.is_dir(), (
        f"Stage 28.11 requires {PROTO_SOURCE_ROOT}"
    )
    actual = {
        p.name for p in PROTO_SOURCE_ROOT.iterdir()
        if p.is_file()
    }
    expected = {"geyser.proto", "solana-storage.proto"}
    assert actual == expected, (
        f"Stage 28.11 vendored proto set drift: expected="
        f"{sorted(expected)!r} actual={sorted(actual)!r}"
    )


def test_generated_stub_dir_contains_expected_files():
    assert PROTO_GENERATED_ROOT.is_dir(), (
        f"Stage 28.11 requires {PROTO_GENERATED_ROOT}"
    )
    actual = {
        p.name for p in PROTO_GENERATED_ROOT.iterdir()
        if p.is_file()
    }
    required = {
        "__init__.py",
        "geyser_pb2.py",
        "geyser_pb2_grpc.py",
        "solana_storage_pb2.py",
    }
    assert required.issubset(actual), (
        f"Stage 28.11 generated stubs missing: "
        f"{sorted(required - actual)!r}"
    )


def test_proto_parent_dir_is_namespace_package_no_init_marker():
    """``PHX2/proto/`` is a PEP 420 namespace package (no
    ``__init__.py``); the Stage 28.11 audit refused an untracked
    ``__init__.py`` at that level. The imports
    ``from PHX2.proto.stage28_11._generated import ...`` still
    resolve via Python's implicit namespace-package semantics
    because ``PHX2/`` is a regular package and the leaf
    ``PHX2/proto/stage28_11/`` and
    ``PHX2/proto/stage28_11/_generated/`` are regular packages
    (each carrying its own ``__init__.py``).

    Re-introducing ``PHX2/proto/__init__.py`` requires explicit
    scope admission in the Stage 28-wide manifest + Stage 28.11
    manifest + an update to this boundary test. Leaving it
    silently present would re-trip the original audit finding.
    """
    init_path = PHX2_ROOT / "proto" / "__init__.py"
    assert not init_path.exists(), (
        f"PHX2/proto/ must remain a PEP 420 namespace package; "
        f"the untracked {init_path!s} flagged in the Stage 28.11 "
        f"audit was removed."
    )


def test_proto_stage28_11_subpackages_are_regular_packages():
    """The Stage-28.11-scoped proto sub-tree
    (``PHX2/proto/stage28_11/`` and
    ``PHX2/proto/stage28_11/_generated/``) IS in Stage 28.11
    scope; each carries an explicit ``__init__.py`` marker so
    the generated stubs import as a regular package. These two
    markers are admitted by the Stage 28.11 manifest's
    ``STAGE28_11_GENERATED_STUB_PATH`` /
    ``STAGE28_11_VENDORED_PROTO_SOURCE_PATH`` scope."""
    for sub_init in (
        PHX2_ROOT / "proto" / "stage28_11" / "__init__.py",
        (
            PHX2_ROOT / "proto" / "stage28_11"
            / "_generated" / "__init__.py"
        ),
    ):
        assert sub_init.is_file(), (
            f"Stage 28.11 generated-stub package marker missing: "
            f"{sub_init!s}"
        )


# ---------------------------------------------------------------------------
# 2. Env-read isolation
# ---------------------------------------------------------------------------


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


def _module_reads_environ(source: str) -> bool:
    tree = ast.parse(source)
    os_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    if alias.name in _ENV_ATTR_NAMES:
                        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in _ENV_ATTR_NAMES
            ):
                return True
    return False


def test_only_readiness_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage28_11_production_py_files():
        if path.name == _STAGE_28_11_ENV_READ_ADMITTED_BASENAME:
            continue
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 28.11 production must not read os.environ "
        f"outside {_STAGE_28_11_ENV_READ_ADMITTED_BASENAME!r}; "
        f"offenders: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# 3. grpc / protobuf admission
# ---------------------------------------------------------------------------


_GRPC_IMPORT_PATTERNS: tuple[str, ...] = (
    "grpc",
    "grpcio",
    "grpc_tools",
    "google.protobuf",
    "protobuf",
    _STAGE_28_11_GENERATED_PREFIX,
)


def _module_imports_any(source: str, needles: tuple[str, ...]) -> set[str]:
    targets = _collect_imported_module_paths(source)
    hits: set[str] = set()
    for t in targets:
        for n in needles:
            if t == n or t.startswith(n + "."):
                hits.add(t)
    return hits


def test_only_client_and_decode_import_grpc_or_pb2():
    for path in _iter_stage28_11_production_py_files():
        hits = _module_imports_any(_read(path), _GRPC_IMPORT_PATTERNS)
        if path.name in _STAGE_28_11_GRPC_ADMITTED_BASENAMES:
            # Admitted; no assertion needed.
            continue
        assert not hits, (
            f"{path.name}: Stage 28.11 admits grpc / "
            f"generated-stub imports only in "
            f"{_STAGE_28_11_GRPC_ADMITTED_BASENAMES!r}; "
            f"offenders: {sorted(hits)!r}"
        )


def test_decode_module_imports_generated_stubs():
    src = _read(
        STAGE28_ROOT / "chainstack_yellowstone_grpc_decode.py",
    )
    assert _STAGE_28_11_GENERATED_PREFIX in src


def test_client_module_imports_generated_stubs_and_grpc():
    src = _read(
        STAGE28_ROOT / "chainstack_yellowstone_grpc_client.py",
    )
    assert _STAGE_28_11_GENERATED_PREFIX in src
    assert "import grpc" in src


# ---------------------------------------------------------------------------
# 4. Forbidden imports
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "urllib3",
    "websockets",
    "solders",
    "solana",
    "construct",
    "base58",
    "helius",
    "jupiter",
    "birdeye",
    "discord",
    "discord.",
    "discord_py",
    "telegram",
    "telethon",
    "webhook_client",
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "sqlalchemy",
    "sqlite3",
    "dotenv",
    "keyring",
    "tweepy",
    "twitter",
    "socket",
    "asyncio",
    "threading",
    "multiprocessing",
    "subprocess",
    "queue",
    "sched",
    "http.client",
)


def test_no_stage_28_11_production_imports_forbidden_runtime_pattern():
    for path in _iter_stage28_11_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if target.startswith("PHX2."):
                continue
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path.name}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
                )


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
    "PHX2.stage25",
    "PHX2.stage26",
    "PHX2.stage27",
)


def test_no_stage_28_11_production_imports_prior_stages():
    for path in _iter_stage28_11_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden prior-stage import "
                    f"{target!r}"
                )


# Stage 28.11 must NOT import the Stage 28.9 adapter / transport
# / models / Stage 28.6 runner / Stage 28.4 transport. Stage
# 28.11 is bounded to readiness / connect / decode; the Stage
# 28.9 dispatch surface is Stage 28.12 territory.
_FORBIDDEN_STAGE_28_9_SURFACE_IMPORTS: tuple[str, ...] = (
    "PHX2.stage28.live_provider_session_adapter",
    "PHX2.stage28.live_provider_session_transport",
    "PHX2.stage28.live_provider_session_models",
    "PHX2.stage28.bounded_private_session_runner",
    "PHX2.stage28.audited_http_transport",
    "PHX2.stage28.dispatch_ledger",
)


def test_no_stage_28_11_production_imports_stage_28_9_dispatch_surface():
    for path in _iter_stage28_11_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert target not in (
                _FORBIDDEN_STAGE_28_9_SURFACE_IMPORTS
            ), (
                f"{path.name}: Stage 28.11 must not import "
                f"Stage 28.9 dispatch surface {target!r}"
            )


def test_no_stage_28_11_production_imports_stage_29():
    for path in _iter_stage28_11_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert not target.startswith("PHX2.stage29"), (
                f"{path.name}: Stage 28.11 must not import Stage "
                f"29 module; saw {target!r}"
            )


# ---------------------------------------------------------------------------
# 5. No Stage 29 tree
# ---------------------------------------------------------------------------


# Stage 29.0 narrow amendment: allow ``PHX2/stage29/`` to exist
# iff it contains the Stage 29.0 scaffold (package marker +
# spec-lock doc).
# Stage 29.1 PumpSwap-only narrow amendment (authorized): also
# admit the Stage 29.1 PumpSwap-only hint-extractor tree. Stage
# 29.2 / 29.3 implementation files AND any Pump.fun
# bonding-curve files remain blocked from Stage 28.11.
_STAGE_29_0_ALLOWED_PROD_BASENAMES: frozenset[str] = frozenset(
    {"__init__.py", "STAGE_29_0_SPEC_LOCK.md"}
)


_STAGE_29_1_PUMPSWAP_ALLOWED_PROD_BASENAMES: frozenset[str] = (
    frozenset(
        {
            "pumpswap_program_constants.py",
            "pumpswap_hint_models.py",
            "pumpswap_hint_extractor.py",
            "pumpswap_hint_aware_decoder.py",
            "stage29_1_hint_probe_models.py",
            "stage29_1_pumpswap_hint_probe.py",
            "stage29_1_manifest.py",
            "STAGE_29_1_PUMPSWAP_HINT_EXTRACTOR_RUNBOOK.md",
        }
    )
)


# Stage 29.2 Birdeye price / ATH adapter (authorized 2026-05-25).
# Stage 28.11 narrow amendment widens the Stage-29-tree allowlist
# to admit the Stage 29.2 inventory while continuing to block
# Stage 29.3 implementation files + Pump.fun bonding-curve.
_STAGE_29_2_BIRDEYE_ALLOWED_PROD_BASENAMES: frozenset[str] = (
    frozenset(
        {
            "birdeye_constants.py",
            "stage29_2_birdeye_models.py",
            "stage29_2_birdeye_readiness.py",
            "stage29_2_birdeye_http_transport.py",
            "stage29_2_birdeye_price_source.py",
            "stage29_2_birdeye_ath_source.py",
            "stage29_2_birdeye_probe_models.py",
            "stage29_2_birdeye_probe.py",
            "stage29_2_manifest.py",
            "STAGE_29_2_BIRDEYE_PRICE_ATH_RUNBOOK.md",
        }
    )
)


# Stage 29.3 first real private tradeable PHX2 ping (authorized
# 2026-05-25). Stage 28.11 narrow amendment widens the Stage-29-
# tree allowlist to admit the Stage 29.3 inventory.
_STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "stage29_3_smoke_models.py",
        "stage29_3_no_migration_evidence_source.py",
        "stage29_3_hint_aware_event_source.py",
        "stage29_3_artifact_writer.py",
        "stage29_3_tradeable_smoke.py",
        "stage29_3_manifest.py",
        "STAGE_29_3_FIRST_PRIVATE_TRADEABLE_SMOKE_RUNBOOK.md",
    }
)


# Stage 29.4 short-session private soak (authorized 2026-05-25).
# Stage 29.4.0 is spec-lock-only: this narrow amendment widens
# the Stage-29-tree allowlist to admit the Stage 29.4 runbook
# only. Stage 29.4.1 (separately authorized) widens this further
# to admit the five Stage 29.4 production .py basenames.
_STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md",
        # Stage 29.4.1 widens the Stage 28.11 narrow amendment to
        # admit the five Stage 29.4 production .py basenames
        # pinned by the Stage 29.4.0 runbook (Section 9).
        "stage29_4_soak_models.py",
        "stage29_4_dedupe_index.py",
        "stage29_4_soak_orchestrator.py",
        "stage29_4_soak_artifact_writer.py",
        "stage29_4_manifest.py",
    }
)


# Stage 29.5 Helius WS migration evidence adapter + live private
# ping context join (authorized 2026-05-25). Stage 29.5.0 is
# spec-lock-only: this narrow amendment widens the Stage-29-tree
# allowlist to admit the Stage 29.5 spec-lock runbook only.
# Stage 29.5.1 production .py files
# (stage29_5_migration_models.py / stage29_5_helius_ws_adapter.py
# / stage29_5_migration_artifact_reader.py /
# stage29_5_candidate_to_migration_join.py /
# stage29_5_private_ping_context_projection.py /
# stage29_5_manifest.py) remain blocked at Stage 29.5.0.
_STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md",
        # Stage 29.5.1 production .py files (authorized 2026-05-25).
        "stage29_5_migration_models.py",
        "stage29_5_helius_ws_adapter.py",
        "stage29_5_migration_artifact_reader.py",
        "stage29_5_candidate_to_migration_join.py",
        "stage29_5_private_ping_context_projection.py",
        "stage29_5_manifest.py",
    }
)


# Stage 29.5.2 offline integration proof (authorized 2026-05-26).
# Stage 29.5.2 is the offline composition proof substage: this
# narrow amendment widens the Stage 28.11 narrow Stage-29-prod
# allowlist to admit the Stage 29.5.2 production + doc inventory.
# No runtime wiring into Stage 29.3 / 29.4 lands at Stage 29.5.2.
_STAGE_29_5_2_OFFLINE_INTEGRATION_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_2_OFFLINE_INTEGRATION_PROOF_RUNBOOK.md",
        "stage29_5_2_offline_integration.py",
        "stage29_5_2_synthetic_evidence_fixtures.py",
        "stage29_5_2_manifest.py",
    }
)


# Stage 29.5.3 soak pass-entrypoint wrapper (authorized
# 2026-05-26). Stage 29.5.3 ships the runtime-adjacent wrapper +
# side-channel artifact surface that bridges Stage 29.5.2's
# offline composition into the Stage 29.4 soak path WITHOUT
# editing any Stage 29.3 or Stage 29.4 production source. This
# narrow amendment widens the Stage 28.11 Stage-29-prod allowlist
# to admit the Stage 29.5.3 production + doc inventory.
_STAGE_29_5_3_SOAK_PASS_WRAPPER_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_3_SOAK_PASS_WRAPPER_RUNBOOK.md",
        "stage29_5_3_wrapped_pass_models.py",
        "stage29_5_3_soak_pass_wrapper.py",
        "stage29_5_3_side_channel_artifact_writer.py",
        "stage29_5_3_manifest.py",
    }
)


# Stage 29.5.4 direct opt-in migration context injection (authorized
# 2026-05-26). Narrow amendment widens the Stage 28.11 Stage-29-
# prod allowlist to admit the Stage 29.5.4 production + doc
# inventory.
_STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_RUNBOOK.md",
        "stage29_5_4_migration_context_source_adapter.py",
        "stage29_5_4_manifest.py",
    }
)


# Stage 29.5.5 formatted private discord migration context
# rendering (authorized 2026-05-26). Narrow amendment widens
# the Stage 28.11 Stage-29-prod allowlist to admit the Stage
# 29.5.5 production + doc inventory.
_STAGE_29_5_5_PRIVATE_DISCORD_RENDERING_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERING_RUNBOOK.md",
        "stage29_5_5_render_models.py",
        "stage29_5_5_private_discord_migration_context_renderer.py",
        "stage29_5_5_migration_context_recorder.py",
        "stage29_5_5_side_channel_artifact_writer.py",
        "stage29_5_5_manifest.py",
    }
)


# Stage 29.5.6 private ping body migration context injection
# (authorized 2026-05-27). Narrow amendment widens the Stage 28.11
# Stage-29-prod allowlist to admit the Stage 29.5.6 production +
# doc inventory.
_STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_RUNBOOK.md",
        "stage29_5_6_private_ping_migration_context_injector.py",
        "stage29_5_6_manifest.py",
    }
)


# Stage 29.6 bounded private single-shot live proof (authorized
# 2026-05-27). Stage 29.6 is Option A only: two markdown
# deliverables, no production .py files. Narrow amendment widens
# the Stage 28.11 Stage-29-prod allowlist to admit the two Stage
# 29.6 markdown basenames.
_STAGE_29_6_BOUNDED_LIVE_PROOF_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_6_BOUNDED_LIVE_PROOF_RUNBOOK.md",
        "STAGE_29_6_SPEC_LOCK.md",
    }
)


# Stage 29.5.7 Helius raw migration evidence producer/normalizer
# (authorized 2026-06-04). Narrow amendment widens the Stage-29
# allowlist to admit the Stage 29.5.7 production + test inventory.
_STAGE_29_5_7_HELIUS_RAW_MIGRATION_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_7_HELIUS_RAW_MIGRATION_RUNBOOK.md",
        "stage29_5_7_helius_raw_migration_models.py",
        "stage29_5_7_helius_raw_migration_normalizer.py",
        "stage29_5_7_live_migration_evidence_producer.py",
        "stage29_5_7_manifest.py",
    }
)


_STAGE_29_0_PLUS_29_1_ALLOWED_PROD_BASENAMES: frozenset[str] = (
    _STAGE_29_0_ALLOWED_PROD_BASENAMES
    | _STAGE_29_1_PUMPSWAP_ALLOWED_PROD_BASENAMES
    | _STAGE_29_2_BIRDEYE_ALLOWED_PROD_BASENAMES
    | _STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_PROD_BASENAMES
    | _STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_2_OFFLINE_INTEGRATION_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_3_SOAK_PASS_WRAPPER_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_5_PRIVATE_DISCORD_RENDERING_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_ALLOWED_PROD_BASENAMES
    | _STAGE_29_6_BOUNDED_LIVE_PROOF_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_7_HELIUS_RAW_MIGRATION_ALLOWED_PROD_BASENAMES
)


_STAGE_29_0_ALLOWED_TEST_BASENAMES: frozenset[str] = frozenset(
    {"__init__.py", "test_stage_29_0_spec_lock.py"}
)


_STAGE_29_1_PUMPSWAP_ALLOWED_TEST_BASENAMES: frozenset[str] = (
    frozenset(
        {
            "test_stage_29_1_pumpswap_program_constants.py",
            "test_stage_29_1_pumpswap_hint_models.py",
            "test_stage_29_1_pumpswap_hint_extractor.py",
            "test_stage_29_1_pumpswap_hint_aware_decoder.py",
            "test_stage_29_1_hint_probe_models.py",
            "test_stage_29_1_pumpswap_hint_probe.py",
            "test_stage_29_1_runbook.py",
            "test_stage_29_1_boundaries.py",
            "test_stage_29_1_vendored_idl.py",
        }
    )
)


_STAGE_29_2_BIRDEYE_ALLOWED_TEST_BASENAMES: frozenset[str] = (
    frozenset(
        {
            "test_stage_29_2_birdeye_constants.py",
            "test_stage_29_2_birdeye_models.py",
            "test_stage_29_2_birdeye_readiness.py",
            "test_stage_29_2_birdeye_http_transport.py",
            "test_stage_29_2_birdeye_price_source.py",
            "test_stage_29_2_birdeye_ath_source.py",
            "test_stage_29_2_birdeye_probe_models.py",
            "test_stage_29_2_birdeye_probe.py",
            "test_stage_29_2_runbook.py",
            "test_stage_29_2_boundaries.py",
        }
    )
)


_STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_3_smoke_models.py",
        "test_stage_29_3_no_migration_evidence_source.py",
        "test_stage_29_3_hint_aware_event_source.py",
        "test_stage_29_3_tradeable_smoke_orchestrator.py",
        "test_stage_29_3_artifact_writer.py",
        "test_stage_29_3_runbook.py",
        "test_stage_29_3_boundaries.py",
    }
)


# Stage 29.4 short-session private soak (authorized 2026-05-25).
# Stage 29.4.0 is spec-lock-only: this narrow amendment widens
# the Stage-29-tests allowlist to admit the Stage 29.4 spec-
# lock test only. Stage 29.4.1 (separately authorized) widens
# this further to admit the focused Stage 29.4 test files.
_STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_4_spec_lock.py",
        # Stage 29.4.1 widens the Stage 28.11 narrow amendment to
        # admit the focused Stage 29.4 test files.
        "test_stage_29_4_soak_models.py",
        "test_stage_29_4_dedupe_index.py",
        "test_stage_29_4_soak_orchestrator.py",
        "test_stage_29_4_soak_artifact_writer.py",
        "test_stage_29_4_boundaries.py",
    }
)


# Stage 29.5 Helius WS migration evidence adapter + live private
# ping context join (authorized 2026-05-25). Stage 29.5.0 is
# spec-lock-only: this narrow amendment widens the Stage-29-
# tests allowlist to admit the Stage 29.5 spec-lock test only.
# Stage 29.5.1 test files remain blocked at Stage 29.5.0.
_STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_spec_lock.py",
        # Stage 29.5.1 focused test files (authorized 2026-05-25).
        "test_stage_29_5_migration_models.py",
        "test_stage_29_5_helius_ws_adapter.py",
        "test_stage_29_5_migration_artifact_reader.py",
        "test_stage_29_5_candidate_to_migration_join.py",
        "test_stage_29_5_private_ping_context_projection.py",
        "test_stage_29_5_manifest.py",
        "test_stage_29_5_boundaries.py",
    }
)


# Stage 29.5.2 offline integration proof tests (authorized
# 2026-05-26). Narrow amendment widens the Stage 28.11 Stage-29-
# tests allowlist to admit the Stage 29.5.2 test inventory.
_STAGE_29_5_2_OFFLINE_INTEGRATION_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_2_offline_integration.py",
        "test_stage_29_5_2_boundaries.py",
        "test_stage_29_5_2_no_integration_into_stage_29_3.py",
        "test_stage_29_5_2_manifest.py",
        "test_stage_29_5_2_spec_lock.py",
    }
)


# Stage 29.5.3 soak pass-entrypoint wrapper tests (authorized
# 2026-05-26). Narrow amendment widens the Stage 28.11 Stage-29-
# tests allowlist to admit the Stage 29.5.3 test inventory.
_STAGE_29_5_3_SOAK_PASS_WRAPPER_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_3_wrapped_pass_models.py",
        "test_stage_29_5_3_soak_pass_wrapper.py",
        "test_stage_29_5_3_side_channel_artifact_writer.py",
        "test_stage_29_5_3_manifest.py",
        "test_stage_29_5_3_boundaries.py",
        "test_stage_29_5_3_no_modification_to_stage_29_3_or_29_4.py",
        "test_stage_29_5_3_spec_lock.py",
    }
)


# Stage 29.5.4 direct opt-in migration context injection tests
# (authorized 2026-05-26). Narrow amendment widens the Stage 28.11
# Stage-29-tests allowlist to admit the Stage 29.5.4 test
# inventory.
_STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_4_migration_context_source_adapter.py",
        "test_stage_29_5_4_stage29_3_integration.py",
        "test_stage_29_5_4_default_preserves_no_migration_path.py",
        "test_stage_29_5_4_no_duplicate_dispatch.py",
        "test_stage_29_5_4_no_live_surface.py",
        "test_stage_29_5_4_no_public_no_enforcement_no_trading_no_social.py",
        "test_stage_29_5_4_boundaries.py",
        "test_stage_29_5_4_manifest.py",
        "test_stage_29_5_4_spec_lock.py",
        "test_stage_29_5_4_counter_invariants.py",
    }
)


# Stage 29.5.5 formatted private discord migration context
# rendering tests (authorized 2026-05-26). Narrow amendment
# widens the Stage 28.11 Stage-29-tests allowlist to admit the
# Stage 29.5.5 test inventory.
_STAGE_29_5_5_PRIVATE_DISCORD_RENDERING_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_5_render_models.py",
        "test_stage_29_5_5_renderer.py",
        "test_stage_29_5_5_status_matrix.py",
        "test_stage_29_5_5_migration_context_recorder.py",
        "test_stage_29_5_5_side_channel_artifact_writer.py",
        "test_stage_29_5_5_redaction.py",
        "test_stage_29_5_5_stage29_3_integration.py",
        "test_stage_29_5_5_default_preserves_no_renderer_path.py",
        "test_stage_29_5_5_no_duplicate_dispatch.py",
        "test_stage_29_5_5_no_live_surface.py",
        "test_stage_29_5_5_no_enforcement_activation.py",
        "test_stage_29_5_5_no_public_no_enforcement_no_trading_no_social.py",
        "test_stage_29_5_5_boundaries.py",
        "test_stage_29_5_5_manifest.py",
        "test_stage_29_5_5_spec_lock.py",
        "test_stage_29_5_5_counter_invariants.py",
    }
)


# Stage 29.5.6 private ping body migration context injection tests
# (authorized 2026-05-27). Narrow amendment widens the Stage 28.11
# Stage-29-tests allowlist.
_STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_6_private_ping_migration_context.py",
        "test_stage_29_5_6_boundaries.py",
        "test_stage_29_5_6_manifest.py",
        "test_stage_29_5_6_spec_lock.py",
    }
)


# Stage 29.6 bounded private single-shot live proof tests
# (authorized 2026-05-27). Narrow amendment widens the Stage 28.11
# Stage-29-tests allowlist to admit the two Stage 29.6 test
# basenames.
_STAGE_29_6_BOUNDED_LIVE_PROOF_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_6_spec_lock.py",
        "test_stage_29_6_bounded_live_proof.py",
    }
)


# Stage 29.5.7 Helius raw migration evidence producer/normalizer
# (authorized 2026-06-04). Narrow amendment widens the Stage-29
# allowlist to admit the Stage 29.5.7 production + test inventory.
_STAGE_29_5_7_HELIUS_RAW_MIGRATION_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_7_helius_raw_migration_models.py",
        "test_stage_29_5_7_helius_raw_migration_normalizer.py",
        "test_stage_29_5_7_live_migration_evidence_producer.py",
        "test_stage_29_5_7_composition.py",
        "test_stage_29_5_7_vendored_idl.py",
        "test_stage_29_5_7_boundaries.py",
        "test_stage_29_5_7_manifest.py",
        "test_stage_29_5_7_fake_evidence_proof.py",
        "_stage_29_5_7_helius_fixtures.py",
    }
)


_STAGE_29_0_PLUS_29_1_ALLOWED_TEST_BASENAMES: frozenset[str] = (
    _STAGE_29_0_ALLOWED_TEST_BASENAMES
    | _STAGE_29_1_PUMPSWAP_ALLOWED_TEST_BASENAMES
    | _STAGE_29_2_BIRDEYE_ALLOWED_TEST_BASENAMES
    | _STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_TEST_BASENAMES
    | _STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_2_OFFLINE_INTEGRATION_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_3_SOAK_PASS_WRAPPER_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_5_PRIVATE_DISCORD_RENDERING_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_ALLOWED_TEST_BASENAMES
    | _STAGE_29_6_BOUNDED_LIVE_PROOF_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_7_HELIUS_RAW_MIGRATION_ALLOWED_TEST_BASENAMES
)


def test_no_stage29_implementation_tree_exists():
    # Stage 29.0 + Stage 29.1 PumpSwap-only narrow amendment:
    # PHX2/stage29/ may exist iff it ships only the Stage 29.0
    # scaffold AND the Stage 29.1 PumpSwap-only hint-extractor
    # tree. Stage 29.2 / 29.3 implementation files AND any
    # Pump.fun bonding-curve files remain blocked from Stage
    # 28.11.
    if not STAGE29_ROOT.exists():
        return
    actual = {
        entry.name
        for entry in STAGE29_ROOT.iterdir()
        if not (entry.is_dir() and entry.name == "__pycache__")
    }
    forbidden = (
        actual - _STAGE_29_0_PLUS_29_1_ALLOWED_PROD_BASENAMES
    )
    assert not forbidden, (
        f"Stage 28.11 narrow amendment: PHX2/stage29 admits "
        f"only the Stage 29.0 scaffold + Stage 29.1 PumpSwap-"
        f"only tree "
        f"({sorted(_STAGE_29_0_PLUS_29_1_ALLOWED_PROD_BASENAMES)!r}); "
        f"Stage 29.2 / 29.3 files + Pump.fun bonding-curve "
        f"files remain blocked. Forbidden entries: "
        f"{sorted(forbidden)!r}"
    )


def test_no_stage29_tests_tree_exists():
    # Stage 29.0 + Stage 29.1 PumpSwap-only narrow amendment:
    # PHX2/tests/stage29/ may exist iff it ships only the Stage
    # 29.0 tests package marker, the Stage 29.0 spec-lock test,
    # and the Stage 29.1 PumpSwap-only test set. Stage 29.2 /
    # 29.3 test files + Pump.fun bonding-curve test files
    # remain blocked.
    tests_stage29 = PHX2_ROOT / "tests" / "stage29"
    if not tests_stage29.exists():
        return
    actual = {
        entry.name
        for entry in tests_stage29.iterdir()
        if not (entry.is_dir() and entry.name == "__pycache__")
    }
    forbidden = (
        actual - _STAGE_29_0_PLUS_29_1_ALLOWED_TEST_BASENAMES
    )
    assert not forbidden, (
        f"Stage 28.11 narrow amendment: PHX2/tests/stage29 "
        f"admits only the Stage 29.0 tests + Stage 29.1 "
        f"PumpSwap-only tests "
        f"({sorted(_STAGE_29_0_PLUS_29_1_ALLOWED_TEST_BASENAMES)!r}); "
        f"Stage 29.2 / 29.3 test files + Pump.fun bonding-curve "
        f"test files remain blocked. Forbidden entries: "
        f"{sorted(forbidden)!r}"
    )


# ---------------------------------------------------------------------------
# 6. Generated stubs stay outside PHX2/stage28/
# ---------------------------------------------------------------------------


def test_no_generated_protobuf_stub_under_stage28():
    """The Stage 28.10 ban on generated ``*_pb2.py`` /
    ``*_pb2_grpc.py`` stubs under ``PHX2/stage28/`` remains in
    force. Stage 28.11 stubs live under
    ``PHX2/proto/stage28_11/_generated/``.
    """
    leaked: list[str] = []
    for entry in STAGE28_ROOT.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix != ".py":
            continue
        if entry.name.endswith("_pb2.py"):
            leaked.append(entry.name)
        if entry.name.endswith("_pb2_grpc.py"):
            leaked.append(entry.name)
    assert not leaked, (
        f"Stage 28.11 must not place generated protobuf stubs "
        f"under PHX2/stage28/; offenders: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# 7. URL host / raw-secret literal scan
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_HOST_SUBSTRINGS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + ".rpc.com",
    "public-api.birdeye" + ".so",
    "birdeye" + ".so/v1",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com/",
    "yellowstone" + ".chainstack",
)


def test_no_url_host_literal_in_stage_28_11_production_source():
    for path in _iter_stage28_11_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOST_SUBSTRINGS:
            assert needle not in source, (
                f"{path.name}: forbidden URL host literal "
                f"{needle!r}"
            )


_FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
    "CHAINSTACK_API" + "_KEY=",
)


def test_no_raw_secret_literal_in_stage_28_11_production_source():
    for path in _iter_stage28_11_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES:
            assert needle not in source, (
                f"{path.name}: forbidden raw-secret-looking "
                f"literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# 8. Forbidden later-substage / public-routing identifier scan
# ---------------------------------------------------------------------------


_FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS: tuple[str, ...] = (
    "public" + "_router",
    "subscriber" + "_router",
    "paid" + "_tier_router",
    "live" + "_router",
    "telegram" + "_sender",
    "telegram" + "_client",
    "x" + "_social",
    "social" + "_sidecar",
    "tweet" + "_ranking",
    "enforcement" + "_gate",
    "enforce" + "_policy",
    "approval" + "_gate",
    "approval" + "_status",
    "enforcement" + "_result",
    "auto" + "_trade",
    "position" + "_size",
    "trade" + "_executor",
    "wallet" + "_signer",
    "private" + "_key_loader",
    "buy" + "_signal",
    "sell" + "_signal",
    "execute" + "_trade",
    "control" + "_server",
    "http" + "_control_server",
    "auto" + "restart",
    "systemd" + "_unit",
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
    return idents


def test_no_stage_28_11_production_identifier_implements_later_or_public_surface():
    for path in _iter_stage28_11_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{path.name}: forbidden later-substage / "
                    f"public-routing identifier substring "
                    f"{needle!r} in identifier {ident!r}"
                )


# ---------------------------------------------------------------------------
# 9. No top-level Call / no top-level filesystem or subprocess
# ---------------------------------------------------------------------------


def _has_top_level_call(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            return True
    return False


def test_no_stage_28_11_production_has_top_level_call():
    for path in _iter_stage28_11_production_py_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path.name}: Stage 28.11 production .py modules "
            f"must contain no top-level Call (no implicit I/O "
            f"at import time)"
        )


_FORBIDDEN_TOP_LEVEL_WRITE_TARGETS: frozenset[str] = frozenset(
    {
        "write_bytes",
        "write_text",
        "open",
        "mkdir",
        "touch",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "system",
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
    }
)


def test_no_stage_28_11_production_has_top_level_write():
    for path in _iter_stage28_11_production_py_files():
        tree = ast.parse(_read(path))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(
                node.value, ast.Call
            ):
                func = node.value.func
                if isinstance(func, ast.Attribute):
                    assert (
                        func.attr
                        not in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                    ), (
                        f"{path.name}: forbidden top-level "
                        f"write/io call {func.attr!r}"
                    )
                elif isinstance(func, ast.Name):
                    assert (
                        func.id
                        not in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                    ), (
                        f"{path.name}: forbidden top-level "
                        f"write/io call {func.id!r}"
                    )


# ---------------------------------------------------------------------------
# 10. Stage 28.11 manifest pins
# ---------------------------------------------------------------------------


def test_manifest_pins_locked_inventories():
    from PHX2.stage28.stage28_11_manifest import (
        STAGE28_11_DEPENDENCY_BASENAMES,
        STAGE28_11_DOC_BASENAMES,
        STAGE28_11_PRODUCTION_PY_BASENAMES,
        STAGE28_11_TEST_BASENAMES,
    )

    assert (
        STAGE28_11_PRODUCTION_PY_BASENAMES
        == _STAGE_28_11_PRODUCTION_PY_BASENAMES
    )
    assert (
        STAGE28_11_DEPENDENCY_BASENAMES
        == _STAGE_28_11_DEPENDENCY_BASENAMES
    )
    assert (
        STAGE28_11_DOC_BASENAMES
        == _STAGE_28_11_DOC_BASENAMES
    )
    assert (
        STAGE28_11_TEST_BASENAMES
        == _STAGE_28_11_TEST_BASENAMES
    )


def test_manifest_pins_locked_proto_pin():
    from PHX2.stage28.stage28_11_manifest import (
        STAGE28_11_VENDORED_PROTO_COMMIT_SHA,
        STAGE28_11_VENDORED_PROTO_FILES,
        STAGE28_11_VENDORED_PROTO_REPO,
        STAGE28_11_VENDORED_PROTO_TAG,
    )

    assert STAGE28_11_VENDORED_PROTO_REPO == (
        "rpcpool/yellowstone-grpc"
    )
    assert STAGE28_11_VENDORED_PROTO_TAG == (
        "v13.1.0+solana.4.0.0"
    )
    assert STAGE28_11_VENDORED_PROTO_COMMIT_SHA == (
        "62893fb7644b1ceafd2f8d840f8e3997f44a483f"
    )
    assert STAGE28_11_VENDORED_PROTO_FILES == (
        "geyser.proto",
        "solana-storage.proto",
    )


def test_manifest_pins_locked_dependency_versions():
    from PHX2.stage28.stage28_11_manifest import (
        STAGE28_11_PINNED_DEPENDENCIES,
    )

    assert STAGE28_11_PINNED_DEPENDENCIES == (
        ("grpcio", "1.66.2"),
        ("grpcio-tools", "1.66.2"),
        ("protobuf", "5.28.3"),
    )


def test_manifest_listed_forbidden_surfaces_carry_stage_28_9_wrapper_ban():
    from PHX2.stage28.stage28_11_manifest import (
        STAGE28_11_FORBIDDEN_SURFACES,
    )

    expected_present = {
        "Stage 29 implementation",
        "enforcement",
        "public routing",
        "subscriber routing",
        "paid tiers",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / private-key / signer logic",
        "position sizing",
        "trade execution",
        "Stage 28.9 wrapper invocation in Stage 28.11",
        "real Discord send in Stage 28.11",
    }
    assert expected_present.issubset(
        set(STAGE28_11_FORBIDDEN_SURFACES)
    )


# ---------------------------------------------------------------------------
# 11. Requirements file pins
# ---------------------------------------------------------------------------


def test_requirements_file_pins_exact_versions():
    path = STAGE28_ROOT / "stage28_11_requirements.txt"
    text = path.read_text(encoding="utf-8")
    assert "grpcio==1.66.2" in text
    assert "grpcio-tools==1.66.2" in text
    assert "protobuf==5.28.3" in text
    # No other (non-comment) requirement lines.
    for raw in text.splitlines():
        line = raw.strip()
        if line == "" or line.startswith("#"):
            continue
        assert line in {
            "grpcio==1.66.2",
            "grpcio-tools==1.66.2",
            "protobuf==5.28.3",
        }, (
            f"Stage 28.11 requirements admits only the three "
            f"pinned dependencies; saw {line!r}"
        )


# ---------------------------------------------------------------------------
# 12. Endpoint-secret redaction discipline (end-to-end)
# ---------------------------------------------------------------------------


def test_endpoint_secret_repr_never_echoes_raw_endpoint():
    from PHX2.stage28.chainstack_yellowstone_grpc_models import (
        build_chainstack_yellowstone_grpc_endpoint_secret,
    )

    raw_endpoint = "leak-detector.example:443"
    raw_token = "leak-token-1234567890abcdefghij"
    secret = (
        build_chainstack_yellowstone_grpc_endpoint_secret(
            endpoint_url=raw_endpoint,
            x_token=raw_token,
        )
    )
    text = repr(secret) + str(secret) + repr(secret.to_safe_dict())
    assert raw_endpoint not in text
    assert raw_token not in text
