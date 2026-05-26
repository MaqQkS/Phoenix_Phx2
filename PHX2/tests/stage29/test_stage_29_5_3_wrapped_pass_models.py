"""Stage 29.5.3 wrapped-pass model tests.

Pins the closed-set Stage 29.5.3 observation status vocabulary,
the immutable ``Stage29_5_3WrappedPassObservation`` frozen
dataclass + its validators, the locked schema version, and the
Stage 29.5.3 module-local exception hierarchy.
"""

from __future__ import annotations

import pytest

from pathlib import Path

from PHX2.stage29.stage29_5_3_wrapped_pass_models import (
    OBSERVATION_STATUS_COMPOSED,
    OBSERVATION_STATUS_COMPOSITION_REJECTED,
    OBSERVATION_STATUS_NO_CANDIDATE_AXES,
    OBSERVATION_STATUS_PROVIDER_REJECTED,
    STAGE29_5_3_OBSERVATION_FIELD_NAMES,
    STAGE29_5_3_OBSERVATION_SCHEMA_VERSION,
    STAGE29_5_3_OBSERVATION_STATUS_VALUES,
    Stage29_5_3MigrationEvidenceProviderError,
    Stage29_5_3PendingPassObservation,
    Stage29_5_3SideChannelArtifactError,
    Stage29_5_3WrappedPassError,
    Stage29_5_3WrappedPassObservation,
    is_stage29_5_3_observation_status_value,
    is_stage29_5_3_safe_candidate_base_mint,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    REDACTION_STATUS_SAFE,
)


_OBSERVED_AT = "2026-05-26T12:00:00+00:00"


def _build_obs(
    *,
    pass_index: int = 1,
    observation_status: str = (
        OBSERVATION_STATUS_NO_CANDIDATE_AXES
    ),
    candidate_base_mint=None,
    join_status_echoed=None,
    measurement_status_echoed=None,
    post_migration_ath_verified_echoed=None,
    warnings_echoed=(),
    observed_at_utc: str = _OBSERVED_AT,
) -> Stage29_5_3WrappedPassObservation:
    return Stage29_5_3WrappedPassObservation(
        pass_index=pass_index,
        observation_status=observation_status,
        candidate_base_mint=candidate_base_mint,
        join_status_echoed=join_status_echoed,
        measurement_status_echoed=measurement_status_echoed,
        post_migration_ath_verified_echoed=(
            post_migration_ath_verified_echoed
        ),
        warnings_echoed=warnings_echoed,
        observed_at_utc=observed_at_utc,
    )


# ---------------------------------------------------------------------------
# Closed-set vocabulary
# ---------------------------------------------------------------------------


def test_observation_status_values_are_closed_set_quartet():
    assert STAGE29_5_3_OBSERVATION_STATUS_VALUES == (
        OBSERVATION_STATUS_NO_CANDIDATE_AXES,
        OBSERVATION_STATUS_COMPOSED,
        OBSERVATION_STATUS_COMPOSITION_REJECTED,
        OBSERVATION_STATUS_PROVIDER_REJECTED,
    )


def test_observation_status_predicate_accepts_each_token():
    for token in STAGE29_5_3_OBSERVATION_STATUS_VALUES:
        assert is_stage29_5_3_observation_status_value(token)


def test_observation_status_predicate_rejects_non_str_and_unknown_token():
    assert not is_stage29_5_3_observation_status_value(None)
    assert not is_stage29_5_3_observation_status_value(0)
    assert not is_stage29_5_3_observation_status_value(b"COMPOSED")
    assert not is_stage29_5_3_observation_status_value(
        "COMPOSED_BUT_NOT_IN_THE_VOCAB"
    )


def test_schema_version_locked_string():
    assert STAGE29_5_3_OBSERVATION_SCHEMA_VERSION == (
        "stage29_5_3_wrapped_pass_observation_v0"
    )


def test_observation_field_names_lock_order():
    assert STAGE29_5_3_OBSERVATION_FIELD_NAMES == (
        "schema_version",
        "pass_index",
        "observation_status",
        "candidate_base_mint",
        "join_status_echoed",
        "measurement_status_echoed",
        "post_migration_ath_verified_echoed",
        "warnings_echoed",
        "observed_at_utc",
        "filter_enforcement_status",
        "redaction_status",
    )


