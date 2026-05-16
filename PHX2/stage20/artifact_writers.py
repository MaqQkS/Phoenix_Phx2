"""Stage 20.2 artifact writers.

Four artifacts in one module:

  * ``write_preview_candidates_csv``           -- 18-col preview CSV
  * ``write_alert_eligibility_decisions_csv``  -- 10-col decision CSV
  * ``write_readme_md``                        -- byte-stable README
  * ``write_stage20_run_log``                  -- JSON-Lines run log

Encoding contract (locked):
  * UTF-8 only. No BOM. Line endings "\\n" everywhere.
  * CSV: ``csv.writer(f, quoting=csv.QUOTE_MINIMAL,
    lineterminator="\\n")``. Header always written -- even if data
    list is empty.
  * Sort orders (locked, deterministic):
      preview_candidates.csv          -- review_timestamp_utc ASC,
                                         candidate_id ASC
      alert_eligibility_decisions.csv -- candidate_id ASC,
                                         decision_step_index ASC
      stage20_run.log artifacts_written.detail.artifacts -- name ASC

Operator constraint A (Phase C reminder): README.md MUST NOT
contain any output SHA-256 hash values. It lists artifact names
only and includes the verbatim line
``"Output SHA-256 hashes are recorded in manifest.json."``.

Operator constraint B: artifacts_written event lists exactly the
three non-log artifacts -- preview_candidates.csv,
alert_eligibility_decisions.csv, README.md -- never
stage20_run.log itself (self-reference avoidance).

Operator constraint C: manifest_written event detail is literally
``{"path": "manifest.json", "planned": true}`` -- no manifest hash,
no manifest size, no manifest mtime, no absolute path, no extra
fields. The log is written BEFORE the manifest, so its sha256 is
recorded in the manifest without forming a cycle. This breaks
both the manifest<->log and README<->log circular hash
dependencies.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Mapping, Sequence

from PHX2.stage20.constants import (
    ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS,
    ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMN_TO_FIELD,
    PREVIEW_CANDIDATES_CSV_COLUMNS,
    PREVIEW_CANDIDATES_CSV_COLUMN_TO_FIELD,
    PREVIEW_STATE_COUNT_KEYS,
    csv_column_to_model_field,
)
from PHX2.stage20.models import DecisionStep, PreviewCandidate


# ---------------------------------------------------------------------------
# Cell formatting (centralized so both CSV writers handle bool/int
# identically)
# ---------------------------------------------------------------------------


def _format_cell(value: object) -> str:
    """Serialize a single value for CSV emission.

    bool   -> "true" | "false"
    None   -> ""
    int    -> str(value)  (NamedTuple ints emit without thousands sep)
    other  -> str(value)
    """

    # bool must be checked BEFORE int (bool is a subclass of int).
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


# ---------------------------------------------------------------------------
# preview_candidates.csv
# ---------------------------------------------------------------------------


def write_preview_candidates_csv(
    path: Path,
    candidates: Sequence[PreviewCandidate],
) -> None:
    """Write the 18-column preview_candidates.csv at ``path``.

    Header always written. Sort: review_timestamp_utc ASC,
    candidate_id ASC.
    """

    sorted_candidates = sorted(
        candidates,
        key=lambda c: (c.review_timestamp_utc, c.candidate_id),
    )

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(
            f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n",
        )
        writer.writerow(list(PREVIEW_CANDIDATES_CSV_COLUMNS))
        for c in sorted_candidates:
            writer.writerow([
                _format_cell(getattr(
                    c,
                    csv_column_to_model_field(
                        col,
                        PREVIEW_CANDIDATES_CSV_COLUMN_TO_FIELD,
                    ),
                ))
                for col in PREVIEW_CANDIDATES_CSV_COLUMNS
            ])


# ---------------------------------------------------------------------------
# alert_eligibility_decisions.csv
# ---------------------------------------------------------------------------


def write_alert_eligibility_decisions_csv(
    path: Path,
    decisions: Sequence[DecisionStep],
) -> None:
    """Write the 10-column alert_eligibility_decisions.csv at ``path``.

    Header always written. Sort: candidate_id ASC,
    decision_step_index ASC.
    """

    sorted_decisions = sorted(
        decisions,
        key=lambda d: (d.candidate_id, d.decision_step_index),
    )

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(
            f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n",
        )
        writer.writerow(list(ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS))
        for d in sorted_decisions:
            writer.writerow([
                _format_cell(getattr(
                    d,
                    csv_column_to_model_field(
                        col,
                        ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMN_TO_FIELD,
                    ),
                ))
                for col in ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS
            ])


# ---------------------------------------------------------------------------
# README.md
# ---------------------------------------------------------------------------

# Verbatim strings the test suite asserts on (operator constraints).
_SAFETY_CALLOUT_LINE = (
    "safe_for_live_dispatch: false. Stage 20 outputs are operator-"
    "historical and offline; Stage 21 owns live dispatch checks."
)
_OUTPUT_HASH_DISCLAIMER = (
    "Output SHA-256 hashes are recorded in manifest.json."
)
_STAGE21_BOUNDARY_FOOTER = (
    "Stage 21 boundary: live freshness, duplicate suppression, and "
    "dispatch readiness are not promised by Stage 20."
)

# Run-identifier rows (in this exact order). Each tuple is
# (display_label, manifest_dict_key).
_RUN_ID_ROWS: tuple[tuple[str, str], ...] = (
    ("stage20_run_id",            "stage20_run_id"),
    ("stage18_run_id",            "stage18_run_id"),
    ("stage19_run_id",            "stage19_run_id"),
    ("generated_at_utc",          "generated_at_utc"),
    ("stage20_version",           "stage20_version"),
    ("stage20_minor_version",     "stage20_minor_version"),
    ("mapping_version",           "mapping_version"),
    ("consumer_contract_version", "consumer_contract_version"),
)


def write_readme_md(
    path: Path,
    manifest_dict: Mapping[str, object],
) -> None:
    """Write README.md byte-stably from a partial manifest dict.

    ``manifest_dict`` must already contain every run-identifier
    key, ``input_hashes``, ``preview_candidates_row_count``,
    ``alert_eligibility_decisions_row_count``,
    ``preview_state_counts``, and ``warnings``. It is NOT required
    to contain output SHA-256 hashes -- README never reads them.
    """

    lines: list[str] = []

    # 1. Title
    lines.append("PHX2 Stage 20.2 — Preview Candidate Builder")
    lines.append("")

    # 2. Safety callout
    lines.append(_SAFETY_CALLOUT_LINE)
    lines.append("")

    # 3. Run identifiers
    lines.append("Run identifiers:")
    for label, key in _RUN_ID_ROWS:
        lines.append(f"  {label}: {manifest_dict[key]}")
    lines.append("")

    # 4. Input hashes (sorted by key for byte-stable order; 4 or 5)
    #
    # Asymmetry note (Codex remediation): INPUT SHA-256 values ARE
    # emitted in README; OUTPUT SHA-256 values are NOT emitted.
    # This is the locked Stage 20.2 README design for circular-hash
    # avoidance (operator constraint A). Output hashes are recorded
    # in manifest.json exclusively; the README's "Output artifacts"
    # block lists artifact names only and references manifest.json
    # via the verbatim disclaimer line. Input hashes are upstream
    # values that do not depend on any artifact written during this
    # run, so embedding them in README creates no cycle.
    lines.append("Input hashes:")
    ih = manifest_dict["input_hashes"]
    assert isinstance(ih, Mapping)
    for key in sorted(ih.keys()):
        lines.append(f"  {key}: {ih[key]}")
    lines.append("")

    # 5. Output artifacts block (name-only, plus the disclaimer)
    lines.append("Output artifacts:")
    lines.append("  - preview_candidates.csv")
    lines.append("  - alert_eligibility_decisions.csv")
    lines.append("  - README.md")
    lines.append("  - stage20_run.log")
    lines.append(_OUTPUT_HASH_DISCLAIMER)
    lines.append("")

    # 6. Counts block
    lines.append("Counts:")
    lines.append(
        f"  total candidates:    "
        f"{manifest_dict['preview_candidates_row_count']}"
    )
    lines.append(
        f"  total decision rows: "
        f"{manifest_dict['alert_eligibility_decisions_row_count']}"
    )
    psc = manifest_dict["preview_state_counts"]
    assert isinstance(psc, Mapping)
    lines.append("  per state:")
    for state_key in PREVIEW_STATE_COUNT_KEYS:
        lines.append(f"    {state_key}: {psc[state_key]}")
    lines.append("")

    # 7. Active warnings block
    warnings = manifest_dict["warnings"]
    assert isinstance(warnings, Mapping)
    active: list[tuple[str, object]] = []
    for key in sorted(warnings.keys()):
        v = warnings[key]
        if isinstance(v, bool):
            if v:
                active.append((key, v))
        elif isinstance(v, int):
            if v > 0:
                active.append((key, v))
    if active:
        lines.append("Active warnings:")
        for key, v in active:
            # bool -> "true"/"false"; int -> decimal.
            value_str = "true" if (isinstance(v, bool) and v) else (
                "false" if isinstance(v, bool) else str(v)
            )
            lines.append(f"  {key}: {value_str}")
    else:
        lines.append("Active warnings: none")
    lines.append("")

    # 8. Stage 21 boundary footer
    lines.append(_STAGE21_BOUNDARY_FOOTER)
    # Trailing newline so the file ends cleanly.
    lines.append("")

    text = "\n".join(lines)
    path.write_bytes(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# stage20_run.log  (JSON Lines)
# ---------------------------------------------------------------------------


def write_stage20_run_log(
    path: Path,
    events: Sequence[Mapping[str, object]],
) -> None:
    """Write the run log as JSON Lines (one event per line).

    Each line: ``json.dumps(event, sort_keys=True,
    separators=(",", ":"), ensure_ascii=False)`` followed by "\\n".
    UTF-8 encoded, no BOM. Trailing newline after the last line.
    """

    rendered = []
    for event in events:
        rendered.append(json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ))
    text = "\n".join(rendered) + ("\n" if rendered else "")
    path.write_bytes(text.encode("utf-8"))


__all__ = [
    "write_alert_eligibility_decisions_csv",
    "write_preview_candidates_csv",
    "write_readme_md",
    "write_stage20_run_log",
]
