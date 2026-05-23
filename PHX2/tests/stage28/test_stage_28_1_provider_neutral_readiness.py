"""Stage 28.1 provider-neutral readiness tests.

Every test uses obvious fake canary values; no real keys are read
from ``os.environ``. Each canary value is asserted not to appear
in any readiness summary, exception, repr, or artifact-like dict.

Pins:

  * ``detect_stage28_1_readiness`` projects the explicit ``env``
    mapping (never falls through to ``os.environ`` when ``env``
    is supplied).
  * ``READY`` requires every Stage 28.1 required canonical field
    to resolve cleanly (PRESENT, no CONFLICT, no INVALID).
  * Legacy-only required values still mark ``READY`` (with
    ``legacy_alias_used=True``).
  * Missing endpoint / RPC / API key / provider id -> ``NOT_READY``
    with ``MISSING_REQUIRED_FIELD``.
  * Invalid provider_id -> ``NOT_READY`` with
    ``INVALID_PROVIDER_ID`` or ``SECRET_LIKE_PROVIDER_LABEL``.
  * Invalid provider_kind -> ``NOT_READY`` with
    ``UNSUPPORTED_PROVIDER_KIND``.
  * Conflicting provider env values -> ``NOT_READY`` with
    ``CONFLICTING_PROVIDER_ENV_VALUES``.
  * ``redaction_status`` is one of the closed-set tokens.
  * Redacted summary lines never carry a canary substring.
  * Stage 28.1 readiness does NOT import / call any HTTP, gRPC,
    Discord, or scheduler library; the monkeypatched stub
    factories prove a regression by reference.
"""

from __future__ import annotations

import sys

import pytest

from PHX2.stage28 import provider_neutral_models as m
from PHX2.stage28.provider_neutral_readiness import (
    STAGE28_1_READ_ENV_NAMES,
    assess_provider_neutral_readiness,
    build_redacted_summary,
    detect_stage28_1_readiness,
    project_stage28_1_env,
)


# ---------------------------------------------------------------------------
# Distinctive canary fake values
# ---------------------------------------------------------------------------


CANARY_GRPC_ENDPOINT: str = "canary.fake.test:1234"
CANARY_GRPC_ENDPOINT_ALT: str = "canary.fake.test:9999"
CANARY_RPC_PATH: str = "canary.fake.test/rpc/aaaa1111"
CANARY_API_KEY: str = "CANARY_FAKE_PROVIDER_API_KEY_aaaaaa1111"
CANARY_PROVIDER_ID: str = "chainstack_yellowstone_primary"
CANARY_PROVIDER_KIND: str = "yellowstone_grpc"


def _canary_full_provider_neutral_env() -> dict[str, str]:
    return {
        m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME: CANARY_GRPC_ENDPOINT,
        m.STAGE28_PROVIDER_RPC_URL_NAME: (
            ("h" + "ttps") + "://" + CANARY_RPC_PATH
        ),
        m.STAGE28_PROVIDER_API_KEY_NAME: CANARY_API_KEY,
        m.STAGE28_PROVIDER_ID_NAME: CANARY_PROVIDER_ID,
        m.STAGE28_PROVIDER_KIND_NAME: CANARY_PROVIDER_KIND,
    }


def _canary_full_legacy_env() -> dict[str, str]:
    return {
        "HELIUS_GRPC_ENDPOINT": CANARY_GRPC_ENDPOINT,
        "HELIUS_RPC_URL": ("h" + "ttps") + "://" + CANARY_RPC_PATH,
        "HELIUS_API_KEY": CANARY_API_KEY,
        m.STAGE28_PROVIDER_ID_NAME: CANARY_PROVIDER_ID,
        m.STAGE28_PROVIDER_KIND_NAME: CANARY_PROVIDER_KIND,
    }


_CANARY_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    CANARY_GRPC_ENDPOINT,
    CANARY_GRPC_ENDPOINT_ALT,
    CANARY_RPC_PATH,
    CANARY_API_KEY,
)


def _assert_no_canary_leak_in_summary(
    summary: m.ProviderNeutralRedactedSummary,
) -> None:
    for line in summary.lines:
        for needle in _CANARY_FORBIDDEN_SUBSTRINGS:
            assert needle not in line, (
                f"redacted summary line leaks canary: line={line!r} "
                f"needle={needle!r}"
            )


def _assert_no_canary_leak_in_report(
    report: m.ProviderNeutralReadinessReport,
) -> None:
    rep = repr(report)
    for needle in _CANARY_FORBIDDEN_SUBSTRINGS:
        assert needle not in rep, f"report repr leaks canary: {needle!r}"