# ---------------------------------------------------------------------------
# Dataclass: happy-path construction
# ---------------------------------------------------------------------------


def test_observation_happy_path_no_candidate_axes():
    obs = _build_obs()
    assert obs.pass_index == 1
    assert (
        obs.observation_status
        == OBSERVATION_STATUS_NO_CANDIDATE_AXES
    )
    assert obs.candidate_base_mint is None
    assert obs.join_status_echoed is None
    assert obs.measurement_status_echoed is None
    assert obs.post_migration_ath_verified_echoed is None
    assert obs.warnings_echoed == ()
    assert obs.observed_at_utc == _OBSERVED_AT
    assert (
        obs.filter_enforcement_status
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    assert obs.redaction_status == REDACTION_STATUS_SAFE
    assert obs.schema_version == (
        STAGE29_5_3_OBSERVATION_SCHEMA_VERSION
    )


def test_observation_happy_path_composed():
    obs = _build_obs(
        pass_index=3,
        observation_status=OBSERVATION_STATUS_COMPOSED,
        candidate_base_mint="BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump",
        join_status_echoed="JOINED",
        measurement_status_echoed="COMPLETE",
        post_migration_ath_verified_echoed=True,
        warnings_echoed=("MIGRATION_SOURCE_UNKNOWN",),
    )
    assert obs.pass_index == 3
    assert obs.observation_status == OBSERVATION_STATUS_COMPOSED
    assert obs.candidate_base_mint == (
        "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
    )
    assert obs.join_status_echoed == "JOINED"
    assert obs.measurement_status_echoed == "COMPLETE"
    assert obs.post_migration_ath_verified_echoed is True
    assert obs.warnings_echoed == (
        "MIGRATION_SOURCE_UNKNOWN",
    )


def test_observation_is_frozen():
    obs = _build_obs()
    with pytest.raises(Exception):
        obs.pass_index = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Dataclass: validator rejections
# ---------------------------------------------------------------------------


def test_observation_rejects_non_int_pass_index():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(pass_index="1")  # type: ignore[arg-type]


def test_observation_rejects_bool_pass_index():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(pass_index=True)  # type: ignore[arg-type]


def test_observation_rejects_zero_pass_index():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(pass_index=0)


def test_observation_rejects_negative_pass_index():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(pass_index=-1)


def test_observation_rejects_non_closed_set_observation_status():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(observation_status="SOMETHING_ELSE")


def test_observation_rejects_empty_candidate_base_mint():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint="")


def test_observation_rejects_too_long_candidate_base_mint():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint="A" * 65)


def test_observation_rejects_too_short_candidate_base_mint():
    """Stage 29.5.3 candidate_base_mint must be ≥ 32 chars; the
    Solana base58 mint window is [32, 64].
    """
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint="A" * 31)


