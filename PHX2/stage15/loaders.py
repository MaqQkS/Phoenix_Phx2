"""Stage 15 load-time validation.

Three loaders, each owning a slice of L01-L26:

  Stage14ArtifactLoader  -- Stage 14 manifest + shadow_policy_rules.json
                            (L01-L13)
  ImpactSummaryLoader    -- Stage 14 impact_summary_by_rule.csv (L26)
  OperatorReviewLoader   -- operator review CSV (L14-L23)

Plus output-dir initialization (L24) and git-commit capture (L25). Both
of those are driven by the CLI/pipeline rather than a loader class
because they have no input artifact of their own.

Stage 15's warning-flag contract is concentrated here:

  * ImpactSummaryLoader reads warning_flags directly from Stage 14's
    impact CSV. Semicolon-split, whitespace-stripped, empty segments
    dropped, names preserved verbatim. No derivation. No name
    validation. Unknown future flag names pass through.

  * Every Stage 14 rule must have exactly one matching impact CSV
    row. Missing or duplicate rows trigger L26. Extra impact rows not
    in Stage 14 rules are allowed but logged.

This module is the only place in Stage 15 that touches Stage 14's
warning-flag column. Downstream Stage 15 code receives the parsed
flags as immutable tuples.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from PHX2.stage15.errors import Stage15LoadTimeError
from PHX2.stage15.hashing import sha256_file


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_STAGE13_SCHEMA_VERSION = "1.1"
RECOGNIZED_STAGE14_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})

REQUIRED_OPERATOR_COLUMNS: tuple[str, ...] = (
    "rule_id",
    "operator_decision",
    "operator_reason",
    "reviewer",
    "reviewed_at_utc",
    "override_warning_flags",
    "notes",
)

ALLOWED_OPERATOR_DECISIONS: frozenset[str] = frozenset({
    "APPROVE_OBSERVE_ONLY",
    "REJECT",
    "HOLD",
    "NEEDS_MORE_DATA",
})

REQUIRED_OPERATOR_NON_EMPTY: tuple[str, ...] = (
    "rule_id",
    "operator_decision",
    "reviewer",
    "reviewed_at_utc",
    "override_warning_flags",
)

REQUIRED_IMPACT_COLUMNS: frozenset[str] = frozenset({"rule_id", "warning_flags"})

# Wall-clock tolerance for future-dated reviewed_at_utc timestamps. The
# spec allows up to +1 hour ahead of now (clock skew between operator and
# Stage 15 host); anything more triggers L20.
FUTURE_TIMESTAMP_TOLERANCE = timedelta(hours=1)

STAGE14_MANIFEST_FILENAME = "manifest.json"
STAGE14_RULES_FILENAME = "shadow_policy_rules.json"
STAGE14_IMPACT_FILENAME = "impact_summary_by_rule.csv"

WARNING_FLAG_SOURCE = "stage14_impact_csv"


# ---------------------------------------------------------------------------
# Loaded-artifact dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage14Rule:
    """One rule loaded from shadow_policy_rules.json.

    The predicate dict captures the identity tuple (tier_scope,
    filter_name, filter_version, filter_label, threshold_version) used
    for Stage 16 wiring. ``simulated_action`` is the Stage 14 action.
    ``raw`` carries the original rule dict for hash-stable per-rule
    hashing in writer.py if a Stage 14 schema ever exposes one.
    """

    rule_id: str
    predicate: Mapping[str, Any]
    simulated_action: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class Stage14Artifact:
    """Loaded Stage 14 run directory.

    Carries the resolved paths, content hashes, parsed manifest, and the
    ordered tuple of Stage 14 rules. Hash format is ``"sha256:<hex>"``
    to match Stage 14's own manifest hash format.

    ``stage13_manifest_hash`` is the chain reference Stage 14 records
    when it consumes a Stage 13 run. Stage 15 propagates it to its own
    outputs so reviewers can audit the Stage 13 -> Stage 14 -> Stage 15
    hash chain end-to-end without re-reading the Stage 14 manifest.
    """

    run_path: Path
    manifest_path: Path
    rules_path: Path
    manifest: Mapping[str, Any]
    manifest_hash: str
    rules_hash: str
    rules: tuple[Stage14Rule, ...]
    stage14_run_id: str
    stage14_schema_version: str
    stage13_schema_version: str
    stage13_manifest_hash: str
    stage12_manifest_hash: str


@dataclass(frozen=True)
class ImpactSummary:
    """Loaded Stage 14 impact_summary_by_rule.csv.

    ``warning_flags_by_rule`` maps Stage 14 rule_id to the verbatim
    parsed warning_flags tuple. ``row_by_rule`` keeps the full raw row
    for markdown context. ``extra_rule_ids`` are impact CSV rule_ids
    that do not appear in shadow_policy_rules.json (allowed but logged).
    """

    path: Path
    csv_hash: str
    warning_flags_by_rule: Mapping[str, tuple[str, ...]]
    row_by_rule: Mapping[str, Mapping[str, str]]
    extra_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class OperatorRow:
    """One row from operator_rule_review.csv.

    ``source_csv_row_number`` is 1-indexed including the header row.
    Booleans and timestamps are already parsed and normalized.
    """

    rule_id: str
    operator_decision: str
    operator_reason: str
    reviewer: str
    reviewed_at_utc: datetime
    reviewed_at_utc_raw: str
    override_warning_flags: bool
    notes: str
    source_csv_row_number: int


@dataclass(frozen=True)
class OperatorReview:
    """Loaded operator review CSV."""

    path: Path
    csv_hash: str
    rows: tuple[OperatorRow, ...]


# ---------------------------------------------------------------------------
# Warning-flag parsing
# ---------------------------------------------------------------------------


def parse_warning_flags(raw: str) -> tuple[str, ...]:
    """Parse a Stage 14 warning_flags cell into a verbatim tuple.

    Rules (per Stage 15 spec):
      * split on semicolon ``;``
      * strip whitespace from each segment
      * drop empty segments
      * preserve names verbatim (no rename, no enum validation)
      * unknown future Stage 14 flag names pass through as-is

    Examples:
      "" -> ()
      "small_n_rule" -> ("small_n_rule",)
      "  small_n_rule ; high_winners_blocked_rate  "
          -> ("small_n_rule", "high_winners_blocked_rate")
    """

    if raw is None:
        return ()
    segments = []
    for piece in raw.split(";"):
        stripped = piece.strip()
        if stripped:
            segments.append(stripped)
    return tuple(segments)


# ---------------------------------------------------------------------------
# Output-dir safety (L24)
# ---------------------------------------------------------------------------


def initialize_output_dir(output_dir: Path) -> None:
    """L24: ensure --output-dir is creatable or empty.

    Behavior:
      * If the path does not exist, create it (including parents).
      * If the path exists and is empty, accept it.
      * If the path exists and is non-empty, raise L24.
      * If the path exists but is not a directory, raise L24.
      * Any OSError during creation propagates as L24 (Tier 1: the
        CLI converts this to stderr-only exit, no manifest, no log).
    """

    try:
        if output_dir.exists():
            if not output_dir.is_dir():
                raise Stage15LoadTimeError(
                    "L24",
                    f"--output-dir exists but is not a directory: "
                    f"{output_dir}",
                )
            # exists() + is_dir() -> directory; iterdir empty check
            for _ in output_dir.iterdir():
                raise Stage15LoadTimeError(
                    "L24",
                    f"--output-dir exists and is non-empty: {output_dir}",
                )
            return
        output_dir.mkdir(parents=True, exist_ok=False)
    except Stage15LoadTimeError:
        raise
    except OSError as exc:
        raise Stage15LoadTimeError(
            "L24",
            f"--output-dir could not be initialized: {output_dir} ({exc})",
        ) from exc


# ---------------------------------------------------------------------------
# Stage 14 artifact loader (L01-L13)
# ---------------------------------------------------------------------------


def load_stage14_artifact(run_path: Path) -> Stage14Artifact:
    """Load a Stage 14 run directory and validate L01-L13.

    Returns the loaded artifact with manifest hash, rules hash, and
    parsed rule list. Raises Stage15LoadTimeError on any L01-L13.

    L08 note: the spec requires Stage 14 manifest to reference Stage 13
    schema version "1.1". The current Stage 14 baseline (commit 6c11b8a)
    does not emit ``stage13_schema_version`` in its manifest; it does
    emit ``stage13_manifest_hash`` (the chain reference to Stage 13).
    Stage 14's own loader validates Stage 13 schema_version == "1.1" at
    load time, so the existence of a valid Stage 14 manifest is
    transitive proof. Stage 15 enforces L08 as:

      * stage13_manifest_hash must be a non-empty string (the chain
        reference), AND
      * if Stage 14 manifest carries ``stage13_schema_version``, it
        must equal exactly "1.1" (forward-compatible with future
        Stage 14 schemas that may surface this field).

    L10/L11 are explicitly conditional in the spec ("if Stage 14 schema
    records one"); the current Stage 14 manifest does not record a
    shadow_policy_rules.json hash, so these are skipped without error.
    """

    # L01: --stage14-run-path exists and is a directory
    if not run_path.exists():
        raise Stage15LoadTimeError(
            "L01",
            f"--stage14-run-path does not exist: {run_path}",
        )
    if not run_path.is_dir():
        raise Stage15LoadTimeError(
            "L01",
            f"--stage14-run-path is not a directory: {run_path}",
        )

    manifest_path = run_path / STAGE14_MANIFEST_FILENAME
    rules_path = run_path / STAGE14_RULES_FILENAME

    # L02: manifest.json exists
    if not manifest_path.is_file():
        raise Stage15LoadTimeError(
            "L02",
            f"Stage 14 manifest.json not found at {manifest_path}",
        )
    # L03: shadow_policy_rules.json exists
    if not rules_path.is_file():
        raise Stage15LoadTimeError(
            "L03",
            f"Stage 14 shadow_policy_rules.json not found at {rules_path}",
        )

    # L04: manifest parses as JSON
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except json.JSONDecodeError as exc:
        raise Stage15LoadTimeError(
            "L04",
            f"Stage 14 manifest.json is not valid JSON ({exc})",
        ) from exc

    if not isinstance(manifest, dict):
        raise Stage15LoadTimeError(
            "L04",
            f"Stage 14 manifest.json top-level must be a JSON object",
        )

    # L05: safe_for_live_policy_consumption=false
    safe_live = manifest.get("safe_for_live_policy_consumption")
    if safe_live is not False:
        raise Stage15LoadTimeError(
            "L05",
            f"Stage 14 manifest field 'safe_for_live_policy_consumption' "
            f"must be literal false; got {safe_live!r}",
        )

    # L06: runtime_consumable=false
    runtime_consumable = manifest.get("runtime_consumable")
    if runtime_consumable is not False:
        raise Stage15LoadTimeError(
            "L06",
            f"Stage 14 manifest field 'runtime_consumable' must be literal "
            f"false; got {runtime_consumable!r}",
        )

    # L07: recognized stage14_schema_version
    schema_version = manifest.get("stage14_schema_version")
    if schema_version not in RECOGNIZED_STAGE14_SCHEMA_VERSIONS:
        raise Stage15LoadTimeError(
            "L07",
            f"Stage 14 manifest field 'stage14_schema_version' {schema_version!r} "
            f"is not in recognized set {sorted(RECOGNIZED_STAGE14_SCHEMA_VERSIONS)!r}",
        )

    # L08: Stage 14 manifest references Stage 13 schema version "1.1".
    # See module docstring for L08 interpretation.
    stage13_manifest_hash = manifest.get("stage13_manifest_hash")
    if not isinstance(stage13_manifest_hash, str) or not stage13_manifest_hash.strip():
        raise Stage15LoadTimeError(
            "L08",
            f"Stage 14 manifest must reference Stage 13 via non-empty "
            f"'stage13_manifest_hash'; got {stage13_manifest_hash!r}",
        )
    embedded_stage13_schema = manifest.get("stage13_schema_version")
    if embedded_stage13_schema is not None and embedded_stage13_schema != EXPECTED_STAGE13_SCHEMA_VERSION:
        raise Stage15LoadTimeError(
            "L08",
            f"Stage 14 manifest 'stage13_schema_version' must equal "
            f"{EXPECTED_STAGE13_SCHEMA_VERSION!r} when present; got "
            f"{embedded_stage13_schema!r}",
        )

    # L09: non-empty Stage 12 manifest hash
    stage12_manifest_hash = manifest.get("stage12_manifest_hash")
    if not isinstance(stage12_manifest_hash, str) or not stage12_manifest_hash.strip():
        raise Stage15LoadTimeError(
            "L09",
            f"Stage 14 manifest field 'stage12_manifest_hash' must be a "
            f"non-empty string; got {stage12_manifest_hash!r}",
        )

    # Compute the rules-file hash (used for L10/L11 if applicable and
    # for source_stage14_rules_hash regardless).
    rules_hash = sha256_file(rules_path)

    # L10/L11: only if Stage 14 manifest records a rules-file hash.
    recorded_rules_hash = manifest.get("shadow_policy_rules_hash")
    if recorded_rules_hash is not None:
        if not isinstance(recorded_rules_hash, str) or not recorded_rules_hash.strip():
            raise Stage15LoadTimeError(
                "L10",
                f"Stage 14 manifest 'shadow_policy_rules_hash' must be a "
                f"non-empty string when present; got {recorded_rules_hash!r}",
            )
        if recorded_rules_hash != rules_hash:
            raise Stage15LoadTimeError(
                "L11",
                f"Computed shadow_policy_rules.json hash {rules_hash!r} "
                f"does not match manifest-recorded {recorded_rules_hash!r}",
            )

    # L12: shadow_policy_rules.json parses + has expected top-level shape
    try:
        with open(rules_path, "r", encoding="utf-8") as handle:
            rules_doc = json.load(handle)
    except json.JSONDecodeError as exc:
        raise Stage15LoadTimeError(
            "L12",
            f"shadow_policy_rules.json is not valid JSON ({exc})",
        ) from exc

    if not isinstance(rules_doc, dict) or "rules" not in rules_doc:
        raise Stage15LoadTimeError(
            "L12",
            f"shadow_policy_rules.json must be a JSON object with a 'rules' "
            f"array at the top level",
        )
    raw_rules = rules_doc.get("rules")
    if not isinstance(raw_rules, list):
        raise Stage15LoadTimeError(
            "L12",
            f"shadow_policy_rules.json 'rules' must be a JSON array",
        )

    # L13: every rule has rule_id and predicate
    rules: list[Stage14Rule] = []
    seen_ids: set[str] = set()
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise Stage15LoadTimeError(
                "L13",
                f"shadow_policy_rules.json rule at index {index} is not "
                f"a JSON object",
            )
        rule_id = raw_rule.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise Stage15LoadTimeError(
                "L13",
                f"shadow_policy_rules.json rule at index {index} has empty "
                f"or non-string rule_id",
            )
        if rule_id in seen_ids:
            raise Stage15LoadTimeError(
                "L13",
                f"shadow_policy_rules.json contains duplicate rule_id "
                f"{rule_id!r}",
            )
        seen_ids.add(rule_id)
        predicate = _extract_predicate(raw_rule)
        if not predicate:
            raise Stage15LoadTimeError(
                "L13",
                f"shadow_policy_rules.json rule {rule_id!r} is missing "
                f"predicate fields (tier_scope, filter_name, filter_version, "
                f"filter_label, threshold_version)",
            )
        simulated_action = raw_rule.get("simulated_action")
        if not isinstance(simulated_action, str) or not simulated_action.strip():
            raise Stage15LoadTimeError(
                "L13",
                f"shadow_policy_rules.json rule {rule_id!r} is missing "
                f"simulated_action",
            )
        rules.append(
            Stage14Rule(
                rule_id=rule_id,
                predicate=predicate,
                simulated_action=simulated_action,
                raw=raw_rule,
            )
        )

    manifest_hash = sha256_file(manifest_path)
    stage14_run_id = _derive_stage14_run_id(run_path, manifest)

    return Stage14Artifact(
        run_path=run_path,
        manifest_path=manifest_path,
        rules_path=rules_path,
        manifest=manifest,
        manifest_hash=manifest_hash,
        rules_hash=rules_hash,
        rules=tuple(rules),
        stage14_run_id=stage14_run_id,
        stage14_schema_version=schema_version,
        stage13_schema_version=EXPECTED_STAGE13_SCHEMA_VERSION,
        stage13_manifest_hash=stage13_manifest_hash,
        stage12_manifest_hash=stage12_manifest_hash,
    )


def _extract_predicate(raw_rule: Mapping[str, Any]) -> dict[str, str]:
    """Pull the predicate identity tuple from a raw Stage 14 rule.

    Returns an empty dict if any required field is missing or blank;
    callers raise L13 in that case. All extracted values are returned
    as strings to keep the downstream policy-draft schema stable.
    """

    fields = (
        "tier_scope",
        "filter_name",
        "filter_version",
        "filter_label",
        "threshold_version",
    )
    out: dict[str, str] = {}
    for name in fields:
        value = raw_rule.get(name)
        if not isinstance(value, str) or not value.strip():
            return {}
        out[name] = value
    return out


def _derive_stage14_run_id(run_path: Path, manifest: Mapping[str, Any]) -> str:
    """Stage 14 doesn't expose a dedicated ``run_id`` field; the dated
    directory name is the stable run identifier. Fall back to the
    run_timestamp_utc string if the directory name is empty (shouldn't
    happen for runs produced by Stage 14 itself).
    """

    name = run_path.name.strip()
    if name:
        return name
    timestamp = manifest.get("run_timestamp_utc")
    if isinstance(timestamp, str) and timestamp.strip():
        return timestamp
    return ""


# ---------------------------------------------------------------------------
# Impact summary loader (L26)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImpactJoinResult:
    """Outcome of joining impact rows to Stage 14 rules.

    ``extra_rule_ids`` are impact rows that don't match any Stage 14
    rule. They're allowed but logged. ``missing_rule_ids`` are Stage 14
    rules that have no impact row -- L26.
    """

    extra_rule_ids: tuple[str, ...]
    missing_rule_ids: tuple[str, ...]
    duplicate_rule_ids: tuple[str, ...]


def load_impact_summary(
    run_path: Path, stage14_rule_ids: tuple[str, ...]
) -> ImpactSummary:
    """L26: load and validate Stage 14 impact_summary_by_rule.csv.

    Requires:
      * file exists (L26)
      * parses as CSV with header row (L26)
      * has rule_id and warning_flags columns (L26)
      * every Stage 14 rule has exactly one matching impact row (L26)
      * no duplicate rows for any Stage 14 rule_id (L26)

    Extra impact rows whose rule_id is not in ``stage14_rule_ids`` are
    allowed and returned via ``ImpactSummary.extra_rule_ids``. They
    must not influence approval logic, so they're omitted from
    ``warning_flags_by_rule``.

    Returns the loaded ``ImpactSummary`` with the impact CSV's
    sha256 hash, the warning_flags-per-rule mapping, and the raw rows
    for markdown context.
    """

    impact_path = run_path / STAGE14_IMPACT_FILENAME

    if not impact_path.is_file():
        raise Stage15LoadTimeError(
            "L26",
            f"Stage 14 impact_summary_by_rule.csv not found at {impact_path}",
        )

    # Use csv.reader (not DictReader) so we can enforce strict row-length
    # consistency. DictReader silently fills short rows with None and
    # dumps long-row extras into a ``restkey`` bucket; neither surfaces
    # as an error. We need malformed CSV to fail L26 loudly.
    raw_rows: list[list[str]] = []
    try:
        with open(impact_path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            for raw in reader:
                raw_rows.append(raw)
    except csv.Error as exc:
        raise Stage15LoadTimeError(
            "L26",
            f"Stage 14 impact_summary_by_rule.csv could not be parsed "
            f"as CSV ({exc})",
        ) from exc

    if not raw_rows:
        raise Stage15LoadTimeError(
            "L26",
            f"Stage 14 impact_summary_by_rule.csv has no header row",
        )

    header = raw_rows[0]
    if not header:
        raise Stage15LoadTimeError(
            "L26",
            f"Stage 14 impact_summary_by_rule.csv has an empty header row",
        )

    missing = REQUIRED_IMPACT_COLUMNS - set(header)
    if missing:
        raise Stage15LoadTimeError(
            "L26",
            f"Stage 14 impact_summary_by_rule.csv missing required "
            f"columns: {sorted(missing)!r}",
        )

    rows: list[dict[str, str]] = []
    header_len = len(header)
    # csv.reader rows are 0-indexed; the first data row is at index 1
    # (after the header), which is CSV row 2 to a human reader.
    for csv_row_index, raw in enumerate(raw_rows[1:], start=2):
        if len(raw) != header_len:
            raise Stage15LoadTimeError(
                "L26",
                f"Stage 14 impact_summary_by_rule.csv row {csv_row_index} "
                f"has {len(raw)} fields, expected {header_len} "
                f"(malformed CSV)",
            )
        rows.append(dict(zip(header, raw)))

    # Index impact rows by rule_id; collect duplicates.
    impact_by_rule: dict[str, dict[str, str]] = {}
    duplicate_ids: list[str] = []
    for row in rows:
        rid = (row.get("rule_id") or "").strip()
        if not rid:
            # Blank rule_id in impact CSV is malformed.
            raise Stage15LoadTimeError(
                "L26",
                f"Stage 14 impact_summary_by_rule.csv has a row with empty "
                f"rule_id",
            )
        if rid in impact_by_rule:
            duplicate_ids.append(rid)
        else:
            impact_by_rule[rid] = row

    stage14_set = set(stage14_rule_ids)
    duplicates_for_stage14 = [d for d in duplicate_ids if d in stage14_set]
    if duplicates_for_stage14:
        raise Stage15LoadTimeError(
            "L26",
            f"Stage 14 impact_summary_by_rule.csv has duplicate rows for "
            f"Stage 14 rule_id(s): {sorted(set(duplicates_for_stage14))!r}",
        )

    missing_ids = [rid for rid in stage14_rule_ids if rid not in impact_by_rule]
    if missing_ids:
        raise Stage15LoadTimeError(
            "L26",
            f"Stage 14 impact_summary_by_rule.csv missing rows for Stage 14 "
            f"rule_id(s): {missing_ids!r}",
        )

    warning_flags: dict[str, tuple[str, ...]] = {}
    row_by_rule: dict[str, Mapping[str, str]] = {}
    for rid in stage14_rule_ids:
        row = impact_by_rule[rid]
        warning_flags[rid] = parse_warning_flags(row.get("warning_flags", ""))
        row_by_rule[rid] = row

    extra_ids = tuple(sorted(set(impact_by_rule.keys()) - stage14_set))

    csv_hash = sha256_file(impact_path)

    return ImpactSummary(
        path=impact_path,
        csv_hash=csv_hash,
        warning_flags_by_rule=warning_flags,
        row_by_rule=row_by_rule,
        extra_rule_ids=extra_ids,
    )


# ---------------------------------------------------------------------------
# Operator review loader (L14-L23)
# ---------------------------------------------------------------------------


def load_operator_review(
    operator_review_path: Path,
    *,
    reviewer_arg: str,
    stage14_rule_ids: tuple[str, ...],
    now_utc: datetime,
) -> OperatorReview:
    """Load and validate the operator review CSV (L14-L23).

    The loader is strict:

      * L14: file exists
      * L15: header row matches REQUIRED_OPERATOR_COLUMNS exactly,
             no extras
      * L16: required non-empty fields are non-empty
      * L17: operator_decision in ALLOWED_OPERATOR_DECISIONS
      * L18: override_warning_flags is a strict boolean (true/false,
             case-insensitive)
      * L19: reviewed_at_utc parses as ISO-8601 UTC
      * L20: reviewed_at_utc <= now_utc + FUTURE_TIMESTAMP_TOLERANCE
      * L21: reviewer column equals reviewer_arg exactly
      * L22: no duplicate rule_id rows
      * L23: every rule_id exists in stage14_rule_ids

    Quoted fields with commas/newlines are supported (csv module).
    BOM is handled via utf-8-sig.
    """

    # L14: file exists
    if not operator_review_path.is_file():
        raise Stage15LoadTimeError(
            "L14",
            f"--operator-review file does not exist: {operator_review_path}",
        )

    rows: list[tuple[int, dict[str, str]]] = []
    try:
        with open(
            operator_review_path, "r", encoding="utf-8-sig", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise Stage15LoadTimeError(
                    "L15",
                    f"--operator-review has no header row: "
                    f"{operator_review_path}",
                )
            # L15: exact columns, no extras
            header = list(reader.fieldnames)
            header_set = set(header)
            missing = set(REQUIRED_OPERATOR_COLUMNS) - header_set
            extras = header_set - set(REQUIRED_OPERATOR_COLUMNS)
            if missing or extras:
                raise Stage15LoadTimeError(
                    "L15",
                    f"--operator-review header mismatch: "
                    f"missing={sorted(missing)!r}, extras={sorted(extras)!r}, "
                    f"required={list(REQUIRED_OPERATOR_COLUMNS)!r}",
                )
            for raw in reader:
                # csv.DictReader sets line_num to 1-indexed CSV row #,
                # counting the header (so header = 1, first data = 2).
                rows.append((reader.line_num, dict(raw)))
    except csv.Error as exc:
        raise Stage15LoadTimeError(
            "L15",
            f"--operator-review could not be parsed as CSV ({exc})",
        ) from exc

    parsed: list[OperatorRow] = []
    seen_rule_ids: set[str] = set()
    stage14_rule_set = set(stage14_rule_ids)
    now_with_tolerance = now_utc + FUTURE_TIMESTAMP_TOLERANCE

    for source_row_num, raw in rows:
        # L16: required non-empty fields
        for field in REQUIRED_OPERATOR_NON_EMPTY:
            value = (raw.get(field) or "").strip()
            if not value:
                raise Stage15LoadTimeError(
                    "L16",
                    f"--operator-review row {source_row_num} has empty "
                    f"required field {field!r}",
                )

        rule_id = raw["rule_id"].strip()
        decision = raw["operator_decision"].strip()
        reason_raw = raw.get("operator_reason") or ""
        reviewer_raw = raw["reviewer"].strip()
        reviewed_at_raw = raw["reviewed_at_utc"].strip()
        override_raw = raw["override_warning_flags"].strip()
        notes_raw = raw.get("notes") or ""

        # L17: allowed decisions
        if decision not in ALLOWED_OPERATOR_DECISIONS:
            raise Stage15LoadTimeError(
                "L17",
                f"--operator-review row {source_row_num} operator_decision "
                f"{decision!r} not in allowed set "
                f"{sorted(ALLOWED_OPERATOR_DECISIONS)!r}",
            )

        # L18: strict boolean for override_warning_flags
        lowered = override_raw.lower()
        if lowered == "true":
            override = True
        elif lowered == "false":
            override = False
        else:
            raise Stage15LoadTimeError(
                "L18",
                f"--operator-review row {source_row_num} "
                f"override_warning_flags must be true/false (case-insensitive); "
                f"got {override_raw!r}",
            )

        # L19: reviewed_at_utc is ISO-8601 UTC
        reviewed_at = _parse_iso_utc(reviewed_at_raw)
        if reviewed_at is None:
            raise Stage15LoadTimeError(
                "L19",
                f"--operator-review row {source_row_num} reviewed_at_utc "
                f"is not valid ISO-8601 UTC: {reviewed_at_raw!r}",
            )

        # L20: future tolerance
        if reviewed_at > now_with_tolerance:
            raise Stage15LoadTimeError(
                "L20",
                f"--operator-review row {source_row_num} reviewed_at_utc "
                f"{reviewed_at_raw!r} exceeds wall-clock now by more than "
                f"{FUTURE_TIMESTAMP_TOLERANCE}",
            )

        # L21: reviewer match
        if reviewer_raw != reviewer_arg:
            raise Stage15LoadTimeError(
                "L21",
                f"--operator-review row {source_row_num} reviewer "
                f"{reviewer_raw!r} does not match --reviewer "
                f"{reviewer_arg!r}",
            )

        # L22: no duplicate rule_id
        if rule_id in seen_rule_ids:
            raise Stage15LoadTimeError(
                "L22",
                f"--operator-review has duplicate rule_id {rule_id!r} "
                f"(row {source_row_num})",
            )
        seen_rule_ids.add(rule_id)

        # L23: rule_id must exist in Stage 14
        if rule_id not in stage14_rule_set:
            raise Stage15LoadTimeError(
                "L23",
                f"--operator-review row {source_row_num} rule_id {rule_id!r} "
                f"is not in Stage 14 shadow_policy_rules.json",
            )

        parsed.append(
            OperatorRow(
                rule_id=rule_id,
                operator_decision=decision,
                operator_reason=reason_raw,
                reviewer=reviewer_raw,
                reviewed_at_utc=reviewed_at,
                reviewed_at_utc_raw=reviewed_at_raw,
                override_warning_flags=override,
                notes=notes_raw,
                source_csv_row_number=source_row_num,
            )
        )

    csv_hash = sha256_file(operator_review_path)
    return OperatorReview(
        path=operator_review_path,
        csv_hash=csv_hash,
        rows=tuple(parsed),
    )


def _parse_iso_utc(value: str) -> datetime | None:
    """Parse a strict ISO-8601 UTC timestamp.

    Accepts trailing 'Z' or '+00:00' offsets. Returns a timezone-aware
    UTC datetime, or None if the input is not a valid ISO-8601 UTC
    timestamp. Naive timestamps and non-UTC offsets are rejected.
    """

    if not value:
        return None
    normalized = value
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    utc = parsed.astimezone(timezone.utc)
    if utc.utcoffset() != timedelta(0):
        return None
    # Reject offsets that aren't UTC even after normalization. Compare
    # the parsed object's utcoffset rather than the converted one.
    if parsed.utcoffset() != timedelta(0):
        return None
    return utc