# ---------------------------------------------------------------------------
# Env-name surface lock
# ---------------------------------------------------------------------------


def test_stage28_1_read_env_names_includes_provider_neutral_set():
    for name in m.PROVIDER_NEUTRAL_ENV_NAMES:
        assert name in STAGE28_1_READ_ENV_NAMES


def test_stage28_1_read_env_names_includes_legacy_aliases():
    for alias in m.LEGACY_ALIAS_GRPC_ENDPOINT_NAMES:
        assert alias in STAGE28_1_READ_ENV_NAMES
    for alias in m.LEGACY_ALIAS_RPC_URL_NAMES:
        assert alias in STAGE28_1_READ_ENV_NAMES
    for alias in m.LEGACY_ALIAS_API_KEY_NAMES:
        assert alias in STAGE28_1_READ_ENV_NAMES


def test_stage28_1_read_env_names_only_known_names():
    """The Stage 28.1 env-read surface must be exactly the union
    of provider-neutral names + legacy aliases. If a future
    substage widens this, the boundary test catches the change."""
    expected = (
        set(m.PROVIDER_NEUTRAL_ENV_NAMES)
        | set(m.LEGACY_ALIAS_GRPC_ENDPOINT_NAMES)
        | set(m.LEGACY_ALIAS_RPC_URL_NAMES)
        | set(m.LEGACY_ALIAS_API_KEY_NAMES)
    )
    assert set(STAGE28_1_READ_ENV_NAMES) == expected


# ---------------------------------------------------------------------------
# Project env-name surface from explicit mapping
# ---------------------------------------------------------------------------


def test_project_env_explicit_mapping_filters_to_known_names():
    env = _canary_full_provider_neutral_env()
    # Extra unrelated env-like value must be filtered out.
    env["UNRELATED_NAME"] = "ignored-value"
    projected = project_stage28_1_env(env=env)
    assert "UNRELATED_NAME" not in projected
    assert m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME in projected


def test_project_env_explicit_empty_mapping_is_empty():
    assert project_stage28_1_env(env={}) == {}


# ---------------------------------------------------------------------------
# Readiness: READY paths
# ---------------------------------------------------------------------------


def test_readiness_ready_when_provider_neutral_only_full():
    env = _canary_full_provider_neutral_env()
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_READY
    assert report.failure_reasons == ()
    assert report.provider_id == CANARY_PROVIDER_ID
    assert report.provider_kind == CANARY_PROVIDER_KIND
    assert report.redaction_status == m.REDACTION_STATUS_REDACTED
    assert report.resolution.legacy_alias_used is False
    _assert_no_canary_leak_in_report(report)


def test_readiness_ready_when_legacy_only_full_marks_legacy_used():
    env = _canary_full_legacy_env()
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_READY
    assert report.failure_reasons == ()
    assert report.resolution.legacy_alias_used is True
    # The redacted summary should include the legacy_alias_used
    # warning line.
    summary = build_redacted_summary(report)
    joined = "\n".join(summary.lines)
    assert "legacy_alias_used=true" in joined
    _assert_no_canary_leak_in_summary(summary)


def test_readiness_ready_when_both_present_and_identical():
    env = dict(_canary_full_provider_neutral_env())
    env["HELIUS_GRPC_ENDPOINT"] = CANARY_GRPC_ENDPOINT
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_READY


# ---------------------------------------------------------------------------
# Readiness: NOT_READY paths
# ---------------------------------------------------------------------------


def test_readiness_not_ready_when_grpc_endpoint_missing():
    env = dict(_canary_full_provider_neutral_env())
    del env[m.STAGE28_PROVIDER_GRPC_ENDPOINT_NAME]
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_NOT_READY
    assert m.FAILURE_REASON_MISSING_REQUIRED_FIELD in report.failure_reasons
    _assert_no_canary_leak_in_report(report)


def test_readiness_not_ready_when_api_key_missing():
    env = dict(_canary_full_provider_neutral_env())
    del env[m.STAGE28_PROVIDER_API_KEY_NAME]
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_NOT_READY
    assert m.FAILURE_REASON_MISSING_REQUIRED_FIELD in report.failure_reasons


def test_readiness_not_ready_when_rpc_url_missing():
    env = dict(_canary_full_provider_neutral_env())
    del env[m.STAGE28_PROVIDER_RPC_URL_NAME]
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_NOT_READY
    assert m.FAILURE_REASON_MISSING_REQUIRED_FIELD in report.failure_reasons


def test_readiness_not_ready_when_provider_id_missing():
    env = dict(_canary_full_provider_neutral_env())
    del env[m.STAGE28_PROVIDER_ID_NAME]
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_NOT_READY
    assert m.FAILURE_REASON_MISSING_REQUIRED_FIELD in report.failure_reasons
    assert report.provider_id is None


