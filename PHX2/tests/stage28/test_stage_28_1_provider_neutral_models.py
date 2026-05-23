"""Stage 28.1 provider-neutral model tests.

Pins:

  * Locked closed-set vocabularies (field status / source status
    / readiness status / redaction status / provider kind /
    failure reason / field kind).
  * Locked canonical-field tokens and per-field env bindings.
  * Locked Stage 28.1 env-name constants and legacy alias tuples.
  * Provider-id allowlist + secret-like rejection paths.
  * Provider-kind closed-set acceptance / rejection.
  * Immutable ``NamedTuple`` record shapes; ``repr()`` / ``str()``
    on a SECRET-kind record never carries a raw value.
  * Module-local exception hierarchy carries only safe metadata.
"""

from __future__ import annotations

import pytest

from PHX2.stage28 import provider_neutral_models as m


# ---------------------------------------------------------------------------
# Distinctive canary fake values
# ---------------------------------------------------------------------------


# Distinctive, obviously fake canary values. The Stage 28.1
# redaction discipline asserts no public surface carries these
# substrings.
CANARY_PROVIDER_API_KEY: str = "CANARY_FAKE_PROVIDER_API_KEY_aaaaaa1111"
CANARY_PROVIDER_GRPC_ENDPOINT: str = "canary.fake.test:9999"
CANARY_PROVIDER_RPC_URL_PATH: str = "canary.fake.test/rpc/aaaa1111"


# ---------------------------------------------------------------------------
# Version axes
# ---------------------------------------------------------------------------


def test_stage28_1_minor_version_locked():
    assert m.STAGE28_1_MINOR_VERSION == "28.1"


def test_stage28_1_schema_version_locked():
    assert m.STAGE28_1_SCHEMA_VERSION == "stage28_v0_provider_neutral_config"


# ---------------------------------------------------------------------------
# Canonical-field tokens
# ---------------------------------------------------------------------------


def test_canonical_field_tokens_locked():
    assert m.PROVIDER_FIELD_GRPC_ENDPOINT == "PROVIDER_GRPC_ENDPOINT"
    assert m.PROVIDER_FIELD_RPC_URL == "PROVIDER_RPC_URL"
    assert m.PROVIDER_FIELD_API_KEY == "PROVIDER_API_KEY"
    assert m.PROVIDER_FIELD_PROVIDER_ID == "PROVIDER_ID"
    assert m.PROVIDER_FIELD_PROVIDER_KIND == "PROVIDER_KIND"


def test_provider_field_values_tuple_locked():
    assert m.PROVIDER_FIELD_VALUES == (
        "PROVIDER_GRPC_ENDPOINT",
        "PROVIDER_RPC_URL",
        "PROVIDER_API_KEY",
        "PROVIDER_ID",
        "PROVIDER_KIND",
    )


# ---------------------------------------------------------------------------
# Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_field_status_values_locked():
    assert m.FIELD_STATUS_PRESENT == "PRESENT"
    assert m.FIELD_STATUS_MISSING == "MISSING"
    assert m.FIELD_STATUS_CONFLICT == "CONFLICT"
    assert m.FIELD_STATUS_INVALID == "INVALID"
    assert set(m.FIELD_STATUS_VALUES) == {
        "PRESENT", "MISSING", "CONFLICT", "INVALID",
    }


def test_source_status_values_locked():
    assert set(m.SOURCE_STATUS_VALUES) == {
        "PROVIDER_NEUTRAL",
        "LEGACY_ALIAS",
        "BOTH_SAME",
        "BOTH_CONFLICT",
        "MISSING",
    }


def test_readiness_status_values_locked():
    assert set(m.READINESS_STATUS_VALUES) == {"READY", "NOT_READY"}


def test_redaction_status_values_locked():
    assert set(m.REDACTION_STATUS_VALUES) == {
        "REDACTED",
        "SAFE_LABEL_ONLY",
        "NO_SECRET_MATERIAL",
    }


