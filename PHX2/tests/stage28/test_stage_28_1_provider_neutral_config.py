"""Stage 28.1 provider-neutral resolver tests.

Pins resolution rules per canonical field:

  * provider-neutral env name only -> source_status =
    ``PROVIDER_NEUTRAL``.
  * legacy alias only -> source_status = ``LEGACY_ALIAS``;
    bundle.legacy_alias_used is True.
  * both present and identical -> source_status = ``BOTH_SAME``.
  * both present and different -> source_status =
    ``BOTH_CONFLICT``; field_status = ``CONFLICT``;
    failure_reason = ``CONFLICTING_PROVIDER_ENV_VALUES``; NEITHER
    raw value appears on the record.
  * neither present -> source_status = ``MISSING``; field_status
    = ``MISSING``; failure_reason =
    ``MISSING_REQUIRED_FIELD`` for required canonical fields.

Pins per-field validation:

  * provider_id -- secret-like rejected with
    ``SECRET_LIKE_PROVIDER_LABEL``; allowlist-rejected with
    ``INVALID_PROVIDER_ID``.
  * provider_kind -- closed set; out-of-set rejected with
    ``UNSUPPORTED_PROVIDER_KIND``; missing is allowed.

Pins additional alias forms:

  * Both ``HELIUS_GRPC_ENDPOINT`` and ``PHX2_HELIUS_GRPC_ENDPOINT``
    are recognized as legacy aliases for the gRPC endpoint.
  * Same for ``HELIUS_RPC_URL`` / ``PHX2_HELIUS_RPC_URL`` and
    ``HELIUS_API_KEY`` / ``PHX2_HELIUS_API_KEY``.
"""

from __future__ import annotations

import pytest

from PHX2.stage28 import provider_neutral_models as m
from PHX2.stage28.provider_neutral_config import (
    resolve_canonical_field,
    resolve_provider_neutral_config,
)


# ---------------------------------------------------------------------------
# Distinctive canary fake values
# ---------------------------------------------------------------------------


CANARY_GRPC_ENDPOINT: str = "canary.fake.test:1234"
CANARY_GRPC_ENDPOINT_ALT: str = "canary.fake.test:9999"
CANARY_RPC_PATH: str = "canary.fake.test/rpc/aaaa1111"
CANARY_API_KEY: str = "CANARY_FAKE_PROVIDER_API_KEY_aaaaaa1111"
CANARY_API_KEY_ALT: str = "CANARY_FAKE_PROVIDER_API_KEY_bbbbbb2222"
CANARY_PROVIDER_ID: str = "chainstack_yellowstone_primary"
CANARY_PROVIDER_KIND: str = "yellowstone_grpc"


# Canary substrings the bundle / records must NEVER carry.
_CANARY_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    CANARY_GRPC_ENDPOINT,
    CANARY_GRPC_ENDPOINT_ALT,
    CANARY_RPC_PATH,
    CANARY_API_KEY,
    CANARY_API_KEY_ALT,
)


def _assert_no_canary_leak(text: str) -> None:
    for needle in _CANARY_FORBIDDEN_SUBSTRINGS:
        assert needle not in text, f"canary leak: {needle!r}"


# ---------------------------------------------------------------------------
# Single-field resolution
# ---------------------------------------------------------------------------


def _full_env_provider_neutral_only() -> dict[str, str]:
    return {
        m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME: CANARY_GRPC_ENDPOINT,
        m.STAGE28_PROVIDER_RPC_URL_NAME: (
            ("h" + "ttps") + "://" + CANARY_RPC_PATH
        ),
        m.STAGE28_PROVIDER_API_KEY_NAME: CANARY_API_KEY,
        m.STAGE28_PROVIDER_ID_NAME: CANARY_PROVIDER_ID,
        m.STAGE28_PROVIDER_KIND_NAME: CANARY_PROVIDER_KIND,
    }


def _full_env_legacy_only() -> dict[str, str]:
    return {
        "HELIUS_GRPC_ENDPOINT": CANARY_GRPC_ENDPOINT,
        "HELIUS_RPC_URL": ("h" + "ttps") + "://" + CANARY_RPC_PATH,
        "HELIUS_API_KEY": CANARY_API_KEY,
        m.STAGE28_PROVIDER_ID_NAME: CANARY_PROVIDER_ID,
        m.STAGE28_PROVIDER_KIND_NAME: CANARY_PROVIDER_KIND,
    }