def test_observation_rejects_url_shaped_candidate_base_mint():
    """A URL-shaped string contains characters outside the base58
    alphabet (``h`` is in base58 but ``t``/``p``/``:``/``/`` are
    not all in base58 — specifically ``:`` and ``/`` are not).
    The Stage 29.5.3 candidate_base_mint validator rejects it.
    """
    needle = (
        "h" + "ttps://discord.com/webhooks/foo"
    ).ljust(40, "x")
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_bearer_shaped_candidate_base_mint():
    needle = ("B" + "earer abcdefghij").ljust(40, "x")
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_sk_prefixed_candidate_base_mint():
    """The ``-`` in ``sk-`` is not in the base58 alphabet."""
    needle = ("s" + "k-test1234567890abcd").ljust(40, "x")
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_pk_prefixed_candidate_base_mint():
    needle = ("p" + "k-test1234567890abcd").ljust(40, "x")
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_authorization_shaped_candidate_base_mint():
    """``Authorization:`` includes a ``:`` which is not base58."""
    needle = ("A" + "uthorization: token").ljust(40, "x")
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_equals_in_candidate_base_mint():
    """An ``=`` (env-assignment shape, base64 padding, query
    string separator) is not in the base58 alphabet.
    """
    needle = "KEY=value12345678901234567890abc"
    assert len(needle) == 32
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_whitespace_in_candidate_base_mint():
    needle = "abcdefghijklm nopqrstuvwxyz123456"
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_non_printable_candidate_base_mint():
    needle = "abcdefghijklm\nopqrstuvwxyz123456"
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_zero_digit_candidate_base_mint():
    """``0`` is forbidden in the Solana base58 alphabet (so are
    ``O`` / ``I`` / ``l``).
    """
    needle = "0123456789abcdefghijklmnopqrstuv"
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_capital_o_candidate_base_mint():
    needle = "Oabcdefghijklmnopqrstuvwxyz12345"
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_capital_i_candidate_base_mint():
    needle = "Iabcdefghijklmnopqrstuvwxyz12345"
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_rejects_lowercase_l_candidate_base_mint():
    needle = "labcdefghijkmnopqrstuvwxyz123456"
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(candidate_base_mint=needle)


def test_observation_accepts_valid_base58_mint_min_length():
    """A 32-char Solana base58 mint string is the minimum
    allowed candidate_base_mint length.
    """
    needle = "abcdefghijkmnopqrstuvwxyz1234567"
    assert len(needle) == 32
    obs = _build_obs(candidate_base_mint=needle)
    assert obs.candidate_base_mint == needle


def test_observation_accepts_valid_base58_mint_canonical_44():
    """A 44-char Solana base58 mint string is the canonical
    Pump.fun-style mint length.
    """
    needle = "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
    assert len(needle) == 44
    obs = _build_obs(candidate_base_mint=needle)
    assert obs.candidate_base_mint == needle


def test_observation_accepts_valid_base58_mint_max_length():
    """A 64-char Solana base58 mint string is the maximum
    allowed candidate_base_mint length.
    """
    needle = "abcdefghijkmnopqrstuvwxyz123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdef"
    assert len(needle) == 64
    obs = _build_obs(candidate_base_mint=needle)
    assert obs.candidate_base_mint == needle


def test_observation_rejects_non_closed_set_join_status_echoed():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(join_status_echoed="MAYBE_JOINED")


def test_observation_rejects_non_closed_set_measurement_status_echoed():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(measurement_status_echoed="MAYBE_COMPLETE")


def test_observation_rejects_non_bool_post_migration_ath_verified_echoed():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(
            post_migration_ath_verified_echoed=1,
        )  # type: ignore[arg-type]


def test_observation_rejects_non_tuple_warnings_echoed():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(
            warnings_echoed=["MIGRATION_MISSING"],
        )  # type: ignore[arg-type]


def test_observation_rejects_non_closed_set_warning_code():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(
            warnings_echoed=("SOMETHING_ELSE",),
        )


def test_observation_rejects_duplicate_warning_codes():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(
            warnings_echoed=(
                "MIGRATION_MISSING",
                "MIGRATION_MISSING",
            ),
        )


def test_observation_rejects_empty_observed_at_utc():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(observed_at_utc="")


def test_observation_rejects_too_long_observed_at_utc():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(observed_at_utc="A" * 65)


def test_observation_rejects_non_str_observed_at_utc():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(observed_at_utc=1234)  # type: ignore[arg-type]


def test_observation_rejects_non_printable_observed_at_utc():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_obs(observed_at_utc="2026-05-26\n12:00:00")


def test_observation_rejects_override_of_locked_filter_enforcement_status():
    with pytest.raises(Stage29_5_3WrappedPassError):
        Stage29_5_3WrappedPassObservation(
            pass_index=1,
            observation_status=(
                OBSERVATION_STATUS_NO_CANDIDATE_AXES
            ),
            candidate_base_mint=None,
            join_status_echoed=None,
            measurement_status_echoed=None,
            post_migration_ath_verified_echoed=None,
            warnings_echoed=(),
            observed_at_utc=_OBSERVED_AT,
            filter_enforcement_status="ACTIVE",
        )


