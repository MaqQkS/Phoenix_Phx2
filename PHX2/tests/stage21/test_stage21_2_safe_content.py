"""Stage 21.2 remediation: safe_content predicate tests (Phase R1).

Locked structure per the remediation prompt:
  * 3 SafeStringKind valid-input groups
  * 9 error-code negative tests (one per E2150..E2158)
  * Boundary tests (max length valid, +1 invalid, empty invalid,
    exact allowed chars)
  * Per-forbidden-substring rejection (11 parametrized cases)
  * TOKEN_ADDRESS specifics (valid mints, length boundaries,
    base58 alphabet violations)
  * Hash validation (exact 64 lowercase hex)
  * Timestamp validation (exact RFC3339 UTC regex)
  * Payload validator (depth + node-count boundaries, key
    validation, value type rejection)
  * Redaction test (offending value never appears in full)
  * Adjudication tests: structural exemption pin (S1+S2+S3 = 10),
    positive rendered-text template lock
"""

from __future__ import annotations

import string
from types import MappingProxyType

import pytest

from PHX2.stage21.constants import (
    FORBIDDEN_SUBSTRINGS,
    KNOWN_SAFE_DOMAIN_TOKEN_KEYS,
    Stage21ErrorCode,
)
from PHX2.stage21.errors import Stage21Error
from PHX2.stage21.safe_content import (
    MARKER_EXEMPT_KEYS_DEFAULT,
    RENDERED_TEXT_EXEMPT_KEYS,
    SafeStringKind,
    validate_payload_hash_value,
    validate_safe_payload_dict,
    validate_safe_string,
    validate_timestamp_value,
)


# ---------------------------------------------------------------------------
# Valid-input groups per SafeStringKind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [
    "x",
    "FAKE_MINT_AAAA",
    "stage21_fake_provider",
    "fake_swap",
    "MIXEDcase123",
    "a" * 64,  # exactly at max length
])
def test_short_label_accepts_valid_values(value):
    validate_safe_string(value, kind=SafeStringKind.SHORT_LABEL, field_name="f")


@pytest.mark.parametrize("value", [
    "evt_a1385fd9c2dc4bff0625c068",
    "cand_19885bf96e7053041bc7ff26",
    "ping_92f53c492a77f67bcba3a01d",
    "stage21_2_test_run",
    "run-with-hyphen",
    "a" * 128,  # exactly at max length
])
def test_short_identifier_accepts_valid_values(value):
    validate_safe_string(
        value,
        kind=SafeStringKind.SHORT_IDENTIFIER,
        field_name="f",
    )


@pytest.mark.parametrize("value", [
    # Standard 32-char Solana base58 strings.
    "So11111111111111111111111111111111",  # 34 chars, valid base58
    "1" * 32,
    "1" * 64,
    # USDC-like length (44 chars).
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
])
def test_token_address_accepts_valid_values(value):
    validate_safe_string(
        value,
        kind=SafeStringKind.TOKEN_ADDRESS,
        field_name="token_address",
    )


# ---------------------------------------------------------------------------
# Nine error-code negative tests
# ---------------------------------------------------------------------------


def test_e2150_empty():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string("", kind=SafeStringKind.SHORT_LABEL, field_name="f")
    assert exc.value.code == "E2150"


def test_e2151_too_long():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            "a" * 65, kind=SafeStringKind.SHORT_LABEL, field_name="f",
        )
    assert exc.value.code == "E2151"


def test_e2152_disallowed_chars():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            "has space",
            kind=SafeStringKind.SHORT_LABEL,
            field_name="f",
        )
    assert exc.value.code == "E2152"


def test_e2153_forbidden_substring():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            "carries_webhook",
            kind=SafeStringKind.SHORT_LABEL,
            field_name="f",
        )
    assert exc.value.code == "E2153"


def test_e2154_control_char():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            "x\x01y",
            kind=SafeStringKind.SHORT_LABEL,
            field_name="f",
        )
    assert exc.value.code == "E2154"


def test_e2155_invalid_base58():
    # Length is valid (32), but contains '0' which is not in base58.
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            "0" * 32,
            kind=SafeStringKind.TOKEN_ADDRESS,
            field_name="token_address",
        )
    assert exc.value.code == "E2155"


def test_e2156_payload_too_deeply_nested():
    # Build a payload deeper than _PAYLOAD_MAX_DEPTH (= 8).
    # depth 0 is the root, then each nested mapping increments
    # depth. depth 9 trips E2156. We wrap 10 nested mappings so
    # the innermost call to _walk is at depth 9.
    nested: object = {"deepest_key": "v"}
    for i in range(8, -1, -1):
        nested = {f"k_{i}": nested}
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict(nested)  # type: ignore[arg-type]
    assert exc.value.code == "E2156"