def test_failure_reason_values_locked():
    expected = {
        "MISSING_REQUIRED_FIELD",
        "CONFLICTING_PROVIDER_ENV_VALUES",
        "INVALID_PROVIDER_ID",
        "INVALID_PROVIDER_KIND",
        "SECRET_LIKE_PROVIDER_LABEL",
        "UNSUPPORTED_PROVIDER_KIND",
    }
    assert set(m.FAILURE_REASON_VALUES) == expected


def test_provider_kind_values_locked():
    assert set(m.PROVIDER_KIND_VALUES) == {
        "yellowstone_grpc",
        "json_rpc",
        "helius_legacy",
        "unknown",
    }


def test_field_kind_values_locked():
    assert set(m.FIELD_KIND_VALUES) == {"SECRET", "LABEL"}


# ---------------------------------------------------------------------------
# Env-name constants
# ---------------------------------------------------------------------------


def test_provider_neutral_env_names_locked():
    assert m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME == "PHX2_PROVIDER_GRPC_ENDPOINT"
    assert m.STAGE28_PROVIDER_RPC_URL_NAME == "PHX2_PROVIDER_RPC_URL"
    assert m.STAGE28_PROVIDER_API_KEY_NAME == "PHX2_PROVIDER_API_KEY"
    assert m.STAGE28_PROVIDER_ID_NAME == "PHX2_PROVIDER_ID"
    assert m.STAGE28_PROVIDER_KIND_NAME == "PHX2_PROVIDER_KIND"


def test_provider_neutral_env_names_tuple_complete():
    assert set(m.PROVIDER_NEUTRAL_ENV_NAMES) == {
        "PHX2_PROVIDER_GRPC_ENDPOINT",
        "PHX2_PROVIDER_RPC_URL",
        "PHX2_PROVIDER_API_KEY",
        "PHX2_PROVIDER_ID",
        "PHX2_PROVIDER_KIND",
    }


def test_legacy_alias_grpc_endpoint_names_locked():
    assert m.LEGACY_ALIAS_GRPC_ENDPOINT_NAMES == (
        "HELIUS_GRPC_ENDPOINT",
        "PHX2_HELIUS_GRPC_ENDPOINT",
    )


def test_legacy_alias_rpc_url_names_locked():
    assert m.LEGACY_ALIAS_RPC_URL_NAMES == (
        "HELIUS_RPC_URL",
        "PHX2_HELIUS_RPC_URL",
    )


def test_legacy_alias_api_key_names_locked():
    assert m.LEGACY_ALIAS_API_KEY_NAMES == (
        "HELIUS_API_KEY",
        "PHX2_HELIUS_API_KEY",
    )


def test_provider_field_env_binding_complete():
    # Every canonical field must have an entry.
    assert set(m.PROVIDER_FIELD_ENV_BINDING.keys()) == set(
        m.PROVIDER_FIELD_VALUES
    )


def test_provider_field_env_binding_neutral_names_match_constants():
    for canonical_field, (neutral_name, _aliases) in (
        m.PROVIDER_FIELD_ENV_BINDING.items()
    ):
        assert neutral_name.startswith("PHX2_PROVIDER_"), (
            f"{canonical_field}: neutral env name must use PHX2_PROVIDER_"
            f" prefix; got {neutral_name!r}"
        )


def test_provider_field_env_binding_legacy_aliases_for_helius_fields():
    grpc_binding = m.PROVIDER_FIELD_ENV_BINDING[
        m.PROVIDER_FIELD_GRPC_ENDPOINT
    ]
    assert grpc_binding[1] == m.LEGACY_ALIAS_GRPC_ENDPOINT_NAMES
    rpc_binding = m.PROVIDER_FIELD_ENV_BINDING[m.PROVIDER_FIELD_RPC_URL]
    assert rpc_binding[1] == m.LEGACY_ALIAS_RPC_URL_NAMES
    key_binding = m.PROVIDER_FIELD_ENV_BINDING[m.PROVIDER_FIELD_API_KEY]
    assert key_binding[1] == m.LEGACY_ALIAS_API_KEY_NAMES


def test_provider_field_env_binding_no_legacy_alias_for_id_kind():
    assert m.PROVIDER_FIELD_ENV_BINDING[
        m.PROVIDER_FIELD_PROVIDER_ID
    ][1] == ()
    assert m.PROVIDER_FIELD_ENV_BINDING[
        m.PROVIDER_FIELD_PROVIDER_KIND
    ][1] == ()


