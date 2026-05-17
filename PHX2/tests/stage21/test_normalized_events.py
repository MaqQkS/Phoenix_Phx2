"""Stage 21.2 normalized_events tests."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage21.errors import Stage21Error, Stage21TelemetryError
from PHX2.stage21.normalized_events import (
    NormalizedLiveEvent,
    STAGE21_2_NORMALIZED_EVENT_TYPES,
    derive_event_id,
    derive_raw_event_hash,
    normalize_fake_event,
)
from PHX2.stage21.ping_payloads import (
    NORMALIZED_EVENT_SCHEMA_VERSION,
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
)


def _kwargs(
    *,
    provider_event_id: str = "fake_pev_aaaa1111",
    provider_name: str = STAGE21_FAKE_PROVIDER_NAME,
    source_kind: str = "stage21_fake_source",
    chain: str = STAGE21_FAKE_CHAIN_NAME,
    mint: str = "FAKE_MINT_AAAA",
    event_type: str = "fake_swap",
    observed_at_utc: str = "2026-05-17T12:00:00Z",
    slot: int = 100,
    signature: str = "fake_sig_aaaa1111",
    raw_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "provider_event_id": provider_event_id,
        "provider_name": provider_name,
        "source_kind": source_kind,
        "chain": chain,
        "mint": mint,
        "event_type": event_type,
        "observed_at_utc": observed_at_utc,
        "slot": slot,
        "signature": signature,
        "raw_payload": raw_payload or {"fake_amount": 1000, "fake_decimals": 6},
    }


# ---------------------------------------------------------------------------
# Required-field validation
# ---------------------------------------------------------------------------


def test_normalize_returns_normalized_live_event():
    out = normalize_fake_event(**_kwargs())
    assert isinstance(out, NormalizedLiveEvent)


def test_normalize_event_id_has_evt_prefix_and_stable_length():
    out = normalize_fake_event(**_kwargs())
    assert out.event_id.startswith("evt_")
    assert len(out.event_id) == len("evt_") + 24


def test_normalize_emits_full_sha256_raw_event_hash():
    out = normalize_fake_event(**_kwargs())
    # Full sha256 hex is 64 chars
    assert len(out.raw_event_hash) == 64
    int(out.raw_event_hash, 16)  # raises if not hex


def test_normalize_pins_normalized_schema_version():
    out = normalize_fake_event(**_kwargs())
    assert out.normalized_schema_version == NORMALIZED_EVENT_SCHEMA_VERSION


def test_normalize_payload_summary_is_mappingproxytype():
    out = normalize_fake_event(**_kwargs())
    assert isinstance(out.payload_summary, MappingProxyType)


def test_normalize_is_deterministic_for_identical_inputs():
    a = normalize_fake_event(**_kwargs())
    b = normalize_fake_event(**_kwargs())
    assert a.event_id == b.event_id
    assert a.raw_event_hash == b.raw_event_hash


def test_normalize_distinct_mint_produces_distinct_event_id():
    a = normalize_fake_event(**_kwargs(mint="FAKE_MINT_AAAA"))
    b = normalize_fake_event(**_kwargs(mint="FAKE_MINT_BBBB"))
    assert a.event_id != b.event_id


# ---------------------------------------------------------------------------
# Required-field rejection
# ---------------------------------------------------------------------------


def test_normalize_rejects_missing_mint():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(mint=""))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_missing_observed_at_utc():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(observed_at_utc=""))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_unknown_event_type():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(event_type="real_swap"))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_empty_provider_event_id():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(provider_event_id=""))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_empty_signature():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(signature=""))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_negative_slot():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(slot=-1))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_non_fake_provider_name():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(provider_name="real_provider"))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_non_fake_chain():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(chain="real_chain"))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_non_mapping_payload():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(raw_payload=["not", "a", "mapping"]))  # type: ignore[arg-type]
    assert excinfo.value.code == "E2113"


# ---------------------------------------------------------------------------
# Secret-like field / URL-shaped value rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_key", [
    "api_key",
    "API_KEY",
    "secret",
    "client_secret",
    "token",
    "auth_token",
    "password",
    "user_password",
    "credential",
    "credentials",
    "webhook",
    "webhook_url",
    "DISCORD_WEBHOOK_URL",
    "bearer",
    "auth",
    "private_key",
])
def test_normalize_rejects_secret_like_field_at_top_level(bad_key):
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(raw_payload={bad_key: "irrelevant"}))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_secret_like_field_in_nested_mapping():
    payload = {
        "outer": {
            "inner_api_key": "leak",
        },
    }
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(raw_payload=payload))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_secret_like_field_inside_list():
    payload = {
        "items": [
            {"fake_amount": 1},
            {"webhook": "value"},
        ],
    }
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(raw_payload=payload))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_url_shaped_value_at_top_level():
    payload = {"endpoint_fake": "http" + "://example.invalid/leak"}
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(raw_payload=payload))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_https_value_at_top_level():
    payload = {"endpoint_fake": "https" + "://example.invalid/leak"}
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(raw_payload=payload))
    assert excinfo.value.code == "E2113"


def test_normalize_rejects_ws_value_at_top_level():
    payload = {"socket_fake": "wss" + "://example.invalid/leak"}
    with pytest.raises(Stage21TelemetryError) as excinfo:
        normalize_fake_event(**_kwargs(raw_payload=payload))
    assert excinfo.value.code == "E2113"


def test_normalize_accepts_benign_payload_unchanged():
    payload = {
        "fake_amount": 1000,
        "fake_decimals": 6,
        "buyer_id_fake": "FAKE_BUYER_A",
    }
    out = normalize_fake_event(**_kwargs(raw_payload=payload))
    assert dict(out.payload_summary) == payload


# ---------------------------------------------------------------------------
# Public summary surface
# ---------------------------------------------------------------------------


def test_normalize_public_summary_contains_all_required_fields():
    out = normalize_fake_event(**_kwargs())
    summary = out.public_summary()
    required = {
        "event_id",
        "provider_event_id",
        "provider_name",
        "source_kind",
        "chain",
        "mint",
        "event_type",
        "observed_at_utc",
        "slot",
        "signature",
        "raw_event_hash",
        "normalized_schema_version",
        "payload_summary",
    }
    assert required.issubset(set(summary.keys()))


# ---------------------------------------------------------------------------
# Locked event-type vocabulary
# ---------------------------------------------------------------------------


def test_locked_event_type_vocabulary_minimum_membership():
    required = {"fake_swap", "fake_mint", "fake_transfer"}
    assert required.issubset(set(STAGE21_2_NORMALIZED_EVENT_TYPES))


# ---------------------------------------------------------------------------
# Deterministic derivation helpers
# ---------------------------------------------------------------------------


def test_derive_raw_event_hash_is_deterministic():
    a = derive_raw_event_hash(
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        provider_event_id="x",
        event_type="fake_swap",
        mint="FAKE_MINT_X",
        chain=STAGE21_FAKE_CHAIN_NAME,
        slot=1,
        signature="fake_sig_x",
        observed_at_utc="2026-05-17T12:00:00Z",
        raw_payload={"fake_amount": 1},
    )
    b = derive_raw_event_hash(
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        provider_event_id="x",
        event_type="fake_swap",
        mint="FAKE_MINT_X",
        chain=STAGE21_FAKE_CHAIN_NAME,
        slot=1,
        signature="fake_sig_x",
        observed_at_utc="2026-05-17T12:00:00Z",
        raw_payload={"fake_amount": 1},
    )
    assert a == b


def test_derive_event_id_is_deterministic_and_has_evt_prefix():
    a = derive_event_id(
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        provider_event_id="x",
        raw_event_hash="0" * 64,
        chain=STAGE21_FAKE_CHAIN_NAME,
        mint="FAKE_MINT_X",
    )
    b = derive_event_id(
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        provider_event_id="x",
        raw_event_hash="0" * 64,
        chain=STAGE21_FAKE_CHAIN_NAME,
        mint="FAKE_MINT_X",
    )
    assert a == b
    assert a.startswith("evt_")


# ---------------------------------------------------------------------------
# Stage 21.2 remediation: Codex PoC #2 reproduction
# ---------------------------------------------------------------------------


def test_codex_poc_2_mint_with_url_rejected_at_normalize():
    """Codex PoC #2: normalize_fake_event rejects URL-laced mint.

    The Stage 21.2 Codex audit produced a normalized event +
    downstream manifest artifact containing a URL value with a
    webhook token in its path. The remediation wires the shared
    safe_content predicate into the normalizer at R11b so a
    URL-shaped mint raises ``Stage21Error`` ``E2153`` before
    any ``NormalizedLiveEvent`` is constructed.
    """
    poisoned_mint = "https" + "://example.invalid/webhook"
    with pytest.raises(Stage21Error) as exc:
        normalize_fake_event(**_kwargs(mint=poisoned_mint))
    assert exc.value.code == "E2153", (
        f"Codex PoC #2 expected E2153 (forbidden_substring); "
        f"got {exc.value.code}"
    )


def test_normalize_rejects_url_signature_via_safe_content():
    """A URL-shaped signature is rejected by the safe_content layer."""
    poisoned_sig = "https" + "://attacker.example/exfil"
    with pytest.raises(Stage21Error) as exc:
        normalize_fake_event(**_kwargs(signature=poisoned_sig))
    assert exc.value.code == "E2153"


def test_normalize_rejects_url_observed_at_utc_via_safe_content():
    """A URL-shaped observed_at_utc is rejected at the timestamp handler."""
    poisoned_ts = "https" + "://attacker.example/leak"
    with pytest.raises(Stage21Error) as exc:
        normalize_fake_event(**_kwargs(observed_at_utc=poisoned_ts))
    # The existing _require_non_empty_str passes (non-empty);
    # the existing chain/provider constant checks pass; then the
    # existing _validate_payload_field walk handles raw_payload
    # (no issue); then safe_content's validate_timestamp_value
    # raises on either the RFC3339-regex miss (E2152) or the
    # forbidden-substring scan (E2153). Either is fail-closed.
    assert exc.value.code in ("E2152", "E2153")


def test_normalize_supplemental_secret_key_rejection_remains_e2113():
    """Preserve S4: the existing wider supplemental layer still raises E2113.

    The shared safe_content layer is appended AFTER the existing
    wider supplemental key-rejection walk. For keys covered by
    the existing supplemental (e.g. "auth_token", which the R4
    locked list does not include), the normalizer must still
    raise Stage21TelemetryError E2113 -- the existing
    15-parameter
    ``test_normalize_rejects_secret_like_field_at_top_level``
    test asserts this and must continue to pass unchanged.
    """
    with pytest.raises(Stage21TelemetryError) as exc:
        normalize_fake_event(**_kwargs(raw_payload={"auth_token": "x"}))
    assert exc.value.code == "E2113"
