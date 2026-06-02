"""Stage 30.11.3 manifest pin tests.

Pins the Stage 30.11.3 manifest constants (minor version, private sink schema
version, source-stage token, the three production basenames + module paths, the
committed composed sibling module paths, the inventory + scanned basenames, the
test basenames, the stdlib + PHX2 import allowlists, the sink decision / reason
tokens, the request / result / summary field names, the fake proof expected
counts, the slice-scoped next-allowed Stage 30.11.4 token, the slice forbidden
surfaces, the operator-auth live-ceremony note), asserts the production + test
files exist, cross-checks the mirrored schema version + decision / reason tokens
+ field names against the Stage 30.11.3 models module, cross-checks the fake
proof expected counts against the proof, confirms the Stage 30.11.0 / 30.11.1 /
30.11.2 constants + planned substages + family next-allowed pointer survive
unchanged, and pins the Stage 30.11.4+ future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_1_NEXT_ALLOWED_STAGE,
    STAGE30_11_2_NEXT_ALLOWED_STAGE,
    STAGE30_11_3_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_3_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_3_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME,
    STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_REJECTED_INVALID,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_REQUESTS_SEEN,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_RUNTIME_TRANSPORT_ATTEMPTS,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ACCEPTED,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ATTEMPTED,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED,
    STAGE30_11_3_FORBIDDEN_SURFACES,
    STAGE30_11_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_3_MINOR_VERSION,
    STAGE30_11_3_NEXT_ALLOWED_STAGE,
    STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION,
    STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON,
    STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME,
    STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
    STAGE30_11_3_PRIVATE_SINK_DECISIONS,
    STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME,
    STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
    STAGE30_11_3_PRIVATE_SINK_PROOF_SUMMARY_FIELDS,
    STAGE30_11_3_PRIVATE_SINK_REASONS,
    STAGE30_11_3_PRIVATE_SINK_REQUEST_FIELDS,
    STAGE30_11_3_PRIVATE_SINK_RESULT_FIELDS,
    STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION,
    STAGE30_11_3_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_3_SOURCE_STAGE,
    STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE,
    STAGE30_11_3_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
    STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
    STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
    STAGE30_11_3_TEST_BASENAMES,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_PLANNED_SUBSTAGES,
    STAGE30_11_STAGE_ID,
)
from PHX2.stage30.stage30_11_3_private_sink_models import (
    STAGE30_11_3_MINOR_VERSION as MODELS_MINOR_VERSION,
    STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION as MODELS_ACCEPT_DECISION,
    STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON as MODELS_ACCEPT_REASON,
    STAGE30_11_3_PRIVATE_SINK_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_3_PRIVATE_SINK_REASONS as MODELS_REASONS,
    STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_3_SOURCE_STAGE as MODELS_SOURCE_STAGE,
    private_sink_proof_summary_field_names,
    private_sink_request_field_names,
    private_sink_result_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema version + source stage (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_3_MINOR_VERSION == "30.11.3"
    assert STAGE30_11_3_MINOR_VERSION == MODELS_MINOR_VERSION


def test_schema_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION == (
        "stage30_11_3_v0_private_sink_adapter"
    )
    assert STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION == MODELS_SCHEMA_VERSION


def test_source_stage_pinned_and_matches_models() -> None:
    assert STAGE30_11_3_SOURCE_STAGE == "30.11.3"
    assert STAGE30_11_3_SOURCE_STAGE == MODELS_SOURCE_STAGE


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME == (
        "stage30_11_3_private_sink_models.py"
    )
    assert STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME == (
        "stage30_11_3_private_sink_adapter.py"
    )
    assert STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME == (
        "stage30_11_3_fake_private_sink_proof.py"
    )
    assert STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_3_private_sink_models"
    )
    assert STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_3_private_sink_adapter"
    )
    assert STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_3_fake_private_sink_proof"
    )


def test_composed_sibling_modules_pinned() -> None:
    assert STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE == (
        "PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models"
    )
    assert STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_2_runtime_gate_models"
    )
    assert STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE == (
        "PHX2.stage30.stage30_11_2_runtime_gate_seam"
    )
    assert STAGE30_11_3_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_2_fake_runtime_gate_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME,
        STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME,
        STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME,
    )
    assert STAGE30_11_3_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_3_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_3_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.3 requires {basename}"
        )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_3_TEST_BASENAMES == (
        "test_stage_30_11_3_private_sink_models.py",
        "test_stage_30_11_3_private_sink_adapter.py",
        "test_stage_30_11_3_fake_private_sink_proof.py",
        "test_stage_30_11_3_boundaries.py",
        "test_stage_30_11_3_manifest.py",
    )
    for basename in STAGE30_11_3_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.3 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_3_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "decimal",
    )
    for forbidden in (
        "os",
        "json",
        "pathlib",
        "sqlite3",
        "zstandard",
        "time",
        "datetime",
    ):
        assert forbidden not in STAGE30_11_3_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_within_family() -> None:
    assert STAGE30_11_3_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE,
        STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE,
        STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE,
        STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE,
        STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE,
        STAGE30_11_3_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE,
    )
    for module in STAGE30_11_3_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_3_ALLOWED_PHX2_IMPORTS)
    for forbidden in ("orchestrator", "suppress", "renderer", "live_provider"):
        assert forbidden not in joined


# ---------------------------------------------------------------------------
# 4. Sink decisions + reasons (mirrored from models)
# ---------------------------------------------------------------------------


def test_sink_decisions_pinned_and_match_models() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_DECISIONS == (
        "PRIVATE_SINK_ACCEPTED",
        "PRIVATE_SINK_REJECTED_INVALID_INPUT",
        "PRIVATE_SINK_TRANSPORT_FAILED",
    )
    assert STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION == "PRIVATE_SINK_ACCEPTED"
    assert STAGE30_11_3_PRIVATE_SINK_DECISIONS == MODELS_DECISIONS
    assert STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION == MODELS_ACCEPT_DECISION


def test_sink_reasons_pinned_and_match_models() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_REASONS == (
        "WOULD_SEND_PRIVATE_OPERATOR_MESSAGE",
        "INVALID_SINK_INPUT",
        "FAKE_TRANSPORT_REJECTED",
    )
    assert STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON == (
        "WOULD_SEND_PRIVATE_OPERATOR_MESSAGE"
    )
    assert STAGE30_11_3_PRIVATE_SINK_REASONS == MODELS_REASONS
    assert STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON == MODELS_ACCEPT_REASON


# ---------------------------------------------------------------------------
# 5. Field-name tuples (mirrored from models)
# ---------------------------------------------------------------------------


def test_request_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_REQUEST_FIELDS == (
        "candidate_id",
        "token_mint",
        "candidate_ref",
        "tier_token",
        "compact_body",
        "created_at_utc",
        "source_stage",
    )
    assert STAGE30_11_3_PRIVATE_SINK_REQUEST_FIELDS == (
        private_sink_request_field_names()
    )


def test_result_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_RESULT_FIELDS == (
        "candidate_id",
        "token_mint",
        "sink_decision",
        "sink_reason",
        "transport_attempted",
        "transport_accepted",
        "created_at_utc",
    )
    assert STAGE30_11_3_PRIVATE_SINK_RESULT_FIELDS == (
        private_sink_result_field_names()
    )


def test_summary_fields_pinned_and_match_models() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_PROOF_SUMMARY_FIELDS == (
        "requests_seen",
        "accepted",
        "rejected_invalid",
        "transport_failed",
        "transport_attempted",
        "transport_accepted",
        "created_at_utc",
    )
    assert STAGE30_11_3_PRIVATE_SINK_PROOF_SUMMARY_FIELDS == (
        private_sink_proof_summary_field_names()
    )


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        STAGE30_11_3_PRIVATE_SINK_REQUEST_FIELDS
        + STAGE30_11_3_PRIVATE_SINK_RESULT_FIELDS
        + STAGE30_11_3_PRIVATE_SINK_PROOF_SUMMARY_FIELDS
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "webhook",
            "api_key",
            "bearer",
            "authorization",
            "secret",
            "raw_payload",
            "getenv",
            "environ",
            "url",
            "host",
        ):
            assert forbidden not in lower, (
                f"Stage 30.11.3 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 6. Fake proof expected counts
# ---------------------------------------------------------------------------


def test_fake_proof_expected_counts_pinned() -> None:
    assert STAGE30_11_3_FAKE_PROOF_EXPECTED_REQUESTS_SEEN == 3
    assert STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED == 1
    assert STAGE30_11_3_FAKE_PROOF_EXPECTED_REJECTED_INVALID == 1
    assert STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED == 1
    assert STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ATTEMPTED == 2
    assert STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ACCEPTED == 1
    assert STAGE30_11_3_FAKE_PROOF_EXPECTED_RUNTIME_TRANSPORT_ATTEMPTS == 1
    # The decision partition holds, and only valid inputs reach the transport.
    assert (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED
        + STAGE30_11_3_FAKE_PROOF_EXPECTED_REJECTED_INVALID
        + STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED
        == STAGE30_11_3_FAKE_PROOF_EXPECTED_REQUESTS_SEEN
    )
    assert (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED
        + STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED
        == STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ATTEMPTED
    )
    assert (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ACCEPTED
        == STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED
    )


def test_fake_proof_expected_counts_match_the_proof() -> None:
    from PHX2.stage30.stage30_11_3_fake_private_sink_proof import (
        run_stage30_11_3_direct_sink_proof,
        run_stage30_11_3_runtime_integration_proof,
    )

    _results, summary, _transport = run_stage30_11_3_direct_sink_proof()
    assert summary.requests_seen == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_REQUESTS_SEEN
    )
    assert summary.accepted == STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED
    assert summary.rejected_invalid == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_REJECTED_INVALID
    )
    assert summary.transport_failed == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED
    )
    assert summary.transport_attempted == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ATTEMPTED
    )
    assert summary.transport_accepted == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ACCEPTED
    )

    _outcomes, _rsummary, transport = (
        run_stage30_11_3_runtime_integration_proof()
    )
    assert transport.attempted == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_RUNTIME_TRANSPORT_ATTEMPTS
    )


# ---------------------------------------------------------------------------
# 7. Next allowed stage + family pointer + planned substages unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_stage_is_30_11_4_and_family_pointers_intact() -> None:
    # The 30.11.3-scoped pointer advances to 30.11.4; the Stage 30.11.0 family
    # pointer stays pinned at 30.11.1 and the earlier scoped pointers survive.
    assert STAGE30_11_3_NEXT_ALLOWED_STAGE == "30.11.4"
    assert STAGE30_11_2_NEXT_ALLOWED_STAGE == "30.11.3"
    assert STAGE30_11_1_NEXT_ALLOWED_STAGE == "30.11.2"
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


def test_planned_substages_unchanged_30_11_0_through_30_11_4() -> None:
    assert STAGE30_11_PLANNED_SUBSTAGES == (
        "30.11.0",
        "30.11.1",
        "30.11.2",
        "30.11.3",
        "30.11.4",
    )
    joined = " ".join(STAGE30_11_PLANNED_SUBSTAGES)
    assert "30.12" not in joined
    assert "31" not in joined


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 8. Forbidden surfaces remain locked
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_3_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_3_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_3_FORBIDDEN_SURFACES)
    for token in (
        "real transport call",
        "real Discord send",
        "Discord send",
        "real dispatch reservation",
        "live run",
        "live provider call",
        "env read",
        "wall-clock read",
        "new live runner",
        "new provider",
        "new readiness gate",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "daemon",
        "background service",
        "autorestart loop",
        "unbounded loop",
        "Stage 28 transport-internals edit",
        "Stage 28 suppression-logic edit",
        "Stage 29 live provider / session edit",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "compression implementation",
        "default storage root",
        "public routing",
        "subscriber routing",
        "paid tiers",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "commit",
        "tag",
        "push",
        "Stage 30.11.4+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.3 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 9. Manifest __all__ exports the Stage 30.11.3 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_3_surface() -> None:
    for name in (
        "STAGE30_11_3_MINOR_VERSION",
        "STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION",
        "STAGE30_11_3_SOURCE_STAGE",
        "STAGE30_11_3_PRIVATE_SINK_MODELS_BASENAME",
        "STAGE30_11_3_PRIVATE_SINK_ADAPTER_BASENAME",
        "STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_BASENAME",
        "STAGE30_11_3_PRIVATE_SINK_MODELS_MODULE",
        "STAGE30_11_3_PRIVATE_SINK_ADAPTER_MODULE",
        "STAGE30_11_3_FAKE_PRIVATE_SINK_PROOF_MODULE",
        "STAGE30_11_3_STAGE30_9_3_GATE_MODELS_MODULE",
        "STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_MODELS_MODULE",
        "STAGE30_11_3_STAGE30_11_2_RUNTIME_GATE_SEAM_MODULE",
        "STAGE30_11_3_STAGE30_11_2_FAKE_RUNTIME_GATE_PROOF_MODULE",
        "STAGE30_11_3_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_3_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_3_TEST_BASENAMES",
        "STAGE30_11_3_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_3_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_3_PRIVATE_SINK_DECISIONS",
        "STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION",
        "STAGE30_11_3_PRIVATE_SINK_REASONS",
        "STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON",
        "STAGE30_11_3_PRIVATE_SINK_REQUEST_FIELDS",
        "STAGE30_11_3_PRIVATE_SINK_RESULT_FIELDS",
        "STAGE30_11_3_PRIVATE_SINK_PROOF_SUMMARY_FIELDS",
        "STAGE30_11_3_FAKE_PROOF_EXPECTED_REQUESTS_SEEN",
        "STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED",
        "STAGE30_11_3_FAKE_PROOF_EXPECTED_REJECTED_INVALID",
        "STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED",
        "STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ATTEMPTED",
        "STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ACCEPTED",
        "STAGE30_11_3_FAKE_PROOF_EXPECTED_RUNTIME_TRANSPORT_ATTEMPTS",
        "STAGE30_11_3_NEXT_ALLOWED_STAGE",
        "STAGE30_11_3_NEXT_ALLOWED_STAGE_TITLE",
        "STAGE30_11_3_FORBIDDEN_SURFACES",
        "STAGE30_11_3_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_3_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_0_through_30_11_2_constants_still_present() -> None:
    # The Stage 30.11.3 manifest edit is purely additive: the Stage 30.11.0 /
    # 30.11.1 / 30.11.2 constants survive.
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_PLANNED_SUBSTAGES",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_FORBIDDEN_SURFACES",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_11_1_MINOR_VERSION",
        "STAGE30_11_1_NEXT_ALLOWED_STAGE",
        "STAGE30_11_2_MINOR_VERSION",
        "STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION",
        "STAGE30_11_2_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_2_TEST_BASENAMES",
        "STAGE30_11_2_NEXT_ALLOWED_STAGE",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 10. Stage 30.11.4+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_4_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_3_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_3_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 4:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.3 inventory must not admit a Stage 30.11.4+ file yet; "
        f"saw {violations!r}"
    )