def test_provider_field_kind_partition():
    assert m.PROVIDER_FIELD_KIND[m.PROVIDER_FIELD_GRPC_ENDPOINT] == "SECRET"
    assert m.PROVIDER_FIELD_KIND[m.PROVIDER_FIELD_RPC_URL] == "SECRET"
    assert m.PROVIDER_FIELD_KIND[m.PROVIDER_FIELD_API_KEY] == "SECRET"
    assert m.PROVIDER_FIELD_KIND[m.PROVIDER_FIELD_PROVIDER_ID] == "LABEL"
    assert m.PROVIDER_FIELD_KIND[m.PROVIDER_FIELD_PROVIDER_KIND] == "LABEL"


def test_provider_required_fields_locked():
    assert set(m.PROVIDER_REQUIRED_FIELDS) == {
        "PROVIDER_GRPC_ENDPOINT",
        "PROVIDER_RPC_URL",
        "PROVIDER_API_KEY",
        "PROVIDER_ID",
    }
    # PROVIDER_KIND must NOT be required (the readiness layer
    # defaults it to ``unknown`` when absent).
    assert m.PROVIDER_FIELD_PROVIDER_KIND not in m.PROVIDER_REQUIRED_FIELDS


# ---------------------------------------------------------------------------
# Redaction token
# ---------------------------------------------------------------------------


def test_redaction_token_distinctive_literal():
    assert m.STAGE28_1_REDACTION_TOKEN == "<<STAGE28_1_REDACTED>>"
    assert m.STAGE28_1_REDACTION_TOKEN.startswith("<<")
    assert m.STAGE28_1_REDACTION_TOKEN.endswith(">>")
    # Distinct from the Stage 27 token so a scanner cannot
    # accidentally collide.
    assert m.STAGE28_1_REDACTION_TOKEN != "<<STAGE27_REDACTED>>"


# ---------------------------------------------------------------------------
# Provider-id allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    [
        "chainstack_yellowstone_primary",
        "helius_primary",
        "local_fake_provider",
        "chainstack-yellowstone",
        "p1",
        "abc",
        "ab",
    ],
)
def test_provider_id_label_accepts_valid_label(label):
    assert m.is_provider_id_label_safe(label) is True


@pytest.mark.parametrize(
    "label",
    [
        "",
        "a",                       # too short
        "A" * 65,                  # too long
        "Has Spaces",
        "Has-Uppercase",
        "_leading_underscore",
        "trailing_underscore_",
        "-leading-dash",
        "trailing-dash-",
        "two__underscores",
        "two--dashes",
        "with.dot",
        "with/slash",
        "with:colon",
        "with@at",
    ],
)
def test_provider_id_label_rejects_invalid_label(label):
    assert m.is_provider_id_label_safe(label) is False


@pytest.mark.parametrize(
    "label",
    [
        ("h" + "ttps") + "://example.fake",
        ("h" + "ttp") + "://example.fake/path",
        ("w" + "ss") + "://example.fake/ws",
        ("w" + "s") + "://example.fake/ws",
        "bearer_token_blob",
        "authorization_blob",
        "token=secret",
        "apikey=secret",
        "secret=very-secret-value",
        "password_blob",
        ("discord" + ".com") + "_webhook",
        "/webhooks/12345/abcdef",
    ],
)
def test_provider_id_label_secret_like_detected(label):
    # The function only flags secret-like patterns; it does not
    # assert allowlist failure, but a downstream resolver uses
    # this flag first to classify SECRET_LIKE_PROVIDER_LABEL
    # distinctly from a generic INVALID_PROVIDER_ID.
    assert m.is_provider_id_label_secret_like(label) is True


@pytest.mark.parametrize(
    "label",
    [
        "chainstack_yellowstone_primary",
        "helius_primary",
        "local_fake_provider",
    ],
)
def test_provider_id_label_not_secret_like_for_clean_labels(label):
    assert m.is_provider_id_label_secret_like(label) is False


