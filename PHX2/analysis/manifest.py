"""Stage 12 manifest builder.

The manifest is the authoritative description of one run: parameters,
counts, censoring rule, primitives analyzed, output schemas, git
fingerprint, environment, and the standing research-only warning. It is
serialized via ``writers.write_manifest`` with ``indent=2,
sort_keys=True`` so that reruns with the same inputs produce
byte-identical files (TEST 9).

Construction is explicit (register/set methods) rather than implicit
from a dataclass so that under-populated runs (empty substrate, no
primitives) still emit a complete manifest with the missing fields as
empty dicts or null values.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


STAGE_NAME = "decision_outcome_analysis"
STAGE_VERSION = "12.v0"
SCHEMA_VERSION = "1"

RESEARCH_ONLY_WARNING = (
    "RESEARCH ONLY. Stage 12 produces exploratory cohort summaries from "
    "alert_decisions, filter_evaluations, decision_score_features, and "
    "outcome_windows. It runs no significance tests, produces no scores, "
    "and influences no policy. Effect sizes are not corrected for multiple "
    "comparisons; small-N cohorts (n_complete < 10) are flagged "
    "low_confidence. Treat all rates as observational, hypothesis-"
    "generating signals -- not decision inputs."
)


CENSORING_RULE = (
    "Per-window completeness is derived from the Stage 9 outcome_windows "
    "schema. For each (alert_decision_id, window_seconds) pair a window "
    "is COMPLETE iff a row exists with data_status='COMPLETE'; CENSORED "
    "iff a row exists with data_status != 'COMPLETE'; NO_OUTCOME iff no "
    "row exists for that window. For the primary 24h outcome "
    "(window_seconds=86400) the long CSV emits per-row flags "
    "has_outcome_window_24h, outcome_censored_24h, no_outcome_24h, and "
    "has_primary_outcome; has_primary_outcome is True iff the 24h "
    "window is COMPLETE. Both censored and no_outcome decisions are "
    "excluded from the hit_2x_within_24h rate denominator (n_complete). "
    "The cohort tables emit n_complete, n_censored, and n_no_outcome as "
    "three mutually-exclusive, collectively-exhaustive counts whose sum "
    "equals n_decisions."
)


@dataclass
class _PrimitiveAnalysis:
    method: str
    skipped: bool
    skip_reason: str | None
    edges: list[float] | None
    buckets: list[dict[str, Any]]
    distinct_value_count: int


@dataclass
class _OutputDescriptor:
    filename: str
    schema: list[str]
    row_count: int


@dataclass
class ManifestBuilder:
    """Mutable builder for the Stage 12 run manifest.

    Fields are populated incrementally as the pipeline progresses; the
    final ``to_dict`` call produces the JSON-serializable shape.
    """

    run_id: str
    created_at: datetime
    stage: str = STAGE_NAME
    stage_version: str = STAGE_VERSION
    schema_version: str = SCHEMA_VERSION
    research_only_warning: str = RESEARCH_ONLY_WARNING
    censoring_rule: str = CENSORING_RULE
    parameters: dict[str, Any] = field(default_factory=dict)
    pre_join_row_counts: dict[str, int] = field(default_factory=dict)
    post_join_row_counts: dict[str, int] = field(default_factory=dict)
    primitives_analyzed: dict[str, _PrimitiveAnalysis] = field(default_factory=dict)
    primitives_skipped: dict[str, dict[str, Any]] = field(default_factory=dict)
    outputs: dict[str, _OutputDescriptor] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    git_commit: str | None = None
    git_dirty: bool | None = None

    # ---------- registration helpers (explicit, per spec §6.2) ----------

    def set_parameter(self, key: str, value: Any) -> None:
        self.parameters[key] = value

    def set_pre_join_count(self, table: str, n: int) -> None:
        self.pre_join_row_counts[table] = int(n)

    def set_post_join_count(self, key: str, n: int) -> None:
        self.post_join_row_counts[key] = int(n)

    def register_primitive(
        self,
        name: str,
        *,
        method: str,
        skipped: bool,
        skip_reason: str | None,
        edges: tuple[float, float, float] | None,
        buckets: list[dict[str, Any]],
        distinct_value_count: int,
    ) -> None:
        if skipped:
            self.primitives_skipped[name] = {
                "method": method,
                "skip_reason": skip_reason,
                "distinct_value_count": distinct_value_count,
            }
            return
        self.primitives_analyzed[name] = _PrimitiveAnalysis(
            method=method,
            skipped=False,
            skip_reason=None,
            edges=list(edges) if edges is not None else None,
            buckets=buckets,
            distinct_value_count=distinct_value_count,
        )

    def register_output(
        self,
        key: str,
        *,
        filename: str,
        schema: list[str],
        row_count: int,
    ) -> None:
        self.outputs[key] = _OutputDescriptor(
            filename=filename,
            schema=list(schema),
            row_count=int(row_count),
        )

    def capture_environment(self) -> None:
        self.environment = {
            "python_version": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
        }

    def set_git_fingerprint(
        self, commit: str | None, dirty: bool | None
    ) -> None:
        """Record the git fingerprint values produced by the CLI.

        The values are captured by the CLI via subprocess (an
        environmental I/O side-effect) and passed in through RunParams;
        this setter is a pure store. The orchestrator's run(...) stays
        free of subprocess invocations per spec §6.2 (m-3 remediation).
        """

        self.git_commit = commit if commit else None
        self.git_dirty = dirty

    # ---------- serialization ----------

    def _primitives_analyzed_dict(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name, info in self.primitives_analyzed.items():
            out[name] = {
                "method": info.method,
                "skipped": info.skipped,
                "skip_reason": info.skip_reason,
                "edges": info.edges,
                "buckets": info.buckets,
                "distinct_value_count": info.distinct_value_count,
            }
        return out

    def _outputs_dict(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key, desc in self.outputs.items():
            out[key] = {
                "filename": desc.filename,
                "schema": desc.schema,
                "row_count": desc.row_count,
            }
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "stage_version": self.stage_version,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at": _iso(self.created_at),
            "research_only_warning": self.research_only_warning,
            "censoring_rule": self.censoring_rule,
            "parameters": self.parameters,
            "pre_join_row_counts": self.pre_join_row_counts,
            "post_join_row_counts": self.post_join_row_counts,
            "primitives_analyzed": self._primitives_analyzed_dict(),
            "primitives_skipped": self.primitives_skipped,
            "outputs": self._outputs_dict(),
            "environment": self.environment,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
        }


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()
