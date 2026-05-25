"""Stage 29.2 readiness boundary pin tests.

Locks the four env names, the closed-set status / refusal /
timeout-status sets, and the redaction discipline on the secret
record + readiness report.
"""

from __future__ import annotations

import dataclasses
import json
import pickle

import pytest

from PHX2.stage29 import stage29_2_birdeye_readiness as R
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_API_KEY_MISSING,
    BIRDEYE_REFUSAL_REASON_API_KEY_UNSAFE,
    BIRDEYE_REFUSAL_REASON_ENDPOINT_MISSING,
    BIRDEYE_REFUSAL_REASON_ENDPOINT_UNSAFE,
    BIRDEYE_REFUSAL_REASON_NONE,
    BIRDEYE_REFUSAL_REASON_TIMEOUT_INVALID,
    Stage29_2BirdeyeError,
)


# A well-shaped Stage 29.2 env mapping for the happy path.
GOOD_API_KEY = "abcd1234efgh5678ijkl9012mnop3456"
GOOD_BASE_URL = "https://aaaa-bbbb.example"


def _env(
    *,
    api_key=GOOD_API_KEY,
    base_url=GOOD_BASE_URL,
    live="1",
    timeout=None,
):
    out: dict[str, str] = {}
    if api_key is not None:
        out[R.ENV_NAME_BIRDEYE_API_KEY] = api_key
    if base_url is not None:
        out[R.ENV_NAME_BIRDEYE_BASE_URL] = base_url
    if live is not None:
        out[R.ENV_NAME_ALLOW_LIVE_HTTP] = live
    if timeout is not None:
        out[R.ENV_NAME_HTTP_TIMEOUT_SECONDS] = timeout
    return out


# ---------------------------------------------------------------------------
# Env-name pins
# ---------------------------------------------------------------------------


def test_env_name_api_key_pinned():
    assert (
        R.ENV_NAME_BIRDEYE_API_KEY
        == "PHX2_STAGE29_2_BIRDEYE_API_KEY"
    )


def test_env_name_base_url_pinned():
    assert (
        R.ENV_NAME_BIRDEYE_BASE_URL
        == "PHX2_STAGE29_2_BIRDEYE_BASE_URL"
    )


def test_env_name_allow_live_http_pinned():
    assert (
        R.ENV_NAME_ALLOW_LIVE_HTTP
        == "PHX2_STAGE29_2_ALLOW_LIVE_HTTP"
    )


def test_env_name_http_timeout_seconds_pinned():
    assert (
        R.ENV_NAME_HTTP_TIMEOUT_SECONDS
        == "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS"
    )


def test_read_env_names_tuple_is_exactly_four():
    assert R.STAGE29_2_READ_ENV_NAMES == (
        "PHX2_STAGE29_2_BIRDEYE_API_KEY",
        "PHX2_STAGE29_2_BIRDEYE_BASE_URL",
        "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
        "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS",
    )


def test_no_phx1_fallback_env_name_anywhere_in_module():
    import importlib
    mod = importlib.import_module(
        "PHX2.stage29.stage29_2_birdeye_readiness"
    )
    with open(mod.__file__, "r", encoding="utf-8") as f:
        source = f.read()
    # Stage 29.2 must NOT fall back to a generic BIRDEYE_API_KEY
    # / BIRDEYE_BASE_URL name. Two concatenated needles so this
    # test file itself does not trip the same scan.
    forbidden = (
        "BIRDEYE_API" + "_KEY=",
        "B" + "earer ",
    )
    for needle in forbidden:
        assert needle not in source


# ---------------------------------------------------------------------------
# project_stage29_2_env_safe redaction discipline
# ---------------------------------------------------------------------------


def test_safe_projection_redacts_raw_values():
    proj = R.project_stage29_2_env_safe(env=_env())
    assert proj.api_key_present is True
    assert proj.base_url_present is True
    assert proj.live_flag_present is True
    assert proj.live_flag_value_is_allow is True
    assert proj.timeout_status == R.TIMEOUT_STATUS_DEFAULT
    # repr/asdict must NOT carry the raw values
    r = repr(proj)
    assert GOOD_API_KEY not in r
    assert GOOD_BASE_URL not in r
    d = dataclasses.asdict(proj)
    assert GOOD_API_KEY not in json.dumps(d)
    assert GOOD_BASE_URL not in json.dumps(d)


def test_safe_projection_with_invalid_timeout():
    proj = R.project_stage29_2_env_safe(
        env=_env(timeout="not-an-int")
    )
    assert proj.timeout_status == R.TIMEOUT_STATUS_INVALID


def test_safe_projection_with_valid_timeout_override():
    proj = R.project_stage29_2_env_safe(
        env=_env(timeout="45")
    )
    assert proj.timeout_status == R.TIMEOUT_STATUS_OVERRIDE


def test_safe_projection_with_empty_env():
    proj = R.project_stage29_2_env_safe(env={})
    assert proj.api_key_present is False
    assert proj.base_url_present is False
    assert proj.live_flag_present is False
    assert proj.timeout_present is False
    assert proj.timeout_status == R.TIMEOUT_STATUS_DEFAULT


def test_safe_projection_live_flag_only_truthy_for_exact_1():
    for val in ("0", "true", "yes", "on", "True"):
        proj = R.project_stage29_2_env_safe(
            env=_env(live=val)
        )
        assert proj.live_flag_present is True
        assert proj.live_flag_value_is_allow is False
    proj = R.project_stage29_2_env_safe(env=_env(live="1"))
    assert proj.live_flag_value_is_allow is True