def test_e2157_payload_too_many_nodes():
    # Build a flat mapping with 1100 entries; node count
    # (1 root + 1100 leaves + 1100 leaf-counter bumps) exceeds
    # the 1024 budget. Use safe SHORT_LABEL key + value shapes.
    big = {f"k_{i:04d}": f"v_{i:04d}" for i in range(1100)}
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict(big)
    assert exc.value.code == "E2157"


def test_e2158_payload_unsupported_value_type():
    # bytes is not in {None, bool, int, float, str, Mapping, list, tuple}.
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict({"mint": b"FAKE_BYTES"})
    assert exc.value.code == "E2158"


# ---------------------------------------------------------------------------
# Boundary tests
# ---------------------------------------------------------------------------


def test_short_label_max_length_64_valid():
    validate_safe_string("a" * 64, kind=SafeStringKind.SHORT_LABEL, field_name="f")


def test_short_label_max_length_plus_one_invalid():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            "a" * 65, kind=SafeStringKind.SHORT_LABEL, field_name="f",
        )
    assert exc.value.code == "E2151"


def test_short_identifier_max_length_128_valid():
    validate_safe_string(
        "a" * 128, kind=SafeStringKind.SHORT_IDENTIFIER, field_name="f",
    )


def test_short_identifier_max_length_plus_one_invalid():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            "a" * 129, kind=SafeStringKind.SHORT_IDENTIFIER, field_name="f",
        )
    assert exc.value.code == "E2151"


def test_empty_string_is_invalid_for_every_kind():
    for kind in (
        SafeStringKind.SHORT_LABEL,
        SafeStringKind.SHORT_IDENTIFIER,
        SafeStringKind.TOKEN_ADDRESS,
    ):
        with pytest.raises(Stage21Error) as exc:
            validate_safe_string("", kind=kind, field_name="f")
        assert exc.value.code == "E2150"


def test_short_label_exact_allowed_char_set():
    # Every char in [A-Za-z0-9_] should pass when used solo.
    for ch in string.ascii_letters + string.digits + "_":
        validate_safe_string(
            f"a{ch}", kind=SafeStringKind.SHORT_LABEL, field_name="f",
        )


# ---------------------------------------------------------------------------
# Per-forbidden-substring parameterization
# ---------------------------------------------------------------------------


_FORBIDDEN_AS_LABEL_FRAGMENTS: tuple[tuple[str, str], ...] = (
    # (forbidden, label-safe placement) — embeds the forbidden
    # substring inside an otherwise SHORT_LABEL-compliant string.
    # URL fragments use a wrapping char outside the label set so
    # the matcher trips on the forbidden substring rather than on
    # the disallowed-char check.
    ("http://", "ahttp://b"),
    ("https://", "ahttps://b"),
    ("://", "a://b"),
    ("webhook", "carries_webhook"),
    ("api_key", "shows_api_key"),
    ("secret", "shows_secret"),
    ("password", "shows_password"),
    ("credential", "shows_credential"),
    ("public_dispatch", "calls_public_dispatch"),
    ("paid_dispatch", "calls_paid_dispatch"),
    ("subscriber", "wraps_subscriber"),
)


@pytest.mark.parametrize("forbidden,sample", _FORBIDDEN_AS_LABEL_FRAGMENTS)
def test_forbidden_substring_rejection(forbidden, sample):
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            sample, kind=SafeStringKind.SHORT_LABEL, field_name="f",
        )
    # URL fragments may trip E2152 (disallowed chars '/' / ':')
    # before the substring check is reached. Both E2152 and E2153
    # are valid fail-closed outcomes; assert the violation is one
    # of them.
    assert exc.value.code in ("E2152", "E2153"), (forbidden, sample, exc.value.code)


def test_forbidden_substrings_locked_set_membership():
    expected = {
        "http://",
        "https://",
        "://",
        "webhook",
        "api_key",
        "secret",
        "password",
        "credential",
        "public_dispatch",
        "paid_dispatch",
        "subscriber",
    }
    assert set(FORBIDDEN_SUBSTRINGS) == expected


# ---------------------------------------------------------------------------
# TOKEN_ADDRESS specifics
# ---------------------------------------------------------------------------


def test_token_address_min_length_32_valid():
    validate_safe_string(
        "1" * 32, kind=SafeStringKind.TOKEN_ADDRESS, field_name="t",
    )


