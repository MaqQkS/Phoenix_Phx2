"""Stage 30.5.1 migration-context source-protocol tests.

A fake source implementing the duck-typed protocol must satisfy
``isinstance`` against the runtime-checkable protocol, must return a
record or ``None``, and the protocol module must NOT require any
Stage 29 import. No live network, no env, no Discord, no provider
call.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional, Set

from PHX2.stage30.stage30_5_migration_context_models import (
    MIGRATION_BASIS_ON_CHAIN_EVENT,
    MIGRATION_STATUS_KNOWN,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_STATUS_PRESENT,
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
    Stage30_5MigrationContextRecord,
)
from PHX2.stage30.stage30_5_migration_context_source_protocol import (
    SOURCE_FORBIDDEN_ATTRIBUTE_NAMES,
    Stage30_5MigrationContextSourceProtocol,
    is_source_forbidden_attribute_name,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
PROTOCOL_PATH: Path = (
    STAGE30_ROOT / "stage30_5_migration_context_source_protocol.py"
)


_VALID_TS: str = "2026-05-29T00:02:00Z"


def _known_record() -> Stage30_5MigrationContextRecord:
    return Stage30_5MigrationContextRecord(
        schema_version=STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
        token_label="ABcd...WXyz",
        migration_status=MIGRATION_STATUS_KNOWN,
        migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
        migration_event_time_utc=None,
        migration_age_seconds=None,
        source_label="stage29_5_migration_evidence",
        source_status=SOURCE_STATUS_PRESENT,
        source_reason=SOURCE_REASON_SOURCE_PRESENT,
        runtime_consumable=False,
        observed_at_utc=_VALID_TS,
    )


# ---------------------------------------------------------------------------
# Fake sources
# ---------------------------------------------------------------------------


class _FakeRecordSource:
    """Fake offline source that returns a fixed record (or None).
    No network, no env, no live secret.
    """

    def __init__(
        self, record: Optional[Stage30_5MigrationContextRecord]
    ) -> None:
        self._record = record
        self.reads: list = []

    def read(
        self,
        token_mint: str,
        observed_at_utc: Optional[str] = None,
    ) -> Optional[Stage30_5MigrationContextRecord]:
        self.reads.append((token_mint, observed_at_utc))
        return self._record


class _NotASource:
    """Carries no ``read`` method, so it must NOT satisfy the
    protocol.
    """

    def lookup(self, token_mint: str) -> None:
        return None


# ---------------------------------------------------------------------------
# runtime_checkable protocol conformance
# ---------------------------------------------------------------------------


def test_fake_record_source_satisfies_protocol() -> None:
    source = _FakeRecordSource(_known_record())
    assert isinstance(source, Stage30_5MigrationContextSourceProtocol)


def test_object_without_read_does_not_satisfy_protocol() -> None:
    assert not isinstance(
        _NotASource(), Stage30_5MigrationContextSourceProtocol
    )


# ---------------------------------------------------------------------------
# Source read returns a record / returns None
# ---------------------------------------------------------------------------


def test_fake_source_returns_record() -> None:
    record = _known_record()
    source = _FakeRecordSource(record)
    out = source.read("So11111111111111111111111111111111111111112")
    assert out is record
    assert source.reads == [
        ("So11111111111111111111111111111111111111112", None)
    ]


def test_fake_source_returns_none() -> None:
    source = _FakeRecordSource(None)
    assert source.read("anymint", _VALID_TS) is None
    assert source.reads == [("anymint", _VALID_TS)]


# ---------------------------------------------------------------------------
# Forbidden-attribute guard
# ---------------------------------------------------------------------------


def test_forbidden_attribute_guard_exposed_and_works() -> None:
    assert callable(is_source_forbidden_attribute_name)
    assert len(SOURCE_FORBIDDEN_ATTRIBUTE_NAMES) >= 15
    # Split-literal needles so this test source carries none bare.
    assert is_source_forbidden_attribute_name("api_" + "key")
    assert is_source_forbidden_attribute_name("b" + "earer_token")
    assert is_source_forbidden_attribute_name("rpc_url")
    assert is_source_forbidden_attribute_name("dis" + "cord_send")
    assert is_source_forbidden_attribute_name("post")
    # The only method the adapter ever calls is allowed.
    assert not is_source_forbidden_attribute_name("read")
    assert not is_source_forbidden_attribute_name(None)
    assert not is_source_forbidden_attribute_name(b"url")


# ---------------------------------------------------------------------------
# Protocol module does not require Stage 29 imports
# ---------------------------------------------------------------------------


def _module_imports(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def test_protocol_module_requires_no_stage29_import() -> None:
    imports = _module_imports(PROTOCOL_PATH)
    for target in imports:
        assert not target.startswith("PHX2.stage29"), (
            f"protocol must not import Stage 29 module {target!r}"
        )
        for stage_n in range(21, 30):
            assert not target.startswith(f"PHX2.stage{stage_n}"), (
                f"protocol must not import Stage 21-29 module "
                f"{target!r}"
            )
        assert not target.startswith("PHX1"), (
            f"protocol must not import PHX1 module {target!r}"
        )


def test_protocol_only_phx2_import_is_the_models_sibling() -> None:
    imports = _module_imports(PROTOCOL_PATH)
    phx2_imports = {t for t in imports if t.startswith("PHX2.")}
    assert phx2_imports == {
        "PHX2.stage30.stage30_5_migration_context_models"
    }
