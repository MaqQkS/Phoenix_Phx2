"""Stage 30.9.0 bounded private live compact session bridge spec-lock
pin tests.

Pure read-only repo inspection. No live network calls, no env reads, no
Discord traffic, no provider calls. The test does not shell out to ``git``
and does not pin any git-SHA snapshot; it asserts the Stage 30.9.0
contract via direct filesystem inspection of the three-file inventory
(spec lock markdown + manifest module + this pin test) plus substring /
line-parse / AST matches against those files, plus membership checks
against the Stage 30.0 inventory allowlist.

Pinned contract:

  * The spec doc and the manifest exist; the pin test exists.
  * The Stage 30.0 inventory allowlist admits exactly the Stage 30.9.0
    files and no Stage 30.9.1+ file.
  * The spec doc locks reuse of the EXISTING bounded private live compact
    engine (``run_stage30_4_2_compact_runtime_session`` /
    ``run_stage30_3_compact_runtime_session`` /
    ``run_stage28_9_live_provider_session`` /
    ``evaluate_stage28_9_readiness`` /
    ``Stage28_9LiveProviderSessionConfig`` /
    ``Stage28_9PrivateWebhookTransport`` / Stage 27.6 + Stage 28.2 runtime
    dedupe).
  * The spec doc locks the Stage 30.9.1 artifact-bridge contract (a thin
    capture transport + a post-session projector that drives
    ``write_compact_session_artifact_bundle`` /
    ``read_compact_session_bundle`` / ``build_compact_session_index``
    POST-SESSION ONLY, never per ping; no new live loop).
  * The spec doc locks the gating + caps (incl. the
    ``max_runtime_seconds`` NOT-supported-except-external-``stop_signal``
    caveat), the dedupe stance, the artifact identity fields, the
    fail-closed failure behavior, the planned 30.9.0 / 30.9.1 / 30.9.2
    substages, and the forbidden surfaces (public / subscriber / paid
    routing, Telegram, X / social, trading, wallet, enforcement, DB /
    SQLite, zstd / compression, default storage root, background daemon,
    Stage 31).
  * The manifest is constants-only (no def / class / Call; imports only
    ``__future__`` + ``typing``; no PHX2 import).
  * No Stage 30.9 runtime module / bridge / capture / projector file
    exists; no Stage 30.9.2+ file is admitted. Among Stage 30.10+ tokens,
    only the Stage 30.10.0 spec-lock scaffold (spec doc + manifest + pin
    test) is admitted; every other Stage 30.10+ token and every Stage 31
    token remains forbidden.
  * No Stage 30.9.0 Python file carries a forbidden runtime / Stage
    21-29 / PHX1 import or a forbidden secret / transport text needle.

Stage 30.9.0 is a spec-lock / handoff document only. This test makes no
live call, sends no Discord message, and changes no runtime behavior.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Tuple

from PHX2.stage30.stage30_9_manifest import (
    STAGE30_9_0_MINOR_VERSION,
    STAGE30_9_0_SPEC_VERSION,
    STAGE30_9_0_TEST_BASENAMES,
    STAGE30_9_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_9_1_TEST_BASENAMES,
    STAGE30_9_2_ALLOWED_STAGE30_BASENAMES,
    STAGE30_9_2_TEST_BASENAMES,
    STAGE30_9_3_ALLOWED_STAGE30_BASENAMES,
    STAGE30_9_3_TEST_BASENAMES,
    STAGE30_9_ALLOWED_INITIAL_FILES,
    STAGE30_9_ALLOWED_STDLIB_IMPORTS,
    STAGE30_9_ARTIFACT_BRIDGE_REQUIRED_SURFACES,
    STAGE30_9_ARTIFACT_IDENTITY_FIELDS,
    STAGE30_9_DEDUPE_STANCE,
    STAGE30_9_EXISTING_ENGINE_REUSE_SURFACES,
    STAGE30_9_FAILURE_BEHAVIOR,
    STAGE30_9_FORBIDDEN_RUNTIME_IMPORTS,
    STAGE30_9_FORBIDDEN_SURFACES,
    STAGE30_9_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_9_GATING_REQUIREMENTS,
    STAGE30_9_MANIFEST_BASENAME,
    STAGE30_9_NEXT_ALLOWED_STAGE,
    STAGE30_9_PLANNED_SUBSTAGES,
    STAGE30_9_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_9_SPEC_LOCK_FILENAME,
    STAGE30_9_SPEC_LOCK_PATH_PARTS,
    STAGE30_9_STAGE_ID,
)

# The single source of truth for the Stage 30.0 inventory allowlist. The
# Stage 30.9.0 inventory-pin tests read these frozensets directly so the
# allowlist (not a duplicated copy) is what is asserted to admit exactly
# the Stage 30.9.0 files.
from PHX2.tests.stage30.test_stage_30_0_spec_lock import (
    _STAGE30_ALLOWED_BASENAMES,
    _TESTS_STAGE30_ALLOWED_BASENAMES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
SPEC_LOCK_PATH: Path = STAGE30_ROOT / STAGE30_9_SPEC_LOCK_FILENAME
MANIFEST_PATH: Path = STAGE30_ROOT / STAGE30_9_MANIFEST_BASENAME
TEST_PATH: Path = TESTS_STAGE30_ROOT / STAGE30_9_0_TEST_BASENAMES[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


def _test_text() -> str:
    return TEST_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a phrase
    that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


def _all_30_9_0_files() -> Dict[str, str]:
    return {
        "spec": _spec_text(),
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _python_30_9_0_files() -> Dict[str, str]:
    return {
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _is_real_import_line(line: str) -> bool:
    """Return True iff ``line`` is an actual Python import statement (not a
    comment, not a string-literal line inside a tuple).
    """
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if stripped.startswith("\"") or stripped.startswith("'"):
        return False
    return stripped.startswith("import ") or stripped.startswith("from ")


def _extract_imported_module(line: str) -> str:
    """Return the module token from an ``import X`` or ``from X import Y``
    line. Empty string on malformed.
    """
    stripped = line.strip()
    tokens = stripped.split()
    if len(tokens) < 2:
        return ""
    if tokens[0] in ("import", "from"):
        return tokens[1]
    return ""


# Matches any Stage 30.9.<N> minor-version token in a basename (both the
# production ``stage30_9_<N>`` and the test ``stage_30_9_<N>`` spellings).
# A captured N >= 2 names a Stage 30.9.2+ file; N in {0, 1} is the Stage
# 30.9.0 scaffold / the now-admitted Stage 30.9.1 artifact-bridge slice and
# is allowed. The now-admitted Stage 30.9.2 resume planning slice carries an
# N == 2 token but is explicitly allowed via ``_ADMITTED_STAGE_30_9_2_BASENAMES``
# (``_future_30_9_violations`` skips it); any OTHER N >= 2 token remains
# forbidden. The Stage 30.9.0 manifest basename (``stage30_9_manifest.py``)
# carries no digit after ``stage30_9_`` and so matches no token at all.
_STAGE_30_9_MINOR_RE = re.compile(r"stage_?30_9_(\d+)")

# Matches a Stage 30.10+ token (``stage30_10`` / ``stage_30_10`` / ...) or a
# Stage 31 token (``stage31`` / ``stage_31``). Stage 31 is not admitted yet;
# among Stage 30.10+ tokens, ONLY the Stage 30.10.0 spec-lock scaffold below
# is admitted (any other Stage 30.10+ token -- a Stage 30.10.1+
# implementation file, a Stage 30.11+ file -- remains forbidden here).
_STAGE_30_10_PLUS_RE = re.compile(r"stage_?30_1\d")
_STAGE_31_RE = re.compile(r"stage_?31\b")

# The Stage 30.10.0 spec-lock scaffold (spec doc + constants-only manifest +
# pin test) plus the now-admitted Stage 30.10.1 fake / offline eligibility
# model + classifier slice (the two production modules + their four tests), the
# Stage 30.10.2 optional fake / offline pre-dispatch gate slice (the three
# production modules + their five tests), and the Stage 30.10.3 fake / offline
# gate artifact integration proof slice (the three production modules + their
# five tests) are admitted here; the Stage 30.10.0 pin test owns the
# authoritative "no Stage 30.10.4+ file" guard going forward. Any other Stage
# 30.10+ token (a Stage 30.10.4+ implementation file, a Stage 30.11+ file)
# remains forbidden in this guard.
_ADMITTED_STAGE_30_10_BASENAMES = frozenset(
    {
        # Stage 30.10.0 spec-lock scaffold.
        "STAGE_30_10_0_COMPACT_TIER_DIP_ELIGIBILITY_SPEC_LOCK.md",
        "stage30_10_manifest.py",
        "test_stage_30_10_0_compact_tier_dip_eligibility_spec_lock.py",
        # Stage 30.10.1 fake / offline eligibility model + classifier slice.
        "stage30_10_1_tier_dip_eligibility_models.py",
        "stage30_10_1_tier_dip_eligibility_classifier.py",
        "test_stage_30_10_1_tier_dip_eligibility_models.py",
        "test_stage_30_10_1_tier_dip_eligibility_classifier.py",
        "test_stage_30_10_1_boundaries.py",
        "test_stage_30_10_1_manifest.py",
        # Stage 30.10.2 optional fake / offline pre-dispatch tier-dip gate
        # slice.
        "stage30_10_2_pre_dispatch_gate_models.py",
        "stage30_10_2_pre_dispatch_gate.py",
        "stage30_10_2_fake_gate_proof.py",
        "test_stage_30_10_2_pre_dispatch_gate_models.py",
        "test_stage_30_10_2_pre_dispatch_gate.py",
        "test_stage_30_10_2_fake_gate_proof.py",
        "test_stage_30_10_2_boundaries.py",
        "test_stage_30_10_2_manifest.py",
        # Stage 30.10.3 fake / offline gate artifact integration proof slice.
        "stage30_10_3_gate_artifact_models.py",
        "stage30_10_3_gate_artifact_projector.py",
        "stage30_10_3_fake_artifact_proof.py",
        "test_stage_30_10_3_gate_artifact_models.py",
        "test_stage_30_10_3_gate_artifact_projector.py",
        "test_stage_30_10_3_fake_artifact_proof.py",
        "test_stage_30_10_3_boundaries.py",
        "test_stage_30_10_3_manifest.py",
    }
)


# The now-admitted Stage 30.11.0 dip-gated live dispatch wiring spec-lock
# scaffold (the spec-lock markdown + constants-only manifest + pin test) PLUS
# the now-admitted Stage 30.11.1 offline live-candidate assembly bridge slice
# (the three production modules + their five tests) PLUS the now-admitted Stage
# 30.11.2 offline runtime gate seam slice (the three production modules + their
# five tests) PLUS the now-admitted Stage 30.11.3 private sink adapter slice
# (the three production modules + their five tests) PLUS the now-admitted Stage
# 30.11.4 offline end-to-end proof slice (the two production modules + their four
# tests). These basenames carry the ``stage30_11`` / ``stage_30_11`` token and so
# match the Stage 30.10+ guard regex; they are admitted here while the Stage
# 30.11.0 pin test owns the authoritative "no Stage 30.11.5+ file" guard going
# forward. Any other Stage 30.11+ token (a Stage 30.11.5+ implementation file)
# remains forbidden in this guard.
_ADMITTED_STAGE_30_11_BASENAMES = frozenset(
    {
        # Stage 30.11.0 spec-lock scaffold.
        "STAGE_30_11_0_DIP_GATED_LIVE_DISPATCH_WIRING_SPEC_LOCK.md",
        "stage30_11_manifest.py",
        "test_stage_30_11_0_dip_gated_live_dispatch_wiring_spec_lock.py",
        # Stage 30.11.1 offline live-candidate assembly bridge slice.
        "stage30_11_1_live_candidate_bridge_models.py",
        "stage30_11_1_live_candidate_bridge.py",
        "stage30_11_1_fake_bridge_proof.py",
        "test_stage_30_11_1_live_candidate_bridge_models.py",
        "test_stage_30_11_1_live_candidate_bridge.py",
        "test_stage_30_11_1_fake_bridge_proof.py",
        "test_stage_30_11_1_boundaries.py",
        "test_stage_30_11_1_manifest.py",
        # Stage 30.11.2 offline runtime gate seam slice.
        "stage30_11_2_runtime_gate_models.py",
        "stage30_11_2_runtime_gate_seam.py",
        "stage30_11_2_fake_runtime_gate_proof.py",
        "test_stage_30_11_2_runtime_gate_models.py",
        "test_stage_30_11_2_runtime_gate_seam.py",
        "test_stage_30_11_2_fake_runtime_gate_proof.py",
        "test_stage_30_11_2_boundaries.py",
        "test_stage_30_11_2_manifest.py",
        # Stage 30.11.3 private sink adapter slice.
        "stage30_11_3_private_sink_models.py",
        "stage30_11_3_private_sink_adapter.py",
        "stage30_11_3_fake_private_sink_proof.py",
        "test_stage_30_11_3_private_sink_models.py",
        "test_stage_30_11_3_private_sink_adapter.py",
        "test_stage_30_11_3_fake_private_sink_proof.py",
        "test_stage_30_11_3_boundaries.py",
        "test_stage_30_11_3_manifest.py",
        # Stage 30.11.4 offline end-to-end proof slice.
        "stage30_11_4_offline_e2e_proof_models.py",
        "stage30_11_4_offline_e2e_proof.py",
        "test_stage_30_11_4_offline_e2e_proof_models.py",
        "test_stage_30_11_4_offline_e2e_proof.py",
        "test_stage_30_11_4_boundaries.py",
        "test_stage_30_11_4_manifest.py",
        # Stage 30.11.5 controlled live ceremony wiring slice.
        "stage30_11_5_live_wiring_models.py",
        "stage30_11_5_live_candidate_snapshot_assembler.py",
        "stage30_11_5_private_transport_adapter.py",
        "stage30_11_5_bounded_live_runner.py",
        "stage30_11_5_fake_live_wiring_proof.py",
        "test_stage_30_11_5_live_wiring_models.py",
        "test_stage_30_11_5_live_candidate_snapshot_assembler.py",
        "test_stage_30_11_5_private_transport_adapter.py",
        "test_stage_30_11_5_bounded_live_runner.py",
        "test_stage_30_11_5_fake_live_wiring_proof.py",
        "test_stage_30_11_5_boundaries.py",
        "test_stage_30_11_5_manifest.py",
        # Stage 30.11.6 real candidate source / harvest seam slice.
        "stage30_11_6_candidate_source_models.py",
        "stage30_11_6_stage29_projection_adapter.py",
        "stage30_11_6_candidate_harvest_adapter.py",
        "stage30_11_6_fake_candidate_source_proof.py",
        "test_stage_30_11_6_candidate_source_models.py",
        "test_stage_30_11_6_stage29_projection_adapter.py",
        "test_stage_30_11_6_candidate_harvest_adapter.py",
        "test_stage_30_11_6_fake_candidate_source_proof.py",
        "test_stage_30_11_6_boundaries.py",
        "test_stage_30_11_6_manifest.py",
    }
)


# The now-admitted Stage 30.9.2_RESUME dip-filtered live proof planning /
# fake-proof slice (the three production modules + their five tests). These
# basenames carry the ``stage30_9_2`` / ``stage_30_9_2`` minor token but are
# the legitimately-landed resume planning files; the future guard admits
# exactly these and still forbids any OTHER Stage 30.9.2 file and any Stage
# 30.9.3+ file. The Stage 30.9.2 actual dip-filtered live ceremony remains a
# separate, explicitly operator-authorized step (no live runtime ships here).
_ADMITTED_STAGE_30_9_2_BASENAMES = frozenset(
    set(STAGE30_9_2_ALLOWED_STAGE30_BASENAMES)
    | set(STAGE30_9_2_TEST_BASENAMES)
)


# The now-admitted Stage 30.9.3 dip-filtered live dispatch integration seam
# (the four production modules + their six tests). These basenames carry the
# ``stage30_9_3`` / ``stage_30_9_3`` minor token but are the legitimately-landed
# integration-seam files; the future guard admits exactly these and still
# forbids any OTHER Stage 30.9.3 file and any Stage 30.9.4+ file. The actual
# dip-filtered live ceremony remains a separate, explicitly operator-authorized
# step (no live runtime ships here).
_ADMITTED_STAGE_30_9_3_BASENAMES = frozenset(
    set(STAGE30_9_3_ALLOWED_STAGE30_BASENAMES)
    | set(STAGE30_9_3_TEST_BASENAMES)
)


def _future_30_9_violations(basenames) -> list:
    violations = []
    for basename in basenames:
        if basename in _ADMITTED_STAGE_30_9_2_BASENAMES:
            # The now-admitted Stage 30.9.2 resume planning slice.
            continue
        if basename in _ADMITTED_STAGE_30_9_3_BASENAMES:
            # The now-admitted Stage 30.9.3 integration-seam slice.
            continue
        for match in _STAGE_30_9_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 2:
                violations.append(basename)
    return violations


# ---------------------------------------------------------------------------
# 1. (Group 1) files exist
# ---------------------------------------------------------------------------


def test_spec_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 30.9.0 requires the spec-lock document {SPEC_LOCK_PATH}"
    )


def test_manifest_exists() -> None:
    assert MANIFEST_PATH.is_file(), (
        f"Stage 30.9.0 requires the manifest module {MANIFEST_PATH}"
    )


def test_pin_test_file_exists() -> None:
    assert TEST_PATH.is_file(), (
        f"Stage 30.9.0 requires the pin test {TEST_PATH}"
    )


def test_spec_lock_path_parts_resolve_to_the_doc() -> None:
    assert STAGE30_9_SPEC_LOCK_PATH_PARTS == (
        "PHX2",
        "stage30",
        STAGE30_9_SPEC_LOCK_FILENAME,
    )
    resolved = PHX2_ROOT.parent.joinpath(*STAGE30_9_SPEC_LOCK_PATH_PARTS)
    assert resolved == SPEC_LOCK_PATH
    assert resolved.is_file()


# ---------------------------------------------------------------------------
# 2. Version + basename + stage id pins
# ---------------------------------------------------------------------------


def test_stage_id_and_minor_version_pinned() -> None:
    assert STAGE30_9_STAGE_ID == "30.9"
    assert STAGE30_9_0_MINOR_VERSION == "30.9.0"


def test_spec_version_pinned() -> None:
    assert STAGE30_9_0_SPEC_VERSION == (
        "stage30_9_v0_bounded_private_live_compact"
    )


def test_basenames_pinned() -> None:
    assert STAGE30_9_SPEC_LOCK_FILENAME == (
        "STAGE_30_9_0_BOUNDED_PRIVATE_LIVE_COMPACT_SPEC_LOCK.md"
    )
    assert STAGE30_9_MANIFEST_BASENAME == "stage30_9_manifest.py"
    assert STAGE30_9_0_TEST_BASENAMES == (
        "test_stage_30_9_0_bounded_private_live_compact_spec_lock.py",
    )


def test_next_allowed_stage_is_30_9_1() -> None:
    assert STAGE30_9_NEXT_ALLOWED_STAGE == "30.9.1"


# ---------------------------------------------------------------------------
# 3. Required section headings, in order
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: Tuple[str, ...] = (
    "# PHX2 Stage 30.9.0",
    "## 1. Purpose",
    "## 2. Non-purpose",
    "## 3. Existing engine reuse",
    "## 4. Stage 30.8 artifact bridge contract",
    "## 5. Gating and caps",
    "## 6. Dedupe stance",
    "## 7. Artifact fields",
    "## 8. Failure behavior",
    "## 9. Future slices",
    "## 10. Forbidden surfaces",
    "## 11. Forbidden terms and secret hygiene",
)


def test_spec_contains_all_required_section_headings() -> None:
    text = _spec_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30.9.0 spec lock missing required section heading: "
            f"{heading!r}"
        )


def test_spec_section_headings_appear_in_order() -> None:
    text = _spec_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30.9.0 spec lock section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


def test_spec_lock_only_stance_pinned_in_doc() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30.9.0 is spec lock and tests only",
        "ZERO production `.py` file beyond the constants-only manifest",
    ):
        assert phrase in normalized, (
            f"Stage 30.9.0 spec doc must pin the spec-lock-only stance; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 4. (Group 2) Spec content: existing engine reuse surfaces
# ---------------------------------------------------------------------------


def test_spec_locks_existing_engine_reuse_surfaces() -> None:
    text = _spec_text()
    for surface in (
        "run_stage30_4_2_compact_runtime_session",
        "run_stage30_3_compact_runtime_session",
        "run_stage28_9_live_provider_session",
        "evaluate_stage28_9_readiness",
        "Stage28_9LiveProviderSessionConfig",
        "Stage28_9PrivateWebhookTransport",
    ):
        assert surface in text, (
            "Stage 30.9.0 spec lock must lock reuse of the existing engine "
            f"surface {surface!r}"
        )
    # Stage 27.6 / Stage 28.2 runtime dedupe / dispatch ledger.
    assert "Stage 27.6" in text and "Stage 28.2" in text, (
        "Stage 30.9.0 spec lock must lock the Stage 27.6 / Stage 28.2 "
        "runtime dedupe / dispatch ledger reuse"
    )


def test_spec_locks_no_new_live_loop_and_no_new_gate() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "no new live loop" in lowered, (
        "Stage 30.9.0 spec lock must state Stage 30.9 introduces no new "
        "live loop"
    )
    assert "not a new live runner" in lowered, (
        "Stage 30.9.0 spec lock must state Stage 30.9 is not a new live "
        "runner"
    )
    assert "not a new readiness gate" in lowered, (
        "Stage 30.9.0 spec lock must state Stage 30.9 is not a new "
        "readiness gate"
    )


# ---------------------------------------------------------------------------
# 5. (Group 2) Spec content: Stage 30.8 artifact bridge contract
# ---------------------------------------------------------------------------


def test_spec_locks_capture_transport_and_projector() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "capture transport" in lowered, (
        "Stage 30.9.0 spec lock must lock the thin capture transport"
    )
    assert "post-session projector" in lowered, (
        "Stage 30.9.0 spec lock must lock the post-session projector"
    )


def test_spec_locks_stage_30_8_writer_reader_index_surfaces() -> None:
    text = _spec_text()
    for surface in (
        "write_compact_session_artifact_bundle",
        "read_compact_session_bundle",
        "build_compact_session_index",
    ):
        assert surface in text, (
            "Stage 30.9.0 spec lock must lock the Stage 30.8 storage "
            f"surface {surface!r}"
        )


def test_spec_locks_post_session_only_and_no_per_ping_writes() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "post-session only" in lowered, (
        "Stage 30.9.0 spec lock must state Stage 30.8 writes are "
        "post-session only"
    )
    assert "never called per ping" in lowered, (
        "Stage 30.9.0 spec lock must state the Stage 30.8 writer is never "
        "called per ping"
    )
    assert "post-run proof only" in lowered, (
        "Stage 30.9.0 spec lock must state the Stage 30.8 index is "
        "post-run proof only"
    )


# ---------------------------------------------------------------------------
# 6. (Group 2) Spec content: gating + caps caveat
# ---------------------------------------------------------------------------


def test_spec_locks_gating_and_caps() -> None:
    text = _spec_text()
    for field in (
        "live_env_ready",
        "live_operator_request",
        "private_webhook_url",
        "output_dir",
        "max_events",
        "max_dispatches",
        "max_ticks",
        "max_total_retries",
    ):
        assert field in text, (
            f"Stage 30.9.0 spec lock must lock the gating field {field!r}"
        )
    lowered = _normalized(text).lower()
    assert "dry_run" in lowered and "live_private" in lowered, (
        "Stage 30.9.0 spec lock must lock the DRY_RUN / LIVE_PRIVATE "
        "session-mode separation"
    )
    assert "no default storage root" in lowered, (
        "Stage 30.9.0 spec lock must forbid a default storage root"
    )


def test_spec_locks_max_runtime_seconds_caveat() -> None:
    text = _spec_text()
    assert "max_runtime_seconds" in text, (
        "Stage 30.9.0 spec lock must name max_runtime_seconds"
    )
    assert "stop_signal" in text, (
        "Stage 30.9.0 spec lock must name the external stop_signal path"
    )
    lowered = _normalized(text).lower()
    assert "not currently supported" in lowered, (
        "Stage 30.9.0 spec lock must state max_runtime_seconds is not "
        "currently supported except via an external stop_signal path"
    )


# ---------------------------------------------------------------------------
# 7. (Group 2) Spec content: no public / social / trading / wallet /
#    enforcement surfaces
# ---------------------------------------------------------------------------


def test_spec_forbids_public_social_trading_wallet_enforcement() -> None:
    text = _spec_text()
    for token in (
        "public routing",
        "subscriber routing",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "Stage 31",
    ):
        assert token in text, (
            "Stage 30.9.0 spec lock must forbid the surface "
            f"{token!r}"
        )


def test_spec_locks_artifact_identity_fields() -> None:
    text = _spec_text()
    for field in STAGE30_9_ARTIFACT_IDENTITY_FIELDS:
        assert field in text, (
            "Stage 30.9.0 spec lock must lock the artifact identity field "
            f"{field!r}"
        )


def test_spec_locks_dedupe_stance() -> None:
    text = _spec_text()
    lowered = _normalized(text).lower()
    assert "stage 27.6 + stage 28.2" in lowered, (
        "Stage 30.9.0 spec lock must state runtime dedupe stays Stage "
        "27.6 + Stage 28.2"
    )
    assert "post-run proof only" in lowered, (
        "Stage 30.9.0 spec lock must state the Stage 30.8 dedupe index is "
        "post-run proof only"
    )
    assert "no cross-session runtime dedupe" in lowered, (
        "Stage 30.9.0 spec lock must forbid cross-session runtime dedupe"
    )


def test_spec_locks_future_substages() -> None:
    text = _spec_text()
    for substage in ("Stage 30.9.0", "Stage 30.9.1", "Stage 30.9.2"):
        assert substage in text, (
            "Stage 30.9.0 spec lock must define the future stage; missing "
            f"{substage!r}"
        )


# ---------------------------------------------------------------------------
# 8. (Group 3) Manifest constants: planned substages
# ---------------------------------------------------------------------------


def test_planned_substages_are_exactly_three() -> None:
    assert STAGE30_9_PLANNED_SUBSTAGES == ("30.9.0", "30.9.1", "30.9.2")


def test_existing_engine_reuse_surfaces_cover_required_names() -> None:
    joined = " | ".join(STAGE30_9_EXISTING_ENGINE_REUSE_SURFACES)
    for surface in (
        "run_stage30_4_2_compact_runtime_session",
        "run_stage30_3_compact_runtime_session",
        "run_stage28_9_live_provider_session",
        "evaluate_stage28_9_readiness",
        "Stage28_9LiveProviderSessionConfig",
        "Stage28_9PrivateWebhookTransport",
        "Stage28_6BoundedPrivateSessionRunner",
        "Stage 28.4 audited HTTP transport",
    ):
        assert surface in joined, (
            "STAGE30_9_EXISTING_ENGINE_REUSE_SURFACES must name "
            f"{surface!r}"
        )
    # Stage 27.6 / Stage 28.2 runtime dedupe / dispatch ledger.
    assert "27.6" in joined and "28.2" in joined, (
        "STAGE30_9_EXISTING_ENGINE_REUSE_SURFACES must name the Stage "
        "27.6 / Stage 28.2 runtime dedupe / dispatch ledger"
    )


def test_artifact_bridge_required_surfaces_cover_contract() -> None:
    joined = " | ".join(STAGE30_9_ARTIFACT_BRIDGE_REQUIRED_SURFACES)
    for surface in (
        "thin innermost capture transport",
        "wraps inner_transport",
        "records webhook_identity",
        "records enriched payload content exactly as sent",
        "records sanitized transport result",
        "forwards the payload verbatim",
        "post-session projector",
        "obtains dedupe_key from runtime dispatch ledger",
        "emits Stage 30.8.1 model types",
        "write_compact_session_artifact_bundle",
        "read_compact_session_bundle",
        "build_compact_session_index",
        "post-session only writes",
        "no per-ping Stage 30.8 writer call",
        "Stage 30.8 index is post-run proof only",
    ):
        assert surface in joined, (
            "STAGE30_9_ARTIFACT_BRIDGE_REQUIRED_SURFACES must name "
            f"{surface!r}"
        )


# ---------------------------------------------------------------------------
# 9. (Group 3) Manifest constants: gating requirements
# ---------------------------------------------------------------------------


def test_gating_requirements_cover_required_terms() -> None:
    joined = " | ".join(STAGE30_9_GATING_REQUIREMENTS)
    for token in (
        "live_env_ready",
        "live_operator_request",
        "private_webhook_url",
        "output_dir",
        "max_events",
        "max_dispatches",
        "max_ticks",
        "max_total_retries",
        "DRY_RUN",
        "LIVE_PRIVATE",
        "no default storage root",
        "max_runtime_seconds",
        "stop_signal",
    ):
        assert token in joined, (
            f"STAGE30_9_GATING_REQUIREMENTS must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 10. (Group 3) Manifest constants: dedupe stance
# ---------------------------------------------------------------------------


def test_dedupe_stance_covers_runtime_and_index_split() -> None:
    joined = " | ".join(STAGE30_9_DEDUPE_STANCE)
    assert "runtime dedupe = Stage 27.6 + Stage 28.2" in joined, (
        "STAGE30_9_DEDUPE_STANCE must state runtime dedupe = Stage 27.6 + "
        "Stage 28.2"
    )
    assert "Stage 30.8 dedupe index = post-run proof only" in joined, (
        "STAGE30_9_DEDUPE_STANCE must state the Stage 30.8 dedupe index = "
        "post-run proof only"
    )
    assert "dedupe_key carried into Stage 30.8 compact ping artifacts" in (
        joined
    ), (
        "STAGE30_9_DEDUPE_STANCE must state dedupe_key is carried into the "
        "Stage 30.8 compact ping artifacts"
    )
    assert "no new DB-backed dedupe" in joined, (
        "STAGE30_9_DEDUPE_STANCE must forbid new DB-backed dedupe"
    )
    assert "no cross-session runtime dedupe in Stage 30.9" in joined, (
        "STAGE30_9_DEDUPE_STANCE must forbid cross-session runtime dedupe"
    )


# ---------------------------------------------------------------------------
# 11. (Group 3) Manifest constants: artifact identity fields
# ---------------------------------------------------------------------------


def test_artifact_identity_fields_are_the_eight_axes() -> None:
    assert STAGE30_9_ARTIFACT_IDENTITY_FIELDS == (
        "run_id",
        "session_id",
        "ping_id",
        "candidate_id",
        "token_mint",
        "dedupe_key",
        "artifact_created_at_utc",
        "artifact_kind",
    )


# ---------------------------------------------------------------------------
# 12. (Group 3) Manifest constants: failure behavior
# ---------------------------------------------------------------------------


def test_failure_behavior_is_fail_closed() -> None:
    joined = " | ".join(STAGE30_9_FAILURE_BEHAVIOR).lower()
    for token in (
        "readiness failure => no provider call, no discord send",
        "writer failure => artifact proof failure, sent pings unaffected",
        "missing dedupe_key => invalid artifact proof",
        "duplicate candidate => runtime suppressed before send",
        "cap hit => clean bounded stop",
    ):
        assert token in joined, (
            f"STAGE30_9_FAILURE_BEHAVIOR must state {token!r}"
        )


# ---------------------------------------------------------------------------
# 13. (Group 3) Manifest constants: forbidden surfaces
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_all_listed_scopes() -> None:
    assert isinstance(STAGE30_9_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_9_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_9_FORBIDDEN_SURFACES)
    for token in (
        "public routing",
        "subscriber routing",
        "paid tiers",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "auto-buy",
        "strategy execution",
        "broad always-on daemon",
        "background service",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "zstd dependency",
        "compression implementation",
        "default storage root",
        "inline per-ping Stage 30.8 writes",
        "new live runner",
        "new readiness gate",
        "Stage 30.8 implementation edit",
        "Stage 25/27/28/29 production import",
        "commit",
        "tag",
        "push",
        "Stage 31",
        "Stage 30.9.1+ implementation file",
    ):
        assert token in joined, (
            f"Stage 30.9 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 14. (Group 4) Boundaries: manifest is constants-only
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only() -> None:
    """AST proof: the manifest contains no function / class definition and
    no Call node anywhere (constants-only; the split-literal needle
    concatenations use ``+`` BinOps, never Calls), and imports only
    ``__future__`` + ``typing`` (no PHX2 import).
    """
    tree = ast.parse(_manifest_text())

    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), "Stage 30.9.0 manifest must be constants-only (no def / class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.9.0 manifest must be constants-only (no Call -- no "
            "implicit I/O at import time)"
        )

    allowed_import_roots = set(STAGE30_9_ALLOWED_STDLIB_IMPORTS)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.9.0 manifest may only import __future__ / "
                f"typing; saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.9.0 manifest may only import __future__ / "
                    f"typing; saw {alias.name!r}"
                )


def test_manifest_imports_no_phx2_module() -> None:
    for line in _manifest_text().split("\n"):
        if not _is_real_import_line(line):
            continue
        module = _extract_imported_module(line)
        assert not module.startswith("PHX2"), (
            "Stage 30.9.0 manifest must import no PHX2 module; saw "
            f"{module!r}"
        )


def test_allowed_initial_files_are_exactly_spec_and_manifest() -> None:
    assert STAGE30_9_ALLOWED_INITIAL_FILES == (
        STAGE30_9_SPEC_LOCK_FILENAME,
        STAGE30_9_MANIFEST_BASENAME,
    )
    # The only NEW production .py is the manifest; the spec lock is
    # markdown.
    py_additions = [
        name
        for name in STAGE30_9_ALLOWED_INITIAL_FILES
        if name.endswith(".py")
    ]
    assert py_additions == [STAGE30_9_MANIFEST_BASENAME]
    assert STAGE30_9_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_9_MANIFEST_BASENAME,
    )


# ---------------------------------------------------------------------------
# 15. (Group 4) Boundaries: no forbidden runtime / Stage 21-29 / PHX1 /
#     network / DB / compression imports
# ---------------------------------------------------------------------------


_FORBIDDEN_MODULE_PREFIXES: Tuple[str, ...] = (
    "os",
    "dotenv",
    "keyring",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "grpc",
    "http",
    "websocket",
    "websockets",
    "sqlite3",
    "zstandard",
    "zstd",
    "gzip",
    "zlib",
    "lzma",
    "bz2",
)


def test_no_forbidden_runtime_imports_in_30_9_0_files() -> None:
    for filename, text in _python_30_9_0_files().items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for prefix in _FORBIDDEN_MODULE_PREFIXES:
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.9.0 file {filename!r} imports forbidden "
                    f"module {module!r} on line {line.rstrip()!r}"
                )


def test_no_os_environ_or_getenv_in_30_9_0_files() -> None:
    """No env read at Stage 30.9.0: no ``os.environ`` / ``os.getenv`` /
    ``os.environb`` appears as an actual call in the manifest or test (the
    manifest names these only as split-literal-free documentation strings
    in the forbidden-import tuple, which are not call sites).
    """
    for filename, text in _python_30_9_0_files().items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in (
                    "environ",
                    "getenv",
                    "environb",
                ), (
                    f"Stage 30.9.0 file {filename!r} must not read env via "
                    f"os.{node.attr}"
                )


def test_no_stage21_29_or_phx1_imports_in_30_9_0_files() -> None:
    """Neither the manifest NOR this pin test imports a Stage 21-29 /
    Stage 29.5 / PHX1 production module. (The pin test legitimately
    imports the Stage 30.0 sibling TEST module to read the inventory
    allowlist -- a ``PHX2.tests`` import -- and the Stage 30.9 manifest --
    a ``PHX2.stage30`` import -- both of which are outside the forbidden
    Stage 21-29 production range and so pass this scan.)
    """
    for filename, text in _python_30_9_0_files().items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for stage_n in range(21, 30):
                assert not module.startswith(f"PHX2.stage{stage_n}"), (
                    f"Stage 30.9.0 file {filename!r} imports forbidden "
                    f"Stage 21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.9.0 file {filename!r} imports forbidden PHX1 "
                f"module {module!r}"
            )


def test_forbidden_runtime_imports_tuple_is_non_empty() -> None:
    assert len(STAGE30_9_FORBIDDEN_RUNTIME_IMPORTS) >= 20, (
        "STAGE30_9_FORBIDDEN_RUNTIME_IMPORTS must enumerate the forbidden "
        "runtime import surfaces"
    )


# ---------------------------------------------------------------------------
# 16. (Group 4) Boundaries: no Discord / webhook send / secret / transport
#     text needle in any Stage 30.9.0 file
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles_in_30_9_0_files() -> None:
    """Case-insensitive substring scan over the spec lock, the manifest,
    and this test file. The manifest's ``STAGE30_9_FORBIDDEN_TEXT_NEEDLES``
    tuple uses split-literal forms so the manifest source itself does not
    carry the bare needles; this test imports the values at runtime and
    scans every Stage 30.9.0 file. This proves no Discord / webhook send
    surface, no transport scheme, no provider host, and no request
    auth-metadata leaks into the spec-lock files.
    """
    for filename, text in _all_30_9_0_files().items():
        lower = text.lower()
        for needle in STAGE30_9_FORBIDDEN_TEXT_NEEDLES:
            needle_lower = needle.lower()
            assert needle_lower not in lower, (
                f"Stage 30.9.0 file {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_forbidden_text_needles_tuple_is_non_empty() -> None:
    assert len(STAGE30_9_FORBIDDEN_TEXT_NEEDLES) >= 12, (
        "STAGE30_9_FORBIDDEN_TEXT_NEEDLES must enumerate the forbidden "
        "text needles"
    )


# ---------------------------------------------------------------------------
# 17. (Group 4) Boundaries: no Stage 30.9 runtime / bridge / capture /
#     projector module exists yet
# ---------------------------------------------------------------------------


def test_stage30_9_production_entries_are_the_admitted_inventory() -> None:
    """Every Stage 30.9 entry under ``PHX2/stage30/`` must be exactly the
    Stage 30.9.0 spec doc + constants-only manifest PLUS the now-admitted
    Stage 30.9.1 artifact-bridge production files (passive models + capture
    transport + projector + proof) PLUS the now-admitted Stage 30.9.2_RESUME
    dip-filtered live proof planning files (resume models + plan + fake
    proof) PLUS the now-admitted Stage 30.9.3 dip-filtered live dispatch
    integration seam files (integration models + adapter + orchestrator +
    fake integration proof). NO Stage 30.9.4+ module may exist yet.
    """
    observed = {
        entry.name
        for entry in STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and (
            entry.name.startswith("stage30_9")
            or entry.name.startswith("STAGE_30_9")
        )
    }
    allowed = (
        {
            STAGE30_9_SPEC_LOCK_FILENAME,
            STAGE30_9_MANIFEST_BASENAME,
        }
        | set(STAGE30_9_1_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_9_2_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_9_3_ALLOWED_STAGE30_BASENAMES)
    )
    assert observed == allowed, (
        "Stage 30.9 production entries must be exactly the Stage 30.9.0 "
        "spec lock + manifest plus the Stage 30.9.1 bridge files plus the "
        "Stage 30.9.2 resume planning files plus the Stage 30.9.3 "
        "integration-seam files; "
        f"unexpected entries: {sorted(observed - allowed)}"
    )


def test_stage30_9_test_entries_are_the_admitted_inventory() -> None:
    """Every Stage 30.9 test under ``PHX2/tests/stage30/`` must be exactly
    the Stage 30.9.0 spec-lock pin test PLUS the now-admitted Stage 30.9.1
    test files PLUS the now-admitted Stage 30.9.2_RESUME test files PLUS the
    now-admitted Stage 30.9.3 integration-seam test files. NO Stage 30.9.4+
    test may exist yet.
    """
    observed = {
        entry.name
        for entry in TESTS_STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and entry.name.startswith("test_stage_30_9")
    }
    allowed = (
        {STAGE30_9_0_TEST_BASENAMES[0]}
        | set(STAGE30_9_1_TEST_BASENAMES)
        | set(STAGE30_9_2_TEST_BASENAMES)
        | set(STAGE30_9_3_TEST_BASENAMES)
    )
    assert observed == allowed, (
        "Stage 30.9 test entries must be exactly the 30.9.0 pin test plus "
        "the Stage 30.9.1 tests plus the Stage 30.9.2 resume tests plus the "
        f"Stage 30.9.3 integration-seam tests; "
        f"unexpected entries: {sorted(observed - allowed)}"
    )


# ---------------------------------------------------------------------------
# 18. (Group 1 + 5) Stage 30.0 allowlist admits exactly the 30.9.0 files;
#     no Stage 30.9.1+ / Stage 30.10 / Stage 31 file admitted.
# ---------------------------------------------------------------------------


def test_stage30_0_allowlist_admits_the_30_9_0_files() -> None:
    assert STAGE30_9_SPEC_LOCK_FILENAME in _STAGE30_ALLOWED_BASENAMES
    assert STAGE30_9_MANIFEST_BASENAME in _STAGE30_ALLOWED_BASENAMES
    assert (
        STAGE30_9_0_TEST_BASENAMES[0] in _TESTS_STAGE30_ALLOWED_BASENAMES
    )
    assert SPEC_LOCK_PATH.is_file()
    assert MANIFEST_PATH.is_file()
    assert TEST_PATH.is_file()


def test_stage30_0_allowlist_admits_only_the_30_9_2_resume_slice() -> None:
    """The Stage 30.0 allowlist admits exactly the now-landed Stage 30.9.2
    resume planning slice among Stage 30.9.<N>=2+ tokens, and no other. The
    Stage 30.9.1 artifact-bridge files (``stage30_9_<no minor>`` models /
    capture / projector / proof basenames carry no minor digit after
    ``stage30_9_``) are admitted with no minor-token match; the guard skips
    the explicitly-admitted Stage 30.9.2 resume basenames and still catches
    ANY non-admitted Stage 30.9.<N>=2+ token (a stray 30_9_2, a future
    30_9_3, ...).
    """
    production = _future_30_9_violations(_STAGE30_ALLOWED_BASENAMES)
    assert production == [], (
        "Stage 30.0 production allowlist must admit only the Stage 30.9.2 "
        f"resume slice among Stage 30.9.2+ files; saw {production!r}"
    )
    tests = _future_30_9_violations(_TESTS_STAGE30_ALLOWED_BASENAMES)
    assert tests == [], (
        "Stage 30.0 test allowlist must admit only the Stage 30.9.2 resume "
        f"slice among Stage 30.9.2+ test files; saw {tests!r}"
    )


def test_no_stage_30_10_or_stage_31_file_admitted() -> None:
    """Only the Stage 30.10.0 spec-lock scaffold + the now-admitted Stage
    30.10.1 eligibility model + classifier slice + the Stage 30.10.2 optional
    pre-dispatch gate slice + the Stage 30.10.3 gate artifact integration
    proof slice + the now-admitted Stage 30.11.0 dip-gated live dispatch wiring
    spec-lock scaffold + the now-admitted Stage 30.11.1 offline live-candidate
    assembly bridge slice + the now-admitted Stage 30.11.2 offline runtime gate
    seam slice are admitted among Stage 30.10+ tokens; every other Stage 30.10+
    token (a Stage 30.10.4+ implementation file, a Stage 30.11.3+
    implementation file) and every Stage 31 token remains forbidden -- in both
    the Stage 30.0 allowlists and the on-disk Stage 30 dirs. The Stage 30.11.0
    pin test owns the authoritative "no Stage 30.11.3+ file" guard going
    forward.
    """
    haystacks = (
        _STAGE30_ALLOWED_BASENAMES
        | _TESTS_STAGE30_ALLOWED_BASENAMES
        | {e.name for e in STAGE30_ROOT.iterdir()}
        | {e.name for e in TESTS_STAGE30_ROOT.iterdir()}
    )
    for basename in haystacks:
        if (
            basename in _ADMITTED_STAGE_30_10_BASENAMES
            or basename in _ADMITTED_STAGE_30_11_BASENAMES
        ):
            # The Stage 30.10.0 scaffold + the Stage 30.10.1 / 30.10.2 /
            # 30.10.3 slices + the Stage 30.11.0 spec-lock scaffold + the
            # Stage 30.11.1 assembly bridge slice + the Stage 30.11.2 runtime
            # gate seam slice are admitted.
            continue
        lowered = basename.lower()
        assert _STAGE_30_10_PLUS_RE.search(lowered) is None, (
            "Only the Stage 30.10.0 scaffold + the Stage 30.10.1 / 30.10.2 / "
            "30.10.3 slices + the Stage 30.11.0 spec-lock scaffold + the "
            "Stage 30.11.1 assembly bridge slice + the Stage 30.11.2 runtime "
            f"gate seam slice are admitted among Stage 30.10+ files; offender "
            f"{basename!r}"
        )
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 31 file is not admitted yet; offender {basename!r}"
        )


def test_planned_substages_admit_no_future_token() -> None:
    """The planned-substage tuple stops at 30.9.2; it admits no 30.9.3+,
    no 30.10, and no 31 token.
    """
    assert STAGE30_9_PLANNED_SUBSTAGES[-1] == "30.9.2"
    joined = " ".join(STAGE30_9_PLANNED_SUBSTAGES)
    assert "30.9.3" not in joined
    assert "30.10" not in joined
    assert "31" not in joined