def test_observation_rejects_override_of_locked_redaction_status():
    with pytest.raises(Stage29_5_3WrappedPassError):
        Stage29_5_3WrappedPassObservation(
            pass_index=1,
            observation_status=(
                OBSERVATION_STATUS_NO_CANDIDATE_AXES
            ),
            candidate_base_mint=None,
            join_status_echoed=None,
            measurement_status_echoed=None,
            post_migration_ath_verified_echoed=None,
            warnings_echoed=(),
            observed_at_utc=_OBSERVED_AT,
            redaction_status="REDACTED",
        )


def test_observation_rejects_override_of_locked_schema_version():
    with pytest.raises(Stage29_5_3WrappedPassError):
        Stage29_5_3WrappedPassObservation(
            pass_index=1,
            observation_status=(
                OBSERVATION_STATUS_NO_CANDIDATE_AXES
            ),
            candidate_base_mint=None,
            join_status_echoed=None,
            measurement_status_echoed=None,
            post_migration_ath_verified_echoed=None,
            warnings_echoed=(),
            observed_at_utc=_OBSERVED_AT,
            schema_version="stage29_5_3_wrapped_pass_observation_v1",
        )


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_stage29_5_3_wrapped_pass_error_base_carries_reason_and_detail():
    err = Stage29_5_3WrappedPassError("REASON_X", "detail Y")
    assert err.reason == "REASON_X"
    assert err.detail == "detail Y"
    assert "REASON_X" in str(err)


def test_stage29_5_3_wrapped_pass_error_rejects_non_str_reason():
    with pytest.raises(ValueError):
        Stage29_5_3WrappedPassError(123)  # type: ignore[arg-type]


def test_stage29_5_3_wrapped_pass_error_rejects_non_str_detail():
    with pytest.raises(ValueError):
        Stage29_5_3WrappedPassError(
            "REASON",
            detail=123,
        )  # type: ignore[arg-type]


def test_provider_error_is_wrapped_pass_error_subclass():
    err = Stage29_5_3MigrationEvidenceProviderError("FOO")
    assert isinstance(err, Stage29_5_3WrappedPassError)


def test_side_channel_artifact_error_is_wrapped_pass_error_subclass():
    err = Stage29_5_3SideChannelArtifactError("FOO")
    assert isinstance(err, Stage29_5_3WrappedPassError)


# ---------------------------------------------------------------------------
# repr() safety (no raw URL / secret literal could appear because
# the dataclass only admits closed-set tokens / safe strings)
# ---------------------------------------------------------------------------


def test_observation_repr_is_safe_to_log():
    obs = _build_obs(
        observation_status=OBSERVATION_STATUS_COMPOSED,
        candidate_base_mint=(
            "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
        ),
        join_status_echoed="JOINED",
        measurement_status_echoed="COMPLETE",
        post_migration_ath_verified_echoed=True,
        warnings_echoed=(),
    )
    text = repr(obs)
    forbidden = (
        "http" + "s://",
        "http" + "://",
        "ws" + "s://",
        "ws" + "://",
        "discord" + ".com",
        "/webhooks/",
        "B" + "earer ",
        "A" + "uthorization:",
        "s" + "k-",
        "p" + "k-",
    )
    for needle in forbidden:
        assert needle not in text


# ---------------------------------------------------------------------------
# is_stage29_5_3_safe_candidate_base_mint predicate
# ---------------------------------------------------------------------------


def test_safe_candidate_base_mint_predicate_accepts_canonical_pump_mint():
    assert is_stage29_5_3_safe_candidate_base_mint(
        "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump",
    )


def test_safe_candidate_base_mint_predicate_rejects_none():
    assert not is_stage29_5_3_safe_candidate_base_mint(None)


def test_safe_candidate_base_mint_predicate_rejects_bytes():
    assert not is_stage29_5_3_safe_candidate_base_mint(
        b"BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump",
    )


def test_safe_candidate_base_mint_predicate_rejects_too_short():
    assert not is_stage29_5_3_safe_candidate_base_mint(
        "abc",
    )


