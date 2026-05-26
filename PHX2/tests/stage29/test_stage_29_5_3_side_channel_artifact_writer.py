"""Stage 29.5.3 side-channel artifact writer tests.

Pins:

  * The writer encodes each observation as a single canonical
    JSONL line (sorted keys, no extra whitespace, LF
    terminator).
  * The encoding is deterministic: same observation -> byte-
    equal line on every encode call.
  * Append-only semantics: N writes -> N lines in pass-arrival
    order.
  * Caller-shape failures raise
    ``Stage29_5_3SideChannelArtifactError`` (closed-set), not
    ``OSError`` / ``ValueError`` / ``TypeError``.
  * Missing directory raises
    ``Stage29_5_3SideChannelArtifactError``.
  * The JSONL line carries no URL host literal, no API key
    pattern, no raw webhook URL, no auth header.
  * Locked schema version + ``filter_enforcement_status`` +
    ``redaction_status`` survive the round-trip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage29.stage29_5_3_side_channel_artifact_writer import (
    STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME,
    append_stage29_5_3_migration_context_observation,
    encode_observation_jsonl_line,
    observation_to_dict,
)
from PHX2.stage29.stage29_5_3_wrapped_pass_models import (
    OBSERVATION_STATUS_COMPOSED,
    OBSERVATION_STATUS_NO_CANDIDATE_AXES,
    Stage29_5_3SideChannelArtifactError,
    Stage29_5_3WrappedPassError,
    Stage29_5_3WrappedPassObservation,
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
# Locked basename
# ---------------------------------------------------------------------------


def test_side_channel_artifact_basename_is_locked() -> None:
    assert STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME == (
        "stage29_5_3_migration_context.jsonl"
    )


# ---------------------------------------------------------------------------
# observation_to_dict
# ---------------------------------------------------------------------------


def test_observation_to_dict_pins_field_order() -> None:
    obs = _build_obs()
    projected = observation_to_dict(obs)
    assert list(projected.keys()) == [
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
    ]


def test_observation_to_dict_projects_warnings_as_list() -> None:
    obs = _build_obs(
        observation_status=OBSERVATION_STATUS_COMPOSED,
        candidate_base_mint=(
            "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
        ),
        join_status_echoed="NO_MATCH",
        measurement_status_echoed="MISSING_MIGRATION",
        warnings_echoed=(
            "MIGRATION_MISSING",
            "POST_MIGRATION_ATH_UNVERIFIED",
        ),
    )
    projected = observation_to_dict(obs)
    assert isinstance(projected["warnings_echoed"], list)
    assert projected["warnings_echoed"] == [
        "MIGRATION_MISSING",
        "POST_MIGRATION_ATH_UNVERIFIED",
    ]


def test_observation_to_dict_rejects_non_observation_input() -> None:
    with pytest.raises(Stage29_5_3SideChannelArtifactError):
        observation_to_dict("not_an_observation")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# encode_observation_jsonl_line
# ---------------------------------------------------------------------------


def test_encode_observation_jsonl_line_is_deterministic_for_same_observation() -> None:
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
    line_a = encode_observation_jsonl_line(obs)
    line_b = encode_observation_jsonl_line(obs)
    assert line_a == line_b


def test_encode_observation_jsonl_line_ends_with_newline() -> None:
    obs = _build_obs()
    line = encode_observation_jsonl_line(obs)
    assert line.endswith("\n")


def test_encode_observation_jsonl_line_is_one_line() -> None:
    obs = _build_obs()
    line = encode_observation_jsonl_line(obs)
    # Exactly one newline at the end.
    assert line.count("\n") == 1


def test_encode_observation_jsonl_line_uses_sorted_keys() -> None:
    obs = _build_obs(
        observation_status=OBSERVATION_STATUS_COMPOSED,
        candidate_base_mint=(
            "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
        ),
        join_status_echoed="JOINED",
        measurement_status_echoed="COMPLETE",
        warnings_echoed=("MIGRATION_SOURCE_UNKNOWN",),
    )
    line = encode_observation_jsonl_line(obs).rstrip("\n")
    parsed = json.loads(line)
    # sorted keys at the JSON top level (the json library emits
    # them lexicographically sorted, which lets a downstream
    # reader diff two observation lines byte-for-byte).
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_encode_observation_jsonl_line_round_trips_safe_values() -> None:
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
    line = encode_observation_jsonl_line(obs).rstrip("\n")
    parsed = json.loads(line)
    assert parsed["schema_version"] == (
        "stage29_5_3_wrapped_pass_observation_v0"
    )
    assert parsed["pass_index"] == 1
    assert parsed["observation_status"] == (
        OBSERVATION_STATUS_COMPOSED
    )
    assert parsed["candidate_base_mint"] == (
        "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
    )
    assert parsed["join_status_echoed"] == "JOINED"
    assert parsed["measurement_status_echoed"] == "COMPLETE"
    assert parsed["post_migration_ath_verified_echoed"] is True
    assert parsed["warnings_echoed"] == []
    assert parsed["filter_enforcement_status"] == (
        "NOT_ACTIVE_STAGE_29_PENDING"
    )
    assert parsed["redaction_status"] == "SAFE"


# ---------------------------------------------------------------------------
# Append semantics
# ---------------------------------------------------------------------------


def test_append_writes_jsonl_line_into_locked_basename(
    tmp_path: Path,
) -> None:
    obs = _build_obs()
    target = (
        append_stage29_5_3_migration_context_observation(
            soak_output_dir=tmp_path,
            observation=obs,
        )
    )
    assert (
        target
        == tmp_path
        / STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME
    )
    assert target.is_file()
    lines = target.read_text(
        encoding="utf-8",
    ).splitlines()
    assert len(lines) == 1


def test_append_n_observations_produces_n_lines_in_order(
    tmp_path: Path,
) -> None:
    obs1 = _build_obs(pass_index=1)
    obs2 = _build_obs(
        pass_index=2,
        observation_status=OBSERVATION_STATUS_COMPOSED,
        candidate_base_mint=(
            "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
        ),
        join_status_echoed="JOINED",
        measurement_status_echoed="COMPLETE",
        post_migration_ath_verified_echoed=True,
    )
    obs3 = _build_obs(pass_index=3)
    append_stage29_5_3_migration_context_observation(
        soak_output_dir=tmp_path, observation=obs1,
    )
    append_stage29_5_3_migration_context_observation(
        soak_output_dir=tmp_path, observation=obs2,
    )
    append_stage29_5_3_migration_context_observation(
        soak_output_dir=tmp_path, observation=obs3,
    )
    target = (
        tmp_path
        / STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME
    )
    lines = target.read_text(
        encoding="utf-8",
    ).splitlines()
    assert len(lines) == 3
    parsed_indices = [
        json.loads(line)["pass_index"] for line in lines
    ]
    assert parsed_indices == [1, 2, 3]


def test_append_rejects_non_path_soak_output_dir() -> None:
    obs = _build_obs()
    with pytest.raises(Stage29_5_3SideChannelArtifactError):
        append_stage29_5_3_migration_context_observation(
            soak_output_dir="/tmp/output",  # type: ignore[arg-type]
            observation=obs,
        )


def test_append_rejects_non_observation_input(
    tmp_path: Path,
) -> None:
    with pytest.raises(Stage29_5_3SideChannelArtifactError):
        append_stage29_5_3_migration_context_observation(
            soak_output_dir=tmp_path,
            observation="not_an_observation",  # type: ignore[arg-type]
        )


def test_append_rejects_missing_directory(
    tmp_path: Path,
) -> None:
    obs = _build_obs()
    missing_dir = tmp_path / "does_not_exist"
    with pytest.raises(Stage29_5_3SideChannelArtifactError):
        append_stage29_5_3_migration_context_observation(
            soak_output_dir=missing_dir,
            observation=obs,
        )


def test_append_rejects_path_that_is_a_file_not_a_directory(
    tmp_path: Path,
) -> None:
    obs = _build_obs()
    file_path = tmp_path / "regular_file.txt"
    file_path.write_text("not a directory")
    with pytest.raises(Stage29_5_3SideChannelArtifactError):
        append_stage29_5_3_migration_context_observation(
            soak_output_dir=file_path,
            observation=obs,
        )


# ---------------------------------------------------------------------------
# Redaction safety
# ---------------------------------------------------------------------------


def test_jsonl_line_carries_no_url_or_secret_substring(
    tmp_path: Path,
) -> None:
    """Every observation_status branch produces a JSONL line that
    is byte-safe against the canonical Stage 29.5.3 forbidden-
    needle set (URLs, webhooks, API keys, auth headers).
    """
    forbidden_needles = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "discord" + ".com",
        "discord" + "app.com",
        "/webhooks/",
        "hooks" + ".slack.com",
        "B" + "earer ",
        "A" + "uthorization:",
        "s" + "k-",
        "p" + "k-",
        "BIRDEYE_API" + "_KEY=",
        "HELIUS_API" + "_KEY=",
        "DISCORD_WEBHOOK" + "_URL=",
        "CHAINSTACK_API" + "_KEY=",
        "PHX2_CHAINSTACK_YELLOWSTONE_X" + "_TOKEN=",
    )
    observations = (
        _build_obs(
            observation_status=(
                OBSERVATION_STATUS_NO_CANDIDATE_AXES
            ),
        ),
        _build_obs(
            observation_status=OBSERVATION_STATUS_COMPOSED,
            candidate_base_mint=(
                "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
            ),
            join_status_echoed="JOINED",
            measurement_status_echoed="COMPLETE",
            post_migration_ath_verified_echoed=True,
        ),
        _build_obs(
            observation_status="COMPOSITION_REJECTED",
        ),
        _build_obs(
            observation_status="PROVIDER_REJECTED",
        ),
    )
    for obs in observations:
        line = encode_observation_jsonl_line(obs)
        for needle in forbidden_needles:
            assert needle not in line, (
                f"observation JSONL line carries forbidden "
                f"needle {needle!r}; line={line!r}"
            )
        append_stage29_5_3_migration_context_observation(
            soak_output_dir=tmp_path,
            observation=obs,
        )
    artifact = (
        tmp_path
        / STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME
    )
    content = artifact.read_text(encoding="utf-8")
    for needle in forbidden_needles:
        assert needle not in content, (
            f"JSONL artifact file carries forbidden needle "
            f"{needle!r}"
        )


def test_jsonl_line_locks_filter_enforcement_status_and_schema_version(
    tmp_path: Path,
) -> None:
    obs = _build_obs()
    line = encode_observation_jsonl_line(obs).rstrip("\n")
    parsed = json.loads(line)
    assert parsed["filter_enforcement_status"] == (
        "NOT_ACTIVE_STAGE_29_PENDING"
    )
    assert parsed["redaction_status"] == "SAFE"
    assert parsed["schema_version"] == (
        "stage29_5_3_wrapped_pass_observation_v0"
    )


# ---------------------------------------------------------------------------
# Writer-surface candidate_base_mint redaction
# ---------------------------------------------------------------------------
#
# The Stage 29.5.3 wrapped-pass observation dataclass's
# ``candidate_base_mint`` validator (positive Solana base58
# shape check; rejects URLs / Bearer / sk- / pk- / whitespace
# / equals / non-printable / forbidden URL hosts) bars an
# unsafe ``candidate_base_mint`` from ever reaching the public
# writer surface. The tests below pin that the writer chain
# refuses to materialize an observation carrying an unsafe
# ``candidate_base_mint``; the writer therefore cannot emit a
# JSONL line that leaks a URL / webhook / secret on that axis.


_UNSAFE_CANDIDATE_BASE_MINT_NEEDLES: tuple[str, ...] = (
    # URL with embedded webhook path
    ("h" + "ttps://discord.com/webhooks/foo").ljust(40, "x"),
    # http variant
    ("h" + "ttp://example.com/raw").ljust(40, "x"),
    # ws variants
    ("w" + "ss://example.com/socket").ljust(40, "x"),
    ("w" + "s://example.com/socket").ljust(40, "x"),
    # Bearer token
    ("B" + "earer abcdef12345").ljust(40, "x"),
    # OpenAI-style sk- secret
    ("s" + "k-test1234567890abcd").ljust(40, "x"),
    # pk- prefix
    ("p" + "k-test1234567890abcd").ljust(40, "x"),
    # Authorization header
    ("A" + "uthorization: token1").ljust(40, "x"),
    # env-assignment shape
    "BIRDEYE_API_KEY=value12345678901abc",
    # whitespace in middle
    "abcdefghijklm nopqrstuvwxyz123456",
    # non-printable
    "abcdefghijklm\nopqrstuvwxyz123456",
)


@pytest.mark.parametrize(
    "needle", _UNSAFE_CANDIDATE_BASE_MINT_NEEDLES,
)
def test_writer_cannot_serialize_unsafe_candidate_base_mint(
    needle: str,
    tmp_path: Path,
) -> None:
    """Pin that the public observation→writer surface refuses to
    emit a JSONL line whose ``candidate_base_mint`` would carry
    a URL / Bearer / sk- / pk- / Authorization / equals /
    whitespace / non-printable shape.

    The redaction discipline is enforced at the
    ``Stage29_5_3WrappedPassObservation`` dataclass validator
    rather than at the writer; the writer therefore never sees
    an unsafe value because the model construction raises first
    with :class:`Stage29_5_3WrappedPassError`.
    """
    with pytest.raises(Stage29_5_3WrappedPassError):
        Stage29_5_3WrappedPassObservation(
            pass_index=1,
            observation_status=OBSERVATION_STATUS_COMPOSED,
            candidate_base_mint=needle,
            join_status_echoed="JOINED",
            measurement_status_echoed="COMPLETE",
            post_migration_ath_verified_echoed=True,
            warnings_echoed=(),
            observed_at_utc=_OBSERVED_AT,
        )
    # Defense in depth: pin that no JSONL artifact file exists
    # under tmp_path. Construction raised, so the writer never
    # ran, so the file should not have been created.
    artifact = (
        tmp_path
        / STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME
    )
    assert not artifact.exists(), (
        f"writer-surface redaction failure: artifact "
        f"{artifact!r} was created even though the unsafe "
        f"candidate_base_mint should have been rejected at "
        f"model construction time"
    )


def test_writer_accepts_canonical_base58_candidate_base_mint(
    tmp_path: Path,
) -> None:
    """Positive control: a canonical 44-char Solana base58 mint
    (the Pump.fun-style mint shape) flows through the writer
    surface unchanged.
    """
    valid_mint = (
        "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
    )
    assert len(valid_mint) == 44
    obs = Stage29_5_3WrappedPassObservation(
        pass_index=1,
        observation_status=OBSERVATION_STATUS_COMPOSED,
        candidate_base_mint=valid_mint,
        join_status_echoed="JOINED",
        measurement_status_echoed="COMPLETE",
        post_migration_ath_verified_echoed=True,
        warnings_echoed=(),
        observed_at_utc=_OBSERVED_AT,
    )
    line = encode_observation_jsonl_line(obs)
    parsed = json.loads(line.rstrip("\n"))
    assert parsed["candidate_base_mint"] == valid_mint
    target = append_stage29_5_3_migration_context_observation(
        soak_output_dir=tmp_path,
        observation=obs,
    )
    contents = target.read_text(encoding="utf-8")
    assert valid_mint in contents