def test_readiness_not_ready_when_provider_id_invalid():
    env = dict(_canary_full_provider_neutral_env())
    env[m.STAGE28_PROVIDER_ID_NAME] = "Has Spaces"
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_NOT_READY
    assert m.FAILURE_REASON_INVALID_PROVIDER_ID in report.failure_reasons
    assert report.provider_id is None


def test_readiness_not_ready_when_provider_id_secret_like():
    env = dict(_canary_full_provider_neutral_env())
    env[m.STAGE28_PROVIDER_ID_NAME] = (
        ("h" + "ttps") + "://canary.fake.test/webhooks/123"
    )
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_NOT_READY
    assert (
        m.FAILURE_REASON_SECRET_LIKE_PROVIDER_LABEL
        in report.failure_reasons
    )
    assert report.provider_id is None


def test_readiness_not_ready_when_provider_kind_invalid():
    env = dict(_canary_full_provider_neutral_env())
    env[m.STAGE28_PROVIDER_KIND_NAME] = "geyser_v2"
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_NOT_READY
    assert (
        m.FAILURE_REASON_UNSUPPORTED_PROVIDER_KIND
        in report.failure_reasons
    )
    # provider_kind defaults to unknown when the env value is INVALID.
    assert report.provider_kind == m.PROVIDER_KIND_UNKNOWN


def test_readiness_provider_kind_missing_defaults_unknown_and_stays_ready():
    env = dict(_canary_full_provider_neutral_env())
    del env[m.STAGE28_PROVIDER_KIND_NAME]
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_READY
    assert report.provider_kind == m.PROVIDER_KIND_UNKNOWN


def test_readiness_not_ready_when_conflict():
    env = dict(_canary_full_provider_neutral_env())
    env["HELIUS_GRPC_ENDPOINT"] = CANARY_GRPC_ENDPOINT_ALT
    report = detect_stage28_1_readiness(env=env)
    assert report.readiness_status == m.READINESS_STATUS_NOT_READY
    assert (
        m.FAILURE_REASON_CONFLICTING_PROVIDER_ENV_VALUES
        in report.failure_reasons
    )
    _assert_no_canary_leak_in_report(report)


# ---------------------------------------------------------------------------
# Redaction status
# ---------------------------------------------------------------------------


def test_redaction_status_redacted_when_secret_present():
    env = _canary_full_provider_neutral_env()
    report = detect_stage28_1_readiness(env=env)
    assert report.redaction_status == m.REDACTION_STATUS_REDACTED


def test_redaction_status_safe_label_only_when_only_labels_present():
    env = {
        m.STAGE28_PROVIDER_ID_NAME: CANARY_PROVIDER_ID,
        m.STAGE28_PROVIDER_KIND_NAME: CANARY_PROVIDER_KIND,
    }
    report = detect_stage28_1_readiness(env=env)
    assert report.redaction_status == m.REDACTION_STATUS_SAFE_LABEL_ONLY


def test_redaction_status_no_secret_material_when_nothing_set():
    report = detect_stage28_1_readiness(env={})
    assert report.redaction_status == m.REDACTION_STATUS_NO_SECRET_MATERIAL


# ---------------------------------------------------------------------------
# Redacted summary surface
# ---------------------------------------------------------------------------


def test_redacted_summary_lines_carry_no_canary_value():
    env = _canary_full_provider_neutral_env()
    report = detect_stage28_1_readiness(env=env)
    summary = build_redacted_summary(report)
    assert isinstance(summary, m.ProviderNeutralRedactedSummary)
    _assert_no_canary_leak_in_summary(summary)
    # The redaction token should appear on SECRET-field lines.
    joined = "\n".join(summary.lines)
    assert m.STAGE28_1_REDACTION_TOKEN in joined
    # And readiness_status / redaction_status / provider_id /
    # provider_kind tokens should be visible in the header.
    assert m.READINESS_STATUS_READY in summary.lines[0]
    assert m.REDACTION_STATUS_REDACTED in summary.lines[0]
    assert CANARY_PROVIDER_ID in summary.lines[0]
    assert CANARY_PROVIDER_KIND in summary.lines[0]


def test_redacted_summary_lines_under_conflict_do_not_leak():
    env = dict(_canary_full_provider_neutral_env())
    env["HELIUS_GRPC_ENDPOINT"] = CANARY_GRPC_ENDPOINT_ALT
    report = detect_stage28_1_readiness(env=env)
    summary = build_redacted_summary(report)
    _assert_no_canary_leak_in_summary(summary)
    joined = "\n".join(summary.lines)
    assert "CONFLICT" in joined
    assert "CONFLICTING_PROVIDER_ENV_VALUES" in joined


