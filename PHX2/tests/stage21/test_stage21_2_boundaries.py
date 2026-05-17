"""Stage 21.2 boundary / static checks.

These tests are Stage 21.2-specific extensions of the Stage 21.1
boundary suite. They run AST-level checks over the seven Stage
21.2 production files plus a substring check that the four
Stage 21.2 artifacts (when produced by a real simulator run)
contain no secret/webhook/URL/routing material.

Stage 21.2 production files under test:
  * PHX2/stage21/normalized_events.py
  * PHX2/stage21/ping_payloads.py
  * PHX2/stage21/ping_builder.py
  * PHX2/stage21/fake_provider.py
  * PHX2/stage21/fake_transport.py
  * PHX2/stage21/telemetry_writer.py
  * PHX2/stage21/live_path_simulator.py
  * PHX2/stage21/stage21_2_manifest.py
"""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path

from PHX2.stage21.clock import FrozenClock
from PHX2.stage21.fake_provider import Stage21FakeEventSeed
from PHX2.stage21.live_path_simulator import run_live_path_simulation


STAGE21_ROOT = Path(__file__).parent.parent.parent / "stage21"


STAGE21_2_PRODUCTION_FILES: tuple[str, ...] = (
    "normalized_events.py",
    "ping_payloads.py",
    "ping_builder.py",
    "fake_provider.py",
    "fake_transport.py",
    "telemetry_writer.py",
    "live_path_simulator.py",
    "stage21_2_manifest.py",
)


def _stage21_2_files() -> list[Path]:
    out: list[Path] = []
    for name in STAGE21_2_PRODUCTION_FILES:
        p = STAGE21_ROOT / name
        assert p.exists(), f"Stage 21.2 production file missing: {p}"
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# Import boundaries (Stage 21.2 specific)
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_MODULE_PATTERNS: tuple[str, ...] = (
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


_FORBIDDEN_PHX2_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
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


def _collect_modules_and_full_targets(source: str) -> tuple[set[str], set[str]]:
    tree = ast.parse(source)
    modules: set[str] = set()
    full_targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                full_targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
                full_targets.add(mod)
            for alias in node.names:
                if mod:
                    full_targets.add(f"{mod}.{alias.name}")
    return modules, full_targets


def test_stage21_2_no_forbidden_runtime_module_patterns():
    for path in _stage21_2_files():
        modules, _ = _collect_modules_and_full_targets(
            path.read_text(encoding="utf-8")
        )
        for module in modules:
            lower = module.lower()
            for pattern in _FORBIDDEN_IMPORT_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden module pattern {pattern!r} in import "
                    f"target {module!r}"
                )


def test_stage21_2_no_forbidden_phx2_prefix_imports():
    for path in _stage21_2_files():
        _, full = _collect_modules_and_full_targets(
            path.read_text(encoding="utf-8")
        )
        for target in full:
            for forbidden in _FORBIDDEN_PHX2_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden PHX2 target {target!r}"
                )


