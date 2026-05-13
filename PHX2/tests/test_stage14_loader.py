"""Stage 14 loader / validator unit tests.

Covers:
  * safe_for_live_policy_consumption invariant (any non-False value fails).
  * Stage 13 schema_version must be in the 1.x series.
  * Stage 12 schema_version must equal "1".
  * Stage 12 manifest hash override sanity check.
  * Missing-input + missing-column hard fails.
  * Stage 12 long CSV nullable bool / int coercion.
  * resolve_stage12_run_path branches.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage14.loader import (
    Stage14IncompatibleStage12,
    Stage14IncompatibleStage13,
    Stage14MissingColumn,
    Stage14MissingInput,
    load_stage12_run,
    load_stage13_run,
    resolve_stage12_run_path,
)
from PHX2.tests.fixtures.stage14.stage14_fixture_writer import (
    Stage12LongRow,
    Stage13CandidateRow,
    build_default_bundle,
    sha256_of_file,
    write_stage12_run,
    write_stage13_run,
)


# Convenience: schema_version + missing-CSV checks fire BEFORE the
# hash check, so those tests can pass any string here.
_ANY_HASH = "sha256:placeholder_for_pre_hash_check_failures"


def test_load_stage13_happy_path(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    stage13 = load_stage13_run(bundle.stage13_run_path)
    assert stage13.manifest["safe_for_live_policy_consumption"] is False
    assert len(stage13.candidate_rows) == 1
    assert stage13.candidate_rows[0]["filter_name"] == "fee_gate_v1"
    assert stage13.manifest_hash.startswith("sha256:")
    assert stage13.candidate_csv_hash.startswith("sha256:")


def test_load_stage13_rejects_safe_for_live_true(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path, safe_for_live=True)
    with pytest.raises(Stage14IncompatibleStage13, match="safe_for_live"):
        load_stage13_run(bundle.stage13_run_path)


def test_load_stage13_rejects_safe_for_live_truthy_string(tmp_path: Path) -> None:
    # Build then patch the manifest in place to inject the bad value
    # (the fixture writer cannot emit non-bool because it uses bool).
    bundle = build_default_bundle(tmp_path)
    import json

    manifest_path = bundle.stage13_run_path / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["safe_for_live_policy_consumption"] = "false"  # string, not bool
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    with pytest.raises(Stage14IncompatibleStage13, match="safe_for_live"):
        load_stage13_run(bundle.stage13_run_path)


def test_load_stage13_rejects_missing_safe_for_live_field(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    import json

    manifest_path = bundle.stage13_run_path / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("safe_for_live_policy_consumption")
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    with pytest.raises(Stage14IncompatibleStage13, match="safe_for_live"):
        load_stage13_run(bundle.stage13_run_path)


def test_load_stage13_rejects_schema_version_2x(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path, schema_version_stage13="2.0")
    with pytest.raises(Stage14IncompatibleStage13, match="schema_version"):
        load_stage13_run(bundle.stage13_run_path)


def test_load_stage13_requires_exactly_1_1(tmp_path: Path) -> None:
    """Stage 14 requires Stage 13 schema_version == '1.1' exactly.

    Schema 1.0 lacks the explicit filter-identity columns Stage 14
    needs for tuple matching, and any future bump must be audited
    against Stage 14 -- so reject anything other than the exact
    locked value loudly.
    """

    bundle11 = build_default_bundle(tmp_path / "v11", schema_version_stage13="1.1")
    assert (
        load_stage13_run(bundle11.stage13_run_path).manifest["stage13_schema_version"]
        == "1.1"
    )

    bundle10 = build_default_bundle(tmp_path / "v10", schema_version_stage13="1.0")
    with pytest.raises(Stage14IncompatibleStage13, match="schema_version"):
        load_stage13_run(bundle10.stage13_run_path)

    bundle12 = build_default_bundle(tmp_path / "v12", schema_version_stage13="1.2")
    with pytest.raises(Stage14IncompatibleStage13, match="schema_version"):
        load_stage13_run(bundle12.stage13_run_path)


def test_load_stage13_rejects_missing_manifest(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    (bundle.stage13_run_path / "manifest.json").unlink()
    with pytest.raises(Stage14MissingInput, match="manifest"):
        load_stage13_run(bundle.stage13_run_path)


def test_load_stage13_rejects_missing_candidate_csv(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    (bundle.stage13_run_path / "candidate_recommendations.csv").unlink()
    with pytest.raises(Stage14MissingInput, match="candidate"):
        load_stage13_run(bundle.stage13_run_path)


def test_load_stage12_rejects_wrong_schema_version(tmp_path: Path) -> None:
    stage12_path = write_stage12_run(
        tmp_path / "stage12_bad",
        long_rows=[Stage12LongRow(alert_decision_id="d1")],
        schema_version="2",
    )
    with pytest.raises(Stage14IncompatibleStage12, match="schema_version"):
        load_stage12_run(stage12_path, expected_manifest_hash=_ANY_HASH)


def test_load_stage12_rejects_missing_long_csv(tmp_path: Path) -> None:
    stage12_path = write_stage12_run(
        tmp_path / "stage12_x",
        long_rows=[Stage12LongRow(alert_decision_id="d1")],
    )
    (stage12_path / "decision_filter_outcome_long.csv").unlink()
    with pytest.raises(Stage14MissingInput, match="long CSV"):
        load_stage12_run(stage12_path, expected_manifest_hash=_ANY_HASH)


def test_load_stage12_rejects_missing_required_column(tmp_path: Path) -> None:
    stage12_path = write_stage12_run(
        tmp_path / "stage12_short",
        long_rows=[Stage12LongRow(alert_decision_id="d1")],
    )
    # Truncate the header to drop a required column.
    long_path = stage12_path / "decision_filter_outcome_long.csv"
    text = long_path.read_text(encoding="utf-8")
    header, rest = text.split("\n", 1)
    new_header = ",".join(c for c in header.split(",") if c != "decision_type")
    long_path.write_text(new_header + "\n" + rest, encoding="utf-8")
    # Column check fires AFTER the hash check, so the actual sha256
    # of the manifest must be supplied here -- otherwise the hash
    # check would short-circuit and the test would never reach the
    # column-presence assertion.
    actual_hash = sha256_of_file(stage12_path / "manifest.json")
    with pytest.raises(Stage14MissingColumn, match="decision_type"):
        load_stage12_run(stage12_path, expected_manifest_hash=actual_hash)


def test_load_stage12_override_hash_match(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    # Pretend the user passed --stage12-run pointing at the same dir.
    stage12 = load_stage12_run(
        bundle.stage12_run_path,
        expected_manifest_hash=bundle.stage12_manifest_hash,
    )
    assert stage12.manifest_hash == bundle.stage12_manifest_hash


def test_load_stage12_override_hash_mismatch(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    with pytest.raises(Stage14IncompatibleStage12, match="hash mismatch"):
        load_stage12_run(
            bundle.stage12_run_path,
            expected_manifest_hash="sha256:wrong",
        )


def test_load_stage12_nullable_bool_coercion(tmp_path: Path) -> None:
    stage12_path = write_stage12_run(
        tmp_path / "stage12_nullable",
        long_rows=[
            Stage12LongRow(
                alert_decision_id="dt_true",
                has_primary_outcome=True,
                primary_outcome_hit_2x_24h=True,
            ),
            Stage12LongRow(
                alert_decision_id="dt_false",
                has_primary_outcome=True,
                primary_outcome_hit_2x_24h=False,
            ),
            Stage12LongRow(
                alert_decision_id="dt_none",
                has_primary_outcome=None,
                primary_outcome_hit_2x_24h=None,
            ),
        ],
    )
    actual_hash = sha256_of_file(stage12_path / "manifest.json")
    stage12 = load_stage12_run(stage12_path, expected_manifest_hash=actual_hash)
    rows = {r.alert_decision_id: r for r in stage12.long_rows}
    assert rows["dt_true"].primary_outcome_hit_2x_24h is True
    assert rows["dt_false"].primary_outcome_hit_2x_24h is False
    assert rows["dt_none"].primary_outcome_hit_2x_24h is None
    assert rows["dt_none"].has_primary_outcome is None


def test_load_stage12_requires_expected_manifest_hash_kwarg(tmp_path: Path) -> None:
    """Calling load_stage12_run without expected_manifest_hash must
    raise TypeError at the call site. The pipeline/CLI path is safe
    by construction (resolve_stage12_run_path always supplies the
    recorded hash); this test pins down that ad-hoc direct callers
    cannot silently bypass the Stage 12 manifest integrity check by
    omitting the keyword argument.
    """

    stage12_path = write_stage12_run(
        tmp_path / "stage12_required",
        long_rows=[Stage12LongRow(alert_decision_id="d1")],
    )
    with pytest.raises(TypeError, match="expected_manifest_hash"):
        load_stage12_run(stage12_path)  # type: ignore[call-arg]


def test_resolve_stage12_path_default_branch_returns_recorded_hash(
    tmp_path: Path,
) -> None:
    """The default branch must surface the recorded hash so the
    loader can verify the Stage 12 manifest integrity."""

    bundle = build_default_bundle(tmp_path)
    import json

    stage13_manifest = json.loads(
        (bundle.stage13_run_path / "manifest.json").read_text(encoding="utf-8")
    )
    path, expected_hash = resolve_stage12_run_path(
        stage13_manifest=stage13_manifest, override=None
    )
    assert path == Path(stage13_manifest["stage12_run_path"])
    assert expected_hash == bundle.stage12_manifest_hash


def test_resolve_stage12_path_override_branch(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    import json

    stage13_manifest = json.loads(
        (bundle.stage13_run_path / "manifest.json").read_text(encoding="utf-8")
    )
    override = tmp_path / "elsewhere"
    path, expected_hash = resolve_stage12_run_path(
        stage13_manifest=stage13_manifest, override=override
    )
    assert path == override
    assert expected_hash == bundle.stage12_manifest_hash


def test_resolve_stage12_path_missing_recorded_path_fails(tmp_path: Path) -> None:
    # Manifest carries the hash but no stage12_run_path; the missing
    # path branch is what fails (with no override to fall back on).
    manifest = {"stage12_manifest_hash": "sha256:abc"}
    with pytest.raises(Stage14IncompatibleStage13, match="stage12_run_path"):
        resolve_stage12_run_path(stage13_manifest=manifest, override=None)


def test_resolve_stage12_path_default_without_hash_fails(tmp_path: Path) -> None:
    """Default branch must reject manifests that omit the integrity
    anchor; Stage 14 will not run blind against a Stage 12 directory
    whose contents it cannot pin."""

    manifest_without_hash = {"stage12_run_path": str(tmp_path)}
    with pytest.raises(
        Stage14IncompatibleStage13, match="stage12_manifest_hash"
    ):
        resolve_stage12_run_path(
            stage13_manifest=manifest_without_hash, override=None
        )


def test_resolve_stage12_path_override_without_hash_fails(tmp_path: Path) -> None:
    # Override branch must also reject manifests that omit the hash.
    manifest_without_hash = {"stage12_run_path": str(tmp_path)}
    with pytest.raises(
        Stage14IncompatibleStage13, match="stage12_manifest_hash"
    ):
        resolve_stage12_run_path(
            stage13_manifest=manifest_without_hash, override=tmp_path
        )
