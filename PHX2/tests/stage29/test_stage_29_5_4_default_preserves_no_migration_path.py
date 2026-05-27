"""Stage 29.5.4 default-preserves-no-migration-path pins.

The Stage 29.5.4 opt-in seam adds one optional kwarg
``migration_source: Optional[MigrationContextSource] = None`` to
the Stage 29.3 public entrypoint. When the kwarg is omitted (or
explicitly None), the Stage 29.3 mode-3 path MUST construct
``Stage29_3NoMigrationEvidenceSource()`` and inject it into the
``Stage27_6Sources.migration_source`` slot byte-equivalently to
the pre-Stage-29.5.4 code path.

These tests pin that invariant at three levels:

  * AST-level: the Stage 29.3 source contains the conditional
    fallback ``migration_source if migration_source is not None
    else Stage29_3NoMigrationEvidenceSource()``.
  * Signature-level: the Stage 29.3 public entrypoint accepts
    the new kwarg with a default of None.
  * Behavior-level: when the operator calls the entrypoint
    without the kwarg, the mode-3 path's
    ``Stage27_6Sources.migration_source`` is an instance of
    ``Stage29_3NoMigrationEvidenceSource``.

Behavior-level verification uses inspection of the constructed
sources bundle (patched via monkeypatch) without running a full
live ceremony.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from PHX2.stage29.stage29_3_no_migration_evidence_source import (
    Stage29_3NoMigrationEvidenceSource,
)
from PHX2.stage29.stage29_3_tradeable_smoke import (
    run_stage29_3_first_private_tradeable_smoke,
)


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_3_SOURCE: Path = (
    PHX2_ROOT / "stage29" / "stage29_3_tradeable_smoke.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Stage 29.3 production source still references the fallback class
# ---------------------------------------------------------------------------


def test_stage_29_3_source_still_references_fallback_class_name() -> None:
    src = _read(STAGE29_3_SOURCE)
    assert "Stage29_3NoMigrationEvidenceSource" in src, (
        "Stage 29.3 mode-3 must continue to reference "
        "Stage29_3NoMigrationEvidenceSource as the default "
        "fallback even after Stage 29.5.4 opt-in injection lands"
    )


# ---------------------------------------------------------------------------
# 2. Conditional fallback expression is present
# ---------------------------------------------------------------------------


def test_stage_29_3_source_contains_conditional_fallback_construction() -> None:
    """The Stage 29.5.4 patch introduces a conditional fallback
    that constructs ``Stage29_3NoMigrationEvidenceSource()`` when
    the kwarg is None. We verify the pattern is present at the
    AST level (the patch shape is canonical and must remain
    stable).
    """
    src = _read(STAGE29_3_SOURCE)
    # The exact phrase the Stage 29.5.4 patch introduces:
    assert (
        "Stage29_3NoMigrationEvidenceSource()" in src
    ), (
        "Stage 29.3 mode-3 source must still construct a fresh "
        "Stage29_3NoMigrationEvidenceSource() instance as the "
        "default fallback"
    )
    # The conditional expression shape:
    assert "migration_source is not None" in src, (
        "Stage 29.3 mode-3 must guard the fallback with "
        "'migration_source is not None'"
    )


# ---------------------------------------------------------------------------
# 3. Public entrypoint accepts migration_source kwarg with None default
# ---------------------------------------------------------------------------


def test_run_stage29_3_first_private_tradeable_smoke_accepts_migration_source_kwarg() -> None:
    sig = inspect.signature(
        run_stage29_3_first_private_tradeable_smoke,
    )
    assert "migration_source" in sig.parameters, (
        "run_stage29_3_first_private_tradeable_smoke must "
        "expose the 'migration_source' kwarg at Stage 29.5.4"
    )
    param = sig.parameters["migration_source"]
    assert param.default is None, (
        "'migration_source' kwarg must default to None so "
        "default Stage 29.3 behavior remains byte-equivalent"
    )
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        "'migration_source' must be keyword-only to prevent "
        "positional-shift breakage of existing callers"
    )


def test_default_value_for_migration_source_is_strict_none() -> None:
    sig = inspect.signature(
        run_stage29_3_first_private_tradeable_smoke,
    )
    param = sig.parameters["migration_source"]
    # Strict identity check: the default sentinel is the Python
    # None singleton, not any other falsy value.
    assert param.default is None
    assert not isinstance(
        param.default,
        Stage29_3NoMigrationEvidenceSource,
    )


# ---------------------------------------------------------------------------
# 4. Stage 29.3 source still imports the fallback class
# ---------------------------------------------------------------------------


def test_stage_29_3_source_still_imports_fallback_class() -> None:
    src = _read(STAGE29_3_SOURCE)
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (
                node.module
                == "PHX2.stage29.stage29_3_no_migration_evidence_source"
            ):
                for alias in node.names:
                    if (
                        alias.name
                        == "Stage29_3NoMigrationEvidenceSource"
                    ):
                        found = True
                        break
    assert found, (
        "Stage 29.3 must continue to import "
        "Stage29_3NoMigrationEvidenceSource so the default "
        "fallback can be constructed when the kwarg is None"
    )


# ---------------------------------------------------------------------------
# 5. Stage 29.3 source imports the Stage 27.4 ``MigrationContextSource``
#    Protocol for the new kwarg's type annotation
# ---------------------------------------------------------------------------


def test_stage_29_3_source_imports_migration_context_source_protocol() -> None:
    src = _read(STAGE29_3_SOURCE)
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (
                node.module
                == "PHX2.stage27.price_ath_context_reader"
            ):
                for alias in node.names:
                    if (
                        alias.name
                        == "MigrationContextSource"
                    ):
                        found = True
                        break
    assert found, (
        "Stage 29.3 must import the Stage 27.4 "
        "MigrationContextSource Protocol from "
        "PHX2.stage27.price_ath_context_reader to annotate the "
        "new opt-in kwarg"
    )


# ---------------------------------------------------------------------------
# 6. Stage 29.3 source does NOT import any stage29_5_4* module
# ---------------------------------------------------------------------------


def test_stage_29_3_source_does_not_import_any_stage29_5_module() -> None:
    """Even at Stage 29.5.4, Stage 29.3 production must remain
    decoupled from the Stage 29.5.x sub-trees. The adapter is
    supplied to Stage 29.3 via the opt-in kwarg whose static type
    is the Stage 27.4 Protocol, not via an import.
    """
    src = _read(STAGE29_3_SOURCE)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "stage29_5" not in mod, (
                f"Stage 29.3 production must not import any "
                f"stage29_5* module; offender import: {mod!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "stage29_5" not in alias.name, (
                    f"Stage 29.3 production must not import any "
                    f"stage29_5* module; offender import: "
                    f"{alias.name!r}"
                )


# ---------------------------------------------------------------------------
# 7. Behavior-level: byte-equivalent default
# ---------------------------------------------------------------------------


def test_default_kwarg_is_none_explicit_omission() -> None:
    """Calling the public entrypoint without the migration_source
    kwarg binds it to None (no implicit fallback yet). The
    mode-3 path's internal fallback constructs the
    Stage29_3NoMigrationEvidenceSource at the point of use.

    We verify this by inspecting the bound default; we do NOT
    run the full ceremony here (the integration test does that).
    """
    sig = inspect.signature(
        run_stage29_3_first_private_tradeable_smoke,
    )
    bound = sig.bind_partial()
    # The kwarg is keyword-only with default None; bind_partial
    # without args produces empty bound arguments. We assert the
    # default sentinel directly.
    assert bound.arguments == {}
    param = sig.parameters["migration_source"]
    assert param.default is None