def test_stage21_2_no_phoenix1_imports():
    for path in _stage21_2_files():
        _, full = _collect_modules_and_full_targets(
            path.read_text(encoding="utf-8")
        )
        for target in full:
            assert not target.startswith("phoenix1"), (
                f"{path}: forbidden phoenix1 target {target!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden real-provider / real-transport class names
# ---------------------------------------------------------------------------


_FORBIDDEN_REAL_LIKE_CLASS_NAMES: tuple[str, ...] = (
    # Original Stage 21.2 forbidden names (real provider /
    # real transport adapters reserved for later sub-stages).
    "DiscordTransport",
    "TelegramTransport",
    "WebhookTransport",
    "HeliusProvider",
    "GrpcProvider",
    "BirdeyeProvider",
    # Stage 21.2 remediation R6: extended forbidden names. These
    # generic "real" / "live" provider / transport class names
    # MUST NOT appear in Stage 21.2 production code. They are
    # reserved for sub-stages that introduce real live
    # adapters under their own operator-locked design review.
    "LiveProvider",
    "LiveTransport",
    "RealProvider",
    "RealTransport",
)


# Stage-21-owned fake-only class names that are explicitly
# allowed in Stage 21.2 production code. The lock-set test
# pins these names so a future refactor that removes the
# Stage21Fake* identity must surface in review.
_ALLOWED_STAGE21_2_FAKE_CLASS_NAMES: tuple[str, ...] = (
    "Stage21FakeProvider",
    "Stage21FakeEvent",
    "Stage21FakeEventSeed",
    "FakePrivateTransport",
    "FakeTransportCaptureRecord",
)


def _collect_top_level_class_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
    return names


def _collect_all_identifier_references(source: str) -> set[str]:
    """Return every identifier-position name in ``source``.

    Mirrors the routing-test ``_extract_identifiers`` helper at
    the bottom of this file. Used by the R6 reference scan to
    catch any production reference to a forbidden real-like
    class name (definition, import, attribute access, type
    annotation, function arg, keyword arg, import alias, etc.).

    String literals inside docstrings, comments, or list/tuple
    literals are NOT identifiers and are NOT collected -- which
    is why this scan tolerates the forbidden tuple
    ``_FORBIDDEN_REAL_LIKE_CLASS_NAMES`` declared as string
    literals in this test file (the test file is not in the
    production tree anyway).
    """
    tree = ast.parse(source)
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
        elif isinstance(node, ast.alias):
            for part in node.name.split("."):
                if part:
                    idents.add(part)
            if node.asname:
                idents.add(node.asname)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for part in node.module.split("."):
                if part:
                    idents.add(part)
    return idents


def test_stage21_2_does_not_define_real_provider_or_transport_classes():
    for path in _stage21_2_files():
        names = _collect_top_level_class_names(
            path.read_text(encoding="utf-8")
        )
        for forbidden in _FORBIDDEN_REAL_LIKE_CLASS_NAMES:
            assert forbidden not in names, (
                f"{path}: forbidden real-like class {forbidden!r} defined"
            )


def test_stage21_2_does_not_reference_real_like_provider_or_transport_names():
    """R6: no production source may even reference the forbidden names.

    The class-definition scan above catches direct ``class
    LiveProvider(...):`` declarations. This scan additionally
    catches any identifier-position reference (import target,
    import alias, attribute access, type annotation, argument
    name) so a future caller that imports ``LiveProvider`` from
    an external module is still blocked at the boundary.
    """
    for path in _stage21_2_files():
        idents = _collect_all_identifier_references(
            path.read_text(encoding="utf-8")
        )
        for forbidden in _FORBIDDEN_REAL_LIKE_CLASS_NAMES:
            assert forbidden not in idents, (
                f"{path}: forbidden real-like name {forbidden!r} referenced "
                f"as an identifier"
            )


def test_r6_forbidden_real_like_class_names_lock_set():
    """R6 lock-set: the forbidden tuple contains exactly the 10 expected names.

    Adding to this set is allowed but requires explicit
    acknowledgement via updating this test.
    """
    expected = {
        # Original Stage 21.2 forbidden names.
        "DiscordTransport",
        "TelegramTransport",
        "WebhookTransport",
        "HeliusProvider",
        "GrpcProvider",
        "BirdeyeProvider",
        # R6 additions.
        "LiveProvider",
        "LiveTransport",
        "RealProvider",
        "RealTransport",
    }
    assert set(_FORBIDDEN_REAL_LIKE_CLASS_NAMES) == expected, (
        f"forbidden set drifted; got "
        f"{set(_FORBIDDEN_REAL_LIKE_CLASS_NAMES)}"
    )
    # No duplicates.
    assert len(_FORBIDDEN_REAL_LIKE_CLASS_NAMES) == len(expected)


def test_r6_allowed_stage21_2_fake_class_names_remain_allowed():
    """R6: the explicitly-allowed fake class names are NOT in the forbidden set.

    Pins that the 5 Stage-21-owned fake-only class names
    (``Stage21FakeProvider`` / ``Stage21FakeEvent`` /
    ``Stage21FakeEventSeed`` / ``FakePrivateTransport`` /
    ``FakeTransportCaptureRecord``) remain explicitly allowed in
    Stage 21.2 production code.
    """
    forbidden = set(_FORBIDDEN_REAL_LIKE_CLASS_NAMES)
    for name in _ALLOWED_STAGE21_2_FAKE_CLASS_NAMES:
        assert name not in forbidden, (
            f"explicitly-allowed fake class name {name!r} is in the "
            f"forbidden set"
        )


def test_r6_allowed_fake_class_names_actually_exist_in_production():
    """R6: each allowed fake class name actually appears in Stage 21.2 production.

    Pins that the Stage-21-owned fake-only contract surface is
    still present. If a refactor removes one of these classes,
    this test surfaces it explicitly so the change can be
    re-reviewed.
    """
    all_class_names: set[str] = set()
    for path in _stage21_2_files():
        all_class_names |= _collect_top_level_class_names(
            path.read_text(encoding="utf-8")
        )
    for name in _ALLOWED_STAGE21_2_FAKE_CLASS_NAMES:
        assert name in all_class_names, (
            f"expected Stage 21.2 allowed fake class {name!r} to be "
            f"defined somewhere in the production tree"
        )


def test_stage21_2_fake_provider_class_is_explicitly_fake_only():
    # Production file must expose the fake-only marker attribute
    # so the boundary contract is statically discoverable.
    from PHX2.stage21.fake_provider import Stage21FakeProvider
    assert Stage21FakeProvider.IS_FAKE_ONLY is True


def test_stage21_2_fake_transport_class_is_explicitly_fake_only():
    from PHX2.stage21.fake_transport import FakePrivateTransport
    assert FakePrivateTransport.IS_FAKE_ONLY is True


# ---------------------------------------------------------------------------
# Stage 21.2 remediation R6: end-to-end Codex PoC simulator test (verify)
# ---------------------------------------------------------------------------
#
# R6 requires an end-to-end Codex PoC simulator test that:
#   1. Runs ``run_live_path_simulation`` with a poisoned
#      run_id containing a forbidden substring.
#   2. Asserts ``Stage21Error`` raised with code ``E2153``.
#   3. Asserts the output directory contains zero artifact
#      files.
#
# Phase R2 already added an equivalent run-level test in
# ``test_live_path_simulator.py`` (see
# ``test_codex_poc_1_run_level_url_run_id_no_artifacts_written``).
# Per the R6 prompt instruction to "verify it fully satisfies
# this R6 requirement, add only the missing assertion(s), if
# any" -- the existing test covers all three R6 assertions:
#   * Stage21Error raised: pytest.raises(Stage21Error)
#   * E2153: assert exc.value.code == "E2153"
#   * Zero artifact files: assert _no_files_in(output_dir)
#
# The check below imports the existing test by name to ensure
# the R6 PoC coverage cannot be quietly deleted from
# test_live_path_simulator.py without surfacing here. (This is
# a structural pin, not a duplicate run of the simulator.)


def test_r6_end_to_end_codex_poc_run_level_test_exists():
    """R6: structural pin -- the R2 run-level PoC test must still exist."""
    from PHX2.tests.stage21 import test_live_path_simulator as live_test_mod

    assert hasattr(
        live_test_mod,
        "test_codex_poc_1_run_level_url_run_id_no_artifacts_written",
    ), (
        "R6 requires the end-to-end Codex PoC simulator test "
        "test_codex_poc_1_run_level_url_run_id_no_artifacts_written "
        "to exist in test_live_path_simulator.py. R2 added it; "
        "this pin ensures it is not silently removed."
    )


# ---------------------------------------------------------------------------
# No URL literals in Stage 21.2 production source
# ---------------------------------------------------------------------------


def test_stage21_2_no_url_literals_in_production_source():
    for path in _stage21_2_files():
        source = path.read_text(encoding="utf-8")
        assert "https://" not in source, (
            f"{path}: forbidden 'https://' literal in source"
        )
        assert "http://" not in source, (
            f"{path}: forbidden 'http://' literal in source"
        )
        assert "wss://" not in source, (
            f"{path}: forbidden 'wss://' literal in source"
        )


# ---------------------------------------------------------------------------
# No env reads in any Stage 21.2 module
# ---------------------------------------------------------------------------


def _module_reads_env(source: str) -> bool:
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
                    bound = alias.asname or alias.name
                    if alias.name in ("environ", "environb"):
                        env_attr_aliases.add(bound)
                    elif alias.name == "getenv":
                        env_call_aliases.add(bound)
            elif mod == "os.environ" or mod.startswith("os.environ."):
                return True
    if env_attr_aliases or env_call_aliases:
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in ("environ", "getenv", "environb")
            ):
                return True
    return False


