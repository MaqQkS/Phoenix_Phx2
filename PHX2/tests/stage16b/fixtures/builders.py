"""Stage 16B test fixture builders.

Reuse strategy:

  * The canonical ``INSERT INTO alert_decisions`` and ``INSERT INTO
    filter_evaluations`` SQL lives in
    ``PHX2.tests.fixtures.analysis_fixture_builder``
    (``insert_alert_decision`` and ``insert_filter_evaluation``). Stage
    16B's thin wrappers below pin Stage-16B-relevant defaults (WOULD_ALERT
    posture; Stage 16A canonical filter identity columns) but never
    duplicate the underlying INSERT SQL.
  * ``stage16b_phx2_connection`` opens a raw ``sqlite3.Connection`` with
    ``row_factory = sqlite3.Row`` and applies the Stage 16B migration
    chain. It deliberately does NOT use
    ``PHX2.db.connection.get_phx2_connection`` -- the audit found that
    ``PHX2.db.connection`` and ``PHX2.db.repositories`` transitively
    load ``PHX2.config.settings`` and ``PHX2.models.enums``, widening
    Stage 16B's sidecar boundary. Test fixtures follow the same posture
    so they exercise the same code paths Stage 16B production uses.
  * Observer test wiring helpers (``make_observer``, ``StubPolicyLoader``)
    are kept here so each of the five observer test files
    (matching/idempotency/non_mutation/uses_stage16a_evaluator/partial_crash)
    shares one wiring surface.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Iterator, Optional

from PHX2.db.migrations import apply_stage16b_schema
from PHX2.stage16a.models import LoadedObserveOnlyPolicy, LoadedRule
from PHX2.stage16a.observe_only_policy_evaluator import ObserveOnlyPolicyEvaluator
from PHX2.stage16b.decision_context_assembler import DecisionContextAssembler
from PHX2.stage16b.observer import ObserveOnlyObserverService
from PHX2.stage16b.repository import ObserveOnlyEvaluationRepository
from PHX2.tests.fixtures.analysis_fixture_builder import (
    insert_alert_decision,
    insert_filter_evaluation,
)


# ---------------------------------------------------------------------------
# DB / connection helpers
# ---------------------------------------------------------------------------


def make_stage16b_db_path(base: Path) -> Path:
    """Return a fresh, never-yet-existing ``.db`` path under ``base``.

    Used with pytest's ``tmp_path`` fixture so each test gets a unique
    file. The path is not created here -- the caller's connection helper
    does that on first connect.
    """

    return base / f"stage16b_{uuid.uuid4().hex}.db"


@contextmanager
def stage16b_phx2_connection(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a Stage 16B-schema ``sqlite3.Connection`` at ``path``.

    Applies the full migration chain (Stage 4 -> 11 -> 16B). The yielded
    connection is a raw ``sqlite3.Connection`` (not a PHX2Connection
    wrapper) with ``row_factory = sqlite3.Row`` set so the migration
    chain's ``PRAGMA table_info`` queries and Stage 16B's own
    column-name accessors work uniformly.

    The function name is kept as ``stage16b_phx2_connection`` for
    backwards compatibility with existing Stage 16B tests; only the
    underlying connection wrapper has changed (from ``PHX2Connection``
    to raw ``sqlite3.Connection``) to honor the audit's HIGH-finding
    boundary requirement.
    """

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        apply_stage16b_schema(connection)
        yield connection
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Canonical Stage 16A rule fixtures used across observer test files
# ---------------------------------------------------------------------------


DEFAULT_POLICY_HASH: str = "sha256:" + "9" * 64
ALT_POLICY_HASH: str = "sha256:" + "e" * 64


def _make_loaded_rule(
    *,
    rule_id: str,
    tier_scope: str,
    filter_label: str,
    filter_name: str = "fee_gate",
    filter_version: str = "fee_gate_v1_no_bribes",
    threshold_version: str = "thresholds_v0_observe_only",
) -> LoadedRule:
    return LoadedRule(
        rule_id=rule_id,
        tier_scope=tier_scope,
        filter_name=filter_name,
        filter_version=filter_version,
        filter_label=filter_label,
        threshold_version=threshold_version,
    )


DEFAULT_RULE_T2_SCAM: LoadedRule = _make_loaded_rule(
    rule_id="rule_t2_fee_gate_scam_likely",
    tier_scope="T2",
    filter_label="SCAM_LIKELY",
)


DEFAULT_RULE_T1_NORMAL: LoadedRule = _make_loaded_rule(
    rule_id="rule_t1_fee_gate_normal",
    tier_scope="T1",
    filter_label="NORMAL",
)


