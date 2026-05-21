"""Synthetic Stage 25 test fixture builders.

These helpers build deterministic, secret-free synthetic Stage 25
records and JSONL row dicts used by the Stage 25 test suite. No
live provider payloads are checked into the repository; the
fixtures are constructed from short non-secret literals.

The builders are intentionally simple wrappers around the Stage
25 production model and input-reader surfaces so the test suite
exercises the same closed-set validation and projection paths
the production runner / measurer implementations will exercise
in 25.2+.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, Optional

from PHX2.stage25.constants import (
    INPUT_KIND_SYNTHETIC_MIGRATION_OBSERVATIONS_JSONL,
    INPUT_KIND_SYNTHETIC_PRICE_OBSERVATIONS_JSONL,
    QUOTE_DENOMINATION_USD_MICRO,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_FAMILY_ON_CHAIN_SWAP_REPLAY,
    SOURCE_STATUS_PRESENT,
)
from PHX2.stage25.models import (
    Stage25MigrationObservation,
    Stage25PriceObservation,
    build_migration_observation,
    build_price_observation,
)


# ---------------------------------------------------------------------------
# Injected-clock literal
# ---------------------------------------------------------------------------


FIXED_CLOCK_UTC: str = "2026-01-01T00:00:00Z"


# Convenience: short non-secret token-mint literals used by tests.
SAMPLE_TOKEN_MINT_A: str = "MintAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SAMPLE_TOKEN_MINT_B: str = "MintBbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
SAMPLE_TOKEN_MINT_C: str = "MintCcccccccccccccccccccccccccccccccccccccc"
SAMPLE_MIGRATION_POOL: str = "PoolXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
SAMPLE_MIGRATION_SIG: str = "sig_migration_synthetic_001"
SAMPLE_MIGRATION_SIG_ALT: str = "sig_migration_synthetic_002"
SAMPLE_MIGRATION_SIG_THIRD: str = "sig_migration_synthetic_003"


def _frozen_empty_mapping() -> Mapping[str, object]:
    return MappingProxyType({})


# ---------------------------------------------------------------------------
# Synthetic Stage 25 record builders
# ---------------------------------------------------------------------------


def make_migration_observation(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_BIRDEYE,
    source_status: str = SOURCE_STATUS_PRESENT,
    observed_at_utc: str = FIXED_CLOCK_UTC,
    slot: int = 251_000_000,
    block_time: int = 1_750_000_000,
    migration_signature: str = SAMPLE_MIGRATION_SIG,
    migration_pool: str = SAMPLE_MIGRATION_POOL,
    provider_id: str = "fake_provider",
    reason_codes: tuple[str, ...] = (),
    evidence: Optional[Mapping[str, object]] = None,
    input_missing_fields: tuple[str, ...] = (),
) -> Stage25MigrationObservation:
    """Build a synthetic ``Stage25MigrationObservation`` with safe defaults.

    All defaults are short non-secret strings / integers; the
    builder is deterministic so two invocations with the same
    arguments produce byte-identical records (including the
    derived ``observation_hash`` field).
    """
    evidence_mapping = (
        evidence if evidence is not None else _frozen_empty_mapping()
    )
    return build_migration_observation(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        observed_at_utc=observed_at_utc,
        slot=slot,
        block_time=block_time,
        migration_signature=migration_signature,
        migration_pool=migration_pool,
        provider_id=provider_id,
        reason_codes=reason_codes,
        evidence=evidence_mapping,
        input_missing_fields=input_missing_fields,
    )


def make_price_observation(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_DEXSCREENER,
    source_status: str = SOURCE_STATUS_PRESENT,
    observed_at_utc: str = FIXED_CLOCK_UTC,
    slot: int = 251_000_010,
    block_time: int = 1_750_000_010,
    price: Optional[int] = 1_234_567,
    quote_denomination: str = QUOTE_DENOMINATION_USD_MICRO,
    provider_id: str = "fake_provider",
    reason_codes: tuple[str, ...] = (),
    evidence: Optional[Mapping[str, object]] = None,
    input_missing_fields: tuple[str, ...] = (),
) -> Stage25PriceObservation:
    """Build a synthetic ``Stage25PriceObservation`` with safe defaults."""
    evidence_mapping = (
        evidence if evidence is not None else _frozen_empty_mapping()
    )
    return build_price_observation(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        observed_at_utc=observed_at_utc,
        slot=slot,
        block_time=block_time,
        price=price,
        quote_denomination=quote_denomination,
        provider_id=provider_id,
        reason_codes=reason_codes,
        evidence=evidence_mapping,
        input_missing_fields=input_missing_fields,
    )


# ---------------------------------------------------------------------------
# JSONL row builders
# ---------------------------------------------------------------------------


def make_migration_observation_row(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_BIRDEYE,
    source_status: str = SOURCE_STATUS_PRESENT,
    observed_at_utc: str = FIXED_CLOCK_UTC,
    slot: int = 251_000_000,
    block_time: int = 1_750_000_000,
    migration_signature: str = SAMPLE_MIGRATION_SIG,
    migration_pool: str = SAMPLE_MIGRATION_POOL,
    provider_id: str = "fake_provider",
    reason_codes: tuple[str, ...] = (),
    evidence: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    """Build a Stage 25-shaped migration-observation JSONL row as a plain dict.

    Tests serialize the dict via ``json.dumps`` and write it to a
    JSONL file for the input-reader tests. The dict carries only
    short non-secret literals.
    """
    if evidence is None:
        evidence = {"raw_pool_kind": "amm"}
    return {
        "token_mint": token_mint,
        "source_family": source_family,
        "source_status": source_status,
        "observed_at_utc": observed_at_utc,
        "slot": slot,
        "block_time": block_time,
        "migration_signature": migration_signature,
        "migration_pool": migration_pool,
        "provider_id": provider_id,
        "reason_codes": list(reason_codes),
        "evidence": evidence,
    }


def make_price_observation_row(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_DEXSCREENER,
    source_status: str = SOURCE_STATUS_PRESENT,
    observed_at_utc: str = FIXED_CLOCK_UTC,
    slot: int = 251_000_010,
    block_time: int = 1_750_000_010,
    price: Optional[int] = 1_234_567,
    quote_denomination: str = QUOTE_DENOMINATION_USD_MICRO,
    provider_id: str = "fake_provider",
    reason_codes: tuple[str, ...] = (),
    evidence: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    """Build a Stage 25-shaped price-observation JSONL row as a plain dict."""
    if evidence is None:
        evidence = {"window_label": "post_migration_primary"}
    row: dict[str, object] = {
        "token_mint": token_mint,
        "source_family": source_family,
        "source_status": source_status,
        "observed_at_utc": observed_at_utc,
        "slot": slot,
        "block_time": block_time,
        "quote_denomination": quote_denomination,
        "provider_id": provider_id,
        "reason_codes": list(reason_codes),
        "evidence": evidence,
    }
    if price is not None:
        row["price"] = price
    else:
        row["price"] = None
    return row


# ---------------------------------------------------------------------------
# Intentionally malformed / leaky rows for the input reader tests
# ---------------------------------------------------------------------------


def make_migration_row_with_secret_field_name() -> dict[str, object]:
    """Migration row that carries a forbidden secret-bearing field name."""
    base = make_migration_observation_row(
        migration_signature="sig_secret_field_001",
    )
    base["api_key"] = "fake_value_001"
    return base


def make_migration_row_with_url_value() -> dict[str, object]:
    """Migration row whose ``provider_id`` carries a URL substring."""
    return make_migration_observation_row(
        migration_signature="sig_url_value_001",
        provider_id="ht" + "tps://fake-rpc.example/path",
    )


def make_migration_row_with_long_hex_credential() -> dict[str, object]:
    """Migration row carrying a 64-hex-char credential-shape token value."""
    return make_migration_observation_row(
        migration_signature="sig_hex_001",
        migration_pool=("a" * 64),
    )


def make_migration_row_with_nested_secret_key() -> dict[str, object]:
    """Migration row whose ``evidence`` mapping carries a nested secret key."""
    return make_migration_observation_row(
        evidence={"raw_pool_kind": "amm", "authorization": "fake"},
    )


def make_price_row_with_secret_field_name() -> dict[str, object]:
    """Price row that carries a forbidden secret-bearing field name."""
    base = make_price_observation_row()
    base["webhook_url"] = "fake_value_002"
    return base


def make_price_row_with_url_value() -> dict[str, object]:
    """Price row whose ``provider_id`` carries a URL substring."""
    return make_price_observation_row(
        provider_id="ht" + "tps://fake-rpc.example/path",
    )


__all__ = [
    "FIXED_CLOCK_UTC",
    "SAMPLE_MIGRATION_POOL",
    "SAMPLE_MIGRATION_SIG",
    "SAMPLE_MIGRATION_SIG_ALT",
    "SAMPLE_MIGRATION_SIG_THIRD",
    "SAMPLE_TOKEN_MINT_A",
    "SAMPLE_TOKEN_MINT_B",
    "SAMPLE_TOKEN_MINT_C",
    "make_migration_observation",
    "make_migration_observation_row",
    "make_migration_row_with_long_hex_credential",
    "make_migration_row_with_nested_secret_key",
    "make_migration_row_with_secret_field_name",
    "make_migration_row_with_url_value",
    "make_price_observation",
    "make_price_observation_row",
    "make_price_row_with_secret_field_name",
    "make_price_row_with_url_value",
]