# ---------------------------------------------------------------------------
# Provider-kind closed-set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    ["yellowstone_grpc", "json_rpc", "helius_legacy", "unknown"],
)
def test_provider_kind_supported(kind):
    assert m.is_provider_kind_supported(kind) is True


@pytest.mark.parametrize(
    "kind",
    [
        "",
        "YELLOWSTONE_GRPC",
        "yellowstone-grpc",
        "json_rpc_v2",
        "helius",
        "chainstack",
        "geyser",
        "Unknown",
    ],
)
def test_provider_kind_rejected(kind):
    assert m.is_provider_kind_supported(kind) is False


# ---------------------------------------------------------------------------
# canonical_field_kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "canonical_field,kind",
    [
        ("PROVIDER_GRPC_ENDPOINT", "SECRET"),
        ("PROVIDER_RPC_URL", "SECRET"),
        ("PROVIDER_API_KEY", "SECRET"),
        ("PROVIDER_ID", "LABEL"),
        ("PROVIDER_KIND", "LABEL"),
    ],
)
def test_canonical_field_kind_known(canonical_field, kind):
    assert m.canonical_field_kind(canonical_field) == kind


def test_canonical_field_kind_unknown_raises():
    with pytest.raises(ValueError):
        m.canonical_field_kind("not_a_real_canonical_field")


# ---------------------------------------------------------------------------
# Record-shape immutability and repr safety
# ---------------------------------------------------------------------------


def _build_secret_resolution_present(
    canonical_field: str, length: int
) -> m.ProviderFieldResolution:
    return m.ProviderFieldResolution(
        canonical_field=canonical_field,
        kind=m.FIELD_KIND_SECRET,
        field_status=m.FIELD_STATUS_PRESENT,
        source_status=m.SOURCE_STATUS_PROVIDER_NEUTRAL,
        provider_neutral_present=True,
        legacy_alias_present=False,
        legacy_alias_env_name=None,
        safe_label_value=None,
        raw_value_length=length,
        failure_reason=None,
    )


def _build_label_resolution_present(
    canonical_field: str, value: str
) -> m.ProviderFieldResolution:
    return m.ProviderFieldResolution(
        canonical_field=canonical_field,
        kind=m.FIELD_KIND_LABEL,
        field_status=m.FIELD_STATUS_PRESENT,
        source_status=m.SOURCE_STATUS_PROVIDER_NEUTRAL,
        provider_neutral_present=True,
        legacy_alias_present=False,
        legacy_alias_env_name=None,
        safe_label_value=value,
        raw_value_length=len(value),
        failure_reason=None,
    )


def test_provider_field_resolution_is_namedtuple_immutable():
    rec = _build_secret_resolution_present("PROVIDER_API_KEY", 24)
    assert isinstance(rec, tuple)
    with pytest.raises(AttributeError):
        rec.canonical_field = "spoof"  # type: ignore[misc]


def test_secret_resolution_repr_does_not_leak_value():
    # The SECRET-kind record carries ``safe_label_value=None`` by
    # construction; the canary value never reaches the record.
    rec = _build_secret_resolution_present(
        "PROVIDER_API_KEY", len(CANARY_PROVIDER_API_KEY)
    )
    rep = repr(rec)
    assert CANARY_PROVIDER_API_KEY not in rep
    assert CANARY_PROVIDER_GRPC_ENDPOINT not in rep
    assert CANARY_PROVIDER_RPC_URL_PATH not in rep
    assert "safe_label_value=None" in rep
    # No raw stage 28.1 redaction token leaks on a record either;
    # only the redacted-summary surface emits it.
    assert m.STAGE28_1_REDACTION_TOKEN not in rep


def test_label_resolution_repr_exposes_safe_value():
    rec = _build_label_resolution_present(
        "PROVIDER_ID", "chainstack_yellowstone_primary"
    )
    rep = repr(rec)
    assert "safe_label_value='chainstack_yellowstone_primary'" in rep


def test_provider_neutral_resolution_is_namedtuple_immutable():
    res = m.ProviderNeutralResolution(
        fields=(),
        missing_required_fields=(),
        conflicting_fields=(),
        invalid_fields=(),
        legacy_alias_used=False,
    )
    assert isinstance(res, tuple)
    with pytest.raises(AttributeError):
        res.legacy_alias_used = True  # type: ignore[misc]