def make_loaded_policy(
    *rules: LoadedRule,
    policy_hash: str = DEFAULT_POLICY_HASH,
) -> LoadedObserveOnlyPolicy:
    """Build a LoadedObserveOnlyPolicy directly, bypassing the on-disk artifact.

    Used by Phase 6 unit tests so test setup does not depend on a real
    Stage 16A runtime artifact file. Phase 9's end-to-end test does use
    the real artifact pipeline via Stage 16A's
    ``make_runtime_artifact_path`` helper.
    """

    return LoadedObserveOnlyPolicy(
        schema_version="observe_only_runtime_policy_v0",
        policy_hash=policy_hash,
        generated_at_utc="2026-05-13T12:00:00+00:00",
        git_commit="cafebabecafebabecafebabecafebabecafebabe",
        rules=rules,
        lineage=MappingProxyType({}),
    )


class StubPolicyLoader:
    """Test stub: returns a pre-built LoadedObserveOnlyPolicy on every load().

    Used by Phase 6 unit tests so each test can pin the policy shape
    without producing a real Stage 16A artifact file. The
    ``runtime_policy_path`` argument is ignored.
    """

    def __init__(self, policy: LoadedObserveOnlyPolicy) -> None:
        self._policy = policy

    def load(self, runtime_policy_path: Path) -> LoadedObserveOnlyPolicy:
        return self._policy


# ---------------------------------------------------------------------------
# alert_decisions + filter_evaluations Stage 16B-shaped wrappers
# ---------------------------------------------------------------------------


_DEFAULT_DECISION_TIME = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
_DEFAULT_AS_OF_TIME = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)


def insert_would_alert_decision(
    connection,
    *,
    decision_id: int,
    tier_name: Optional[str] = "T1",
    token_address: str = "tok",
) -> None:
    """Insert one WOULD_ALERT alert_decisions row with Stage 16B-relevant defaults.

    Delegates to ``PHX2.tests.fixtures.analysis_fixture_builder.insert_alert_decision``
    (no SQL duplication).
    """

    insert_alert_decision(
        connection,
        decision_id=decision_id,
        token_address=token_address,
        evaluated_at=_DEFAULT_DECISION_TIME,
        decision_type="would_alert",
        would_alert=True,
        tier_name=tier_name,
    )


def insert_canonical_filter_evaluation(
    connection,
    *,
    fe_id: int,
    alert_decision_id: int,
    label: str = "NORMAL",
    filter_name: str = "fee_gate",
    filter_version: str = "fee_gate_v1_no_bribes",
    threshold_version: str = "thresholds_v0_observe_only",
    token_address: str = "tok",
) -> None:
    """Insert one filter_evaluations row whose identity matches a canonical Stage 16A rule.

    The defaults align with ``DEFAULT_RULE_T2_SCAM`` and
    ``DEFAULT_RULE_T1_NORMAL`` so the caller only needs to vary the
    label (and tier_name on the corresponding alert_decision) to
    exercise matched / not_matched / unevaluable paths.

    Delegates to ``PHX2.tests.fixtures.analysis_fixture_builder.insert_filter_evaluation``
    (no SQL duplication).
    """

    insert_filter_evaluation(
        connection,
        filter_evaluation_id=fe_id,
        alert_decision_id=alert_decision_id,
        token_address=token_address,
        as_of_time=_DEFAULT_AS_OF_TIME,
        filter_name=filter_name,
        filter_version=filter_version,
        threshold_version=threshold_version,
        label=label,
    )


# ---------------------------------------------------------------------------
# Observer wiring helper
# ---------------------------------------------------------------------------


def _default_fixed_clock() -> str:
    return "2026-05-13T12:00:00+00:00"


def make_observer(
    connection,
    *,
    policy_loader,
    evaluator_factory=None,
    clock: Optional[Callable[[], str]] = None,
    repository: Optional[ObserveOnlyEvaluationRepository] = None,
    assembler: Optional[DecisionContextAssembler] = None,
) -> ObserveOnlyObserverService:
    """Wire a Stage 16B observer with sensible test defaults.

    Real Stage 16A evaluator factory and Stage 16B assembler/repository
    are the defaults; tests pass a ``policy_loader`` (typically a
    ``StubPolicyLoader``) and override ``evaluator_factory`` /
    ``repository`` / ``clock`` only when targeting a specific behavior
    (e.g., evaluator monkeypatch, partial-crash wrapper).
    """

    return ObserveOnlyObserverService(
        policy_loader=policy_loader,
        evaluator_factory=evaluator_factory or ObserveOnlyPolicyEvaluator,
        assembler=assembler or DecisionContextAssembler(connection),
        repository=repository or ObserveOnlyEvaluationRepository(connection),
        clock=clock or _default_fixed_clock,
    )