def test_token_address_min_length_minus_one_invalid():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            "1" * 31, kind=SafeStringKind.TOKEN_ADDRESS, field_name="t",
        )
    assert exc.value.code == "E2151"


def test_token_address_max_length_64_valid():
    validate_safe_string(
        "1" * 64, kind=SafeStringKind.TOKEN_ADDRESS, field_name="t",
    )


def test_token_address_max_length_plus_one_invalid():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            "1" * 65, kind=SafeStringKind.TOKEN_ADDRESS, field_name="t",
        )
    assert exc.value.code == "E2151"


@pytest.mark.parametrize("bad_char", ["0", "O", "I", "l"])
def test_token_address_rejects_non_base58_chars(bad_char):
    value = bad_char + "1" * 31
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            value, kind=SafeStringKind.TOKEN_ADDRESS, field_name="t",
        )
    assert exc.value.code == "E2155"


def test_token_address_does_not_reject_secret_substring_in_value():
    # R6: TOKEN_ADDRESS does NOT apply the full forbidden-substring
    # list. Lowercase letters "secret" sit inside the base58
    # alphabet but the predicate must NOT trip on it. We construct
    # a 32-char base58-valid string that contains the lowercase
    # letters "secret" as a substring.
    value = "secret" + "x" * 26  # 32 chars, all in base58 alphabet
    validate_safe_string(
        value, kind=SafeStringKind.TOKEN_ADDRESS, field_name="t",
    )


# ---------------------------------------------------------------------------
# Hash validation (R8a)
# ---------------------------------------------------------------------------


def test_payload_hash_accepts_exactly_64_lowercase_hex():
    validate_payload_hash_value("a" * 64, field_name="payload_hash")
    validate_payload_hash_value("0123456789abcdef" * 4, field_name="payload_hash")


def test_payload_hash_rejects_wrong_length():
    with pytest.raises(Stage21Error) as exc:
        validate_payload_hash_value("a" * 63, field_name="payload_hash")
    assert exc.value.code == "E2152"
    with pytest.raises(Stage21Error) as exc2:
        validate_payload_hash_value("a" * 65, field_name="payload_hash")
    assert exc2.value.code == "E2152"


def test_payload_hash_rejects_uppercase_hex():
    with pytest.raises(Stage21Error) as exc:
        validate_payload_hash_value("A" * 64, field_name="payload_hash")
    assert exc.value.code == "E2152"


# ---------------------------------------------------------------------------
# Timestamp validation (R8b)
# ---------------------------------------------------------------------------


def test_timestamp_accepts_valid_rfc3339_utc():
    validate_timestamp_value(
        "2026-05-17T12:00:00Z", field_name="captured_at_utc",
    )


def test_timestamp_accepts_microseconds_suffix():
    validate_timestamp_value(
        "2026-05-17T12:00:00.123456Z", field_name="generated_at_utc_iso",
    )


def test_timestamp_rejects_missing_z():
    with pytest.raises(Stage21Error) as exc:
        validate_timestamp_value(
            "2026-05-17T12:00:00", field_name="f",
        )
    assert exc.value.code == "E2152"


def test_timestamp_rejects_offset_not_z():
    with pytest.raises(Stage21Error) as exc:
        validate_timestamp_value(
            "2026-05-17T12:00:00+00:00", field_name="f",
        )
    assert exc.value.code == "E2152"


def test_timestamp_rejects_non_string():
    with pytest.raises(Stage21Error) as exc:
        validate_timestamp_value(12345, field_name="f")  # type: ignore[arg-type]
    assert exc.value.code == "E2158"


# ---------------------------------------------------------------------------
# Payload-dict validator: depth + node-count + key + value-type
# ---------------------------------------------------------------------------


def test_payload_validator_rejects_non_mapping_root():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict([1, 2, 3])  # type: ignore[arg-type]
    assert exc.value.code == "E2158"


def test_payload_validator_accepts_max_depth_8():
    # Build exactly max depth: root at depth 0 plus 8 nested
    # mappings -> deepest _walk call is at depth 8 (== max). One
    # leaf inside is processed by _validate_leaf, no extra depth.
    nested: object = {"deepest_key": "v"}
    for i in range(7, -1, -1):
        nested = {f"k_{i}": nested}
    # Should NOT raise.
    validate_safe_payload_dict(nested)  # type: ignore[arg-type]


def test_payload_validator_rejects_non_string_key():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict({123: "v"})  # type: ignore[dict-item]
    assert exc.value.code == "E2158"


