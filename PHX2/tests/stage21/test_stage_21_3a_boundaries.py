"""Stage 21.3A boundary / scope tests.

Pins the Stage 21.3A scope at the file / import / vocabulary
level. These checks are deliberately complementary to the global
Stage 21 boundary tests (``test_import_boundaries.py``,
``test_env_read_boundaries.py``, ``test_no_public_routing.py``,
``test_no_secret_leaks.py``) -- the global tests scan every
Stage 21 production module, while this test pins the 21.3A
specifics:

  * The forbidden 21.3A files are absent.
  * The new 21.3A production modules do not import the network /
    messaging / RPC / DB / scheduler / secrets-management
    libraries that are out of scope for 21.3A.
  * The new 21.3A production modules do not import any prior
    Stage 17..20 runtime, Phoenix1, or PHX2 runtime layer.
  * The new live-readiness module does NOT read ``os.environ`` /
    ``os.getenv`` -- the Stage 21 env-read boundary stays at
    ``config.py`` alone.
  * The decoder uses a module-local ``ProviderPayloadError``
    hierarchy and does not modify the Stage 21 central error
    registry.
  * The Stage 21.3A locked vocabularies (instruction-kind set,
    safety acknowledgement, mode token, env-var names, reason
    tokens) match the locked operator decisions.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage21.live_secrets_boundary import (
    LIVE_SAFETY_ACKNOWLEDGEMENT_V1,
    LIVE_SMOKE_MODE_TOKEN,
    STAGE21_3A_NEW_ENV_VAR_NAMES,
    STAGE21_3A_READINESS_REASON_TOKENS,
)
from PHX2.stage21.provider_event_decoder import (
    ProviderPayloadError,
    SUPPORTED_INSTRUCTION_KINDS,
)


STAGE21_ROOT: Path = Path(__file__).parent.parent.parent / "stage21"
LIVE_SECRETS_BOUNDARY_PATH: Path = STAGE21_ROOT / "live_secrets_boundary.py"
PROVIDER_EVENT_DECODER_PATH: Path = STAGE21_ROOT / "provider_event_decoder.py"


# Stage 21.3A scope was contracts / config / live-gate / readiness
# + decoder ONLY. ``provider_adapter_helius.py`` was forbidden in
# 21.3A and landed in Stage 21.3B; this 21.3A boundary test no
# longer flags it. ``discord_private_transport.py`` was forbidden
# in 21.3A and 21.3B and landed in Stage 21.3C; this 21.3A
# boundary test no longer flags it either. The remaining filename
# (``stage21_3_manifest.py``) stays forbidden in 21.3A / 21.3B /
# 21.3C -- the Stage 21.3B and Stage 21.3C boundary tests re-pin
# it so removing the others here does not loosen the overall scope.
_FORBIDDEN_21_3A_FILE_NAMES: tuple[str, ...] = (
    "stage21_3_manifest.py",
)


_FORBIDDEN_RUNTIME_LIB_PATTERNS: tuple[str, ...] = (
    # Network / RPC
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    # Provider clients
    "helius",
    "birdeye",
    "dexscreener",
    "jupiter",
    "jito",
    # Messaging
    "discord",
    "telegram",
    "telethon",
    "webhook",
    # Scheduler / daemon
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "daemon",
    # DB
    "sqlalchemy",
    "sqlite3",
    # Secrets-management libs
    "dotenv",
    "keyring",
)


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
)


_FORBIDDEN_PHX2_RUNTIME_PREFIXES: tuple[str, ...] = (
    "PHX2.db",
    "PHX2.repositories",
    "PHX2.config",
    "PHX2.models",
    "PHX2.services",
    "PHX2.dispatch",
    "PHX2.filters",
    "PHX2.integrations",
    "PHX2.renderers",
    "PHX2.scripts",
    "PHX2.analysis",
)


_ENV_ATTR_NAMES: frozenset[str] = frozenset({"environ", "getenv", "environb"})


def _collect_imported_module_paths(path: Path) -> set[str]:
    """Return the set of imported module paths in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def _module_reads_env(path: Path) -> bool:
    """Return True iff ``path`` reads ``os.environ`` / ``os.getenv``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    os_aliases: set[str] = set()
    env_attr_aliases: set[str] = set()
    env_call_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "") == "os":
                for alias in node.names:
                    bound = alias.asname or alias.name
                    if alias.name in ("environ", "environb"):
                        env_attr_aliases.add(bound)
                    elif alias.name == "getenv":
                        env_call_aliases.add(bound)
            elif (node.module or "").startswith("os.environ"):
                return True

    if env_attr_aliases or env_call_aliases:
        return True

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in _ENV_ATTR_NAMES
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
                and node.args[1].value in _ENV_ATTR_NAMES
            ):
                return True

    return False


# ---------------------------------------------------------------------------
# Forbidden 21.3A files
# ---------------------------------------------------------------------------


def test_forbidden_21_3a_production_files_do_not_exist():
    # Stage 21.3A ships contracts / config / live-gate / readiness
    # + decoder ONLY. The concrete provider adapter, the Discord
    # transport, and any Stage 21.3 manifest writer are deferred
    # to later sub-stages. This test fails closed if any of those
    # files is created in 21.3A.
    for filename in _FORBIDDEN_21_3A_FILE_NAMES:
        assert not (STAGE21_ROOT / filename).exists(), (
            f"Stage 21.3A scope violation: {filename} must not exist"
        )


# ---------------------------------------------------------------------------
# Locked vocabularies
# ---------------------------------------------------------------------------


def test_supported_instruction_kinds_locked_to_placeholder():
    # Locked operator decision Q2: Stage 21.3A only accepts the
    # placeholder kind. The real PumpSwap / Pump.fun vocabulary
    # lands in Stage 21.3B+.
    assert SUPPORTED_INSTRUCTION_KINDS == frozenset({"reserved_for_21_3b"})


def test_live_smoke_mode_token_is_locked():
    assert LIVE_SMOKE_MODE_TOKEN == "live_smoke"


def test_live_safety_acknowledgement_is_v1_locked():
    # Per Q4 the operator acknowledgement is locked at V1. Any
    # future revision (V2+) requires an explicit operator
    # decision to introduce a new constant.
    assert LIVE_SAFETY_ACKNOWLEDGEMENT_V1 == (
        "phx2-stage21-live-smoke-ack-v1"
    )


def test_new_env_var_names_are_exactly_the_four_locked_strings():
    assert STAGE21_3A_NEW_ENV_VAR_NAMES == (
        "PHX2_STAGE21_LIVE_SMOKE_MODE",
        "PHX2_STAGE21_PROVIDER_ID",
        "PHX2_STAGE21_SAFE_FOR_LIVE_DISPATCH",
        "PHX2_STAGE21_LIVE_SAFETY_ACKNOWLEDGEMENT",
    )


def test_readiness_reason_set_is_exactly_twelve_locked_tokens():
    # The Stage 21.3A remediation widened the closed set from 11
    # to 12: the original ``provider_id_missing`` was renamed to
    # ``missing_provider_id`` and the new
    # ``unsupported_provider_id`` reason was added to reject
    # real provider names (e.g. ``"helius"``) in 21.3A. Real
    # provider ids land in Stage 21.3B+.
    assert len(STAGE21_3A_READINESS_REASON_TOKENS) == 12
    assert len(set(STAGE21_3A_READINESS_REASON_TOKENS)) == 12


# ---------------------------------------------------------------------------
# Import-scope invariants for the new 21.3A production modules
# ---------------------------------------------------------------------------


def test_live_secrets_boundary_does_not_import_forbidden_runtime_libs():
    modules = _collect_imported_module_paths(LIVE_SECRETS_BOUNDARY_PATH)
    for module in modules:
        lower = module.lower()
        for pattern in _FORBIDDEN_RUNTIME_LIB_PATTERNS:
            assert pattern not in lower, (
                f"live_secrets_boundary.py imports forbidden runtime "
                f"module pattern {pattern!r} via {module!r}"
            )


def test_provider_event_decoder_does_not_import_forbidden_runtime_libs():
    modules = _collect_imported_module_paths(PROVIDER_EVENT_DECODER_PATH)
    for module in modules:
        lower = module.lower()
        for pattern in _FORBIDDEN_RUNTIME_LIB_PATTERNS:
            assert pattern not in lower, (
                f"provider_event_decoder.py imports forbidden runtime "
                f"module pattern {pattern!r} via {module!r}"
            )


def test_new_21_3a_modules_do_not_import_prior_stage_or_phoenix1():
    for path in (LIVE_SECRETS_BOUNDARY_PATH, PROVIDER_EVENT_DECODER_PATH):
        modules = _collect_imported_module_paths(path)
        for module in modules:
            assert not module.startswith("phoenix1"), (
                f"{path.name}: forbidden phoenix1 import {module!r}"
            )
            for prefix in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not module.startswith(prefix), (
                    f"{path.name}: forbidden prior-stage import "
                    f"{module!r}"
                )


def test_new_21_3a_modules_do_not_import_phx2_runtime_layer():
    for path in (LIVE_SECRETS_BOUNDARY_PATH, PROVIDER_EVENT_DECODER_PATH):
        modules = _collect_imported_module_paths(path)
        for module in modules:
            for prefix in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not module.startswith(prefix), (
                    f"{path.name}: forbidden PHX2 runtime-layer import "
                    f"{module!r}"
                )


# ---------------------------------------------------------------------------
# Env-read boundary stays at config.py
# ---------------------------------------------------------------------------


def test_live_secrets_boundary_does_not_read_environ_directly():
    # Per the locked Stage 21 env-read boundary the new module
    # must operate on the env mapping passed in by its caller.
    # The global test_env_read_boundaries.py also enforces this;
    # this assertion is the explicit 21.3A pin.
    assert not _module_reads_env(LIVE_SECRETS_BOUNDARY_PATH), (
        "live_secrets_boundary.py must not read os.environ / "
        "os.getenv -- the Stage 21 env-read boundary stays at "
        "config.py alone"
    )


def test_provider_event_decoder_does_not_read_environ():
    assert not _module_reads_env(PROVIDER_EVENT_DECODER_PATH)


# ---------------------------------------------------------------------------
# Decoder error hierarchy stays module-local (per Q3)
# ---------------------------------------------------------------------------


def test_decoder_error_hierarchy_is_module_local_not_stage21_error():
    # Per Q3 the decoder uses a module-local ``ProviderPayloadError``
    # hierarchy rooted at Exception. The closed Stage 21
    # E2120..E2122 codes remain reserved for the Stage 21.3B+
    # real adapter contract; the decoder must NOT raise them.
    from PHX2.stage21.errors import Stage21Error

    assert issubclass(ProviderPayloadError, Exception)
    assert not issubclass(ProviderPayloadError, Stage21Error)


# ---------------------------------------------------------------------------
# Source-text invariants for the new modules
# ---------------------------------------------------------------------------


def test_new_21_3a_modules_contain_no_url_literals_in_source():
    # Mirrors test_import_boundaries.test_no_url_literals_in_production_source
    # for the two new files specifically.
    for path in (LIVE_SECRETS_BOUNDARY_PATH, PROVIDER_EVENT_DECODER_PATH):
        source = path.read_text(encoding="utf-8")
        assert "https://" not in source, (
            f"{path.name}: forbidden 'https://' literal in source"
        )
        assert "wss://" not in source, (
            f"{path.name}: forbidden 'wss://' literal in source"
        )


def test_new_21_3a_modules_do_not_reference_bot_db():
    for path in (LIVE_SECRETS_BOUNDARY_PATH, PROVIDER_EVENT_DECODER_PATH):
        source = path.read_text(encoding="utf-8")
        assert "bot.db" not in source, (
            f"{path.name}: forbidden 'bot.db' reference"
        )
