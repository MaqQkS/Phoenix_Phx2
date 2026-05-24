"""Stage 28.10 Chainstack Yellowstone models tests.

Pin:

  * closed-set vocabularies + validators,
  * config builder accepts safe values + rejects unsafe values,
  * payload builder accepts safe values + rejects unsafe values,
  * normalized event builder accepts safe values + rejects unsafe
    values,
  * repr / dict projection is redaction-safe,
  * safe-shape validators refuse URL-like / secret-like values,
  * quote-asset / pair-type / bonding-curve hint enums are
    closed-set and rejected when off-set.

No network. No env reads.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage28.chainstack_yellowstone_models import (
    AUTH_MODE_UNKNOWN,
    AUTH_MODE_USERNAME_PASSWORD,
    AUTH_MODE_VALUES,
    AUTH_MODE_XTOKEN,
    BONDING_CURVE_VERSION_HINT_SOL_LEGACY,
    BONDING_CURVE_VERSION_HINT_UNKNOWN,
    BONDING_CURVE_VERSION_HINT_USDC_FIXED,
    BONDING_CURVE_VERSION_HINT_VALUES,
    CHAIN_SOLANA,
    CHAIN_VALUES,
    EVENT_TYPE_MIGRATION,
    EVENT_TYPE_MINT,
    EVENT_TYPE_SWAP,
    EVENT_TYPE_VALUES,
    INSTRUCTION_KIND_PUMP_CREATE,
    INSTRUCTION_KIND_PUMP_MIGRATION,
    INSTRUCTION_KIND_PUMP_SWAP,
    INSTRUCTION_KIND_UNKNOWN,
    INSTRUCTION_KIND_VALUES,
    PAIR_TYPE_HINT_PUMP_SOL,
    PAIR_TYPE_HINT_PUMP_USDC,
    PAIR_TYPE_HINT_UNKNOWN,
    PAIR_TYPE_HINT_VALUES,
    PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
    PROVIDER_KIND_VALUES,
    QUOTE_ASSET_HINT_SOL,
    QUOTE_ASSET_HINT_UNKNOWN,
    QUOTE_ASSET_HINT_USDC,
    QUOTE_ASSET_HINT_VALUES,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    REDACTION_STATUS_VALUES,
    SOURCE_KIND_FAKE,
    SOURCE_KIND_PROTOCOL,
    SOURCE_KIND_VALUES,
    STAGE28_10_MINOR_VERSION,
    STAGE28_10_NORMALIZED_EVENT_HINT_FIELDS,
    STAGE28_10_NORMALIZED_EVENT_REQUIRED_FIELDS,
    STAGE28_10_PAYLOAD_FIELD_NAMES,
    STAGE28_10_REDACTION_TOKEN,
    STAGE28_10_SCHEMA_VERSION,
    Stage28_10ChainstackYellowstoneConfig,
    Stage28_10ChainstackYellowstoneError,
    Stage28_10ChainstackYellowstonePayload,
    Stage28_10InvalidConfigError,
    Stage28_10InvalidNormalizedEventError,
    Stage28_10InvalidPayloadError,
    Stage28_10NormalizedEvent,
    build_chainstack_yellowstone_config,
    build_chainstack_yellowstone_payload,
    build_normalized_event,
    config_to_dict,
    is_auth_mode_value,
    is_bonding_curve_version_hint_value,
    is_chain_value,
    is_event_type_value,
    is_instruction_kind_value,
    is_pair_type_hint_value,
    is_provider_kind_value,
    is_quote_asset_hint_value,
    is_redaction_status_value,
    is_safe_iso_utc,
    is_safe_payload_string,
    is_safe_provider_label,
    is_source_kind_value,
    payload_to_dict,
)


# ---------------------------------------------------------------------------
# Version axes
# ---------------------------------------------------------------------------


def test_minor_version_is_28_10():
    assert STAGE28_10_MINOR_VERSION == "28.10"


def test_schema_version_is_locked():
    assert (
        STAGE28_10_SCHEMA_VERSION
        == "stage28_10_chainstack_yellowstone_v0"
    )


def test_redaction_token_is_distinct():
    assert "STAGE28_10" in STAGE28_10_REDACTION_TOKEN
    assert STAGE28_10_REDACTION_TOKEN.startswith("<<")
    assert STAGE28_10_REDACTION_TOKEN.endswith(">>")


# ---------------------------------------------------------------------------
# Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_provider_kind_closed_set():
    assert PROVIDER_KIND_VALUES == (
        PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
    )
    assert is_provider_kind_value(
        PROVIDER_KIND_CHAINSTACK_YELLOWSTONE
    )
    assert not is_provider_kind_value("helius_grpc")
    assert not is_provider_kind_value(None)
    assert not is_provider_kind_value(0)


def test_auth_mode_closed_set():
    assert set(AUTH_MODE_VALUES) == {
        AUTH_MODE_XTOKEN,
        AUTH_MODE_USERNAME_PASSWORD,
        AUTH_MODE_UNKNOWN,
    }
    for token in AUTH_MODE_VALUES:
        assert is_auth_mode_value(token)
    assert not is_auth_mode_value("OAUTH2")
    assert not is_auth_mode_value(None)


def test_chain_closed_set():
    assert CHAIN_VALUES == (CHAIN_SOLANA,)
    assert is_chain_value(CHAIN_SOLANA)
    assert not is_chain_value("ETHEREUM")


def test_source_kind_closed_set():
    assert set(SOURCE_KIND_VALUES) == {
        SOURCE_KIND_FAKE,
        SOURCE_KIND_PROTOCOL,
    }
    assert is_source_kind_value(SOURCE_KIND_FAKE)
    assert is_source_kind_value(SOURCE_KIND_PROTOCOL)
    assert not is_source_kind_value("REAL")


def test_event_type_closed_set():
    assert set(EVENT_TYPE_VALUES) == {
        EVENT_TYPE_SWAP,
        EVENT_TYPE_MIGRATION,
        EVENT_TYPE_MINT,
    }
    for token in EVENT_TYPE_VALUES:
        assert is_event_type_value(token)
    assert not is_event_type_value("burn")


def test_instruction_kind_closed_set():
    assert set(INSTRUCTION_KIND_VALUES) == {
        INSTRUCTION_KIND_PUMP_SWAP,
        INSTRUCTION_KIND_PUMP_MIGRATION,
        INSTRUCTION_KIND_PUMP_CREATE,
        INSTRUCTION_KIND_UNKNOWN,
    }
    for token in INSTRUCTION_KIND_VALUES:
        assert is_instruction_kind_value(token)
    assert not is_instruction_kind_value("RAYDIUM_SWAP")


def test_quote_asset_hint_closed_set():
    assert set(QUOTE_ASSET_HINT_VALUES) == {
        QUOTE_ASSET_HINT_SOL,
        QUOTE_ASSET_HINT_USDC,
        QUOTE_ASSET_HINT_UNKNOWN,
    }
    for token in QUOTE_ASSET_HINT_VALUES:
        assert is_quote_asset_hint_value(token)
    assert not is_quote_asset_hint_value("BONK")


def test_pair_type_hint_closed_set():
    assert set(PAIR_TYPE_HINT_VALUES) == {
        PAIR_TYPE_HINT_PUMP_SOL,
        PAIR_TYPE_HINT_PUMP_USDC,
        PAIR_TYPE_HINT_UNKNOWN,
    }
    for token in PAIR_TYPE_HINT_VALUES:
        assert is_pair_type_hint_value(token)
    assert not is_pair_type_hint_value("RAYDIUM_SOL")


def test_bonding_curve_version_hint_closed_set():
    assert set(BONDING_CURVE_VERSION_HINT_VALUES) == {
        BONDING_CURVE_VERSION_HINT_SOL_LEGACY,
        BONDING_CURVE_VERSION_HINT_USDC_FIXED,
        BONDING_CURVE_VERSION_HINT_UNKNOWN,
    }
    for token in BONDING_CURVE_VERSION_HINT_VALUES:
        assert is_bonding_curve_version_hint_value(token)
    assert not is_bonding_curve_version_hint_value("V99")


def test_redaction_status_closed_set():
    assert set(REDACTION_STATUS_VALUES) == {
        REDACTION_STATUS_SAFE,
        REDACTION_STATUS_REDACTED,
    }
    for token in REDACTION_STATUS_VALUES:
        assert is_redaction_status_value(token)
    assert not is_redaction_status_value("PARTIAL")


# ---------------------------------------------------------------------------
# Safe-shape validators
# ---------------------------------------------------------------------------


def test_is_safe_provider_label_accepts_short_alnum():
    assert is_safe_provider_label("chainstack_yellowstone_prod")
    assert is_safe_provider_label("helius-grpc-mainnet")
    assert is_safe_provider_label("a")


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        123,
        "_leading_underscore",
        "trailing_underscore_",
        "has space",
        "has/slash",
        "h" + "ttps://endpoint.example",
        "secret=abc",
        "token=xyz",
        "bearer_prefixed",
        "a" * 65,
    ],
)
def test_is_safe_provider_label_rejects_unsafe(value):
    assert not is_safe_provider_label(value)


def test_is_safe_payload_string_accepts_legitimate_solana_shapes():
    """Legitimate Solana public mints / event-id shapes that do NOT
    overlap with private-key-like prefixes must still pass."""
    assert is_safe_payload_string(
        "So11111111111111111111111111111111111111112"
    )
    # USDC mint
    assert is_safe_payload_string(
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    )
    # Solana transaction signature starting with a non-WIF base58
    # character (1-9, A-J, M-Z, a-k, m-z, excluding 0, O, I, l).
    assert is_safe_payload_string(
        "2bnLp2WHCY"
        + "x" * 70
    )
    assert is_safe_payload_string("event:abc.123")


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        "has space",
        "h" + "ttps://endpoint.example",
        "bearer abc",
        "a" * 129,
    ],
)
def test_is_safe_payload_string_rejects_unsafe(value):
    assert not is_safe_payload_string(value)


# ---------------------------------------------------------------------------
# Private-key-like rejection
# ---------------------------------------------------------------------------


_PRIVATE_KEY_LIKE_VALUES: tuple[str, ...] = (
    # Bitcoin WIF private-key prefixes (5K, 5J, 5H, 5L)
    "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK",
    "5JaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa",
    "5H1234567890abcdef1234567890abcdef1234567890abcd",
    "5LzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZzZ",
    # Bracketed JSON array (Solana keypair JSON export shape)
    "[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]",
    "[" + ",".join(str(i) for i in range(64)) + "]",
    # Pure-hex 64+ chars (raw 32-byte / 64-byte key bytes hex)
    "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    "e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",  # 64 hex
    "0123456789abcdef" * 8,  # 128 hex
    # Base64-padded long string (raw key bytes base64-encoded)
    "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ==",
    "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4=",
)


@pytest.mark.parametrize("value", _PRIVATE_KEY_LIKE_VALUES)
def test_is_safe_payload_string_rejects_private_key_like(value):
    """``is_safe_payload_string`` must refuse every private-key-
    like shape that downstream models might otherwise serialize
    on a public record."""
    assert not is_safe_payload_string(value), (
        f"is_safe_payload_string must reject private-key-like "
        f"value (len={len(value)}, prefix={value[:4]!r})"
    )


@pytest.mark.parametrize("value", _PRIVATE_KEY_LIKE_VALUES)
def test_is_safe_provider_label_rejects_private_key_like(value):
    """``is_safe_provider_label`` must refuse every private-key-
    like shape that public provider / endpoint labels might
    otherwise leak."""
    assert not is_safe_provider_label(value), (
        f"is_safe_provider_label must reject private-key-like "
        f"value (len={len(value)}, prefix={value[:4]!r})"
    )


def test_is_safe_payload_string_rejects_webhook_substring():
    assert not is_safe_payload_string("my_webhook_id_xxxx")


def test_is_safe_provider_label_rejects_webhook_substring():
    assert not is_safe_provider_label("my_webhook_id_xxxx")


@pytest.mark.parametrize(
    "value",
    [
        "x_api_key_xyz",
        "x-api-key-xyz",
        "auth_token_xyz",
        "access_token_xyz",
        "refresh_token_xyz",
        "x_token_value",
        "xtoken_value",
    ],
)
def test_is_safe_provider_label_rejects_api_token_like(value):
    assert not is_safe_provider_label(value)


@pytest.mark.parametrize(
    "value",
    [
        "x_api_key_xyz",
        "x-api-key-xyz",
        "auth_token_xyz",
        "access_token_xyz",
        "refresh_token_xyz",
        "x_token_value",
        "xtoken_value",
    ],
)
def test_is_safe_payload_string_rejects_api_token_like(value):
    assert not is_safe_payload_string(value)


def test_is_safe_iso_utc_accepts_common_shapes():
    assert is_safe_iso_utc("2026-05-24T12:00:00Z")
    assert is_safe_iso_utc("2026-05-24T12:00:00.123Z")
    assert is_safe_iso_utc("2026-05-24T12:00:00+00:00")


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        "not-a-date",
        "2026/05/24 12:00:00",
        "2026-05-24",
    ],
)
def test_is_safe_iso_utc_rejects_unsafe(value):
    assert not is_safe_iso_utc(value)


# ---------------------------------------------------------------------------
# Config builder + validation
# ---------------------------------------------------------------------------


def _good_config_kwargs():
    return {
        "provider_id": "chainstack_yellowstone_prod",
        "endpoint_safe_label": "yellowstone-mainnet",
        "auth_mode": AUTH_MODE_XTOKEN,
        "max_events": 32,
    }


def test_build_config_accepts_safe_values():
    record = build_chainstack_yellowstone_config(
        **_good_config_kwargs(),
    )
    assert isinstance(
        record, Stage28_10ChainstackYellowstoneConfig,
    )
    assert record.provider_id == "chainstack_yellowstone_prod"
    assert (
        record.provider_kind
        == PROVIDER_KIND_CHAINSTACK_YELLOWSTONE
    )
    assert record.endpoint_safe_label == "yellowstone-mainnet"
    assert record.auth_mode == AUTH_MODE_XTOKEN
    assert record.chain == CHAIN_SOLANA
    assert record.max_events == 32
    assert record.cursor is None
    assert record.redaction_status == REDACTION_STATUS_SAFE


def test_build_config_accepts_optional_cursor():
    record = build_chainstack_yellowstone_config(
        cursor="cursor_abc",
        **_good_config_kwargs(),
    )
    assert record.cursor == "cursor_abc"


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("provider_id", ""),
        ("provider_id", "h" + "ttps://leak.example"),
        ("provider_id", "_leading"),
        ("endpoint_safe_label", ""),
        ("endpoint_safe_label", "bearer-prefix"),
        ("auth_mode", "OAUTH2"),
        ("max_events", 0),
        ("max_events", -1),
        ("max_events", 1.5),
        ("max_events", True),
    ],
)
def test_build_config_rejects_unsafe(field, bad_value):
    kwargs = _good_config_kwargs()
    kwargs[field] = bad_value
    with pytest.raises(Stage28_10InvalidConfigError):
        build_chainstack_yellowstone_config(**kwargs)


def test_build_config_rejects_unsafe_provider_kind():
    kwargs = _good_config_kwargs()
    with pytest.raises(Stage28_10InvalidConfigError):
        build_chainstack_yellowstone_config(
            provider_kind="HELIUS_GRPC", **kwargs,
        )


def test_build_config_rejects_unsafe_chain():
    kwargs = _good_config_kwargs()
    with pytest.raises(Stage28_10InvalidConfigError):
        build_chainstack_yellowstone_config(
            chain="ETHEREUM", **kwargs,
        )


def test_build_config_rejects_unsafe_cursor():
    kwargs = _good_config_kwargs()
    with pytest.raises(Stage28_10InvalidConfigError):
        build_chainstack_yellowstone_config(
            cursor="h" + "ttps://leak.example/cursor",
            **kwargs,
        )


def test_config_repr_redaction_safe():
    record = build_chainstack_yellowstone_config(
        **_good_config_kwargs(),
    )
    rendered = repr(record)
    forbidden_needles = (
        "h" + "ttps://",
        "h" + "ttp://",
        "bearer",
        "token=",
        "secret=",
        "password",
    )
    for needle in forbidden_needles:
        assert needle not in rendered.lower(), (
            f"config repr leaked {needle!r}"
        )


def test_config_to_dict_includes_all_fields():
    record = build_chainstack_yellowstone_config(
        cursor="cursor_abc",
        **_good_config_kwargs(),
    )
    d = config_to_dict(record)
    assert d["provider_id"] == "chainstack_yellowstone_prod"
    assert d["max_events"] == 32
    assert d["cursor"] == "cursor_abc"
    assert d["redaction_status"] == REDACTION_STATUS_SAFE


def test_config_to_dict_rejects_non_record():
    with pytest.raises(Stage28_10InvalidConfigError):
        config_to_dict("not_a_record")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Payload builder + validation
# ---------------------------------------------------------------------------


def _good_payload_kwargs():
    return {
        "provider_event_id": "evt_1234567890",
        "provider_name": "chainstack_yellowstone_prod",
        "source_kind": SOURCE_KIND_FAKE,
        "mint": "So11111111111111111111111111111111111111112",
        "event_type": EVENT_TYPE_SWAP,
        "observed_at_utc": "2026-05-24T12:00:00Z",
        "slot": 12345678,
        "signature": (
            "5xyz999999999999999999999999999999999999999999999999"
            "9999999999999999999999999999999999"
        ),
        "instruction_kind": INSTRUCTION_KIND_PUMP_SWAP,
        "decoded_fields": {
            "swap_in_amount": "1000000",
            "swap_out_amount": "500000",
        },
    }


def test_build_payload_accepts_safe_minimum():
    record = build_chainstack_yellowstone_payload(
        **_good_payload_kwargs(),
    )
    assert isinstance(
        record, Stage28_10ChainstackYellowstonePayload,
    )
    assert record.schema_version == STAGE28_10_SCHEMA_VERSION
    assert record.provider_event_id == "evt_1234567890"
    assert record.chain == CHAIN_SOLANA
    assert record.slot == 12345678
    assert record.quote_mint is None
    assert record.provider_quote_asset_hint is None
    assert record.redaction_status == REDACTION_STATUS_SAFE


def test_build_payload_accepts_hint_passthrough():
    kwargs = _good_payload_kwargs()
    record = build_chainstack_yellowstone_payload(
        quote_mint="So11111111111111111111111111111111111111112",
        pool_account=(
            "PoolPoolPoolPoolPoolPoolPoolPoolPoolPoolPool11"
        ),
        pool_program_id=(
            "ProgProgProgProgProgProgProgProgProgProgProg11"
        ),
        base_mint=(
            "BaseBaseBaseBaseBaseBaseBaseBaseBaseBaseBase11"
        ),
        bonding_curve_version_hint=(
            BONDING_CURVE_VERSION_HINT_SOL_LEGACY
        ),
        provider_quote_asset_hint=QUOTE_ASSET_HINT_SOL,
        provider_pair_type_hint=PAIR_TYPE_HINT_PUMP_SOL,
        provider_bonding_curve_version_hint=(
            BONDING_CURVE_VERSION_HINT_SOL_LEGACY
        ),
        **kwargs,
    )
    assert (
        record.quote_mint
        == "So11111111111111111111111111111111111111112"
    )
    assert (
        record.provider_quote_asset_hint == QUOTE_ASSET_HINT_SOL
    )
    assert (
        record.provider_pair_type_hint == PAIR_TYPE_HINT_PUMP_SOL
    )


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("provider_event_id", ""),
        ("provider_event_id", "has space"),
        ("provider_name", ""),
        ("provider_name", "bearer_prefix"),
        ("source_kind", "REAL"),
        ("mint", ""),
        ("event_type", "burn"),
        ("observed_at_utc", "not-a-date"),
        ("slot", -1),
        ("slot", True),
        ("slot", 1.5),
        ("signature", ""),
        ("instruction_kind", "RAYDIUM_SWAP"),
    ],
)
def test_build_payload_rejects_unsafe_required(field, bad_value):
    kwargs = _good_payload_kwargs()
    kwargs[field] = bad_value
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(**kwargs)


def test_build_payload_rejects_unsafe_decoded_fields_not_mapping():
    kwargs = _good_payload_kwargs()
    kwargs["decoded_fields"] = ["not", "a", "mapping"]
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(**kwargs)


def test_build_payload_rejects_unsafe_decoded_fields_too_many():
    kwargs = _good_payload_kwargs()
    kwargs["decoded_fields"] = {
        f"key_{i}": "value" for i in range(20)
    }
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(**kwargs)


def test_build_payload_rejects_unsafe_decoded_fields_unsafe_key():
    kwargs = _good_payload_kwargs()
    kwargs["decoded_fields"] = {"has space": "value"}
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(**kwargs)


def test_build_payload_rejects_unsafe_decoded_fields_url_value():
    kwargs = _good_payload_kwargs()
    kwargs["decoded_fields"] = {
        "url": "h" + "ttps://leak.example",
    }
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(**kwargs)


def test_build_payload_rejects_unsafe_decoded_fields_value_not_string():
    kwargs = _good_payload_kwargs()
    kwargs["decoded_fields"] = {"key": 123}
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(**kwargs)


def test_build_payload_rejects_off_closed_set_quote_asset_hint():
    kwargs = _good_payload_kwargs()
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(
            provider_quote_asset_hint="BONK", **kwargs,
        )


def test_build_payload_rejects_off_closed_set_pair_type_hint():
    kwargs = _good_payload_kwargs()
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(
            provider_pair_type_hint="RAYDIUM_SOL", **kwargs,
        )


def test_build_payload_rejects_off_closed_set_bonding_curve_hint():
    kwargs = _good_payload_kwargs()
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(
            bonding_curve_version_hint="V99", **kwargs,
        )


def test_build_payload_rejects_url_in_quote_mint():
    kwargs = _good_payload_kwargs()
    with pytest.raises(Stage28_10InvalidPayloadError):
        build_chainstack_yellowstone_payload(
            quote_mint="h" + "ttps://leak.example/mint",
            **kwargs,
        )


def test_payload_repr_redaction_safe():
    record = build_chainstack_yellowstone_payload(
        **_good_payload_kwargs(),
    )
    rendered = repr(record)
    forbidden_needles = (
        "h" + "ttps://",
        "h" + "ttp://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
    )
    for needle in forbidden_needles:
        assert needle not in rendered.lower(), (
            f"payload repr leaked {needle!r}"
        )


def test_payload_to_dict_includes_all_fields():
    record = build_chainstack_yellowstone_payload(
        **_good_payload_kwargs(),
    )
    d = payload_to_dict(record)
    for name in STAGE28_10_PAYLOAD_FIELD_NAMES:
        assert name in d, f"missing field {name}"
    assert d["schema_version"] == STAGE28_10_SCHEMA_VERSION


def test_payload_to_dict_rejects_non_record():
    with pytest.raises(Stage28_10InvalidPayloadError):
        payload_to_dict("not_a_record")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Normalized event builder
# ---------------------------------------------------------------------------


def _good_normalized_kwargs():
    return {
        "event_id": "stage28_10_evt_1234567890",
        "provider_event_id": "evt_1234567890",
        "provider_name": "chainstack_yellowstone_prod",
        "mint": "So11111111111111111111111111111111111111112",
        "event_type": "swap",
        "observed_at_utc": "2026-05-24T12:00:00Z",
        "raw_event_hash": "stage28_10_sig_abc",
    }


def test_build_normalized_event_accepts_safe_minimum():
    record = build_normalized_event(**_good_normalized_kwargs())
    assert isinstance(record, Stage28_10NormalizedEvent)
    assert record.event_id == "stage28_10_evt_1234567890"
    assert record.quote_mint is None
    assert record.provider_quote_asset_hint is None


def test_build_normalized_event_accepts_full_hints():
    kwargs = _good_normalized_kwargs()
    record = build_normalized_event(
        quote_mint="So11111111111111111111111111111111111111112",
        pool_account=(
            "PoolPoolPoolPoolPoolPoolPoolPoolPoolPoolPool11"
        ),
        pool_program_id=(
            "ProgProgProgProgProgProgProgProgProgProgProg11"
        ),
        base_mint=(
            "BaseBaseBaseBaseBaseBaseBaseBaseBaseBaseBase11"
        ),
        bonding_curve_program_id=(
            "BCBCBCBCBCBCBCBCBCBCBCBCBCBCBCBCBCBCBCBCBCBC11"
        ),
        bonding_curve_version_hint=(
            BONDING_CURVE_VERSION_HINT_SOL_LEGACY
        ),
        provider_quote_asset_hint=QUOTE_ASSET_HINT_SOL,
        provider_pair_type_hint=PAIR_TYPE_HINT_PUMP_SOL,
        provider_bonding_curve_version_hint=(
            BONDING_CURVE_VERSION_HINT_SOL_LEGACY
        ),
        **kwargs,
    )
    assert (
        record.provider_quote_asset_hint == QUOTE_ASSET_HINT_SOL
    )
    assert (
        record.bonding_curve_version_hint
        == BONDING_CURVE_VERSION_HINT_SOL_LEGACY
    )


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("event_id", ""),
        ("event_id", "has space"),
        ("provider_event_id", ""),
        ("provider_name", "bearer_prefix"),
        ("mint", ""),
        ("event_type", ""),
        ("observed_at_utc", "not-a-date"),
        ("raw_event_hash", ""),
    ],
)
def test_build_normalized_event_rejects_unsafe_required(
    field, bad_value,
):
    kwargs = _good_normalized_kwargs()
    kwargs[field] = bad_value
    with pytest.raises(Stage28_10InvalidNormalizedEventError):
        build_normalized_event(**kwargs)


def test_build_normalized_event_rejects_off_closed_set_hint():
    kwargs = _good_normalized_kwargs()
    with pytest.raises(Stage28_10InvalidNormalizedEventError):
        build_normalized_event(
            provider_quote_asset_hint="BONK", **kwargs,
        )


def test_build_normalized_event_rejects_url_in_pool_account():
    kwargs = _good_normalized_kwargs()
    with pytest.raises(Stage28_10InvalidNormalizedEventError):
        build_normalized_event(
            pool_account="h" + "ttps://leak.example",
            **kwargs,
        )


def test_normalized_event_repr_redaction_safe():
    record = build_normalized_event(**_good_normalized_kwargs())
    rendered = repr(record)
    forbidden_needles = (
        "h" + "ttps://",
        "h" + "ttp://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
    )
    for needle in forbidden_needles:
        assert needle not in rendered.lower(), (
            f"normalized event repr leaked {needle!r}"
        )


# ---------------------------------------------------------------------------
# Field-name inventories
# ---------------------------------------------------------------------------


def test_payload_dataclass_fields_match_inventory():
    record = build_chainstack_yellowstone_payload(
        **_good_payload_kwargs(),
    )
    fields = {f.name for f in dataclasses.fields(record)}
    expected = set(STAGE28_10_PAYLOAD_FIELD_NAMES)
    assert fields == expected


def test_normalized_event_required_fields_present():
    record = build_normalized_event(**_good_normalized_kwargs())
    for name in STAGE28_10_NORMALIZED_EVENT_REQUIRED_FIELDS:
        assert hasattr(record, name)


def test_normalized_event_hint_fields_present():
    record = build_normalized_event(**_good_normalized_kwargs())
    for name in STAGE28_10_NORMALIZED_EVENT_HINT_FIELDS:
        assert hasattr(record, name)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_invalid_config_error_is_subclass():
    assert issubclass(
        Stage28_10InvalidConfigError,
        Stage28_10ChainstackYellowstoneError,
    )


def test_invalid_payload_error_is_subclass():
    assert issubclass(
        Stage28_10InvalidPayloadError,
        Stage28_10ChainstackYellowstoneError,
    )


def test_invalid_normalized_event_error_is_subclass():
    assert issubclass(
        Stage28_10InvalidNormalizedEventError,
        Stage28_10ChainstackYellowstoneError,
    )


def test_invalid_config_error_carries_field_and_reason():
    err = Stage28_10InvalidConfigError(
        field_name="x", reason="REASON_X",
    )
    assert err.field_name == "x"
    assert err.reason == "REASON_X"
    assert "x" in str(err)
    assert "REASON_X" in str(err)


# ---------------------------------------------------------------------------
# Direct-constructor validation: Stage28_10ChainstackYellowstoneConfig
#
# Build factories are not the only entry point for record creation;
# the dataclass constructor is public. These tests pin that direct
# construction with unsafe values is rejected via __post_init__
# (instead of silently leaking through into repr / asdict).
# ---------------------------------------------------------------------------


def _direct_config_kwargs(**overrides) -> dict:
    kwargs = {
        "provider_id": "chainstack_yellowstone_prod",
        "provider_kind": PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
        "endpoint_safe_label": "yellowstone-mainnet",
        "auth_mode": AUTH_MODE_XTOKEN,
        "chain": CHAIN_SOLANA,
        "max_events": 8,
        "cursor": None,
        "redaction_status": REDACTION_STATUS_SAFE,
    }
    kwargs.update(overrides)
    return kwargs


def test_direct_config_construction_accepts_safe_values():
    record = Stage28_10ChainstackYellowstoneConfig(
        **_direct_config_kwargs(),
    )
    assert isinstance(
        record, Stage28_10ChainstackYellowstoneConfig,
    )
    assert record.provider_id == "chainstack_yellowstone_prod"
    assert record.redaction_status == REDACTION_STATUS_SAFE


def test_direct_config_construction_defaults_optional_fields():
    """Direct construction may omit ``cursor`` and ``redaction_status``;
    the defaults route through ``__post_init__`` validation."""
    record = Stage28_10ChainstackYellowstoneConfig(
        provider_id="chainstack_yellowstone_prod",
        provider_kind=PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
        endpoint_safe_label="yellowstone-mainnet",
        auth_mode=AUTH_MODE_XTOKEN,
        chain=CHAIN_SOLANA,
        max_events=8,
    )
    assert record.cursor is None
    assert record.redaction_status == REDACTION_STATUS_SAFE


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("provider_id", "h" + "ttps://leak.example"),
        ("provider_id", "h" + "ttp://leak.example"),
        ("provider_id", "my_webhook_id"),
        ("provider_id", "x_api_key_xyz"),
        ("provider_id", "auth_token_xyz"),
        ("provider_id", "bearer_prefix"),
        (
            "provider_id",
            "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK",
        ),
        ("endpoint_safe_label", "h" + "ttps://leak.example"),
        ("endpoint_safe_label", "my_webhook_id"),
        ("endpoint_safe_label", "auth_token_xyz"),
        ("auth_mode", "OAUTH2"),
        ("chain", "ETHEREUM"),
        ("max_events", 0),
        ("max_events", -1),
        ("max_events", 1.5),
        ("max_events", True),
        ("cursor", "h" + "ttps://leak.example/cursor"),
        ("cursor", "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"),
        ("redaction_status", "PARTIAL"),
    ],
)
def test_direct_config_construction_rejects_unsafe(
    field, bad_value,
):
    kwargs = _direct_config_kwargs(**{field: bad_value})
    with pytest.raises(Stage28_10InvalidConfigError):
        Stage28_10ChainstackYellowstoneConfig(**kwargs)


def test_direct_config_construction_rejects_url_provider_id():
    """Audit example: direct construction must refuse a URL-shaped
    provider_id so repr() cannot render the URL."""
    with pytest.raises(Stage28_10InvalidConfigError):
        Stage28_10ChainstackYellowstoneConfig(
            **_direct_config_kwargs(
                provider_id="h" + "ttps://endpoint.example",
            ),
        )


def test_direct_config_construction_rejects_webhook_value():
    with pytest.raises(Stage28_10InvalidConfigError):
        Stage28_10ChainstackYellowstoneConfig(
            **_direct_config_kwargs(
                endpoint_safe_label="webhook_label_xyz",
            ),
        )


def test_direct_config_construction_rejects_api_token_value():
    with pytest.raises(Stage28_10InvalidConfigError):
        Stage28_10ChainstackYellowstoneConfig(
            **_direct_config_kwargs(
                provider_id="x_api_key_xyz",
            ),
        )


def test_direct_config_construction_rejects_private_key_like_5K():
    with pytest.raises(Stage28_10InvalidConfigError):
        Stage28_10ChainstackYellowstoneConfig(
            **_direct_config_kwargs(
                provider_id=(
                    "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"
                ),
            ),
        )


def test_direct_config_repr_is_redaction_safe_after_construction():
    """If construction succeeds with safe values, repr() must
    expose only safe values -- never any URL / secret literal."""
    record = Stage28_10ChainstackYellowstoneConfig(
        **_direct_config_kwargs(),
    )
    rendered = repr(record).lower()
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
        "webhook",
    )
    for needle in forbidden:
        assert needle not in rendered, (
            f"direct-construct config repr leaked {needle!r}"
        )


def test_direct_config_dataclasses_asdict_is_redaction_safe():
    """``dataclasses.asdict`` on a directly-constructed record must
    expose only safe values."""
    record = Stage28_10ChainstackYellowstoneConfig(
        **_direct_config_kwargs(),
    )
    d = dataclasses.asdict(record)
    rendered = str(d).lower()
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
        "webhook",
    )
    for needle in forbidden:
        assert needle not in rendered, (
            f"asdict leaked {needle!r}"
        )


def test_direct_config_to_dict_is_redaction_safe():
    """The Stage 28.10 public dict helper must also be redaction-
    safe for directly-constructed records."""
    record = Stage28_10ChainstackYellowstoneConfig(
        **_direct_config_kwargs(),
    )
    d = config_to_dict(record)
    rendered = str(d).lower()
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
        "webhook",
    )
    for needle in forbidden:
        assert needle not in rendered, (
            f"config_to_dict leaked {needle!r}"
        )


# ---------------------------------------------------------------------------
# Direct-constructor validation: Stage28_10ChainstackYellowstonePayload
# ---------------------------------------------------------------------------


def _direct_payload_kwargs(**overrides) -> dict:
    kwargs = {
        "provider_event_id": "evt_1234567890",
        "provider_name": "chainstack_yellowstone_prod",
        "source_kind": SOURCE_KIND_FAKE,
        "mint": "So11111111111111111111111111111111111111112",
        "event_type": EVENT_TYPE_SWAP,
        "observed_at_utc": "2026-05-24T12:00:00Z",
        "slot": 12345678,
        "signature": (
            "2bnLp2WHCY" + "x" * 70
        ),
        "instruction_kind": INSTRUCTION_KIND_PUMP_SWAP,
        "decoded_fields": {
            "swap_in_amount": "1000000",
        },
    }
    kwargs.update(overrides)
    return kwargs


def test_direct_payload_construction_accepts_safe_values():
    record = Stage28_10ChainstackYellowstonePayload(
        **_direct_payload_kwargs(),
    )
    assert isinstance(
        record, Stage28_10ChainstackYellowstonePayload,
    )
    assert record.schema_version == STAGE28_10_SCHEMA_VERSION
    assert record.redaction_status == REDACTION_STATUS_SAFE


def test_direct_payload_construction_defaults_optional_fields():
    record = Stage28_10ChainstackYellowstonePayload(
        provider_event_id="evt_1234567890",
        provider_name="chainstack_yellowstone_prod",
        source_kind=SOURCE_KIND_FAKE,
        mint="So11111111111111111111111111111111111111112",
        event_type=EVENT_TYPE_SWAP,
        observed_at_utc="2026-05-24T12:00:00Z",
        slot=12345678,
        signature="2bnLp2WHCY" + "x" * 70,
        instruction_kind=INSTRUCTION_KIND_PUMP_SWAP,
        decoded_fields={"swap_in_amount": "1000000"},
    )
    assert record.chain == CHAIN_SOLANA
    assert record.quote_mint is None
    assert record.provider_quote_asset_hint is None
    assert record.schema_version == STAGE28_10_SCHEMA_VERSION
    assert record.redaction_status == REDACTION_STATUS_SAFE


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("provider_event_id", "h" + "ttps://leak.example"),
        ("provider_event_id", "my_webhook_id_xxxx"),
        ("provider_event_id", "auth_token_xyz"),
        ("provider_event_id", "5KKKKKKKKKKKKKKKK"),
        ("provider_name", "h" + "ttps://leak.example"),
        ("provider_name", "webhook_label_xyz"),
        ("mint", "h" + "ttps://leak.example/mint"),
        (
            "mint",
            "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK",
        ),
        ("signature", "h" + "ttps://leak.example/sig"),
        ("signature", "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"),
        ("event_type", "burn"),
        ("source_kind", "REAL"),
        ("instruction_kind", "RAYDIUM_SWAP"),
        ("slot", -1),
        ("slot", True),
        ("slot", 1.5),
        ("observed_at_utc", "not-a-date"),
    ],
)
def test_direct_payload_construction_rejects_unsafe(
    field, bad_value,
):
    kwargs = _direct_payload_kwargs(**{field: bad_value})
    with pytest.raises(Stage28_10InvalidPayloadError):
        Stage28_10ChainstackYellowstonePayload(**kwargs)


def test_direct_payload_construction_rejects_off_closed_set_schema_version():
    with pytest.raises(Stage28_10InvalidPayloadError):
        Stage28_10ChainstackYellowstonePayload(
            **_direct_payload_kwargs(),
            schema_version="not_a_real_version",
        )


def test_direct_payload_construction_rejects_off_closed_set_redaction_status():
    with pytest.raises(Stage28_10InvalidPayloadError):
        Stage28_10ChainstackYellowstonePayload(
            **_direct_payload_kwargs(),
            redaction_status="PARTIAL",
        )


def test_direct_payload_construction_rejects_unsafe_decoded_fields():
    with pytest.raises(Stage28_10InvalidPayloadError):
        Stage28_10ChainstackYellowstonePayload(
            **_direct_payload_kwargs(
                decoded_fields={
                    "url": "h" + "ttps://leak.example",
                },
            ),
        )


def test_direct_payload_construction_rejects_url_mint():
    with pytest.raises(Stage28_10InvalidPayloadError):
        Stage28_10ChainstackYellowstonePayload(
            **_direct_payload_kwargs(
                mint="h" + "ttps://leak.example/mint",
            ),
        )


def test_direct_payload_construction_rejects_private_key_like_mint():
    with pytest.raises(Stage28_10InvalidPayloadError):
        Stage28_10ChainstackYellowstonePayload(
            **_direct_payload_kwargs(
                mint=(
                    "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"
                ),
            ),
        )


def test_direct_payload_construction_rejects_webhook_provider_name():
    with pytest.raises(Stage28_10InvalidPayloadError):
        Stage28_10ChainstackYellowstonePayload(
            **_direct_payload_kwargs(
                provider_name="my_webhook_provider",
            ),
        )


def test_direct_payload_repr_is_redaction_safe_after_construction():
    record = Stage28_10ChainstackYellowstonePayload(
        **_direct_payload_kwargs(),
    )
    rendered = repr(record).lower()
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
        "webhook",
    )
    for needle in forbidden:
        assert needle not in rendered, (
            f"direct-construct payload repr leaked {needle!r}"
        )


def test_direct_payload_dataclasses_asdict_is_redaction_safe():
    record = Stage28_10ChainstackYellowstonePayload(
        **_direct_payload_kwargs(),
    )
    d = dataclasses.asdict(record)
    rendered = str(d).lower()
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
        "webhook",
    )
    for needle in forbidden:
        assert needle not in rendered, (
            f"asdict leaked {needle!r}"
        )


def test_direct_payload_to_dict_is_redaction_safe():
    record = Stage28_10ChainstackYellowstonePayload(
        **_direct_payload_kwargs(),
    )
    d = payload_to_dict(record)
    rendered = str(d).lower()
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
        "webhook",
    )
    for needle in forbidden:
        assert needle not in rendered, (
            f"payload_to_dict leaked {needle!r}"
        )


# ---------------------------------------------------------------------------
# Direct-constructor validation: Stage28_10NormalizedEvent
# ---------------------------------------------------------------------------


def _direct_normalized_kwargs(**overrides) -> dict:
    kwargs = {
        "event_id": "stage28_10_evt_1234567890",
        "provider_event_id": "evt_1234567890",
        "provider_name": "chainstack_yellowstone_prod",
        "mint": "So11111111111111111111111111111111111111112",
        "event_type": "swap",
        "observed_at_utc": "2026-05-24T12:00:00Z",
        "raw_event_hash": "stage28_10_sig_abc",
    }
    kwargs.update(overrides)
    return kwargs


def test_direct_normalized_event_construction_accepts_safe_values():
    record = Stage28_10NormalizedEvent(
        **_direct_normalized_kwargs(),
    )
    assert isinstance(record, Stage28_10NormalizedEvent)
    assert record.quote_mint is None


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("event_id", "h" + "ttps://leak.example"),
        ("event_id", "my_webhook_id"),
        ("event_id", "5KKKKKKKKKKKKKKKK"),
        ("provider_event_id", "h" + "ttps://leak.example"),
        ("provider_name", "webhook_label_xyz"),
        ("mint", "h" + "ttps://leak.example/mint"),
        ("mint", "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"),
        ("observed_at_utc", "not-a-date"),
        ("raw_event_hash", "h" + "ttps://leak.example"),
    ],
)
def test_direct_normalized_event_construction_rejects_unsafe(
    field, bad_value,
):
    kwargs = _direct_normalized_kwargs(**{field: bad_value})
    with pytest.raises(Stage28_10InvalidNormalizedEventError):
        Stage28_10NormalizedEvent(**kwargs)


def test_direct_normalized_event_construction_rejects_off_closed_set_hint():
    with pytest.raises(Stage28_10InvalidNormalizedEventError):
        Stage28_10NormalizedEvent(
            **_direct_normalized_kwargs(
                provider_quote_asset_hint="BONK",
            ),
        )


def test_direct_normalized_event_construction_rejects_url_pool_account():
    with pytest.raises(Stage28_10InvalidNormalizedEventError):
        Stage28_10NormalizedEvent(
            **_direct_normalized_kwargs(
                pool_account="h" + "ttps://leak.example",
            ),
        )


def test_direct_normalized_event_construction_rejects_private_key_like_pool_account():
    with pytest.raises(Stage28_10InvalidNormalizedEventError):
        Stage28_10NormalizedEvent(
            **_direct_normalized_kwargs(
                pool_account=(
                    "5KKKKKKKKKKKKKKKKKKKKKKKKKKK"
                ),
            ),
        )


def test_direct_normalized_event_repr_is_redaction_safe_after_construction():
    record = Stage28_10NormalizedEvent(
        **_direct_normalized_kwargs(),
    )
    rendered = repr(record).lower()
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
        "webhook",
    )
    for needle in forbidden:
        assert needle not in rendered, (
            f"direct-construct normalized event repr leaked "
            f"{needle!r}"
        )


def test_direct_normalized_event_dataclasses_asdict_is_redaction_safe():
    record = Stage28_10NormalizedEvent(
        **_direct_normalized_kwargs(),
    )
    d = dataclasses.asdict(record)
    rendered = str(d).lower()
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
        "webhook",
    )
    for needle in forbidden:
        assert needle not in rendered, (
            f"asdict leaked {needle!r}"
        )


# ---------------------------------------------------------------------------
# Error-message redaction: unsafe raw values must NOT leak into the
# exception representation.
# ---------------------------------------------------------------------------


_UNSAFE_LEAK_TOKENS: tuple[str, ...] = (
    "leak.example",
    "endpoint.example",
    "5KKKKKKKKKKKK",
    "webhook_id_xxxx",
    "x_api_key_xyz",
    "bearer_prefix_xyz",
    "auth_token_xyz",
)


def _assert_error_does_not_leak(err: Exception, unsafe_value: str):
    rendered = str(err).lower()
    for needle in _UNSAFE_LEAK_TOKENS:
        assert needle.lower() not in rendered, (
            f"error str leaked token {needle!r}"
        )
    assert "h" + "ttps://" not in rendered
    assert "h" + "ttp://" not in rendered
    assert "bearer" not in rendered
    assert "token=" not in rendered
    assert "secret=" not in rendered
    assert "password" not in rendered
    # The raw unsafe value itself must not appear in str(err).
    # We compare full and lowered forms.
    assert unsafe_value not in str(err)
    assert unsafe_value.lower() not in rendered


def test_direct_config_error_does_not_leak_url_provider_id():
    unsafe = "h" + "ttps://leak.example/path"
    try:
        Stage28_10ChainstackYellowstoneConfig(
            **_direct_config_kwargs(provider_id=unsafe),
        )
        raise AssertionError("expected construction to raise")
    except Stage28_10InvalidConfigError as err:
        _assert_error_does_not_leak(err, unsafe)


def test_direct_config_error_does_not_leak_private_key_like_provider_id():
    unsafe = "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"
    try:
        Stage28_10ChainstackYellowstoneConfig(
            **_direct_config_kwargs(provider_id=unsafe),
        )
        raise AssertionError("expected construction to raise")
    except Stage28_10InvalidConfigError as err:
        _assert_error_does_not_leak(err, unsafe)


def test_direct_config_error_does_not_leak_webhook_endpoint_label():
    unsafe = "my_webhook_id_xxxx"
    try:
        Stage28_10ChainstackYellowstoneConfig(
            **_direct_config_kwargs(
                endpoint_safe_label=unsafe,
            ),
        )
        raise AssertionError("expected construction to raise")
    except Stage28_10InvalidConfigError as err:
        _assert_error_does_not_leak(err, unsafe)


def test_direct_payload_error_does_not_leak_url_mint():
    unsafe = "h" + "ttps://leak.example/mint"
    try:
        Stage28_10ChainstackYellowstonePayload(
            **_direct_payload_kwargs(mint=unsafe),
        )
        raise AssertionError("expected construction to raise")
    except Stage28_10InvalidPayloadError as err:
        _assert_error_does_not_leak(err, unsafe)


def test_direct_payload_error_does_not_leak_private_key_like_signature():
    unsafe = "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"
    try:
        Stage28_10ChainstackYellowstonePayload(
            **_direct_payload_kwargs(signature=unsafe),
        )
        raise AssertionError("expected construction to raise")
    except Stage28_10InvalidPayloadError as err:
        _assert_error_does_not_leak(err, unsafe)


def test_direct_normalized_event_error_does_not_leak_url_pool_account():
    unsafe = "h" + "ttps://leak.example/pool"
    try:
        Stage28_10NormalizedEvent(
            **_direct_normalized_kwargs(
                pool_account=unsafe,
            ),
        )
        raise AssertionError("expected construction to raise")
    except Stage28_10InvalidNormalizedEventError as err:
        _assert_error_does_not_leak(err, unsafe)


def test_direct_normalized_event_error_does_not_leak_private_key_like_event_id():
    unsafe = "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"
    try:
        Stage28_10NormalizedEvent(
            **_direct_normalized_kwargs(event_id=unsafe),
        )
        raise AssertionError("expected construction to raise")
    except Stage28_10InvalidNormalizedEventError as err:
        _assert_error_does_not_leak(err, unsafe)


# ---------------------------------------------------------------------------
# event_type strict-shape validation
#
# Stage 28.10 forwards the upstream event-type string to Stage
# 27.3's ``classify_event_kind`` mapping. The upstream alphabet is
# broader than the Stage 28.10 payload-level closed set
# (``EVENT_TYPE_VALUES``), so Stage 28.10 cannot pin event_type to
# {"swap", "migration", "mint"} -- but it MUST refuse URL / webhook
# / API-token / private-key-like / bracketed-key-array shapes. The
# central ``is_safe_payload_string`` validator (allowlisted chars +
# no forbidden substrings + no private-key-like shape) is exactly
# the right gate for this field.
# ---------------------------------------------------------------------------


_UNSAFE_EVENT_TYPE_VALUES: tuple[str, ...] = (
    # URL-like
    "h" + "ttps://leak.example/token=abc",
    "h" + "ttp://leak.example/event",
    "h" + "ttps://endpoint.example/path",
    # Webhook-like
    "my_webhook_event",
    "webhook_label_xyz",
    # API-token-like
    "auth_token_xyz",
    "access_token_xyz",
    "refresh_token_xyz",
    "x_api_key_event",
    "x-api-key-event",
    "xtoken_event",
    "x_token_event",
    # Bearer / Authorization
    "bearer_event_xyz",
    "authorization_event",
    # Private-key-like (WIF prefix)
    "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK",
    "5JaAaAaAaAaAaAaAaAaAaAaA",
    # Bracketed key-array-like
    "[1,2,3,4]",
    "[" + ",".join(str(i) for i in range(64)) + "]",
    # Pure-hex 64+
    "a" * 64,
    "0123456789abcdef" * 4,
    # Base64-padded
    "a" * 48 + "==",
    # Password substring
    "password_event",
    "passwd_event",
)


@pytest.mark.parametrize("bad_value", _UNSAFE_EVENT_TYPE_VALUES)
def test_build_normalized_event_rejects_unsafe_event_type(
    bad_value,
):
    """``build_normalized_event`` MUST refuse every unsafe
    event_type shape so the value never reaches the dataclass
    constructor (and therefore never reaches repr / asdict /
    public dict helpers / Stage 27.3)."""
    kwargs = _good_normalized_kwargs()
    kwargs["event_type"] = bad_value
    with pytest.raises(Stage28_10InvalidNormalizedEventError):
        build_normalized_event(**kwargs)


@pytest.mark.parametrize("bad_value", _UNSAFE_EVENT_TYPE_VALUES)
def test_direct_normalized_event_construction_rejects_unsafe_event_type(
    bad_value,
):
    """Direct ``Stage28_10NormalizedEvent(...)`` construction MUST
    refuse every unsafe event_type shape via ``__post_init__``
    BEFORE a record is built; downstream repr / asdict callers can
    therefore never observe the unsafe value."""
    kwargs = _direct_normalized_kwargs()
    kwargs["event_type"] = bad_value
    with pytest.raises(Stage28_10InvalidNormalizedEventError):
        Stage28_10NormalizedEvent(**kwargs)


def test_normalized_event_accepts_legitimate_stage_21_27_event_types():
    """The Stage 27.3 ``_EVENT_TYPE_TO_EVENT_KIND`` alphabet must
    still pass: ``swap`` / ``fake_swap`` / ``trade`` / ``migration``
    / ``fake_migration`` / ``pool_migration`` / ``mint`` /
    ``fake_mint`` / ``token_mint_created``.
    """
    for legitimate in (
        "swap",
        "fake_swap",
        "trade",
        "migration",
        "fake_migration",
        "pool_migration",
        "mint",
        "fake_mint",
        "token_mint_created",
    ):
        record = build_normalized_event(
            **{
                **_good_normalized_kwargs(),
                "event_type": legitimate,
            }
        )
        assert record.event_type == legitimate


@pytest.mark.parametrize(
    "bad_value",
    [
        "h" + "ttps://leak.example/token=abc",
        "h" + "ttp://leak.example/event",
        "my_webhook_event",
        "auth_token_xyz",
        "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK",
        "[1,2,3,4]",
        "x-api-key-event",
        "bearer_event_xyz",
    ],
)
def test_direct_normalized_event_error_does_not_leak_unsafe_event_type(
    bad_value,
):
    """The ``Stage28_10InvalidNormalizedEventError`` raised on an
    unsafe event_type must never embed the raw unsafe value (so
    the exception cannot become a side-channel leak)."""
    try:
        Stage28_10NormalizedEvent(
            **_direct_normalized_kwargs(event_type=bad_value),
        )
        raise AssertionError("expected construction to raise")
    except Stage28_10InvalidNormalizedEventError as err:
        _assert_error_does_not_leak(err, bad_value)


@pytest.mark.parametrize(
    "bad_value",
    [
        "h" + "ttps://leak.example/token=abc",
        "auth_token_xyz",
        "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK",
        "[1,2,3,4]",
    ],
)
def test_build_normalized_event_error_does_not_leak_unsafe_event_type(
    bad_value,
):
    """``build_normalized_event`` raises the same typed error on
    unsafe event_type; the exception representation must also
    never embed the raw unsafe value."""
    try:
        build_normalized_event(
            **{
                **_good_normalized_kwargs(),
                "event_type": bad_value,
            }
        )
        raise AssertionError("expected build to raise")
    except Stage28_10InvalidNormalizedEventError as err:
        _assert_error_does_not_leak(err, bad_value)


@pytest.mark.parametrize(
    "bad_value",
    [
        "h" + "ttps://leak.example/token=abc",
        "auth_token_xyz",
        "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK",
        "[1,2,3,4]",
        "my_webhook_event",
    ],
)
def test_unsafe_event_type_never_reaches_repr_or_asdict(
    bad_value,
):
    """Unsafe event_type must NEVER produce a constructible
    record. Because direct construction raises before the record
    exists, no ``repr()`` / ``dataclasses.asdict`` call path can
    expose the unsafe value.
    """
    record = None
    try:
        record = Stage28_10NormalizedEvent(
            **_direct_normalized_kwargs(
                event_type=bad_value,
            ),
        )
    except Stage28_10InvalidNormalizedEventError:
        pass
    assert record is None, (
        "unsafe event_type must not produce a constructible "
        "Stage28_10NormalizedEvent record"
    )


# ---------------------------------------------------------------------------
# _looks_private_key_like introspection
# ---------------------------------------------------------------------------


def test_looks_private_key_like_accepts_wif_prefixes():
    from PHX2.stage28.chainstack_yellowstone_models import (
        _looks_private_key_like,
    )

    assert _looks_private_key_like(
        "5KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK"
    )
    assert _looks_private_key_like(
        "5JaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaA"
    )
    assert _looks_private_key_like("5Habc123def456")
    assert _looks_private_key_like("5Labc123def456")


def test_looks_private_key_like_accepts_bracketed_array():
    from PHX2.stage28.chainstack_yellowstone_models import (
        _looks_private_key_like,
    )

    assert _looks_private_key_like("[1,2,3,4,5]")
    assert _looks_private_key_like(
        "[" + ",".join(str(i) for i in range(64)) + "]"
    )


def test_looks_private_key_like_accepts_long_hex():
    from PHX2.stage28.chainstack_yellowstone_models import (
        _looks_private_key_like,
    )

    assert _looks_private_key_like("a" * 64)
    assert _looks_private_key_like("0123456789abcdef" * 4)
    assert _looks_private_key_like("0123456789abcdef" * 8)


def test_looks_private_key_like_accepts_base64_padded():
    from PHX2.stage28.chainstack_yellowstone_models import (
        _looks_private_key_like,
    )

    assert _looks_private_key_like("a" * 44 + "=")
    assert _looks_private_key_like("a" * 48 + "==")


def test_looks_private_key_like_rejects_empty_and_non_string():
    from PHX2.stage28.chainstack_yellowstone_models import (
        _looks_private_key_like,
    )

    assert not _looks_private_key_like("")
    assert not _looks_private_key_like(None)
    assert not _looks_private_key_like(123)


def test_looks_private_key_like_rejects_legitimate_mint_shape():
    from PHX2.stage28.chainstack_yellowstone_models import (
        _looks_private_key_like,
    )

    # Wrapped SOL mint starts with "So", not a WIF prefix
    assert not _looks_private_key_like(
        "So11111111111111111111111111111111111111112"
    )
    # USDC mint starts with "EP", not a WIF prefix
    assert not _looks_private_key_like(
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    )
    # Short safe payload
    assert not _looks_private_key_like("event:abc.123")
    assert not _looks_private_key_like("provider_xyz")