def test_payload_validator_rejects_unsafe_key_predicate():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict({"has space key": "v"})
    assert exc.value.code == "E2152"


def test_payload_validator_routes_token_address_key_through_token_address():
    # Valid base58 mint of length 32+.
    validate_safe_payload_dict(
        {"token_address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"},
    )
    # Invalid base58 fails E2155 at the token-address handler.
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict({"token_address": "0" * 32})
    assert exc.value.code == "E2155"


def test_payload_validator_routes_run_id_through_short_identifier():
    # Hyphen is allowed in SHORT_IDENTIFIER but not in SHORT_LABEL.
    validate_safe_payload_dict({"run_id": "run-with-hyphen"})


def test_payload_validator_routes_payload_hash_through_hash_validator():
    validate_safe_payload_dict({"payload_hash": "a" * 64})
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict({"payload_hash": "a" * 63})
    assert exc.value.code == "E2152"


def test_payload_validator_marker_exempt_keys_skip_predicate():
    # The locked stage marker "21.2" has a literal "." which is not
    # in SHORT_LABEL/SHORT_IDENTIFIER char-sets. Marker-key exempt
    # set must let it through.
    validate_safe_payload_dict(
        {"stage": "21.2"},
        exempt_keys=frozenset({"stage"}),
    )


def test_payload_validator_rendered_text_keys_skip_predicate():
    # summary_text and body_text are built-in exempts; freeform
    # strings should pass without raising.
    validate_safe_payload_dict({
        "summary_text": "[Stage 21.2 private-preview] swap for X",
        "body_text": "candidate_id=cand_x normalized_event_id=evt_y reason=R",
    })


def test_payload_validator_known_safe_domain_keys_are_accepted():
    # token_address / token_mint as keys must NOT be rejected by
    # the bare-token-key rule.
    validate_safe_payload_dict({
        "token_address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "token_mint": "So11111111111111111111111111111111",
    })


# ---------------------------------------------------------------------------
# Redaction (R10): full offending value never appears in raised detail
# ---------------------------------------------------------------------------


def test_offending_value_is_never_included_in_full_in_error_detail():
    offending = "PHX2_LEAK_PROBE_aBcDeFgHiJkLmNoPqRsTuVwXyZ_END"
    # Embed in an otherwise-valid SHORT_IDENTIFIER but make it too
    # long so E2151 trips.
    too_long = offending + "_" + ("x" * 200)
    with pytest.raises(Stage21Error) as exc:
        validate_safe_string(
            too_long, kind=SafeStringKind.SHORT_IDENTIFIER, field_name="f",
        )
    assert exc.value.code == "E2151"
    # Full offending value never appears in the detail.
    assert offending not in exc.value.detail
    assert offending not in str(exc.value)
    # Redacted fragment of the form first4...last2 may appear.
    assert "..." in exc.value.detail


# ---------------------------------------------------------------------------
# Structural exemption test (S3 adjudication)
# ---------------------------------------------------------------------------


def test_payload_validator_exemption_set_is_locked_at_ten_keys():
    """The locked exempt key set is exactly 10 keys.

    Composition (10 total):
      * 5 marker keys (S1) -- passed by callers via
        exempt_keys=PING_PAYLOAD_REQUIRED_MARKER_KEYS
      * 3 timestamp keys (S2) -- _TIMESTAMP_KEYS routed to
        RFC3339-regex handler instead of SHORT_LABEL
      * 2 rendered-text keys (S3) -- RENDERED_TEXT_EXEMPT_KEYS
        truly exempt from predicate

    Adding a new exemption requires updating this test (the
    audit trail).
    """
    from PHX2.stage21.ping_payloads import PING_PAYLOAD_REQUIRED_MARKER_KEYS
    from PHX2.stage21 import safe_content as sc

    marker_keys = frozenset(PING_PAYLOAD_REQUIRED_MARKER_KEYS)
    assert marker_keys == frozenset({
        "stage",
        "visibility",
        "operator_only",
        "live_mode",
        "dispatch_target",
    })
    assert sc._TIMESTAMP_KEYS == frozenset({
        "generated_at_utc_iso",
        "captured_at_utc",
        "observed_at_utc",
    })
    assert RENDERED_TEXT_EXEMPT_KEYS == frozenset({
        "summary_text",
        "body_text",
    })
    total = marker_keys | sc._TIMESTAMP_KEYS | RENDERED_TEXT_EXEMPT_KEYS
    assert len(total) == 10, f"locked exempt-key set must be 10, got {len(total)}"
    # Disjoint check: no key is in more than one category.
    assert len(marker_keys & sc._TIMESTAMP_KEYS) == 0
    assert len(marker_keys & RENDERED_TEXT_EXEMPT_KEYS) == 0
    assert len(sc._TIMESTAMP_KEYS & RENDERED_TEXT_EXEMPT_KEYS) == 0