def test_resolve_grpc_endpoint_provider_neutral_only():
    env = {m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME: CANARY_GRPC_ENDPOINT}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_GRPC_ENDPOINT, env)
    assert rec.field_status == m.FIELD_STATUS_PRESENT
    assert rec.source_status == m.SOURCE_STATUS_PROVIDER_NEUTRAL
    assert rec.provider_neutral_present is True
    assert rec.legacy_alias_present is False
    assert rec.legacy_alias_env_name is None
    assert rec.safe_label_value is None
    assert rec.raw_value_length == len(CANARY_GRPC_ENDPOINT)
    assert rec.failure_reason is None
    _assert_no_canary_leak(repr(rec))


def test_resolve_grpc_endpoint_legacy_only_helius_form():
    env = {"HELIUS_GRPC_ENDPOINT": CANARY_GRPC_ENDPOINT}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_GRPC_ENDPOINT, env)
    assert rec.field_status == m.FIELD_STATUS_PRESENT
    assert rec.source_status == m.SOURCE_STATUS_LEGACY_ALIAS
    assert rec.provider_neutral_present is False
    assert rec.legacy_alias_present is True
    assert rec.legacy_alias_env_name == "HELIUS_GRPC_ENDPOINT"
    _assert_no_canary_leak(repr(rec))


def test_resolve_grpc_endpoint_legacy_only_phx2_helius_form():
    env = {"PHX2_HELIUS_GRPC_ENDPOINT": CANARY_GRPC_ENDPOINT}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_GRPC_ENDPOINT, env)
    assert rec.field_status == m.FIELD_STATUS_PRESENT
    assert rec.source_status == m.SOURCE_STATUS_LEGACY_ALIAS
    assert rec.legacy_alias_env_name == "PHX2_HELIUS_GRPC_ENDPOINT"


def test_resolve_grpc_endpoint_both_same():
    env = {
        m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME: CANARY_GRPC_ENDPOINT,
        "HELIUS_GRPC_ENDPOINT": CANARY_GRPC_ENDPOINT,
    }
    rec = resolve_canonical_field(m.PROVIDER_FIELD_GRPC_ENDPOINT, env)
    assert rec.field_status == m.FIELD_STATUS_PRESENT
    assert rec.source_status == m.SOURCE_STATUS_BOTH_SAME
    assert rec.provider_neutral_present is True
    assert rec.legacy_alias_present is True
    assert rec.failure_reason is None
    _assert_no_canary_leak(repr(rec))


def test_resolve_grpc_endpoint_both_conflict():
    env = {
        m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME: CANARY_GRPC_ENDPOINT,
        "HELIUS_GRPC_ENDPOINT": CANARY_GRPC_ENDPOINT_ALT,
    }
    rec = resolve_canonical_field(m.PROVIDER_FIELD_GRPC_ENDPOINT, env)
    assert rec.field_status == m.FIELD_STATUS_CONFLICT
    assert rec.source_status == m.SOURCE_STATUS_BOTH_CONFLICT
    assert rec.failure_reason == (
        m.FAILURE_REASON_CONFLICTING_PROVIDER_ENV_VALUES
    )
    assert rec.raw_value_length is None
    # Neither raw value appears on the record.
    _assert_no_canary_leak(repr(rec))


def test_resolve_required_field_missing_marks_failure():
    env: dict[str, str] = {}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_GRPC_ENDPOINT, env)
    assert rec.field_status == m.FIELD_STATUS_MISSING
    assert rec.source_status == m.SOURCE_STATUS_MISSING
    assert rec.failure_reason == m.FAILURE_REASON_MISSING_REQUIRED_FIELD


def test_resolve_optional_provider_kind_missing_no_failure():
    env: dict[str, str] = {}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_PROVIDER_KIND, env)
    assert rec.field_status == m.FIELD_STATUS_MISSING
    assert rec.source_status == m.SOURCE_STATUS_MISSING
    assert rec.failure_reason is None


def test_resolve_provider_neutral_empty_string_treated_as_missing():
    env = {m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME: ""}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_GRPC_ENDPOINT, env)
    assert rec.field_status == m.FIELD_STATUS_MISSING


def test_resolve_unknown_canonical_field_raises():
    with pytest.raises(ValueError):
        resolve_canonical_field(
            "not_a_real_canonical_field", {}
        )


# ---------------------------------------------------------------------------
# RPC URL: legacy aliases
# ---------------------------------------------------------------------------


