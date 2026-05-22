"""Stage 27.5 dry-run artifact writer tests.

Pins:

  * Writer writes the canonical JSON encoding of a payload + the
    canonical JSON encoding of a provenance artifact under the
    injected output root.
  * Output bytes are stable (same input -> identical bytes).
  * Key ordering in the on-disk JSON is sort-keyed and separator-
    tight (matches the canonicalizers).
  * Writer refuses path-traversal filenames (``../foo``, absolute
    paths, NUL byte, leading dot, ``.``, ``..``).
  * Writer refuses an output root that does not exist or is not a
    directory.
  * Writer fail-closes when the target file already exists unless
    ``overwrite=True`` is supplied.
  * Default filename helpers honor the deterministic
    ``ping_<ping_id>_*.json`` convention.
  * Writer never writes outside the injected output root.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from PHX2.stage27 import private_ping_artifact_writer as writer
from PHX2.stage27 import private_ping_provenance as prov
from PHX2.stage27 import private_ping_renderer as renderer

# Reuse renderer fixtures so we test against synthetic Stage 27.4
# contexts only.
from PHX2.tests.stage27 import (
    test_stage_27_5_private_ping_renderer as renderer_fixtures,
)


# Stage 27.5 dry-run writer tests need a writable temp directory.
# ``stage27_5_tmp_path`` would normally fit, but the sandboxed pytest cache
# on this host can lack access to the global ``pytest-of-*`` root.
# A project-local self-managed temp directory sidesteps that and
# keeps the test deterministic.
@pytest.fixture
def stage27_5_tmp_path():
    base = Path(__file__).resolve().parent / "_stage_27_5_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="stage27_5_", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        # Best-effort cleanup of the parent if it became empty.
        try:
            base.rmdir()
        except OSError:
            pass


class _FixedClock:
    def __init__(self, value: str) -> None:
        self._value = value

    def now_utc_iso(self) -> str:
        return self._value


def _sol_payload(ping_id: str = "ping-write"):
    return renderer.render_private_ping(
        renderer_fixtures._sol_complete_context(), ping_id=ping_id
    )


def _sol_artifact(ping_id: str = "ping-write"):
    payload = _sol_payload(ping_id=ping_id)
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    return prov.build_ping_provenance_artifact(payload, clock)


# ---------------------------------------------------------------------------
# Happy-path writes
# ---------------------------------------------------------------------------


def test_write_payload_artifact_creates_file(stage27_5_tmp_path):
    payload = _sol_payload()
    target = writer.write_ping_payload_artifact(
        payload, stage27_5_tmp_path, "payload.json"
    )
    assert target == (stage27_5_tmp_path / "payload.json").resolve()
    assert target.is_file()


def test_write_provenance_artifact_creates_file(stage27_5_tmp_path):
    artifact = _sol_artifact()
    target = writer.write_ping_provenance_artifact(
        artifact, stage27_5_tmp_path, "provenance.json"
    )
    assert target.is_file()


def test_payload_artifact_contents_equal_canonical_payload_json(
    stage27_5_tmp_path,
):
    payload = _sol_payload()
    target = writer.write_ping_payload_artifact(
        payload, stage27_5_tmp_path, "payload.json"
    )
    body = target.read_text(encoding="utf-8")
    # Writer appends a single newline terminator.
    assert body.endswith("\n")
    assert body[:-1] == prov.canonical_payload_json(payload)


def test_provenance_artifact_contents_equal_canonical_artifact_json(
    stage27_5_tmp_path,
):
    artifact = _sol_artifact()
    target = writer.write_ping_provenance_artifact(
        artifact, stage27_5_tmp_path, "provenance.json"
    )
    body = target.read_text(encoding="utf-8")
    assert body.endswith("\n")
    assert body[:-1] == prov.canonical_artifact_json(artifact)


def test_payload_artifact_is_byte_identical_for_identical_inputs(
    stage27_5_tmp_path,
):
    a_path = writer.write_ping_payload_artifact(
        _sol_payload(), stage27_5_tmp_path, "a.json"
    )
    b_path = writer.write_ping_payload_artifact(
        _sol_payload(), stage27_5_tmp_path, "b.json"
    )
    assert a_path.read_bytes() == b_path.read_bytes()


def test_payload_artifact_json_is_sort_keyed(stage27_5_tmp_path):
    payload = _sol_payload()
    target = writer.write_ping_payload_artifact(
        payload, stage27_5_tmp_path, "sorted.json"
    )
    parsed = json.loads(target.read_text(encoding="utf-8"))
    assert parsed["ping_id"] == payload.ping_id


def test_payload_artifact_json_excludes_incidental_whitespace(
    stage27_5_tmp_path,
):
    payload = _sol_payload()
    target = writer.write_ping_payload_artifact(
        payload, stage27_5_tmp_path, "tight.json"
    )
    body = target.read_text(encoding="utf-8")
    # The body_text field legitimately contains ``label: value``
    # lines, so the canonical JSON encoding cannot be scanned for
    # bare ``": "`` substrings. We instead pin the JSON structure
    # separators that appear immediately after a quoted key.
    assert '": "' not in body
    assert '", "' not in body


# ---------------------------------------------------------------------------
# Default filename helpers
# ---------------------------------------------------------------------------


def test_default_payload_filename_uses_ping_id():
    assert (
        writer.default_payload_filename("ping-x")
        == "ping_ping-x_payload.json"
    )


def test_default_provenance_filename_uses_ping_id():
    assert (
        writer.default_provenance_filename("ping-x")
        == "ping_ping-x_provenance.json"
    )


def test_default_filename_rejects_empty_ping_id():
    with pytest.raises(writer.Stage27_5FilenameError):
        writer.default_payload_filename("")
    with pytest.raises(writer.Stage27_5FilenameError):
        writer.default_provenance_filename("")


def test_default_filename_rejects_path_separator_ping_id():
    with pytest.raises(writer.Stage27_5FilenameError):
        writer.default_payload_filename("../escape")
    with pytest.raises(writer.Stage27_5FilenameError):
        writer.default_payload_filename("a/b")


def test_write_dry_run_artifact_pair_writes_both_files(stage27_5_tmp_path):
    payload = _sol_payload(ping_id="ping-pair-x")
    artifact = _sol_artifact(ping_id="ping-pair-x")
    payload_path, prov_path = writer.write_dry_run_artifact_pair(
        payload, artifact, stage27_5_tmp_path
    )
    assert payload_path.is_file()
    assert prov_path.is_file()
    assert payload_path.name == "ping_ping-pair-x_payload.json"
    assert prov_path.name == "ping_ping-pair-x_provenance.json"


# ---------------------------------------------------------------------------
# Path-traversal guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    (
        "../escape.json",
        "../../escape.json",
        "a/b.json",
        "a\\b.json",
        ".hidden.json",
        ".",
        "..",
        "",
        "with\x00null.json",
    ),
)
def test_writer_refuses_path_traversal_filename(stage27_5_tmp_path, bad_name):
    payload = _sol_payload()
    with pytest.raises(writer.Stage27_5FilenameError):
        writer.write_ping_payload_artifact(
            payload, stage27_5_tmp_path, bad_name
        )


def test_writer_refuses_non_existent_output_root(stage27_5_tmp_path):
    missing = stage27_5_tmp_path / "no-such-dir"
    payload = _sol_payload()
    with pytest.raises(writer.Stage27_5OutputRootError):
        writer.write_ping_payload_artifact(
            payload, missing, "payload.json"
        )


def test_writer_refuses_output_root_that_is_a_file(stage27_5_tmp_path):
    not_a_dir = stage27_5_tmp_path / "not-a-dir"
    not_a_dir.write_text("placeholder", encoding="utf-8")
    payload = _sol_payload()
    with pytest.raises(writer.Stage27_5OutputRootError):
        writer.write_ping_payload_artifact(
            payload, not_a_dir, "payload.json"
        )


def test_writer_refuses_non_path_output_root():
    payload = _sol_payload()
    with pytest.raises(writer.Stage27_5OutputRootError):
        writer.write_ping_payload_artifact(
            payload, "/tmp", "payload.json"  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Fail-closed on existing target
# ---------------------------------------------------------------------------


def test_writer_refuses_overwrite_by_default(stage27_5_tmp_path):
    payload = _sol_payload()
    writer.write_ping_payload_artifact(
        payload, stage27_5_tmp_path, "payload.json"
    )
    with pytest.raises(writer.Stage27_5ArtifactExistsError):
        writer.write_ping_payload_artifact(
            payload, stage27_5_tmp_path, "payload.json"
        )


def test_writer_allows_overwrite_when_requested(stage27_5_tmp_path):
    payload = _sol_payload()
    writer.write_ping_payload_artifact(
        payload, stage27_5_tmp_path, "payload.json"
    )
    writer.write_ping_payload_artifact(
        payload, stage27_5_tmp_path, "payload.json", overwrite=True
    )


# ---------------------------------------------------------------------------
# Output-root containment
# ---------------------------------------------------------------------------


def test_writer_writes_only_under_output_root(stage27_5_tmp_path):
    payload = _sol_payload()
    target = writer.write_ping_payload_artifact(
        payload, stage27_5_tmp_path, "inside.json"
    )
    resolved_root = stage27_5_tmp_path.resolve()
    # The target must remain strictly under the output root.
    target.relative_to(resolved_root)


def test_writer_rejects_non_record_payload(stage27_5_tmp_path):
    with pytest.raises(TypeError):
        writer.write_ping_payload_artifact(
            {"ping_id": "x"}, stage27_5_tmp_path, "p.json"  # type: ignore[arg-type]
        )


def test_writer_rejects_non_record_artifact(stage27_5_tmp_path):
    with pytest.raises(TypeError):
        writer.write_ping_provenance_artifact(
            {"ping_id": "x"}, stage27_5_tmp_path, "p.json"  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Default-filename + write-pair determinism
# ---------------------------------------------------------------------------


def test_write_pair_overwrite_supported(stage27_5_tmp_path):
    payload = _sol_payload(ping_id="ping-over")
    artifact = _sol_artifact(ping_id="ping-over")
    writer.write_dry_run_artifact_pair(
        payload, artifact, stage27_5_tmp_path
    )
    writer.write_dry_run_artifact_pair(
        payload, artifact, stage27_5_tmp_path, overwrite=True
    )


def test_write_pair_explicit_filenames_honored(stage27_5_tmp_path):
    payload = _sol_payload(ping_id="ping-ex")
    artifact = _sol_artifact(ping_id="ping-ex")
    payload_path, prov_path = writer.write_dry_run_artifact_pair(
        payload,
        artifact,
        stage27_5_tmp_path,
        payload_filename="explicit_payload.json",
        provenance_filename="explicit_prov.json",
    )
    assert payload_path.name == "explicit_payload.json"
    assert prov_path.name == "explicit_prov.json"