# ---------------------------------------------------------------------------
# detect_stage29_2_birdeye_readiness verdicts
# ---------------------------------------------------------------------------


def test_readiness_happy_path_yields_ready():
    rep = R.detect_stage29_2_birdeye_readiness(env=_env())
    assert rep.status == R.READINESS_STATUS_READY
    assert rep.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE


def test_readiness_missing_base_url():
    rep = R.detect_stage29_2_birdeye_readiness(
        env=_env(base_url=None),
    )
    assert rep.status == R.READINESS_STATUS_NOT_READY
    assert rep.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_ENDPOINT_MISSING
    )


def test_readiness_unsafe_base_url():
    rep = R.detect_stage29_2_birdeye_readiness(
        env=_env(base_url="http://insecure.example"),
    )
    assert rep.status == R.READINESS_STATUS_NOT_READY
    assert rep.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_ENDPOINT_UNSAFE
    )


def test_readiness_missing_api_key():
    rep = R.detect_stage29_2_birdeye_readiness(
        env=_env(api_key=None),
    )
    assert rep.status == R.READINESS_STATUS_NOT_READY
    assert rep.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_API_KEY_MISSING
    )


def test_readiness_unsafe_api_key():
    rep = R.detect_stage29_2_birdeye_readiness(
        env=_env(api_key="short"),
    )
    assert rep.status == R.READINESS_STATUS_NOT_READY
    assert rep.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_API_KEY_UNSAFE
    )


def test_readiness_invalid_timeout():
    rep = R.detect_stage29_2_birdeye_readiness(
        env=_env(timeout="0"),
    )
    assert rep.status == R.READINESS_STATUS_NOT_READY
    assert rep.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_TIMEOUT_INVALID
    )


def test_readiness_negative_timeout_string():
    rep = R.detect_stage29_2_birdeye_readiness(
        env=_env(timeout="-1"),
    )
    assert rep.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_TIMEOUT_INVALID
    )


def test_readiness_report_repr_carries_only_safe_fields():
    rep = R.detect_stage29_2_birdeye_readiness(env=_env())
    r = repr(rep)
    assert GOOD_API_KEY not in r
    assert GOOD_BASE_URL not in r


# ---------------------------------------------------------------------------
# Endpoint-secret + runtime-config redaction
# ---------------------------------------------------------------------------


def test_build_endpoint_secret_from_env_ok():
    sec = R.build_endpoint_secret_from_env(env=_env())
    # Raw values are reachable via the explicit reveal-methods
    # only -- never via repr / asdict / pickle.
    assert sec.reveal_api_key() == GOOD_API_KEY
    assert sec.reveal_base_url() == GOOD_BASE_URL


def test_build_endpoint_secret_raises_on_not_ready():
    with pytest.raises(R.Stage29_2ReadinessEnvError) as exc:
        R.build_endpoint_secret_from_env(env={})
    assert exc.value.refusal_reason in (
        BIRDEYE_REFUSAL_REASON_ENDPOINT_MISSING,
        BIRDEYE_REFUSAL_REASON_API_KEY_MISSING,
    )
    # Exception NEVER carries the raw values
    assert GOOD_API_KEY not in str(exc.value)
    assert GOOD_BASE_URL not in str(exc.value)


def test_endpoint_secret_repr_redacts_raw_values():
    sec = R.build_endpoint_secret_from_env(env=_env())
    r = repr(sec)
    s = str(sec)
    assert GOOD_API_KEY not in r
    assert GOOD_BASE_URL not in r
    assert GOOD_API_KEY not in s
    assert GOOD_BASE_URL not in s
    assert "STAGE29_2_REDACTED" in r


def test_endpoint_secret_safe_summary_redacts_raw_values():
    sec = R.build_endpoint_secret_from_env(env=_env())
    summary = sec.safe_summary()
    serialized = json.dumps(summary)
    assert GOOD_API_KEY not in serialized
    assert GOOD_BASE_URL not in serialized
    assert summary["api_key_length"] == len(GOOD_API_KEY)
    assert summary["base_url_length"] == len(GOOD_BASE_URL)


def test_endpoint_secret_pickle_round_trip_is_safe_to_log():
    # The secret IS picklable (it's a normal frozen dataclass);
    # the redaction discipline is enforced by repr / safe_summary,
    # not by blocking pickle. Confirm: after unpickling, repr
    # still redacts.
    sec = R.build_endpoint_secret_from_env(env=_env())
    blob = pickle.dumps(sec)
    sec2 = pickle.loads(blob)
    assert repr(sec2) == repr(sec)
    assert GOOD_API_KEY not in repr(sec2)


def test_runtime_config_carries_secret_subobject():
    rc = R.build_runtime_config_from_env(env=_env())
    assert isinstance(
        rc.endpoint_secret, R.Stage29_2BirdeyeEndpointSecret
    )
    assert rc.live_flag_set is True
    # The runtime config's own repr must NOT echo raw values.
    r = repr(rc)
    assert GOOD_API_KEY not in r
    assert GOOD_BASE_URL not in r


def test_runtime_config_invalid_timeout_rejected_at_construct():
    sec = R.build_endpoint_secret_from_env(env=_env())
    with pytest.raises(Stage29_2BirdeyeError):
        R.Stage29_2BirdeyeRuntimeConfig(
            endpoint_secret=sec,
            timeout_seconds=0,  # below MIN
            live_flag_set=True,
        )
