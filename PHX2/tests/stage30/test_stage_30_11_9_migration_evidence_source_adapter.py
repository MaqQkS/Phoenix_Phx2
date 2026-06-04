"""Stage 30.11.9 mint-keyed evidence-source adapter tests.

Proves the source binds STRICTLY by mint, collapses value-identical duplicates,
returns the single bound record VERBATIM, and fails closed (returns ``None``) on a
missing / wrong-mint / conflicting / raising / blank / malformed lookup -- INCLUDING a
record whose ``warnings`` field is malformed (a non-collection such as the bare string
``"MIGRATION_STALE"``), which must never be silently emptied into a not-stale ``()``.
Also proves the rename-only mapper carries every value verbatim (NEVER normalizing a
non-trailing-Z anchor, NEVER inventing a redaction-safe claim) and fails closed to
``None`` on a malformed ``warnings`` field, while a WELL-FORMED warnings (incl. one
carrying ``MIGRATION_STALE``) is preserved and left for Stage 30.11.8 to block.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_9_migration_evidence_source_adapter import (
    Stage30_11_9MigrationEvidenceSourceAdapter,
    build_evidence_record_from_sanitized_projection,
    build_migration_evidence_source,
    lookup_migration_evidence_in_provider,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_models import (
    Stage30_11_9MigrationEvidenceRecord,
)


def _record(token_mint: str, **kw: object) -> Stage30_11_9MigrationEvidenceRecord:
    # Default to an EXPLICIT empty warnings so these helper-built records stay
    # ROUTABLE (the model's own default is now None = fail-closed; the missing-warnings
    # case is exercised via direct dataclass construction in section 9 below).
    kw.setdefault("warnings", ())
    return Stage30_11_9MigrationEvidenceRecord(token_mint=token_mint, **kw)


def _provider_for(mapping: dict) -> object:
    """Build a mint-scoped provider returning ``mapping[mint]`` (or ``()``)."""

    def provider(token_mint: object) -> object:
        return mapping.get(token_mint, ())

    return provider


def _confirmable(token_mint: str, *, warnings: object) -> object:
    """An OTHERWISE-confirmable record (COMPLETE + SAFE + valid trailing-Z) carrying
    the given ``warnings`` value (possibly malformed) -- built via the dataclass
    DIRECTLY (the dataclass has no validation), so it exercises the ROUTER's warnings
    gate independently of the mapper.
    """
    return Stage30_11_9MigrationEvidenceRecord(
        token_mint=token_mint,
        measurement_status="COMPLETE",
        migration_event_time_utc="2026-05-27T00:00:00Z",
        warnings=warnings,  # type: ignore[arg-type]
        redaction_status="SAFE",
        source_ref="ref",
    )


# Malformed warnings shapes the source + mapper must fail closed on.
_MALFORMED_WARNINGS = (
    "MIGRATION_STALE",  # the Codex repro: a bare string, not a collection
    "anything",
    123,
    object(),
    {"warning": "MIGRATION_STALE"},  # a mapping
    {"MIGRATION_STALE"},  # a set
    frozenset({"MIGRATION_STALE"}),  # a frozenset
    ("MIGRATION_STALE", 123),  # a tuple carrying a non-string element
    ["ok", 5],  # a list carrying a non-string element
    None,  # missing / null
)

# Well-formed warnings shapes the source routes + the mapper accepts.
_WELLFORMED_WARNINGS = (
    (),
    [],
    ("MIGRATION_STALE",),
    ["MIGRATION_STALE"],
    ("MIGRATION_STALE", "MIGRATION_CONFLICT"),
)


# ---------------------------------------------------------------------------
# 1. Happy path: a single matching record is returned VERBATIM
# ---------------------------------------------------------------------------


def test_single_matching_record_returned_verbatim() -> None:
    record = _record(
        "mint-x",
        measurement_status="COMPLETE",
        migration_event_time_utc="2026-05-27T00:00:00Z",
        redaction_status="SAFE",
        source_ref="ref-x",
    )
    source = build_migration_evidence_source(_provider_for({"mint-x": [record]}))
    got = source.lookup_migration_evidence("mint-x")
    assert got is record  # the SAME object, unmodified
    assert got.measurement_status == "COMPLETE"
    assert got.migration_event_time_utc == "2026-05-27T00:00:00Z"
    assert got.redaction_status == "SAFE"
    assert got.source_ref == "ref-x"


def test_provider_may_return_a_single_record_not_a_sequence() -> None:
    record = _record("mint-x", measurement_status="COMPLETE")
    source = build_migration_evidence_source(_provider_for({"mint-x": record}))
    assert source.lookup_migration_evidence("mint-x") is record


def test_provider_may_return_a_flat_mapping_record() -> None:
    flat = {
        "token_mint": "mint-x",
        "measurement_status": "COMPLETE",
        "warnings": (),  # a well-formed (empty) warnings collection
    }
    source = build_migration_evidence_source(_provider_for({"mint-x": [flat]}))
    assert source.lookup_migration_evidence("mint-x") == flat


# ---------------------------------------------------------------------------
# 2. Missing evidence -> None
# ---------------------------------------------------------------------------


def test_absent_mint_returns_none() -> None:
    source = build_migration_evidence_source(_provider_for({}))
    assert source.lookup_migration_evidence("mint-absent") is None


def test_provider_returning_none_yields_none() -> None:
    source = build_migration_evidence_source(lambda mint: None)
    assert source.lookup_migration_evidence("mint-x") is None


def test_provider_returning_empty_sequence_yields_none() -> None:
    source = build_migration_evidence_source(lambda mint: [])
    assert source.lookup_migration_evidence("mint-x") is None


# ---------------------------------------------------------------------------
# 3. Wrong mint -> None (no cross-mint inheritance)
# ---------------------------------------------------------------------------


def test_record_bound_to_another_mint_is_not_returned() -> None:
    other = _record("some-other-mint", measurement_status="COMPLETE")
    source = build_migration_evidence_source(
        _provider_for({"mint-x": [other]})
    )
    assert source.lookup_migration_evidence("mint-x") is None


def test_sloppy_provider_returning_extra_mints_is_filtered_by_mint() -> None:
    want = _record("mint-x", measurement_status="COMPLETE")
    other = _record("mint-y", measurement_status="COMPLETE")
    # A provider that ignores the mint arg and returns ALL records.
    source = build_migration_evidence_source(lambda mint: [other, want])
    assert source.lookup_migration_evidence("mint-x") is want
    assert source.lookup_migration_evidence("mint-y") is other
    assert source.lookup_migration_evidence("mint-z") is None


def test_record_with_blank_mint_is_never_bound() -> None:
    blank = _record("", measurement_status="COMPLETE")
    source = build_migration_evidence_source(lambda mint: [blank])
    assert source.lookup_migration_evidence("mint-x") is None


# ---------------------------------------------------------------------------
# 4. Conflicting / duplicate records
# ---------------------------------------------------------------------------


def test_two_distinct_records_for_one_mint_fail_closed() -> None:
    a = _record("mint-x", measurement_status="COMPLETE")
    b = _record("mint-x", measurement_status="INVALID_MIGRATION")
    source = build_migration_evidence_source(_provider_for({"mint-x": [a, b]}))
    assert source.lookup_migration_evidence("mint-x") is None


def test_value_identical_duplicates_collapse_to_one() -> None:
    a = _record("mint-x", measurement_status="COMPLETE", source_ref="r")
    b = _record("mint-x", measurement_status="COMPLETE", source_ref="r")  # equal
    source = build_migration_evidence_source(_provider_for({"mint-x": [a, b]}))
    got = source.lookup_migration_evidence("mint-x")
    assert got == a


# ---------------------------------------------------------------------------
# 5. Blank / non-string requested mint -> None
# ---------------------------------------------------------------------------


def test_blank_or_nonstring_requested_mint_fails_closed() -> None:
    record = _record("mint-x", measurement_status="COMPLETE")
    source = build_migration_evidence_source(_provider_for({"mint-x": [record]}))
    assert source.lookup_migration_evidence("") is None
    assert source.lookup_migration_evidence("   ") is None
    assert source.lookup_migration_evidence(None) is None
    assert source.lookup_migration_evidence(123) is None


# ---------------------------------------------------------------------------
# 6. Source errors fail closed
# ---------------------------------------------------------------------------


def test_non_callable_provider_fails_closed() -> None:
    source = build_migration_evidence_source(None)
    assert source.lookup_migration_evidence("mint-x") is None
    source2 = build_migration_evidence_source("not-callable")
    assert source2.lookup_migration_evidence("mint-x") is None


def test_raising_provider_fails_closed() -> None:
    def boom(mint: object) -> object:
        raise RuntimeError("provider boom")

    source = build_migration_evidence_source(boom)
    assert source.lookup_migration_evidence("mint-x") is None


def test_malformed_records_are_skipped() -> None:
    # A provider yielding non-record junk: ints, strings, a None.
    source = build_migration_evidence_source(lambda mint: [42, "junk", None])
    assert source.lookup_migration_evidence("mint-x") is None


def test_string_return_is_treated_as_single_unmatched_record() -> None:
    # A bare string is NOT iterated char-by-char; it is one (malformed) record.
    source = build_migration_evidence_source(lambda mint: "mint-x")
    assert source.lookup_migration_evidence("mint-x") is None


# ---------------------------------------------------------------------------
# 7. Adapter surface + module-level helper parity
# ---------------------------------------------------------------------------


def test_adapter_exposes_provider_and_is_constructible_directly() -> None:
    provider = _provider_for({})
    adapter = Stage30_11_9MigrationEvidenceSourceAdapter(provider)
    assert adapter.record_provider is provider
    assert adapter.lookup_migration_evidence("mint-x") is None


def test_module_level_lookup_matches_adapter() -> None:
    record = _record("mint-x", measurement_status="COMPLETE")
    provider = _provider_for({"mint-x": [record]})
    assert lookup_migration_evidence_in_provider(provider, "mint-x") is record
    assert lookup_migration_evidence_in_provider(provider, "mint-y") is None


# ---------------------------------------------------------------------------
# 8. The rename-only mapper: verbatim carry, no cleanup, fail-closed coercions
# ---------------------------------------------------------------------------


def test_mapper_carries_values_verbatim() -> None:
    record = build_evidence_record_from_sanitized_projection(
        token_mint="mint-x",
        measurement_status="COMPLETE",
        migration_event_time_utc="2026-05-27T00:00:00Z",
        warnings=("MIGRATION_STALE",),
        redaction_status="SAFE",
        source_ref="ref-x",
    )
    assert record is not None
    assert record.token_mint == "mint-x"
    assert record.measurement_status == "COMPLETE"
    assert record.migration_event_time_utc == "2026-05-27T00:00:00Z"
    assert record.warnings == ("MIGRATION_STALE",)
    assert record.redaction_status == "SAFE"
    assert record.source_ref == "ref-x"


def test_mapper_never_normalizes_a_non_trailing_z_anchor() -> None:
    # An offset-form anchor is preserved EXACTLY (the Stage 30.11.8 confirmation, not
    # the mapper, rejects it). No cleanup that would turn a bad timestamp valid.
    record = build_evidence_record_from_sanitized_projection(
        token_mint="mint-x",
        measurement_status="COMPLETE",
        migration_event_time_utc="2026-05-27T00:00:00+00:00",
        warnings=(),  # explicit empty so the record routes; isolates the anchor check
        redaction_status="SAFE",
    )
    assert record is not None
    assert record.migration_event_time_utc == "2026-05-27T00:00:00+00:00"


def test_mapper_non_string_fields_coerce_to_none_with_valid_warnings() -> None:
    # With a WELL-FORMED warnings, a non-string status / anchor / redaction / ref /
    # mint each degrades to None (fail-closed downstream); the record is still built.
    record = build_evidence_record_from_sanitized_projection(
        token_mint=123,
        measurement_status=object(),
        migration_event_time_utc=42,
        warnings=(),
        redaction_status=object(),
        source_ref=object(),
    )
    assert record is not None
    assert record.token_mint is None
    assert record.measurement_status is None
    assert record.migration_event_time_utc is None
    assert record.warnings == ()
    assert record.redaction_status is None
    assert record.source_ref is None


def test_mapper_omitted_warnings_fails_closed() -> None:
    # The Codex re-audit repro at the mapper layer: an OMITTED warnings (the param
    # default) is MISSING, not "no warnings", so the mapper fails closed to None -- it
    # must NEVER build a record with a clean empty () from an omitted field.
    assert (
        build_evidence_record_from_sanitized_projection(
            token_mint="mint-x",
            measurement_status="COMPLETE",
            migration_event_time_utc="2026-05-27T00:00:00Z",
            redaction_status="SAFE",
        )
        is None
    )
    # An explicitly-None warnings is likewise rejected.
    assert (
        build_evidence_record_from_sanitized_projection(
            token_mint="mint-x", warnings=None
        )
        is None
    )


def test_mapper_wellformed_warnings_preserved_and_normalized_to_tuple() -> None:
    record = build_evidence_record_from_sanitized_projection(
        token_mint="mint-x",
        warnings=["MIGRATION_STALE", "MIGRATION_CONFLICT"],
    )
    assert record is not None
    assert record.warnings == ("MIGRATION_STALE", "MIGRATION_CONFLICT")
    empty_list = build_evidence_record_from_sanitized_projection(
        token_mint="mint-x", warnings=[]
    )
    assert empty_list is not None
    assert empty_list.warnings == ()


# ---------------------------------------------------------------------------
# 9. Malformed warnings fail closed (Codex repro): stale-but-malformed warnings
#    must NEVER become confirmable clean evidence -- at the mapper AND the router
# ---------------------------------------------------------------------------


def test_mapper_rejects_bare_string_migration_stale() -> None:
    # The Codex repro at the mapper layer: a bare "MIGRATION_STALE" string must NOT
    # be silently emptied into a not-stale (); the mapper fails closed to None.
    assert (
        build_evidence_record_from_sanitized_projection(
            token_mint="mint-x",
            measurement_status="COMPLETE",
            migration_event_time_utc="2026-05-27T00:00:00Z",
            warnings="MIGRATION_STALE",
            redaction_status="SAFE",
        )
        is None
    )


def test_mapper_rejects_every_malformed_warnings_shape() -> None:
    for bad in _MALFORMED_WARNINGS:
        assert (
            build_evidence_record_from_sanitized_projection(
                token_mint="mint-x",
                measurement_status="COMPLETE",
                migration_event_time_utc="2026-05-27T00:00:00Z",
                warnings=bad,
                redaction_status="SAFE",
            )
            is None
        ), f"mapper must reject malformed warnings {bad!r}"


def test_mapper_accepts_every_wellformed_warnings_shape() -> None:
    for good in _WELLFORMED_WARNINGS:
        record = build_evidence_record_from_sanitized_projection(
            token_mint="mint-x",
            measurement_status="COMPLETE",
            migration_event_time_utc="2026-05-27T00:00:00Z",
            warnings=good,
            redaction_status="SAFE",
        )
        assert record is not None, f"mapper must accept well-formed {good!r}"
        assert record.warnings == tuple(good)


def test_lookup_fails_closed_on_bare_string_warnings() -> None:
    # The Codex repro at the source/router layer: an otherwise-confirmable record
    # whose warnings is the bare string "MIGRATION_STALE" must NOT be routed.
    rec = _confirmable("mint-x", warnings="MIGRATION_STALE")
    source = build_migration_evidence_source(_provider_for({"mint-x": [rec]}))
    assert source.lookup_migration_evidence("mint-x") is None


def test_lookup_fails_closed_on_every_malformed_warnings_shape() -> None:
    for bad in _MALFORMED_WARNINGS:
        rec = _confirmable("mint-x", warnings=bad)
        source = build_migration_evidence_source(
            _provider_for({"mint-x": [rec]})
        )
        assert source.lookup_migration_evidence("mint-x") is None, (
            f"lookup must fail closed on malformed warnings {bad!r}"
        )


def test_lookup_routes_every_wellformed_warnings_shape() -> None:
    # A well-formed warnings (tuple/list of strings), INCLUDING one carrying
    # MIGRATION_STALE, is routed VERBATIM; Stage 30.11.8 (not the source) decides
    # staleness. Empty warnings is routed.
    for good in _WELLFORMED_WARNINGS:
        rec = _confirmable("mint-x", warnings=good)
        source = build_migration_evidence_source(
            _provider_for({"mint-x": [rec]})
        )
        assert source.lookup_migration_evidence("mint-x") is rec, (
            f"lookup must route well-formed warnings {good!r}"
        )


def test_dict_record_missing_warnings_fails_closed() -> None:
    flat = {
        "token_mint": "mint-x",
        "measurement_status": "COMPLETE",
        "migration_event_time_utc": "2026-05-27T00:00:00Z",
        "redaction_status": "SAFE",
    }  # no "warnings" key -> malformed (missing) -> fail closed
    source = build_migration_evidence_source(_provider_for({"mint-x": [flat]}))
    assert source.lookup_migration_evidence("mint-x") is None


def test_dict_record_with_empty_warnings_routes() -> None:
    flat = {
        "token_mint": "mint-x",
        "measurement_status": "COMPLETE",
        "warnings": (),
    }
    source = build_migration_evidence_source(_provider_for({"mint-x": [flat]}))
    assert source.lookup_migration_evidence("mint-x") == flat


def test_dataclass_record_omitting_warnings_fails_closed_at_router() -> None:
    # The Codex re-audit repro at the source/router layer: a record built WITHOUT
    # warnings carries the model's fail-closed default (None); even when otherwise
    # confirmable, the router refuses to route it (a missing field is NOT "no
    # warnings"). Built via the dataclass directly (NOT the _record helper, which
    # injects an explicit ()).
    rec = Stage30_11_9MigrationEvidenceRecord(
        token_mint="mint-x",
        measurement_status="COMPLETE",
        migration_event_time_utc="2026-05-27T00:00:00Z",
        redaction_status="SAFE",
    )
    assert rec.warnings is None  # the fail-closed default
    source = build_migration_evidence_source(_provider_for({"mint-x": [rec]}))
    assert source.lookup_migration_evidence("mint-x") is None
