"""Stage 30.11.20 manifest pin tests.

Pins the Stage 30.11.20 manifest constants (minor version, report schema version,
source stage, spec-lock doc, the three production basenames + module paths, the
test basenames, the stdlib + PHX2 import allowlists, the bounded caps, the
duck-typed price-source surface pins, the closed-set Layer-0 enrichment decision +
redaction vocabularies, the enriched price fields, the dataclass field tuples, the
forbidden surfaces, the next-allowed-stage pointer, the operator-auth note),
cross-checks the mirrored values against the Stage 30.11.20 models module + the
committed Stage 30.11.18 facts type + the committed Stage 29.2 snapshot vocabulary
(BY VALUE -- the committed production code imports no Stage 29 module; only this
test cross-checks the mirror), asserts the production + test files + spec-lock doc
exist, and confirms the manifest __all__ exports the surface while the earlier
sections survive.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_19_ENRICHED_MARKET_FIELDS,
    STAGE30_11_20_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_20_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_20_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_20_DEFAULT_MAX_CANDIDATES,
    STAGE30_11_20_ENRICHED_PRICE_FIELDS,
    STAGE30_11_20_ENRICHMENT_ADAPTER_BASENAME,
    STAGE30_11_20_ENRICHMENT_ADAPTER_MODULE,
    STAGE30_11_20_ENRICHMENT_DECISIONS,
    STAGE30_11_20_ENRICHMENT_EVENT_FIELDS,
    STAGE30_11_20_ENRICHMENT_MODELS_BASENAME,
    STAGE30_11_20_ENRICHMENT_MODELS_MODULE,
    STAGE30_11_20_ENRICHMENT_RESULT_FIELDS,
    STAGE30_11_20_ENRICHMENT_SESSION_REPORT_FIELDS,
    STAGE30_11_20_FAKE_ENRICHMENT_PROOF_BASENAME,
    STAGE30_11_20_FAKE_ENRICHMENT_PROOF_MODULE,
    STAGE30_11_20_FORBIDDEN_SURFACES,
    STAGE30_11_20_LIVE_CEREMONY_NOTE,
    STAGE30_11_20_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_20_MAX_CANDIDATES_HARD_CAP,
    STAGE30_11_20_MINOR_VERSION,
    STAGE30_11_20_NEXT_ALLOWED_STAGE,
    STAGE30_11_20_PRICE_SNAPSHOT_REQUIRED_ATTRS,
    STAGE30_11_20_PRICE_SOURCE_METHOD,
    STAGE30_11_20_PRICE_STATUS_MISSING,
    STAGE30_11_20_PRICE_STATUS_PRESENT,
    STAGE30_11_20_PRICE_STATUS_SOURCE_ERROR,
    STAGE30_11_20_REDACTION_STATUS_REDACTED,
    STAGE30_11_20_REDACTION_STATUSES,
    STAGE30_11_20_REPORT_SCHEMA_VERSION,
    STAGE30_11_20_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_20_SOURCE_STAGE,
    STAGE30_11_20_TEST_BASENAMES,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_PRICE_STATUS_MISSING,
    BIRDEYE_PRICE_STATUS_PRESENT,
    BIRDEYE_PRICE_STATUS_SOURCE_ERROR,
)
from PHX2.stage29.stage29_2_birdeye_price_source import (
    Stage29_2BirdeyePriceSource,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    STAGE30_11_17_MAX_CANDIDATES_HARD_CAP,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_20_current_price_enrichment_models import (
    STAGE30_11_20_ENRICHMENT_DECISIONS as MODELS_DECISIONS,
    STAGE30_11_20_MINOR_VERSION as MODELS_MINOR,
    STAGE30_11_20_PRICE_SNAPSHOT_REQUIRED_ATTRS as MODELS_SNAPSHOT_ATTRS,
    STAGE30_11_20_PRICE_SOURCE_METHOD as MODELS_SOURCE_METHOD,
    STAGE30_11_20_PRICE_STATUS_MISSING as MODELS_STATUS_MISSING,
    STAGE30_11_20_PRICE_STATUS_PRESENT as MODELS_STATUS_PRESENT,
    STAGE30_11_20_PRICE_STATUS_SOURCE_ERROR as MODELS_STATUS_SOURCE_ERROR,
    STAGE30_11_20_REDACTION_STATUSES as MODELS_REDACTION_STATUSES,
    STAGE30_11_20_REDACTION_STATUS_REDACTED as MODELS_REDACTED,
    STAGE30_11_20_REPORT_SCHEMA_VERSION as MODELS_SCHEMA,
    STAGE30_11_20_SOURCE_STAGE as MODELS_SOURCE_STAGE,
    price_enrichment_event_field_names,
    price_enrichment_result_field_names,
    price_enrichment_session_report_field_names,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
DOCS_ROOT: Path = PHX2_ROOT / "docs"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity (mirrored from models)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_models() -> None:
    assert STAGE30_11_20_MINOR_VERSION == "30.11.20"
    assert STAGE30_11_20_MINOR_VERSION == MODELS_MINOR


def test_schema_version_and_source_stage_match_models() -> None:
    assert STAGE30_11_20_REPORT_SCHEMA_VERSION == (
        "stage30_11_20_v0_current_price_enrichment"
    )
    assert STAGE30_11_20_REPORT_SCHEMA_VERSION == MODELS_SCHEMA
    assert STAGE30_11_20_SOURCE_STAGE == "30.11.20"
    assert STAGE30_11_20_SOURCE_STAGE == MODELS_SOURCE_STAGE


# ---------------------------------------------------------------------------
# 2. Basenames + module paths + inventory + files exist
# ---------------------------------------------------------------------------


def test_basenames_and_modules_pinned() -> None:
    assert STAGE30_11_20_ENRICHMENT_MODELS_BASENAME == (
        "stage30_11_20_current_price_enrichment_models.py"
    )
    assert STAGE30_11_20_ENRICHMENT_ADAPTER_BASENAME == (
        "stage30_11_20_current_price_enrichment_adapter.py"
    )
    assert STAGE30_11_20_FAKE_ENRICHMENT_PROOF_BASENAME == (
        "stage30_11_20_fake_current_price_enrichment_proof.py"
    )
    assert STAGE30_11_20_ENRICHMENT_MODELS_MODULE == (
        "PHX2.stage30.stage30_11_20_current_price_enrichment_models"
    )
    assert STAGE30_11_20_ENRICHMENT_ADAPTER_MODULE == (
        "PHX2.stage30.stage30_11_20_current_price_enrichment_adapter"
    )
    assert STAGE30_11_20_FAKE_ENRICHMENT_PROOF_MODULE == (
        "PHX2.stage30.stage30_11_20_fake_current_price_enrichment_proof"
    )


def test_allowed_and_scanned_basenames_are_the_three_modules() -> None:
    expected = (
        STAGE30_11_20_ENRICHMENT_MODELS_BASENAME,
        STAGE30_11_20_ENRICHMENT_ADAPTER_BASENAME,
        STAGE30_11_20_FAKE_ENRICHMENT_PROOF_BASENAME,
    )
    assert STAGE30_11_20_ALLOWED_STAGE30_BASENAMES == expected
    assert STAGE30_11_20_SCANNED_PRODUCTION_BASENAMES == expected


def test_production_files_exist() -> None:
    for basename in STAGE30_11_20_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.20 requires {basename}"
        )


def test_spec_lock_doc_exists() -> None:
    assert (
        DOCS_ROOT
        / "STAGE_30_11_20_CURRENT_PRICE_ENRICHMENT_SPEC_LOCK.md"
    ).is_file()


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_11_20_TEST_BASENAMES == (
        "test_stage_30_11_20_current_price_enrichment_adapter.py",
        "test_stage_30_11_20_fake_current_price_enrichment_proof.py",
        "test_stage_30_11_20_boundaries.py",
        "test_stage_30_11_20_manifest.py",
    )
    for basename in STAGE30_11_20_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.11.20 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Import allowlists (stdlib + PHX2)
# ---------------------------------------------------------------------------


def test_stdlib_allowlist_pinned() -> None:
    assert STAGE30_11_20_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
    )
    # The Layer-0 checks REUSE the committed Stage 30.11.18 predicates, so no
    # decimal / io / db / clock is admitted.
    for forbidden in ("os", "json", "pathlib", "datetime", "decimal", "sqlite3"):
        assert forbidden not in STAGE30_11_20_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_within_family_no_stage28_29_or_birdeye() -> None:
    assert STAGE30_11_20_ALLOWED_PHX2_IMPORTS == (
        STAGE30_11_20_ENRICHMENT_MODELS_MODULE,
        STAGE30_11_20_ENRICHMENT_ADAPTER_MODULE,
        STAGE30_11_20_FAKE_ENRICHMENT_PROOF_MODULE,
        "PHX2.stage30.stage30_11_19_market_context_enrichment_adapter",
        "PHX2.stage30.stage30_11_18_harvested_facts_models",
        "PHX2.stage30.stage30_11_18_harvest_to_curated_adapter",
        "PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models",
        "PHX2.stage30.stage30_11_15_ping_dedupe_ledger",
        "PHX2.stage30.stage30_11_5_fake_live_wiring_proof",
    )
    for module in STAGE30_11_20_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_")
        for stage_n in range(21, 30):
            assert not module.startswith(f"PHX2.stage{stage_n}")
    joined = " ".join(STAGE30_11_20_ALLOWED_PHX2_IMPORTS)
    assert "stage28" not in joined
    assert "stage29" not in joined
    assert "stage30_4_3" not in joined
    assert "birdeye" not in joined
    assert "stage30_11_16" not in joined


# ---------------------------------------------------------------------------
# 4. Bounded caps + duck-typed price-source surface pins (mirrored)
# ---------------------------------------------------------------------------


def test_caps_pinned_and_mirror_committed_session() -> None:
    assert STAGE30_11_20_MAX_CANDIDATES_HARD_CAP == 10
    assert STAGE30_11_20_MAX_CANDIDATES_HARD_CAP == (
        STAGE30_11_17_MAX_CANDIDATES_HARD_CAP
    )
    assert STAGE30_11_20_DEFAULT_MAX_CANDIDATES == 10


def test_price_source_method_pinned_and_exists_on_committed_source() -> None:
    # The locked key decision: the NATIVE never-raises surface of the committed
    # Stage 29.2 price source, injected directly with NO read() shim.
    assert STAGE30_11_20_PRICE_SOURCE_METHOD == "fetch_snapshot"
    assert STAGE30_11_20_PRICE_SOURCE_METHOD == MODELS_SOURCE_METHOD
    assert callable(
        getattr(
            Stage29_2BirdeyePriceSource,
            STAGE30_11_20_PRICE_SOURCE_METHOD,
            None,
        )
    ), (
        "the committed Stage 29.2 price source must natively expose the "
        "duck-typed surface Stage 30.11.20 calls"
    )


def test_snapshot_required_attrs_pinned_and_match_models() -> None:
    assert STAGE30_11_20_PRICE_SNAPSHOT_REQUIRED_ATTRS == (
        "price_value",
        "birdeye_price_status",
        "fetched_at_utc",
    )
    assert STAGE30_11_20_PRICE_SNAPSHOT_REQUIRED_ATTRS == MODELS_SNAPSHOT_ATTRS


def test_price_status_tokens_mirror_stage29_2_by_value() -> None:
    # The committed production code imports NO Stage 29 module; the status
    # tokens are mirrored BY VALUE and this pin breaks loudly if Stage 29.2
    # ever renames one.
    assert STAGE30_11_20_PRICE_STATUS_PRESENT == BIRDEYE_PRICE_STATUS_PRESENT
    assert STAGE30_11_20_PRICE_STATUS_MISSING == BIRDEYE_PRICE_STATUS_MISSING
    assert STAGE30_11_20_PRICE_STATUS_SOURCE_ERROR == (
        BIRDEYE_PRICE_STATUS_SOURCE_ERROR
    )
    assert STAGE30_11_20_PRICE_STATUS_PRESENT == MODELS_STATUS_PRESENT
    assert STAGE30_11_20_PRICE_STATUS_MISSING == MODELS_STATUS_MISSING
    assert STAGE30_11_20_PRICE_STATUS_SOURCE_ERROR == (
        MODELS_STATUS_SOURCE_ERROR
    )


# ---------------------------------------------------------------------------
# 5. Closed-set vocabularies (mirrored)
# ---------------------------------------------------------------------------


def test_enrichment_decisions_pinned_and_match_models() -> None:
    assert STAGE30_11_20_ENRICHMENT_DECISIONS[0] == "ENRICHED"
    assert len(STAGE30_11_20_ENRICHMENT_DECISIONS) == 11
    assert STAGE30_11_20_ENRICHMENT_DECISIONS == MODELS_DECISIONS
    for decision in STAGE30_11_20_ENRICHMENT_DECISIONS[1:]:
        assert decision.startswith("SKIPPED_")
    for token in (
        "SKIPPED_NOT_BASE_FACTS",
        "SKIPPED_NO_PRICE_READING",
        "SKIPPED_NOT_A_PRICE_READING",
        "SKIPPED_PRICE_SOURCE_ERROR",
        "SKIPPED_PRICE_MISSING",
        "SKIPPED_PRICE_STATUS_UNRECOGNIZED",
        "SKIPPED_MISSING_PRICE_VALUE",
        "SKIPPED_INVALID_PRICE_VALUE",
        "SKIPPED_MISSING_PRICE_FETCHED_AT",
        "SKIPPED_INVALID_PRICE_FETCHED_AT",
    ):
        assert token in STAGE30_11_20_ENRICHMENT_DECISIONS


def test_redaction_statuses_pinned_and_match_models() -> None:
    assert STAGE30_11_20_REDACTION_STATUS_REDACTED == "REDACTED"
    assert STAGE30_11_20_REDACTION_STATUS_REDACTED == MODELS_REDACTED
    assert STAGE30_11_20_REDACTION_STATUSES == ("REDACTED", "REDACTION_VIOLATION")
    assert STAGE30_11_20_REDACTION_STATUSES == MODELS_REDACTION_STATUSES


# ---------------------------------------------------------------------------
# 6. Enriched price fields + dataclass field tuples (mirrored)
# ---------------------------------------------------------------------------


def test_enriched_price_fields_are_exactly_current_price() -> None:
    facts_field_names = {
        f.name for f in dataclass_fields(Stage30_11_18HarvestedCandidateFacts)
    }
    assert set(STAGE30_11_20_ENRICHED_PRICE_FIELDS) <= facts_field_names
    assert STAGE30_11_20_ENRICHED_PRICE_FIELDS == ("current_price",)
    # migration_time_utc is NEVER enriched here (the next separate seam) and the
    # Stage 30.11.19 market-context bundle is NEVER touched (in particular
    # market_context_fetched_at_utc is NOT overwritten).
    assert "migration_time_utc" not in STAGE30_11_20_ENRICHED_PRICE_FIELDS
    for market_field in STAGE30_11_19_ENRICHED_MARKET_FIELDS:
        assert market_field not in STAGE30_11_20_ENRICHED_PRICE_FIELDS
    # The two seams are disjoint: together they still leave migration_time_utc
    # un-enriched.
    overlap = set(STAGE30_11_20_ENRICHED_PRICE_FIELDS) & set(
        STAGE30_11_19_ENRICHED_MARKET_FIELDS
    )
    assert overlap == set()


def test_field_tuples_pinned_and_match_models() -> None:
    assert STAGE30_11_20_ENRICHMENT_RESULT_FIELDS == (
        price_enrichment_result_field_names()
    )
    assert STAGE30_11_20_ENRICHMENT_EVENT_FIELDS == (
        price_enrichment_event_field_names()
    )
    assert STAGE30_11_20_ENRICHMENT_SESSION_REPORT_FIELDS == (
        price_enrichment_session_report_field_names()
    )


def test_event_and_report_fields_carry_no_magnitude_url_or_secret() -> None:
    for name in (
        STAGE30_11_20_ENRICHMENT_EVENT_FIELDS
        + STAGE30_11_20_ENRICHMENT_SESSION_REPORT_FIELDS
    ):
        lower = name.lower()
        for forbidden in (
            "url",
            "secret",
            "webhook",
            "body",
            "price",
            "liquidity",
            "market_cap",
        ):
            assert forbidden not in lower, (
                f"Stage 30.11.20 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 7. Forbidden surfaces + next allowed stage + operator-auth note
# ---------------------------------------------------------------------------


def test_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_20_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_20_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_20_FORBIDDEN_SURFACES)
    for token in (
        "new price fetcher",
        "real provider transport construction",
        "Stage 29.2 price source edit",
        "Stage 29.2 price source import",
        "Stage 30.4.3 source import",
        "real transport",
        "real send",
        "Discord send",
        "env read",
        "live run",
        "Stage 28 direct import",
        "Stage 29 direct import",
        "migration_time enrichment",
        "market_context_fetched_at_utc overwrite",
        "read() shim",
        "silent pass-through on skip",
        "public routing",
        "subscriber routing",
        "wallet / signing",
        "automated trading",
        "commit",
        "tag",
        "push",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.20 forbidden surfaces must name {token!r}"
        )


def test_next_allowed_stage_is_the_separate_seams() -> None:
    assert STAGE30_11_20_NEXT_ALLOWED_STAGE == (
        "operator-authorized migration_time enrichment seam + real-fed dry-run "
        "ceremony (separate steps)"
    )


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_20_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True
    assert isinstance(STAGE30_11_20_LIVE_CEREMONY_NOTE, str)
    assert STAGE30_11_20_LIVE_CEREMONY_NOTE != ""


# ---------------------------------------------------------------------------
# 8. Manifest __all__ exports the surface + earlier sections survive
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_20_surface() -> None:
    for name in (
        "STAGE30_11_20_MINOR_VERSION",
        "STAGE30_11_20_REPORT_SCHEMA_VERSION",
        "STAGE30_11_20_SOURCE_STAGE",
        "STAGE30_11_20_SPEC_LOCK_FILENAME",
        "STAGE30_11_20_SPEC_LOCK_PATH_PARTS",
        "STAGE30_11_20_ENRICHMENT_MODELS_BASENAME",
        "STAGE30_11_20_ENRICHMENT_ADAPTER_BASENAME",
        "STAGE30_11_20_FAKE_ENRICHMENT_PROOF_BASENAME",
        "STAGE30_11_20_ENRICHMENT_MODELS_MODULE",
        "STAGE30_11_20_ENRICHMENT_ADAPTER_MODULE",
        "STAGE30_11_20_FAKE_ENRICHMENT_PROOF_MODULE",
        "STAGE30_11_20_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_20_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_20_TEST_BASENAMES",
        "STAGE30_11_20_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_20_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_20_MAX_CANDIDATES_HARD_CAP",
        "STAGE30_11_20_DEFAULT_MAX_CANDIDATES",
        "STAGE30_11_20_PRICE_SOURCE_METHOD",
        "STAGE30_11_20_PRICE_SNAPSHOT_REQUIRED_ATTRS",
        "STAGE30_11_20_PRICE_STATUS_PRESENT",
        "STAGE30_11_20_PRICE_STATUS_MISSING",
        "STAGE30_11_20_PRICE_STATUS_SOURCE_ERROR",
        "STAGE30_11_20_ENRICHMENT_DECISIONS",
        "STAGE30_11_20_ENRICHED_PRICE_FIELDS",
        "STAGE30_11_20_REDACTION_STATUS_REDACTED",
        "STAGE30_11_20_REDACTION_STATUSES",
        "STAGE30_11_20_ENRICHMENT_RESULT_FIELDS",
        "STAGE30_11_20_ENRICHMENT_EVENT_FIELDS",
        "STAGE30_11_20_ENRICHMENT_SESSION_REPORT_FIELDS",
        "STAGE30_11_20_NEXT_ALLOWED_STAGE",
        "STAGE30_11_20_FORBIDDEN_SURFACES",
        "STAGE30_11_20_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_20_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_sections_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_15_MINOR_VERSION",
        "STAGE30_11_17_MINOR_VERSION",
        "STAGE30_11_18_MINOR_VERSION",
        "STAGE30_11_19_MINOR_VERSION",
        "STAGE30_11_19_LIVE_CEREMONY_NOTE",
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES",
    ):
        assert name in M.__all__