def test_marker_exempt_keys_default_is_empty():
    assert MARKER_EXEMPT_KEYS_DEFAULT == frozenset()


def test_rendered_text_exempt_keys_is_locked_at_two():
    assert len(RENDERED_TEXT_EXEMPT_KEYS) == 2
    assert "summary_text" in RENDERED_TEXT_EXEMPT_KEYS
    assert "body_text" in RENDERED_TEXT_EXEMPT_KEYS


# ---------------------------------------------------------------------------
# Known-safe domain token-key whitelist
# ---------------------------------------------------------------------------


def test_known_safe_domain_token_keys_is_locked():
    assert set(KNOWN_SAFE_DOMAIN_TOKEN_KEYS) == {"token_address", "token_mint"}


def test_bare_token_key_is_always_forbidden():
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict({"token": "x"})
    assert exc.value.code == "E2153"


# ---------------------------------------------------------------------------
# Positive rendered-text template lock (S3 adjudication)
# ---------------------------------------------------------------------------


def test_rendered_summary_and_body_text_match_deterministic_template():
    """Pin the rendered summary_text and body_text format.

    Stage 21.2 fake fixture inputs -> standard ping builder
    output. If the rendering template changes, this test must be
    updated explicitly. The exemption from the safe_content
    predicate is justified ONLY because the rendering is a
    deterministic template over already-validated candidate
    inputs (chain of trust).
    """
    from PHX2.stage21.normalized_events import normalize_fake_event
    from PHX2.stage21.ping_builder import (
        build_candidate_from_normalized_event,
        build_private_preview_payload,
    )
    from PHX2.stage21.ping_payloads import (
        STAGE21_FAKE_CHAIN_NAME,
        STAGE21_FAKE_PROVIDER_NAME,
    )

    norm = normalize_fake_event(
        provider_event_id="fake_pev_aaaa1111",
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        source_kind="stage21_fake_source",
        chain=STAGE21_FAKE_CHAIN_NAME,
        mint="FAKE_MINT_AAAA",
        event_type="fake_swap",
        observed_at_utc="2026-05-17T12:00:00Z",
        slot=100,
        signature="fake_sig_aaaa1111",
        raw_payload={"fake_amount": 1000, "fake_decimals": 6},
    )
    cand = build_candidate_from_normalized_event(norm)
    payload = build_private_preview_payload(cand)
    assert payload.summary_text == (
        f"[Stage 21.2 private-preview] fake_swap for FAKE_MINT_AAAA"
    )
    assert payload.body_text == (
        f"candidate_id={cand.candidate_id} "
        f"normalized_event_id={cand.normalized_event_id} "
        f"observed_at_utc=2026-05-17T12:00:00Z "
        f"reason={cand.reason} "
        f"source={cand.source}"
    )


# ---------------------------------------------------------------------------
# Exempt-keys parameter passes through frozensets only
# ---------------------------------------------------------------------------


def test_exempt_keys_accepts_frozenset():
    validate_safe_payload_dict(
        {"stage": "21.2"},
        exempt_keys=frozenset({"stage"}),
    )


def test_exempt_keys_does_not_skip_default_short_label():
    # Without exempt_keys, "21.2" should fail SHORT_LABEL on '.'
    with pytest.raises(Stage21Error) as exc:
        validate_safe_payload_dict({"stage": "21.2"})
    assert exc.value.code == "E2152"


# ---------------------------------------------------------------------------
# SafeStringKind public enum stays at three values
# ---------------------------------------------------------------------------


def test_safe_string_kind_enum_has_exactly_three_members():
    members = {m.value for m in SafeStringKind}
    assert members == {"SHORT_LABEL", "SHORT_IDENTIFIER", "TOKEN_ADDRESS"}


# ---------------------------------------------------------------------------
# Mapping-proxy payloads also work (FakeTransport remediation will
# pass frozen MappingProxyType structures through here)
# ---------------------------------------------------------------------------


def test_payload_validator_accepts_mappingproxytype_root():
    frozen = MappingProxyType({"mint": "FAKE_MINT_AAAA"})
    validate_safe_payload_dict(frozen)


def test_payload_validator_accepts_nested_mappingproxytype():
    frozen_inner = MappingProxyType({"value": 1000})
    root = {"data": frozen_inner}
    validate_safe_payload_dict(root)
