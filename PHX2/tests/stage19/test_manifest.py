"""Stage 19 manifest tests.

Covers compute_stage19_run_id determinism + sensitivity,
compute_file_sha256 streaming correctness, build_manifest shape
+ label-counts ordering, and write_manifest_json atomicity.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from PHX2.stage19 import manifest as M
from PHX2.stage19.constants import (
    LABELS,
    STAGE19_SCHEMA_VERSION,
    STAGE19_VERSION,
)


_VALID_64_HEX_A = "0" * 64
_VALID_64_HEX_B = "1" * 64
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _base_run_id_kwargs() -> dict:
    return dict(
        stage18_run_id="0123456789abcdef",
        stage18_input_basename="stage18_run_x",
        operator_id="alice",
        operator_input_sha256=_VALID_64_HEX_A,
        prior_ledger_sha256=None,
        run_timestamp_utc="2026-05-14T05:00:00Z",
        stage19_schema_version="stage19_ledger_v1",
    )


# ===========================================================================
# compute_stage19_run_id
# ===========================================================================


class TestComputeStage19RunIdShape:
    def test_returns_16_hex_lowercase(self) -> None:
        rid = M.compute_stage19_run_id(**_base_run_id_kwargs())
        assert _HEX16.match(rid), rid
        assert rid == rid.lower()

    def test_identical_inputs_yield_identical_id(self) -> None:
        kw = _base_run_id_kwargs()
        assert M.compute_stage19_run_id(**kw) == M.compute_stage19_run_id(**kw)


class TestComputeStage19RunIdSensitivity:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("stage18_run_id", "different_run_id"),
            ("stage18_input_basename", "different_basename"),
            ("operator_id", "bob"),
            ("operator_input_sha256", _VALID_64_HEX_B),
            ("prior_ledger_sha256", _VALID_64_HEX_B),
            ("run_timestamp_utc", "2026-05-15T05:00:00Z"),
            ("stage19_schema_version", "stage19_ledger_v2"),
        ],
    )
    def test_run_id_changes_when_any_field_changes(
        self, field: str, value: str
    ) -> None:
        base = _base_run_id_kwargs()
        base_rid = M.compute_stage19_run_id(**base)
        modified = {**base, field: value}
        assert M.compute_stage19_run_id(**modified) != base_rid


class TestComputeStage19RunIdBasenameSemantics:
    def test_uses_basename_not_absolute_path(self) -> None:
        """Two callers passing the same basename produce the same id
        even if their notional absolute paths would differ. Verified
        by holding stage18_input_basename constant and confirming
        the id is stable; the function does not take an absolute
        path, only a basename, so callers cannot 'leak' the path."""

        kw_a = {**_base_run_id_kwargs(), "stage18_input_basename": "run_x"}
        kw_b = {**_base_run_id_kwargs(), "stage18_input_basename": "run_x"}
        assert M.compute_stage19_run_id(**kw_a) == M.compute_stage19_run_id(**kw_b)

    def test_different_basenames_produce_different_ids(self) -> None:
        kw_a = {**_base_run_id_kwargs(), "stage18_input_basename": "run_x"}
        kw_b = {**_base_run_id_kwargs(), "stage18_input_basename": "run_y"}
        assert M.compute_stage19_run_id(**kw_a) != M.compute_stage19_run_id(**kw_b)


class TestComputeStage19RunIdNullPriorLedger:
    def test_prior_ledger_none_serializes_as_json_null(self) -> None:
        """The canonical JSON used for the digest must serialize
        ``prior_ledger_sha256=None`` as JSON null. Verified by
        recomputing the expected digest manually."""

        kw = _base_run_id_kwargs()
        canonical = json.dumps(
            {
                "operator_id": kw["operator_id"],
                "operator_input_sha256": kw["operator_input_sha256"],
                "prior_ledger_sha256": None,
                "run_timestamp_utc": kw["run_timestamp_utc"],
                "stage18_input_basename": kw["stage18_input_basename"],
                "stage18_run_id": kw["stage18_run_id"],
                "stage19_schema_version": kw["stage19_schema_version"],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        assert M.compute_stage19_run_id(**kw) == expected


# ===========================================================================
# compute_file_sha256
# ===========================================================================


class TestComputeFileSha256:
    def test_returns_64_hex_lowercase(self, tmp_path: Path) -> None:
        f = tmp_path / "x.txt"
        f.write_bytes(b"hello, world\n")
        digest = M.compute_file_sha256(f)
        assert _HEX64.match(digest), digest
        assert digest == digest.lower()

    def test_identical_content_produces_identical_hash(
        self, tmp_path: Path
    ) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"same content")
        b.write_bytes(b"same content")
        assert M.compute_file_sha256(a) == M.compute_file_sha256(b)

    def test_different_content_produces_different_hash(
        self, tmp_path: Path
    ) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"content one")
        b.write_bytes(b"content two")
        assert M.compute_file_sha256(a) != M.compute_file_sha256(b)

    def test_empty_file_hash_matches_known_sha256_of_empty(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        assert M.compute_file_sha256(f) == hashlib.sha256(b"").hexdigest()

    def test_streams_large_file_correctly(self, tmp_path: Path) -> None:
        # Larger than the chunk size to exercise streaming path
        payload = b"x" * (200 * 1024)
        f = tmp_path / "large.bin"
        f.write_bytes(payload)
        assert M.compute_file_sha256(f) == hashlib.sha256(payload).hexdigest()


# ===========================================================================
# build_manifest
# ===========================================================================


def _base_manifest_kwargs(tmp_path: Path) -> dict:
    s18 = tmp_path / "s18"
    s18.mkdir()
    op = tmp_path / "op.csv"
    op.write_text("hi", encoding="utf-8")
    return dict(
        stage19_run_id="aaaaaaaaaaaaaaaa",
        run_timestamp_utc="2026-05-14T05:00:00Z",
        operator_id="alice",
        stage18_input_dir=s18,
        stage18_run_id="0123456789abcdef",
        stage18_manifest_sha256=_VALID_64_HEX_A,
        stage18_review_matrix_sha256=_VALID_64_HEX_B,
        operator_input_path=op,
        operator_input_sha256=_VALID_64_HEX_A,
        prior_ledger_dir=None,
        prior_ledger_sha256=None,
        prior_ledger_schema_version=None,
        new_row_count=3,
        prior_row_count=0,
        total_ledger_row_count=3,
        label_counts={
            "REVIEW_PROMISING_CONFIRMED": 1,
            "REVIEW_HARMFUL_CONFIRMED": 1,
            "INCONCLUSIVE": 1,
        },
        git_commit="0" * 40,
    )


class TestBuildManifestShape:
    def test_contains_all_locked_keys(self, tmp_path: Path) -> None:
        m = M.build_manifest(**_base_manifest_kwargs(tmp_path))
        expected_keys = {
            "stage19_schema_version",
            "stage19_version",
            "stage19_run_id",
            "run_timestamp_utc",
            "operator_id",
            "stage18_input_dir",
            "stage18_input_basename",
            "stage18_run_id",
            "stage18_manifest_sha256",
            "stage18_review_matrix_sha256",
            "operator_input_path",
            "operator_input_sha256",
            "prior_ledger_dir",
            "prior_ledger_sha256",
            "prior_ledger_schema_version",
            "new_row_count",
            "prior_row_count",
            "total_ledger_row_count",
            "label_counts",
            "git_commit",
        }
        assert set(m.keys()) == expected_keys

    def test_pinned_constant_values(self, tmp_path: Path) -> None:
        m = M.build_manifest(**_base_manifest_kwargs(tmp_path))
        assert m["stage19_schema_version"] == STAGE19_SCHEMA_VERSION
        assert m["stage19_version"] == STAGE19_VERSION

    def test_basename_derived_from_dir(self, tmp_path: Path) -> None:
        kw = _base_manifest_kwargs(tmp_path)
        m = M.build_manifest(**kw)
        assert m["stage18_input_basename"] == kw["stage18_input_dir"].name


class TestBuildManifestLabelCountsOrder:
    def test_label_counts_ordered_per_LABELS(self, tmp_path: Path) -> None:
        kw = _base_manifest_kwargs(tmp_path)
        kw["label_counts"] = {
            # Insert in a non-LABELS order
            "INCONCLUSIVE": 5,
            "REVIEW_PROMISING_CONFIRMED": 2,
            "WATCHLIST": 7,
        }
        m = M.build_manifest(**kw)
        keys_in_order = list(m["label_counts"].keys())
        assert tuple(keys_in_order) == LABELS

    def test_missing_labels_default_to_zero(self, tmp_path: Path) -> None:
        kw = _base_manifest_kwargs(tmp_path)
        kw["label_counts"] = {"REVIEW_PROMISING_CONFIRMED": 5}
        m = M.build_manifest(**kw)
        assert m["label_counts"]["WATCHLIST"] == 0
        assert m["label_counts"]["INCONCLUSIVE"] == 0

    def test_all_six_labels_present_even_when_zero(self, tmp_path: Path) -> None:
        kw = _base_manifest_kwargs(tmp_path)
        kw["label_counts"] = {}
        m = M.build_manifest(**kw)
        assert set(m["label_counts"].keys()) == set(LABELS)


class TestBuildManifestPriorLedgerNullSemantics:
    def test_prior_ledger_dir_none_remains_none(self, tmp_path: Path) -> None:
        m = M.build_manifest(**_base_manifest_kwargs(tmp_path))
        assert m["prior_ledger_dir"] is None

    def test_prior_ledger_sha256_none_remains_none(self, tmp_path: Path) -> None:
        m = M.build_manifest(**_base_manifest_kwargs(tmp_path))
        assert m["prior_ledger_sha256"] is None

    def test_prior_ledger_schema_version_none_remains_none(
        self, tmp_path: Path
    ) -> None:
        m = M.build_manifest(**_base_manifest_kwargs(tmp_path))
        assert m["prior_ledger_schema_version"] is None

    def test_prior_ledger_dir_set_resolves_to_absolute(
        self, tmp_path: Path
    ) -> None:
        kw = _base_manifest_kwargs(tmp_path)
        prior = tmp_path / "prior"
        prior.mkdir()
        kw["prior_ledger_dir"] = prior
        kw["prior_ledger_sha256"] = _VALID_64_HEX_B
        kw["prior_ledger_schema_version"] = "stage19_ledger_v1"
        m = M.build_manifest(**kw)
        assert m["prior_ledger_dir"] == str(prior.resolve())


# ===========================================================================
# write_manifest_json
# ===========================================================================


class TestWriteManifestJson:
    def test_byte_identical_for_identical_input(self, tmp_path: Path) -> None:
        m1 = M.build_manifest(**_base_manifest_kwargs(tmp_path))
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        M.write_manifest_json(a, m1)
        M.write_manifest_json(b, m1)
        assert a.read_bytes() == b.read_bytes()

    def test_uses_sort_keys(self, tmp_path: Path) -> None:
        m = M.build_manifest(**_base_manifest_kwargs(tmp_path))
        out = tmp_path / "out.json"
        M.write_manifest_json(out, m)
        text = out.read_text(encoding="utf-8")
        # Quick check: keys appear in sorted order in the serialized
        # JSON. We just check that "git_commit" appears before
        # "label_counts" alphabetically.
        assert text.index("git_commit") < text.index("label_counts")

    def test_round_trips_via_json_load(self, tmp_path: Path) -> None:
        m = M.build_manifest(**_base_manifest_kwargs(tmp_path))
        out = tmp_path / "out.json"
        M.write_manifest_json(out, m)
        loaded = json.loads(out.read_text(encoding="utf-8"))
        for k, v in m.items():
            assert loaded[k] == v, k

    def test_atomic_no_partial_file_on_simulated_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If os.replace raises mid-write, the final path must
        remain absent (no partial file at the published name)."""

        m = M.build_manifest(**_base_manifest_kwargs(tmp_path))
        out = tmp_path / "out.json"

        def boom(src, dst):  # noqa: ARG001
            raise OSError("simulated rename failure")

        monkeypatch.setattr("PHX2.stage19.manifest.os.replace", boom)
        with pytest.raises(OSError, match="simulated"):
            M.write_manifest_json(out, m)
        assert not out.exists()
        # And the .tmp sibling should also be cleaned up
        assert not (tmp_path / "out.json.tmp").exists()