def test_no_stage21_2_module_reads_env():
    for path in _stage21_2_files():
        source = path.read_text(encoding="utf-8")
        assert not _module_reads_env(source), (
            f"{path}: forbidden env-read; only PHX2/stage21/config.py "
            f"may read the process environment"
        )


# ---------------------------------------------------------------------------
# No SQLite / DB import in any Stage 21.2 module
# ---------------------------------------------------------------------------


def test_no_stage21_2_module_imports_sqlite3():
    for path in _stage21_2_files():
        source = path.read_text(encoding="utf-8")
        modules, _ = _collect_modules_and_full_targets(source)
        assert "sqlite3" not in modules, (
            f"{path}: forbidden sqlite3 import"
        )
        for mod in modules:
            assert not mod.lower().startswith("phx2.db"), (
                f"{path}: forbidden PHX2.db import target {mod!r}"
            )
            assert not mod.lower().startswith("phx2.repositories"), (
                f"{path}: forbidden PHX2.repositories import target {mod!r}"
            )


# ---------------------------------------------------------------------------
# No `bot.db` substring anywhere in Stage 21.2 source
# ---------------------------------------------------------------------------


def test_no_bot_db_reference_in_stage21_2_source():
    for path in _stage21_2_files():
        source = path.read_text(encoding="utf-8")
        assert "bot.db" not in source, (
            f"{path}: forbidden 'bot.db' substring in source"
        )


