"""Stage 20.4 closure model shapes (NamedTuple only).

Locked typed records for: validated input config, the operator
test-result block, hash records, audit hit records, the codebase
audit + artifact validation aggregate records, the checklist row,
and the top-level closure packet.

Convention: every collection-typed field declared as ``tuple`` is
materialized as a real ``tuple`` (not a ``list``). ``dict`` fields
are used only where a name-keyed lookup is the natural shape
(artifact presence map). CSV column ordering and JSON key
ordering are sourced from explicit tuples in
``PHX2.stage20.closure.constants``, NOT from the NamedTuple field
ordering, so model field additions never accidentally change an
on-disk schema.

Boundary discipline: this module imports nothing from
``PHX2.stage20`` outside of stdlib typing primitives. Stage 20.4
model declarations are intentionally self-contained.

Phoenix1 departure note: zero Phoenix1 imports or references.

What Stage 20.4 will NOT do (relevant to this module):
  * No alternate model classes beyond those locked below.
  * No runtime mutation of tuples; collections are immutable by
    construction.
  * No re-export of upstream Stage 20.1 / 20.2 / 20.3 models.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Operator-supplied input config
# ---------------------------------------------------------------------------


class OperatorTestResults(NamedTuple):
    """Operator-supplied pytest result snapshot for two runs.

    The operator runs the Stage 20 suite twice (determinism / flake
    guard) and supplies both result blocks in the JSON config.
    Closure validates consistency only; it does NOT run pytest.

    Derived fields ``both_runs_match`` and ``all_green`` are
    populated by ``input_loader`` after the seven numeric/string
    fields are validated.
    """

    test_command: str
    run1_passed: int
    run1_failed: int
    run1_errors: int
    run2_passed: int
    run2_failed: int
    run2_errors: int
    both_runs_match: bool
    all_green: bool


class ClosureInputConfig(NamedTuple):
    """Validated Stage 20.4 input configuration.

    Source: JSON config file supplied on the orchestrator CLI.
    All path fields are absolute (resolved by ``input_loader``).
    ``generated_at_utc`` is captured from the injected clock
    helper at orchestrator entry and embeds in run_id derivation
    + every output artifact's timestamps.
    """

    stage20_1_commit_sha: str
    stage20_2_commit_sha: str
    stage20_3_commit_sha: str
    stage20_2_run_dir: Path
    stage20_3_run_dir: Path
    repo_root: Path
    output_root: Path
    operator_test_results: OperatorTestResults
    generated_at_utc: str


# ---------------------------------------------------------------------------
# Audit / validation record shapes
# ---------------------------------------------------------------------------


class ArtifactHash(NamedTuple):
    """One artifact file's recorded hash record.

    ``relative_path`` is relative to the run directory the
    artifact lives in (stage20_2_run_dir or stage20_3_run_dir).
    """

    relative_path: str
    sha256: str
    bytes: int


class ImportHit(NamedTuple):
    """One forbidden-import (or env-read) record.

    ``module`` carries the offending dotted module name; ``reason``
    is a short, machine-readable category string
    (e.g. ``"network_client"``, ``"env_read"``, ``"subprocess"``,
    ``"sqlite"``, ``"git"``, ``"phoenix1"``, ``"cross_stage"``).
    """

    file: str
    line: int
    module: str
    reason: str


class TokenHit(NamedTuple):
    """One forbidden- or warning-token record (regex source scan).

    ``severity`` is one of ``"error"`` (blocking, E2040) or
    ``"warning"`` (informational, W2025).
    """

    file: str
    line: int
    token: str
    context: str
    severity: str


class CodebaseAuditResult(NamedTuple):
    """Aggregate result of the codebase auditor.

    Every collection field is a ``tuple`` (not ``list``).
    ``passed`` is False if ANY of the error-class collections
    is non-empty. ``warning_token_hits`` does NOT affect
    ``passed``.
    """

    inner_files_scanned: tuple
    outer_files_scanned: tuple
    forbidden_network_imports: tuple
    forbidden_phoenix1_imports: tuple
    cross_stage_violations: tuple
    env_reads_in_closure: tuple
    subprocess_uses_in_closure: tuple
    sqlite_imports_in_closure: tuple
    blocking_token_hits: tuple
    warning_token_hits: tuple
    passed: bool


class ArtifactValidationResult(NamedTuple):
    """Aggregate result of the Stage 20.2 + Stage 20.3 artifact validator.

    ``passed`` is False if any required artifact check failed
    (missing artifact, malformed manifest, unsafe-flag mismatch,
    non-empty filter CSV beyond the header, or lineage hash
    mismatch). Warnings (e.g. missing READMEs) do not flip
    ``passed`` to False.

    The two ``_artifacts_present`` dicts are filename -> bool maps
    enumerating presence of each expected required + optional
    artifact in the respective run directory.
    """

    stage20_2_manifest_valid: bool
    stage20_2_artifacts_present: dict
    stage20_2_artifact_hashes: tuple
    stage20_2_safe_for_live_dispatch_false: bool
    stage20_3_manifest_valid: bool
    stage20_3_artifacts_present: dict
    stage20_3_artifact_hashes: tuple
    stage20_3_safe_for_live_dispatch_false: bool
    stage20_3_live_dispatch_ready_false: bool
    stage20_3_filter_registry_empty: bool
    stage20_3_filter_results_empty: bool
    lineage_crosscheck_passed: bool
    passed: bool


# ---------------------------------------------------------------------------
# Checklist row + top-level closure packet
# ---------------------------------------------------------------------------


class ChecklistItem(NamedTuple):
    """One row of stage20_closure_checklist.csv.

    ``code``     -- ``"C20_4_NN"`` per the locked checklist row order.
    ``status``   -- one of ``"pass" | "fail" | "warning" | "n/a"``.
    ``severity`` -- one of ``"error" | "warning" | "info"``.

    The CSV column order is independent of this field order; see
    ``PHX2.stage20.closure.constants.CHECKLIST_CSV_COLUMNS``.
    """

    code: str
    description: str
    status: str
    detail: str
    severity: str


class ClosurePacket(NamedTuple):
    """Top-level Stage 20.4 closure record (in-memory shape).

    Serialized to ``stage20_closure_manifest.json`` (and projected
    into the rest of the 8-artifact set) by ``closure_writer``.

    ``closure_status`` accepts only ``"closed_pending_operator_review"``
    or ``"closure_blocked"`` (closed set; see
    ``CLOSURE_STATUS_VALUES``).

    ``safe_for_live_dispatch`` and ``live_dispatch_ready`` are
    hardcoded read-only mirrors of the constants of the same name
    in ``PHX2.stage20.closure.constants``; they are always False.

    ``handoff_contract_version`` is the locked
    ``HANDOFF_CONTRACT_VERSION`` string and appears in both the
    closure manifest and the rendered handoff doc.
    """

    inputs: ClosureInputConfig
    codebase_audit: CodebaseAuditResult
    artifact_validation: ArtifactValidationResult
    checklist: tuple
    warnings: tuple
    errors: tuple
    safe_for_live_dispatch: bool
    live_dispatch_ready: bool
    handoff_contract_version: str
    closure_status: str
    run_id: str


__all__ = [
    "ArtifactHash",
    "ArtifactValidationResult",
    "ChecklistItem",
    "ClosureInputConfig",
    "ClosurePacket",
    "CodebaseAuditResult",
    "ImportHit",
    "OperatorTestResults",
    "TokenHit",
]
