"""Validates and loads an observe_only_runtime_policy.json artifact against the R01-R08 runtime-load invariants.

R-codes are checked in declared order; first failure raises ``Stage16AError``
with the specific code. The loader does NOT cache: every call re-reads the
file and re-runs every check, so a stale or tampered artifact never escapes
the check pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.hashing import sha256_canonical_dict
from PHX2.stage16a.models import LoadedObserveOnlyPolicy, LoadedRule
from PHX2.stage16a.safety import (
    ALLOWED_FILTER_LABELS,
    ALLOWED_TIER_SCOPES,
    EXPECTED_RUNTIME_SAFETY_SURFACE,
    REQUIRED_PREDICATE_KEYS_RUNTIME,
    assert_exact_match,
)


RUNTIME_SCHEMA_VERSION = "observe_only_runtime_policy_v0"


# Lineage hash fields R05 demands as non-empty strings. The Stage 16A
# runtime artifact's lineage block carries other passthrough fields too
# (paths, version markers, reviewer); those are passed through but not
# subject to R05's non-empty check, since some are legitimately empty
# strings in synthetic fixtures (e.g. ``source_stage14_run_path`` of an
# orphan draft).
REQUIRED_LINEAGE_HEX_FIELDS: tuple[str, ...] = (
    "source_stage15_manifest_hash",
    "source_stage15_policy_draft_hash",
    "source_stage14_manifest_hash",
    "source_stage14_rules_hash",
    "source_stage14_impact_csv_hash",
    "source_stage13_manifest_hash",
    "source_stage12_manifest_hash",
    "source_operator_review_hash",
)


class ObserveOnlyPolicyLoader:
    """Re-reads and re-validates the runtime artifact on every call; never caches, never mutates global state.

    The loader is intended to be cheap to construct and safe to instantiate
    repeatedly. The returned ``LoadedObserveOnlyPolicy`` is fully frozen,
    so downstream evaluators cannot mutate it.
    """

    def load(self, runtime_policy_path: Path) -> LoadedObserveOnlyPolicy:
        # R01: file exists and parses as JSON.
        if not runtime_policy_path.is_file():
            raise Stage16AError(
                "R01",
                f"{runtime_policy_path} does not exist or is not a file",
            )
        try:
            text = runtime_policy_path.read_text(encoding="utf-8")
            body = json.loads(text)
        except (OSError, json.JSONDecodeError) as exc:
            raise Stage16AError("R01", f"{runtime_policy_path}: {exc}") from exc
        if not isinstance(body, dict):
            raise Stage16AError(
                "R01",
                f"{runtime_policy_path}: top-level JSON is not an object",
            )

        # R02
        if body.get("schema_version") != RUNTIME_SCHEMA_VERSION:
            raise Stage16AError(
                "R02",
                f"got {body.get('schema_version')!r}",
            )

        # R03: safety_surface exact-match (no extras, no missing).
        safety_surface = body.get("safety_surface")
        if not isinstance(safety_surface, dict):
            raise Stage16AError(
                "R03",
                f"safety_surface missing or not a dict; got {type(safety_surface).__name__}",
            )
        assert_exact_match(
            EXPECTED_RUNTIME_SAFETY_SURFACE,
            safety_surface,
            code="R03",
            context="runtime safety_surface",
        )

        # R04: policy_hash exists, non-empty, and matches canonical hash of
        # the body sans policy_hash itself.
        stored_hash = body.get("policy_hash")
        if not isinstance(stored_hash, str) or not stored_hash.strip():
            raise Stage16AError(
                "R04",
                "policy_hash is missing or empty",
            )
        body_sans_hash = {k: v for k, v in body.items() if k != "policy_hash"}
        computed = sha256_canonical_dict(body_sans_hash)
        if computed != stored_hash:
            raise Stage16AError(
                "R04",
                f"computed={computed} stored={stored_hash}",
            )

        # R05: lineage hex fields present and non-empty.
        lineage = body.get("lineage")
        if not isinstance(lineage, dict):
            raise Stage16AError(
                "R05",
                f"lineage missing or not a dict; got {type(lineage).__name__}",
            )
        bad_hex: list[str] = []
        for fld in REQUIRED_LINEAGE_HEX_FIELDS:
            v = lineage.get(fld)
            if not isinstance(v, str) or not v.strip():
                bad_hex.append(fld)
        if bad_hex:
            raise Stage16AError("R05", f"missing/empty: {sorted(bad_hex)!r}")

        # R06: rules is a list; each rule is well-shaped.
        rules = body.get("rules")
        if not isinstance(rules, list):
            raise Stage16AError(
                "R06",
                f"rules is {type(rules).__name__}, expected list",
            )
        for index, rule in enumerate(rules):
            self._validate_rule_shape(rule, index)
            self._validate_rule_predicate_values(rule, index)

        # R08: no duplicate rule_id; no duplicate predicate 5-tuple.
        rule_ids = [r["rule_id"] for r in rules]
        if len(rule_ids) != len(set(rule_ids)):
            seen: set[str] = set()
            dupes: list[str] = []
            for rid in rule_ids:
                if rid in seen and rid not in dupes:
                    dupes.append(rid)
                seen.add(rid)
            raise Stage16AError("R08", f"duplicate rule_ids: {dupes!r}")
        seen_tuples: set[tuple[str, ...]] = set()
        dupe_tuples: list[tuple[str, ...]] = []
        for r in rules:
            p = r["predicate"]
            key = (
                p["tier_scope"],
                p["filter_name"],
                p["filter_version"],
                p["filter_label"],
                p["threshold_version"],
            )
            if key in seen_tuples and key not in dupe_tuples:
                dupe_tuples.append(key)
            seen_tuples.add(key)
        if dupe_tuples:
            raise Stage16AError("R08", f"duplicate 5-tuples: {dupe_tuples!r}")

        # Build the frozen LoadedObserveOnlyPolicy.
        loaded_rules: list[LoadedRule] = []
        for r in rules:
            p = r["predicate"]
            loaded_rules.append(LoadedRule(
                rule_id=r["rule_id"],
                tier_scope=p["tier_scope"],
                filter_name=p["filter_name"],
                filter_version=p["filter_version"],
                filter_label=p["filter_label"],
                threshold_version=p["threshold_version"],
                source_stage14_rule_hash=r.get("source_stage14_rule_hash", ""),
                operator_reason=r.get("operator_reason", ""),
                reviewed_at_utc=r.get("reviewed_at_utc", ""),
            ))

        # generated_at_utc and git_commit must exist (we don't assign
        # a dedicated R code for those; R04 covers the canonical hash
        # which would fail if either was tampered with after the build).
        generated_at_utc = body.get("generated_at_utc")
        git_commit = body.get("git_commit")
        if not isinstance(generated_at_utc, str) or not generated_at_utc.strip():
            raise Stage16AError(
                "R04",
                "generated_at_utc missing or empty (would invalidate hash)",
            )
        if not isinstance(git_commit, str) or not git_commit.strip():
            raise Stage16AError(
                "R04",
                "git_commit missing or empty (would invalidate hash)",
            )

        return LoadedObserveOnlyPolicy(
            schema_version=RUNTIME_SCHEMA_VERSION,
            policy_hash=stored_hash,
            generated_at_utc=generated_at_utc,
            git_commit=git_commit,
            rules=tuple(loaded_rules),
            lineage=MappingProxyType({
                k: v for k, v in lineage.items() if isinstance(v, str)
            }),
        )

    def _validate_rule_shape(self, rule: Any, index: int) -> None:
        """R06: rule is a dict with the right per-rule fields, predicate
        has exactly the 5 runtime keys, and observe-only safety holds."""

        if not isinstance(rule, dict):
            raise Stage16AError(
                "R06",
                f"rules[{index}] is {type(rule).__name__}, expected dict",
            )

        rule_id = rule.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise Stage16AError(
                "R06",
                f"rules[{index}].rule_id missing or empty",
            )

        predicate = rule.get("predicate")
        if not isinstance(predicate, dict):
            raise Stage16AError(
                "R06",
                f"rules[{index}].predicate missing or not a dict",
            )
        actual_keys = set(predicate.keys())
        if actual_keys != set(REQUIRED_PREDICATE_KEYS_RUNTIME):
            extras = sorted(actual_keys - REQUIRED_PREDICATE_KEYS_RUNTIME)
            missing = sorted(REQUIRED_PREDICATE_KEYS_RUNTIME - actual_keys)
            detail = f"rules[{index}].predicate keys mismatch"
            if extras:
                detail += f" extras={extras!r}"
            if missing:
                detail += f" missing={missing!r}"
            raise Stage16AError("R06", detail)

        if rule.get("intended_action") != "LOG_WOULD_BLOCK":
            raise Stage16AError(
                "R06",
                f"rules[{index}].intended_action={rule.get('intended_action')!r}, "
                f"expected 'LOG_WOULD_BLOCK'",
            )

        if rule.get("hard_block_allowed") is not False:
            raise Stage16AError(
                "R06",
                f"rules[{index}].hard_block_allowed={rule.get('hard_block_allowed')!r}, "
                f"expected False",
            )

    def _validate_rule_predicate_values(self, rule: Mapping[str, Any], index: int) -> None:
        """R07: tier_scope and filter_label in the allowed sets."""

        p = rule["predicate"]
        if p["tier_scope"] not in ALLOWED_TIER_SCOPES:
            raise Stage16AError(
                "R07",
                f"rules[{index}].predicate.tier_scope={p['tier_scope']!r}",
            )
        if p["filter_label"] not in ALLOWED_FILTER_LABELS:
            raise Stage16AError(
                "R07",
                f"rules[{index}].predicate.filter_label={p['filter_label']!r}",
            )