# ---------------------------------------------------------------------------
# Forbidden routing identifiers in Stage 21.2 production source
# ---------------------------------------------------------------------------


_FORBIDDEN_ROUTING_TOKENS_LOWER: tuple[str, ...] = (
    "subscriber",
    "subscribers",
    "subscriber_channel",
    "public_channel",
    "public_signal",
    "public_dispatch",
    "paid_signal",
    "paid_signals",
    "paid_channel",
    "paid_dispatch",
)


_EXPLICIT_ALLOWED_LOWER: frozenset[str] = frozenset({
    "safe_for_public_dispatch",
})


def _extract_identifiers(source: str) -> set[str]:
    tree = ast.parse(source)
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
        elif isinstance(node, ast.alias):
            for part in node.name.split("."):
                if part:
                    idents.add(part)
            if node.asname:
                idents.add(node.asname)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for part in node.module.split("."):
                if part:
                    idents.add(part)
    return idents


def _identifier_violates(ident: str) -> str:
    lower = ident.lower()
    if lower in _EXPLICIT_ALLOWED_LOWER:
        return ""
    for token in _FORBIDDEN_ROUTING_TOKENS_LOWER:
        if lower == token:
            return token
        if (
            lower.startswith(token + "_")
            or lower.endswith("_" + token)
            or ("_" + token + "_") in lower
        ):
            return token
    return ""


def test_no_forbidden_routing_identifier_in_stage21_2_source():
    for path in _stage21_2_files():
        for ident in _extract_identifiers(path.read_text(encoding="utf-8")):
            matched = _identifier_violates(ident)
            assert matched == "", (
                f"{path}: identifier {ident!r} carries forbidden routing "
                f"token {matched!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden-content scan of produced artifacts
# ---------------------------------------------------------------------------


_FORBIDDEN_ARTIFACT_SUBSTRINGS: tuple[str, ...] = (
    "http" + "://",
    "https" + "://",
    "webhook",
    "api_key",
    "password",
    "credential",
    # Routing tokens forbidden in Stage 21.
    "public_dispatch",
    "paid_dispatch",
    "subscriber",
    "public_signal",
    "paid_signal",
    "public_channel",
    "paid_channel",
)


# Stage 21.2 remediation R5: artifact-content scan uses the
# JSON-aware ``cleaned_artifact_text_from_path`` helper. The
# helper parses the artifact, strips only the exact locked-
# invariant keypath
# ``run_metadata.safe_for_public_dispatch`` when its value is
# the Python boolean ``False``, and re-serializes the cleaned
# structure for substring scanning. The prior global
# ``.replace("safe_for_public_dispatch", "")`` substring strip
# has been removed.
from PHX2.tests.stage21._artifact_scan_helpers import (
    cleaned_artifact_text_from_path,
)


def test_stage21_2_artifacts_have_no_forbidden_substrings(tmp_path):
    result = run_live_path_simulation(
        seeds=[
            Stage21FakeEventSeed(
                mint="FAKE_MINT_AAAA",
                event_type="fake_swap",
                observed_at_utc="2026-05-17T12:00:00Z",
                slot=1,
                raw_payload={"fake_amount": 1000, "fake_decimals": 6},
            ),
            Stage21FakeEventSeed(
                mint="FAKE_MINT_BBBB",
                event_type="fake_mint",
                observed_at_utc="2026-05-17T12:01:00Z",
                slot=2,
                raw_payload={"fake_supply": 5_000_000, "fake_decimals": 9},
            ),
        ],
        output_dir=tmp_path / "stage21_2_artifact_scan",
        run_id="stage21_2_artifact_scan_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        clock=FrozenClock(
            datetime.fromisoformat("2026-05-17T12:00:00+00:00")
        ),
    )
    for path in (
        result.manifest_path,
        result.ping_ledger_path,
        result.fake_transport_capture_path,
        result.telemetry_summary_path,
    ):
        raw = path.read_text(encoding="utf-8")
        cleaned = cleaned_artifact_text_from_path(path)
        for needle in _FORBIDDEN_ARTIFACT_SUBSTRINGS:
            assert needle not in cleaned, (
                f"{path.name}: forbidden substring {needle!r}"
            )
        # JSON-decoding sanity for the .json artifacts (use raw,
        # not the cleaned form).
        if path.suffix == ".json":
            json.loads(raw)