def test_safe_candidate_base_mint_predicate_rejects_too_long():
    assert not is_stage29_5_3_safe_candidate_base_mint(
        "a" * 65,
    )


def test_safe_candidate_base_mint_predicate_rejects_url():
    assert not is_stage29_5_3_safe_candidate_base_mint(
        ("h" + "ttps://discord.com/webhooks/abc").ljust(40, "x"),
    )


def test_safe_candidate_base_mint_predicate_rejects_bearer():
    assert not is_stage29_5_3_safe_candidate_base_mint(
        ("B" + "earer abc").ljust(40, "x"),
    )


def test_safe_candidate_base_mint_predicate_rejects_sk_prefix():
    assert not is_stage29_5_3_safe_candidate_base_mint(
        ("s" + "k-test12345").ljust(40, "x"),
    )


def test_safe_candidate_base_mint_predicate_rejects_whitespace():
    assert not is_stage29_5_3_safe_candidate_base_mint(
        "abcdefghijklm nopqrstuvwxyz123456",
    )


def test_safe_candidate_base_mint_predicate_rejects_equals():
    assert not is_stage29_5_3_safe_candidate_base_mint(
        "KEY=value12345678901234567890abc",
    )


def test_safe_candidate_base_mint_predicate_rejects_zero():
    assert not is_stage29_5_3_safe_candidate_base_mint(
        "0123456789abcdefghijklmnopqrstuv",
    )


# ---------------------------------------------------------------------------
# Stage29_5_3PendingPassObservation
# ---------------------------------------------------------------------------


def _build_pending(
    *,
    pass_index: int = 1,
    candidate_base_mint=None,
    soak_output_dir: Path = Path("/tmp/soak_output"),
) -> Stage29_5_3PendingPassObservation:
    return Stage29_5_3PendingPassObservation(
        pass_index=pass_index,
        candidate_base_mint=candidate_base_mint,
        soak_output_dir=soak_output_dir,
    )


def test_pending_observation_happy_path_no_candidate_base_mint():
    pending = _build_pending()
    assert pending.pass_index == 1
    assert pending.candidate_base_mint is None
    assert pending.soak_output_dir == Path("/tmp/soak_output")


def test_pending_observation_happy_path_with_valid_mint():
    mint = "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
    pending = _build_pending(candidate_base_mint=mint)
    assert pending.candidate_base_mint == mint


def test_pending_observation_is_frozen():
    pending = _build_pending()
    with pytest.raises(Exception):
        pending.pass_index = 2  # type: ignore[misc]


def test_pending_observation_rejects_non_int_pass_index():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(pass_index="1")  # type: ignore[arg-type]


def test_pending_observation_rejects_bool_pass_index():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(pass_index=True)  # type: ignore[arg-type]


def test_pending_observation_rejects_zero_pass_index():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(pass_index=0)


def test_pending_observation_rejects_negative_pass_index():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(pass_index=-1)


def test_pending_observation_rejects_non_path_soak_output_dir():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(
            soak_output_dir="/tmp/soak_output",  # type: ignore[arg-type]
        )


def test_pending_observation_rejects_url_candidate_base_mint():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(
            candidate_base_mint=(
                "h" + "ttps://discord.com/webhooks/abc"
            ).ljust(40, "x"),
        )


def test_pending_observation_rejects_bearer_candidate_base_mint():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(
            candidate_base_mint=(
                ("B" + "earer abc").ljust(40, "x")
            ),
        )


def test_pending_observation_rejects_sk_candidate_base_mint():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(
            candidate_base_mint=(
                ("s" + "k-test1234567890").ljust(40, "x")
            ),
        )


def test_pending_observation_rejects_whitespace_candidate_base_mint():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(
            candidate_base_mint=(
                "abcdefghijklm nopqrstuvwxyz123456"
            ),
        )


def test_pending_observation_rejects_too_short_candidate_base_mint():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(candidate_base_mint="abc")


def test_pending_observation_rejects_too_long_candidate_base_mint():
    with pytest.raises(Stage29_5_3WrappedPassError):
        _build_pending(candidate_base_mint="a" * 65)