def test_resolve_rpc_url_legacy_phx2_helius_form():
    full_url = ("h" + "ttps") + "://" + CANARY_RPC_PATH
    env = {"PHX2_HELIUS_RPC_URL": full_url}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_RPC_URL, env)
    assert rec.field_status == m.FIELD_STATUS_PRESENT
    assert rec.source_status == m.SOURCE_STATUS_LEGACY_ALIAS
    assert rec.legacy_alias_env_name == "PHX2_HELIUS_RPC_URL"
    assert rec.raw_value_length == len(full_url)
    _assert_no_canary_leak(repr(rec))


def test_resolve_api_key_legacy_phx2_helius_form():
    env = {"PHX2_HELIUS_API_KEY": CANARY_API_KEY}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_API_KEY, env)
    assert rec.field_status == m.FIELD_STATUS_PRESENT
    assert rec.source_status == m.SOURCE_STATUS_LEGACY_ALIAS
    assert rec.legacy_alias_env_name == "PHX2_HELIUS_API_KEY"
    _assert_no_canary_leak(repr(rec))


def test_resolve_api_key_conflict_does_not_leak_either_value():
    env = {
        m.STAGE28_PROVIDER_API_KEY_NAME: CANARY_API_KEY,
        "HELIUS_API_KEY": CANARY_API_KEY_ALT,
    }
    rec = resolve_canonical_field(m.PROVIDER_FIELD_API_KEY, env)
    assert rec.field_status == m.FIELD_STATUS_CONFLICT
    assert rec.failure_reason == (
        m.FAILURE_REASON_CONFLICTING_PROVIDER_ENV_VALUES
    )
    assert rec.raw_value_length is None
    _assert_no_canary_leak(repr(rec))


def test_resolve_helius_bare_takes_precedence_over_phx2_helius_when_both_set():
    # When only legacy aliases are set, the first listed legacy
    # alias (the bare ``HELIUS_*`` form) wins.
    env = {
        "HELIUS_GRPC_ENDPOINT": CANARY_GRPC_ENDPOINT,
        "PHX2_HELIUS_GRPC_ENDPOINT": CANARY_GRPC_ENDPOINT,
    }
    rec = resolve_canonical_field(m.PROVIDER_FIELD_GRPC_ENDPOINT, env)
    assert rec.field_status == m.FIELD_STATUS_PRESENT
    assert rec.source_status == m.SOURCE_STATUS_LEGACY_ALIAS
    assert rec.legacy_alias_env_name == "HELIUS_GRPC_ENDPOINT"


# ---------------------------------------------------------------------------
# Provider-id validation
# ---------------------------------------------------------------------------


def test_resolve_provider_id_valid_label():
    env = {m.STAGE28_PROVIDER_ID_NAME: CANARY_PROVIDER_ID}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_PROVIDER_ID, env)
    assert rec.field_status == m.FIELD_STATUS_PRESENT
    assert rec.safe_label_value == CANARY_PROVIDER_ID
    assert rec.failure_reason is None


def test_resolve_provider_id_secret_like_rejected_distinctly():
    bad_label = ("h" + "ttps") + "://canary.fake.test/webhooks/123"
    env = {m.STAGE28_PROVIDER_ID_NAME: bad_label}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_PROVIDER_ID, env)
    assert rec.field_status == m.FIELD_STATUS_INVALID
    assert rec.failure_reason == m.FAILURE_REASON_SECRET_LIKE_PROVIDER_LABEL
    # safe_label_value must be None so the bad label never reaches
    # a public surface.
    assert rec.safe_label_value is None
    # The bad label has length, but raw_value_length still
    # reports the projected length for diagnostic purposes.
    assert rec.raw_value_length == len(bad_label)
    # The record's repr must not carry the rejected URL substring.
    rep = repr(rec)
    assert bad_label not in rep


def test_resolve_provider_id_allowlist_rejected_invalid_provider_id():
    bad_label = "Has Spaces"
    env = {m.STAGE28_PROVIDER_ID_NAME: bad_label}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_PROVIDER_ID, env)
    assert rec.field_status == m.FIELD_STATUS_INVALID
    assert rec.failure_reason == m.FAILURE_REASON_INVALID_PROVIDER_ID
    assert rec.safe_label_value is None
    rep = repr(rec)
    assert bad_label not in rep


# ---------------------------------------------------------------------------
# Provider-kind validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    ["yellowstone_grpc", "json_rpc", "helius_legacy", "unknown"],
)
def test_resolve_provider_kind_supported_value(kind):
    env = {m.STAGE28_PROVIDER_KIND_NAME: kind}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_PROVIDER_KIND, env)
    assert rec.field_status == m.FIELD_STATUS_PRESENT
    assert rec.safe_label_value == kind
    assert rec.failure_reason is None