def test_redacted_summary_does_not_carry_helius_or_phx2_helius_value_tokens():
    # The legacy env name itself is fine; the raw VALUE must not
    # appear. The HELIUS_GRPC_ENDPOINT legacy-env-name marker IS
    # allowed because it identifies which alias resolved.
    env = _canary_full_legacy_env()
    report = detect_stage28_1_readiness(env=env)
    summary = build_redacted_summary(report)
    _assert_no_canary_leak_in_summary(summary)


def test_redacted_summary_raises_redaction_leak_when_secret_carries_safe_label():
    # Construct a deliberately malformed resolution where a
    # SECRET-kind record carries a non-``None`` safe_label_value;
    # the summary builder must raise rather than silently leak.
    bad_field = m.ProviderFieldResolution(
        canonical_field=m.PROVIDER_FIELD_API_KEY,
        kind=m.FIELD_KIND_SECRET,
        field_status=m.FIELD_STATUS_PRESENT,
        source_status=m.SOURCE_STATUS_PROVIDER_NEUTRAL,
        provider_neutral_present=True,
        legacy_alias_present=False,
        legacy_alias_env_name=None,
        safe_label_value="THIS_SHOULD_NEVER_HAVE_BEEN_SET",
        raw_value_length=8,
        failure_reason=None,
    )
    resolution = m.ProviderNeutralResolution(
        fields=(bad_field,),
        missing_required_fields=(),
        conflicting_fields=(),
        invalid_fields=(),
        legacy_alias_used=False,
    )
    bad_report = m.ProviderNeutralReadinessReport(
        resolution=resolution,
        readiness_status=m.READINESS_STATUS_READY,
        failure_reasons=(),
        provider_id=None,
        provider_kind=m.PROVIDER_KIND_UNKNOWN,
        redaction_status=m.REDACTION_STATUS_REDACTED,
    )
    with pytest.raises(m.Stage28_1RedactionLeakError) as excinfo:
        build_redacted_summary(bad_report)
    msg = str(excinfo.value)
    assert "PROVIDER_API_KEY" in msg
    assert "readiness_summary_secret_safe_label" in msg


# ---------------------------------------------------------------------------
# assess_provider_neutral_readiness from an in-hand resolution
# ---------------------------------------------------------------------------


def test_assess_readiness_round_trip_from_resolution_only():
    env = _canary_full_provider_neutral_env()
    report = detect_stage28_1_readiness(env=env)
    assert (
        assess_provider_neutral_readiness(report.resolution)
        == report
    )


# ---------------------------------------------------------------------------
# Stage 28.1 readiness does not import / call network libraries
# ---------------------------------------------------------------------------


_NETWORK_MODULE_NAMES: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    "discord",
    "telegram",
    "telethon",
    "tweepy",
)


def test_readiness_path_does_not_import_network_modules_during_call(
    monkeypatch: pytest.MonkeyPatch,
):
    # Snapshot of already-imported modules.
    before = {
        name for name in _NETWORK_MODULE_NAMES if name in sys.modules
    }

    # Monkeypatch the network modules so that any subsequent
    # ``import`` of them would fail loudly.
    for name in _NETWORK_MODULE_NAMES:
        monkeypatch.setitem(
            sys.modules,
            name,
            _ForbiddenNetworkModule(name),
        )

    env = _canary_full_provider_neutral_env()
    report = detect_stage28_1_readiness(env=env)
    summary = build_redacted_summary(report)
    assert summary.readiness_status == m.READINESS_STATUS_READY

    # The snapshot proves Stage 28.1 did not import anything new
    # from the network-module list. If it had, the
    # ``_ForbiddenNetworkModule`` would have raised on attribute
    # access during readiness; reaching here is the proof.
    after = {
        name for name in _NETWORK_MODULE_NAMES if name in sys.modules
    }
    # No new network module was added during the call (the
    # monkeypatched entries are also in ``after``, but they were
    # added by monkeypatch, not by Stage 28.1 readiness).
    new_after = after - before - set(_NETWORK_MODULE_NAMES)
    assert new_after == set()


class _ForbiddenNetworkModule:
    """Module stand-in that raises if any attribute is accessed.

    Used to assert Stage 28.1 readiness paths never touch network
    libraries. Plain ``import x`` succeeds (the module is already
    in ``sys.modules``), but the moment something tries to use
    it, this object raises.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, item: str):
        raise AssertionError(
            f"Stage 28.1 readiness path must not touch network "
            f"module {self._name!r}; attribute {item!r} accessed"
        )
