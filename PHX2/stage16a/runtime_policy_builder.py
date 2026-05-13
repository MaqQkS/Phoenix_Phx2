"""Builds the Stage 16A observe_only_runtime_policy.json body from a validated Stage 15 approved draft.

The builder takes a ``Stage15ApprovedDraft`` (already validated by the
Stage 15 loader) plus the run-time clock + git commit, and emits a dict
shaped for canonical JSON serialization. The runtime artifact's
``policy_hash`` is computed over the body sans the ``policy_hash`` field
itself, in compact canonical form. A defensive B01 re-check runs the
output's ``safety_surface`` block through ``assert_exact_match`` against
``EXPECTED_RUNTIME_SAFETY_SURFACE`` so a regression in this module surfaces
as a hard failure rather than a silently-unsafe artifact.

Per Step 0 locked remediation #2, ``direction`` and ``policy_surface`` are
NOT carried in either the input or output predicate -- there is nothing to
trim, and there is no build-time check that reads those keys from the
Stage 15 draft.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.hashing import sha256_canonical_dict
from PHX2.stage16a.safety import (
    EXPECTED_RUNTIME_SAFETY_SURFACE,
    assert_exact_match,
)
from PHX2.stage16a.stage15_loader import Stage15ApprovedDraft


RUNTIME_SCHEMA_VERSION = "observe_only_runtime_policy_v0"


# Lineage fields the Stage 15 manifest carries. The Stage 16A runtime
# artifact passes each one through verbatim plus three Stage-15-level
# identity fields (run path, manifest hash, draft hash).
STAGE15_LINEAGE_PASSTHROUGH_FIELDS: tuple[str, ...] = (
    "source_stage14_manifest_hash",
    "source_stage14_rules_hash",
    "source_stage14_impact_csv_hash",
    "source_stage13_manifest_hash",
    "source_stage12_manifest_hash",
    "source_operator_review_hash",
    "source_stage14_run_path",
    "source_stage14_run_id",
    "source_stage14_schema_version",
    "source_stage13_schema_version",
    "source_operator_review_path",
    "reviewer",
)


def _to_json_ready(value: Any) -> Any:
    """Recursively convert MappingProxyType + tuples to dict + list so the
    output dict can be passed straight to ``json.dumps``."""

    if isinstance(value, Mapping):
        return {k: _to_json_ready(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_to_json_ready(v) for v in value]
    return value


class RuntimePolicyBuilder:
    """Composes the observe-only runtime policy payload (safety surface, rules, lineage, policy_hash) from a loaded Stage 15 draft.

    Construction injects the clock and git_commit so two callers passing
    the same inputs produce byte-identical output (verified by the
    Phase 9 determinism test).
    """

    def build(
        self,
        draft: Stage15ApprovedDraft,
        *,
        now_utc: datetime,
        git_commit: str,
    ) -> dict[str, Any]:
        if not git_commit or not git_commit.strip():
            raise ValueError("git_commit must be a non-empty string")

        # 1. Safety surface (defensive re-check happens at end).
        safety_surface = self._compose_safety_surface()

        # 2. Per-rule projection: 5-key predicate plus the operator-review
        #    metadata Stage 16A wants to carry forward.
        rules_out: list[dict[str, Any]] = []
        for rule in draft.draft["rules"]:
            predicate = rule["predicate"]
            rules_out.append({
                "rule_id": rule["rule_id"],
                "predicate": {
                    "tier_scope": predicate["tier_scope"],
                    "filter_name": predicate["filter_name"],
                    "filter_version": predicate["filter_version"],
                    "filter_label": predicate["filter_label"],
                    "threshold_version": predicate["threshold_version"],
                },
                "intended_action": "LOG_WOULD_BLOCK",
                "hard_block_allowed": False,
                "source_stage14_rule_hash": rule["source_stage14_rule_hash"],
                "operator_reason": rule.get("operator_reason", ""),
                "reviewed_at_utc": rule.get("reviewed_at_utc", ""),
            })

        # 3. Lineage block: Stage 15 manifest fields plus Stage-15-level
        #    identity (run path + file hashes).
        lineage: dict[str, Any] = {
            "source_stage15_run_path": str(draft.run_path.resolve()),
            "source_stage15_manifest_hash": draft.manifest_hash,
            "source_stage15_policy_draft_hash": draft.draft_hash,
        }
        for fld in STAGE15_LINEAGE_PASSTHROUGH_FIELDS:
            lineage[fld] = draft.manifest.get(fld, "")

        # 4. Body sans policy_hash (hashed below).
        body: dict[str, Any] = {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "rule_count": len(rules_out),
            "generated_at_utc": now_utc.astimezone(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "safety_surface": safety_surface,
            "lineage": lineage,
            "rules": rules_out,
        }

        # 5. policy_hash over canonical JSON of body sans policy_hash.
        body["policy_hash"] = sha256_canonical_dict(body)

        # 6. Defensive B01 re-check. If a regression in this builder ever
        #    produces a drifted safety surface, fail loudly rather than
        #    emit an unsafe artifact.
        assert_exact_match(
            EXPECTED_RUNTIME_SAFETY_SURFACE,
            body["safety_surface"],
            code="B01",
            context="runtime safety_surface (post-build defensive check)",
        )

        return body

    def _compose_safety_surface(self) -> dict[str, Any]:
        """Emit the runtime safety_surface block in JSON-ready form.

        Carved out as a method so Phase 5 tests can monkeypatch it to
        produce a drifted surface and exercise the B01 defensive check.
        """

        return _to_json_ready(EXPECTED_RUNTIME_SAFETY_SURFACE)