def test_resolve_provider_kind_unsupported_rejected():
    env = {m.STAGE28_PROVIDER_KIND_NAME: "geyser_v2"}
    rec = resolve_canonical_field(m.PROVIDER_FIELD_PROVIDER_KIND, env)
    assert rec.field_status == m.FIELD_STATUS_INVALID
    assert rec.failure_reason == m.FAILURE_REASON_UNSUPPORTED_PROVIDER_KIND
    assert rec.safe_label_value is None


# ---------------------------------------------------------------------------
# Bulk resolution
# ---------------------------------------------------------------------------


def test_resolve_bulk_provider_neutral_only_clean():
    res = resolve_provider_neutral_config(_full_env_provider_neutral_only())
    assert len(res.fields) == 5
    assert res.missing_required_fields == ()
    assert res.conflicting_fields == ()
    assert res.invalid_fields == ()
    assert res.legacy_alias_used is False
    for record in res.fields:
        assert record.field_status == m.FIELD_STATUS_PRESENT


def test_resolve_bulk_legacy_only_clean_marks_legacy_used():
    res = resolve_provider_neutral_config(_full_env_legacy_only())
    assert res.missing_required_fields == ()
    assert res.conflicting_fields == ()
    assert res.invalid_fields == ()
    assert res.legacy_alias_used is True
    # The PROVIDER_ID + PROVIDER_KIND fields still come from the
    # provider-neutral names because they have no legacy aliases.
    for record in res.fields:
        if record.canonical_field in (
            m.PROVIDER_FIELD_PROVIDER_ID,
            m.PROVIDER_FIELD_PROVIDER_KIND,
        ):
            assert record.source_status == m.SOURCE_STATUS_PROVIDER_NEUTRAL
        else:
            assert record.source_status == m.SOURCE_STATUS_LEGACY_ALIAS


def test_resolve_bulk_neither_present_lists_required_missing():
    res = resolve_provider_neutral_config({})
    assert set(res.missing_required_fields) == set(
        m.PROVIDER_REQUIRED_FIELDS
    )
    assert res.conflicting_fields == ()
    assert res.invalid_fields == ()
    assert res.legacy_alias_used is False


def test_resolve_bulk_conflict_marks_conflicting_fields():
    env = dict(_full_env_provider_neutral_only())
    env["HELIUS_API_KEY"] = CANARY_API_KEY_ALT
    res = resolve_provider_neutral_config(env)
    assert m.PROVIDER_FIELD_API_KEY in res.conflicting_fields
    # The bundle's repr must not carry either canary key value.
    rep = repr(res)
    _assert_no_canary_leak(rep)


def test_resolve_bulk_invalid_provider_id_marks_invalid_field():
    env = dict(_full_env_provider_neutral_only())
    env[m.STAGE28_PROVIDER_ID_NAME] = ("h" + "ttps") + "://bad/webhook"
    res = resolve_provider_neutral_config(env)
    assert m.PROVIDER_FIELD_PROVIDER_ID in res.invalid_fields


def test_resolve_bulk_optional_provider_kind_missing_does_not_count_as_missing_required():
    env = dict(_full_env_provider_neutral_only())
    del env[m.STAGE28_PROVIDER_KIND_NAME]
    res = resolve_provider_neutral_config(env)
    assert res.missing_required_fields == ()
    # PROVIDER_KIND field is still in the per-field list with
    # MISSING status, but its failure_reason is ``None`` so it
    # does not contribute to invalid_fields either.
    for record in res.fields:
        if record.canonical_field == m.PROVIDER_FIELD_PROVIDER_KIND:
            assert record.field_status == m.FIELD_STATUS_MISSING
            assert record.failure_reason is None


def test_resolve_bulk_preserves_canonical_field_order():
    res = resolve_provider_neutral_config({})
    actual_order = tuple(r.canonical_field for r in res.fields)
    assert actual_order == m.PROVIDER_FIELD_VALUES


def test_resolve_bulk_repr_no_canary_leak_under_any_config():
    # Stress: the bulk repr must NEVER leak a canary substring,
    # regardless of which axis triggered.
    for env in (
        _full_env_provider_neutral_only(),
        _full_env_legacy_only(),
        {
            m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME: CANARY_GRPC_ENDPOINT,
            "HELIUS_GRPC_ENDPOINT": CANARY_GRPC_ENDPOINT_ALT,
        },
    ):
        res = resolve_provider_neutral_config(env)
        _assert_no_canary_leak(repr(res))