def test_provider_neutral_readiness_report_is_namedtuple_immutable():
    report = m.ProviderNeutralReadinessReport(
        resolution=m.ProviderNeutralResolution(
            fields=(),
            missing_required_fields=(),
            conflicting_fields=(),
            invalid_fields=(),
            legacy_alias_used=False,
        ),
        readiness_status=m.READINESS_STATUS_NOT_READY,
        failure_reasons=(),
        provider_id=None,
        provider_kind=m.PROVIDER_KIND_UNKNOWN,
        redaction_status=m.REDACTION_STATUS_NO_SECRET_MATERIAL,
    )
    assert isinstance(report, tuple)
    with pytest.raises(AttributeError):
        report.readiness_status = "READY"  # type: ignore[misc]


def test_provider_neutral_redacted_summary_is_namedtuple_immutable():
    summary = m.ProviderNeutralRedactedSummary(
        lines=(),
        readiness_status=m.READINESS_STATUS_NOT_READY,
        redaction_status=m.REDACTION_STATUS_NO_SECRET_MATERIAL,
        redaction_token=m.STAGE28_1_REDACTION_TOKEN,
    )
    assert isinstance(summary, tuple)
    with pytest.raises(AttributeError):
        summary.lines = ("spoof",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Exception hierarchy carries only safe metadata
# ---------------------------------------------------------------------------


def test_stage28_1_provider_config_error_is_base_type():
    assert issubclass(
        m.Stage28_1ConflictingProviderEnvValuesError,
        m.Stage28_1ProviderConfigError,
    )
    assert issubclass(
        m.Stage28_1InvalidProviderLabelError,
        m.Stage28_1ProviderConfigError,
    )
    assert issubclass(
        m.Stage28_1RedactionLeakError,
        m.Stage28_1ProviderConfigError,
    )


def test_conflicting_env_values_error_carries_only_names():
    err = m.Stage28_1ConflictingProviderEnvValuesError(
        canonical_field="PROVIDER_GRPC_ENDPOINT",
        provider_neutral_env_name="PHX2_PROVIDER_GRPC_ENDPOINT",
        legacy_alias_env_name="HELIUS_GRPC_ENDPOINT",
    )
    rep = repr(err)
    msg = str(err)
    # Names appear; no canary endpoint value substring.
    assert "PROVIDER_GRPC_ENDPOINT" in msg
    assert "HELIUS_GRPC_ENDPOINT" in msg
    assert CANARY_PROVIDER_API_KEY not in msg
    assert CANARY_PROVIDER_GRPC_ENDPOINT not in msg
    assert CANARY_PROVIDER_API_KEY not in rep
    assert CANARY_PROVIDER_GRPC_ENDPOINT not in rep


def test_invalid_provider_label_error_carries_only_closed_set_reason():
    err = m.Stage28_1InvalidProviderLabelError(
        canonical_field="PROVIDER_ID",
        failure_reason="INVALID_PROVIDER_ID",
    )
    msg = str(err)
    assert "PROVIDER_ID" in msg
    assert "INVALID_PROVIDER_ID" in msg
    # Constructor does not accept the raw rejected label, so
    # passing the canary at the call site can be confirmed
    # impossible via the signature.
    import inspect

    params = set(inspect.signature(
        m.Stage28_1InvalidProviderLabelError.__init__
    ).parameters.keys())
    assert "raw_value" not in params
    assert "value" not in params
    assert "label" not in params


def test_redaction_leak_error_carries_only_safe_metadata():
    err = m.Stage28_1RedactionLeakError(
        canonical_field="PROVIDER_API_KEY",
        leak_context="readiness_summary_secret_safe_label",
        value_length=24,
    )
    msg = str(err)
    assert "PROVIDER_API_KEY" in msg
    assert "readiness_summary_secret_safe_label" in msg
    assert "length=24" in msg
    # No canary value substring.
    assert CANARY_PROVIDER_API_KEY not in msg
    assert CANARY_PROVIDER_GRPC_ENDPOINT not in msg
    assert CANARY_PROVIDER_RPC_URL_PATH not in msg
