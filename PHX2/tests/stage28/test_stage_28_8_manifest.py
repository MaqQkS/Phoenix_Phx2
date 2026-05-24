"""Stage 28.8 manifest tests.

Pins:

  * ``PHX2/stage28/stage28_manifest.py`` imports cleanly without
    side effects.
  * The manifest is constants-only: no env reads, no file writes,
    no network, no git calls, no tag creation, no Stage 29
    imports, no Stage 28 implementation imports, no top-level
    Call.
  * The substage list is complete (28.0 -> 28.8).
  * The commit-SHA list is complete for 28.0 -> 28.7 and uses
    the locked placeholder for 28.8.
  * The production / doc / test inventories match the on-disk
    Stage 28 files.
  * The forbidden surfaces and tag policy are listed.
  * The no-secrets / no-network / no-live-send declarations
    are present.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
MANIFEST_PATH: Path = STAGE28_ROOT / "stage28_manifest.py"


def _manifest_source() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Manifest file exists + imports cleanly
# ---------------------------------------------------------------------------


def test_manifest_file_exists():
    assert MANIFEST_PATH.is_file(), (
        f"Stage 28.8 requires the closure manifest "
        f"{MANIFEST_PATH}"
    )


def test_manifest_imports_safely():
    # If the module had a runtime side effect it would have
    # triggered at import time. Importing here proves there is
    # no import-time failure / no implicit I/O / no network /
    # no env read.
    from PHX2.stage28 import stage28_manifest  # noqa: F401


def test_manifest_minor_version_label_is_28_closure_manifest_v0():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_MANIFEST_SCHEMA_VERSION,
    )

    assert (
        STAGE28_MANIFEST_SCHEMA_VERSION
        == "stage28_closure_manifest_v0"
    )


def test_manifest_stage_id_is_stage28():
    from PHX2.stage28.stage28_manifest import STAGE28_ID

    assert STAGE28_ID == "stage28"


def test_manifest_stage_status_is_ready_for_review():
    from PHX2.stage28.stage28_manifest import STAGE28_STATUS

    assert STAGE28_STATUS == "READY_FOR_OPERATOR_REVIEW"


# ---------------------------------------------------------------------------
# 2. Constants-only: no Stage 28 implementation imports, no
#    Stage 29 imports, no env reads, no file writes, no network,
#    no git, no top-level Call
# ---------------------------------------------------------------------------


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


_FORBIDDEN_STAGE_28_IMPLEMENTATION_IMPORTS: tuple[str, ...] = (
    "PHX2.stage28.provider_neutral_models",
    "PHX2.stage28.provider_neutral_config",
    "PHX2.stage28.provider_neutral_readiness",
    "PHX2.stage28.dispatch_ledger_models",
    "PHX2.stage28.dispatch_ledger",
    "PHX2.stage28.failure_classification_models",
    "PHX2.stage28.failure_classification",
    "PHX2.stage28.retry_policy_models",
    "PHX2.stage28.retry_policy",
    "PHX2.stage28.audited_http_transport_models",
    "PHX2.stage28.audited_http_transport",
    "PHX2.stage28.health_status_models",
    "PHX2.stage28.heartbeat_writer",
    "PHX2.stage28.health_snapshot_writer",
    "PHX2.stage28.cli_status_line",
    "PHX2.stage28.session_runner_models",
    "PHX2.stage28.bounded_private_session_runner",
    "PHX2.stage28.longer_session_smoke_harness",
)


def test_manifest_does_not_import_stage_28_implementation_modules():
    imported = _collect_imported_module_paths(_manifest_source())
    leaked = imported & set(
        _FORBIDDEN_STAGE_28_IMPLEMENTATION_IMPORTS
    )
    assert not leaked, (
        f"stage28_manifest.py must not import Stage 28 "
        f"implementation modules; offenders: {sorted(leaked)!r}"
    )


def test_manifest_does_not_import_per_substage_manifest_modules():
    """The Stage 28-wide closure manifest must NOT depend on the
    per-substage manifest modules (each per-substage manifest
    re-exports values from its own model module). This keeps
    the closure manifest a pure constants module that can be
    inspected without pulling the entire Stage 28 implementation
    graph.
    """
    imported = _collect_imported_module_paths(_manifest_source())
    forbidden = {
        "PHX2.stage28.stage28_1_manifest",
        "PHX2.stage28.stage28_2_manifest",
        "PHX2.stage28.stage28_3a_manifest",
        "PHX2.stage28.stage28_3b_manifest",
        "PHX2.stage28.stage28_4_manifest",
        "PHX2.stage28.stage28_5_manifest",
        "PHX2.stage28.stage28_6_manifest",
        "PHX2.stage28.stage28_7_manifest",
    }
    leaked = imported & forbidden
    assert not leaked, (
        f"stage28_manifest.py must not import per-substage "
        f"manifests; offenders: {sorted(leaked)!r}"
    )


def test_manifest_does_not_import_stage_29_modules():
    imported = _collect_imported_module_paths(_manifest_source())
    for target in imported:
        assert not target.startswith("PHX2.stage29"), (
            f"stage28_manifest.py must not import any Stage 29 "
            f"module; saw {target!r}"
        )


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


def test_manifest_reads_no_environ():
    assert not _module_reads_environ(_manifest_source())


_FORBIDDEN_NETWORK_AND_RUNTIME_IMPORT_PATTERNS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
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
    "http",
    "ssl",
)


def test_manifest_imports_no_network_or_runtime_library():
    imported = _collect_imported_module_paths(_manifest_source())
    for target in imported:
        lower = target.lower()
        for pattern in _FORBIDDEN_NETWORK_AND_RUNTIME_IMPORT_PATTERNS:
            assert pattern not in lower, (
                f"stage28_manifest.py forbidden runtime pattern "
                f"{pattern!r} in import {target!r}"
            )


_FORBIDDEN_TOP_LEVEL_CALL_TARGETS: frozenset[str] = frozenset(
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


def test_manifest_has_no_top_level_call():
    """Constants-only: the manifest must contain no top-level
    Call expression (no implicit I/O at import time).
    """
    tree = ast.parse(_manifest_source())
    for node in tree.body:
        assert not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
        ), (
            f"stage28_manifest.py must contain no top-level "
            f"Call; saw {ast.dump(node)!r}"
        )


def test_manifest_has_no_top_level_filesystem_or_subprocess_call():
    tree = ast.parse(_manifest_source())
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            func = node.value.func
            if isinstance(func, ast.Attribute):
                if func.attr in _FORBIDDEN_TOP_LEVEL_CALL_TARGETS:
                    offenders.append(func.attr)
            elif isinstance(func, ast.Name):
                if func.id in _FORBIDDEN_TOP_LEVEL_CALL_TARGETS:
                    offenders.append(func.id)
    assert not offenders, (
        f"stage28_manifest.py must contain no top-level "
        f"filesystem / subprocess call; offenders: "
        f"{offenders!r}"
    )


_FORBIDDEN_SUBPROCESS_OR_OS_CALL_TARGETS: dict[
    str, frozenset[str]
] = {
    "subprocess": frozenset(
        {
            "run",
            "Popen",
            "call",
            "check_call",
            "check_output",
        }
    ),
    "os": frozenset(
        {
            "system",
            "popen",
            "execv",
            "execve",
            "spawnv",
            "spawnve",
        }
    ),
}


def _manifest_resolve_root_and_chain(
    call_node: ast.Call,
) -> tuple[str | None, list[str]]:
    chain: list[str] = []
    current = call_node.func
    while isinstance(current, ast.Attribute):
        chain.insert(0, current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        return current.id, chain
    return None, chain


def test_manifest_makes_no_subprocess_or_os_call():
    """The manifest is constants-only. The AST must contain no
    Call to ``subprocess.*`` / ``os.system`` / ``os.popen`` /
    ``os.exec*`` / ``os.spawn*``.

    Descriptive prose stored as a string constant (e.g. the
    tag-policy line that mentions ``git tag``) is intentionally
    NOT flagged by this test -- the test walks ``ast.Call``
    nodes and so cannot trip on text content.
    """
    tree = ast.parse(_manifest_source())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        root, chain = _manifest_resolve_root_and_chain(node)
        if root is None:
            continue
        if root in _FORBIDDEN_SUBPROCESS_OR_OS_CALL_TARGETS:
            if chain:
                head = chain[0]
                if (
                    head
                    in _FORBIDDEN_SUBPROCESS_OR_OS_CALL_TARGETS[
                        root
                    ]
                ):
                    offenders.append(f"{root}.{'.'.join(chain)}")
    assert not offenders, (
        f"stage28_manifest.py must not call subprocess / os "
        f"helpers; offenders: {offenders!r}"
    )


def test_manifest_makes_no_call_at_all():
    """Even stronger: the constants-only manifest must contain
    zero AST Call nodes (no ``Cls()`` constructor call, no
    ``func(...)`` call). Re-exporting constants from another
    module is allowed because that uses ``ImportFrom``, not a
    Call.
    """
    tree = ast.parse(_manifest_source())
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Call), (
            f"stage28_manifest.py must contain no Call; saw "
            f"{ast.dump(node)!r}"
        )


# ---------------------------------------------------------------------------
# 3. Substage list complete
# ---------------------------------------------------------------------------


def test_substage_list_complete():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_SUBSTAGE_IDS,
    )

    assert STAGE28_SUBSTAGE_IDS == (
        "28.0",
        "28.1",
        "28.2",
        "28.3a",
        "28.3b",
        "28.4",
        "28.5",
        "28.6",
        "28.7",
        "28.8",
    )


def test_substage_titles_match_substage_ids():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_SUBSTAGE_IDS,
        STAGE28_SUBSTAGE_TITLES,
    )

    title_ids = tuple(label for label, _title in STAGE28_SUBSTAGE_TITLES)
    assert title_ids == STAGE28_SUBSTAGE_IDS


# ---------------------------------------------------------------------------
# 4. Commit SHA list complete for 28.0 -> 28.7; 28.8 uses
#    placeholder
# ---------------------------------------------------------------------------


_EXPECTED_COMMIT_PAIRS: tuple[tuple[str, str], ...] = (
    ("28.0", "9f94c98b3116cfe141f8835c7e9e5da5ecfb4413"),
    ("28.1", "2300678561de94230549eadabb9445814cdb9d96"),
    ("28.2", "5a91334c45d8574f480600fd9c5a8d42498f9438"),
    ("28.3a", "2d942636a1d42ec651b1115ede447e19a89f3049"),
    ("28.3b", "c6271d7f14f160e4cf5517e6091b0fbe205226df"),
    ("28.4", "0a05b92b582334932906a2cba5bbc65bf991168c"),
    ("28.5", "bd923482e990021d69b368b3ca79d32a786ec56b"),
    ("28.6", "36d44b551272c3c257da761c27c3196e6889e177"),
    ("28.7", "ea9e741bd62bf8b5d2dcd8acd7d2cd61dc979c86"),
)


@pytest.mark.parametrize("label,sha", _EXPECTED_COMMIT_PAIRS)
def test_manifest_pins_each_known_commit_sha(label, sha):
    from PHX2.stage28.stage28_manifest import (
        STAGE28_COMMIT_SHAS,
    )

    assert (label, sha) in STAGE28_COMMIT_SHAS


def test_manifest_28_8_commit_sha_is_placeholder():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_COMMIT_SHAS,
    )

    assert ("28.8", "TO_BE_FILLED_BY_COMMIT_REPORT") in (
        STAGE28_COMMIT_SHAS
    )


def test_manifest_commit_sha_labels_cover_all_substages():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_COMMIT_SHAS,
        STAGE28_SUBSTAGE_IDS,
    )

    labels = tuple(label for label, _sha in STAGE28_COMMIT_SHAS)
    assert labels == STAGE28_SUBSTAGE_IDS


# ---------------------------------------------------------------------------
# 5. Inventories include expected files
# ---------------------------------------------------------------------------


_EXPECTED_INVENTORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "STAGE28_0_PRODUCTION_BASENAMES",
        ("__init__.py", "STAGE_28_0_SPEC_LOCK.md"),
    ),
    (
        "STAGE28_1_PRODUCTION_BASENAMES",
        (
            "provider_neutral_models.py",
            "provider_neutral_config.py",
            "provider_neutral_readiness.py",
            "stage28_1_manifest.py",
        ),
    ),
    (
        "STAGE28_2_PRODUCTION_BASENAMES",
        (
            "dispatch_ledger_models.py",
            "dispatch_ledger.py",
            "stage28_2_manifest.py",
        ),
    ),
    (
        "STAGE28_3A_PRODUCTION_BASENAMES",
        (
            "failure_classification_models.py",
            "failure_classification.py",
            "stage28_3a_manifest.py",
        ),
    ),
    (
        "STAGE28_3B_PRODUCTION_BASENAMES",
        (
            "retry_policy_models.py",
            "retry_policy.py",
            "stage28_3b_manifest.py",
        ),
    ),
    (
        "STAGE28_4_PRODUCTION_BASENAMES",
        (
            "audited_http_transport_models.py",
            "audited_http_transport.py",
            "stage28_4_manifest.py",
        ),
    ),
    (
        "STAGE28_5_PRODUCTION_BASENAMES",
        (
            "health_status_models.py",
            "heartbeat_writer.py",
            "health_snapshot_writer.py",
            "cli_status_line.py",
            "stage28_5_manifest.py",
        ),
    ),
    (
        "STAGE28_6_PRODUCTION_BASENAMES",
        (
            "session_runner_models.py",
            "bounded_private_session_runner.py",
            "stage28_6_manifest.py",
        ),
    ),
    (
        "STAGE28_7_PRODUCTION_BASENAMES",
        (
            "longer_session_smoke_harness.py",
            "stage28_7_manifest.py",
        ),
    ),
    (
        "STAGE28_7_DOC_BASENAMES",
        (
            "STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md",
            "STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md",
        ),
    ),
    (
        "STAGE28_8_DOC_BASENAMES",
        (
            "STAGE_28_CLOSURE_AUDIT.md",
            "STAGE_29_HANDOFF.md",
        ),
    ),
    (
        "STAGE28_8_PRODUCTION_BASENAMES",
        ("stage28_manifest.py",),
    ),
    (
        "STAGE28_8_TEST_BASENAMES",
        (
            "test_stage_28_8_closure_audit.py",
            "test_stage_28_8_stage29_handoff.py",
            "test_stage_28_8_manifest.py",
            "test_stage_28_8_boundaries.py",
        ),
    ),
)


@pytest.mark.parametrize(
    "name,expected", _EXPECTED_INVENTORIES
)
def test_manifest_inventory_matches_expected(name, expected):
    import PHX2.stage28.stage28_manifest as m

    actual = getattr(m, name)
    assert tuple(actual) == expected, (
        f"manifest inventory {name!r} drift: expected="
        f"{expected!r} actual={tuple(actual)!r}"
    )


def test_manifest_inventories_match_on_disk_stage_28_tree():
    """The union of every production / doc basename declared in
    the manifest must exactly match the set of files under
    ``PHX2/stage28/`` (excluding ``__pycache__``).
    """
    from PHX2.stage28.stage28_manifest import (
        STAGE28_ALL_PRODUCTION_BASENAMES,
    )

    actual = set()
    for entry in STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    expected = set(STAGE28_ALL_PRODUCTION_BASENAMES)
    assert actual == expected, (
        f"manifest inventory does not match PHX2/stage28 tree: "
        f"expected={sorted(expected)!r} actual={sorted(actual)!r}"
    )


def test_closure_evidence_inventory_includes_expected_files():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_CLOSURE_EVIDENCE_BASENAMES,
    )

    expected_present = {
        "STAGE_28_0_SPEC_LOCK.md",
        "STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md",
        "STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md",
        "STAGE_28_CLOSURE_AUDIT.md",
        "STAGE_29_HANDOFF.md",
        "stage28_manifest.py",
    }
    assert expected_present.issubset(
        set(STAGE28_CLOSURE_EVIDENCE_BASENAMES)
    )


# ---------------------------------------------------------------------------
# 6. Forbidden surfaces and tag policy
# ---------------------------------------------------------------------------


_EXPECTED_FORBIDDEN_SURFACES: tuple[str, ...] = (
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
    "dashboard / HTTP control server",
    "daemon / systemd / watchdog / autorestart service",
    "live smoke automation",
)


@pytest.mark.parametrize(
    "surface", _EXPECTED_FORBIDDEN_SURFACES
)
def test_manifest_lists_each_forbidden_surface(surface):
    from PHX2.stage28.stage28_manifest import (
        STAGE28_FORBIDDEN_SURFACES,
    )

    assert surface in STAGE28_FORBIDDEN_SURFACES


def test_manifest_lists_forbidden_basenames():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_FORBIDDEN_BASENAMES,
    )

    for basename in (
        "public_router.py",
        "subscriber_router.py",
        "paid_tier_router.py",
        "telegram_sender.py",
        "x_social.py",
        "enforcement_gate.py",
        "enforce_policy.py",
        "auto_trade.py",
        "position_sizer.py",
        "trade_executor.py",
        "wallet_signer.py",
        "private_key_loader.py",
        "dashboard.py",
        "http_control_server.py",
        "watchdog.py",
        "autorestart.py",
        "daemon.py",
        "systemd_unit.py",
    ):
        assert basename in STAGE28_FORBIDDEN_BASENAMES, (
            f"manifest forbidden basename list missing "
            f"{basename!r}"
        )


# ---------------------------------------------------------------------------
# 7. Tag policy
# ---------------------------------------------------------------------------


def test_manifest_closure_tag_name_is_stage_28_closed():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_CLOSURE_TAG_NAME,
    )

    assert STAGE28_CLOSURE_TAG_NAME == "stage-28-closed"


def test_manifest_tag_policy_pins_explicit_authorization():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_TAG_POLICY,
    )

    joined = "\n".join(STAGE28_TAG_POLICY).lower()
    assert "explicit operator authorization" in joined
    assert "must not create" in joined
    assert "must not push" in joined


def test_manifest_tag_policy_requires_annotated_tag():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_TAG_POLICY,
    )

    joined = "\n".join(STAGE28_TAG_POLICY).lower()
    assert "annotated tag" in joined
    assert "lightweight" in joined


# ---------------------------------------------------------------------------
# 8. No-secrets / no-network / no-live-send declarations
# ---------------------------------------------------------------------------


def test_manifest_no_secrets_declarations_present():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_NO_SECRETS_DECLARATIONS,
    )

    joined = " ".join(STAGE28_NO_SECRETS_DECLARATIONS).lower()
    assert "webhook url" in joined
    assert "api key" in joined
    assert "bearer token" in joined
    assert "provider_neutral_readiness.py" in joined


def test_manifest_no_network_declarations_present():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_NO_NETWORK_DECLARATIONS,
    )

    joined = " ".join(STAGE28_NO_NETWORK_DECLARATIONS).lower()
    assert "no network" in joined
    assert "audited_http_transport.py" in joined
    assert "urllib" in joined
    assert "fake transport" in joined


def test_manifest_no_live_send_declarations_present():
    from PHX2.stage28.stage28_manifest import (
        STAGE28_NO_LIVE_SEND_DECLARATIONS,
    )

    joined = " ".join(STAGE28_NO_LIVE_SEND_DECLARATIONS).lower()
    assert "offline-only" in joined
    assert "live_send_attempted=false" in joined
    assert "live_send_count=0" in joined
    assert "manual operator procedure" in joined


# ---------------------------------------------------------------------------
# 9. Manifest exports a stable __all__
# ---------------------------------------------------------------------------


def test_manifest_all_is_a_tuple_of_strings():
    from PHX2.stage28 import stage28_manifest as m

    assert isinstance(m.__all__, tuple)
    for name in m.__all__:
        assert isinstance(name, str)
        assert hasattr(m, name), (
            f"manifest __all__ names {name!r} but it is not "
            f"defined on the module"
        )
