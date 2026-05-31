"""Stage 30.8.3 offline session index / dedupe model tests.

Pure offline unit tests for the passive Stage 30.8.3 index models +
closed-set status tokens + the deterministic dedupe-identity resolution
policy. No filesystem, no env, no network, no Discord, no provider.

Pinned contract:

  * the minor version + index schema version are pinned;
  * the build / ping-dedupe / read / identity-kind closed sets are pinned
    and the membership helpers agree;
  * ``resolve_ping_dedupe_identity`` uses the spec-locked ``dedupe_key``
    ALONE, resolving to the ``none`` identity when ``dedupe_key`` is not a
    non-empty string (there is NO ``ping_id`` fallback); it never uses a
    path / timestamp;
  * the dedupe identity is frozen / hashable and its ``kind`` participates
    in equality / hashing;
  * the index records are frozen, equal-by-value, and carry safe scalars.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage30.stage30_8_session_index_models import (
    DEDUPE_IDENTITY_KIND_DEDUPE_KEY,
    DEDUPE_IDENTITY_KIND_NONE,
    INDEX_BUILD_STATUS_BUILT,
    INDEX_BUILD_STATUS_EMPTY,
    INDEX_BUILD_STATUS_INDEX_FAILED,
    INDEX_BUILD_STATUS_INVALID_INPUT,
    INDEX_BUILD_STATUS_READ_FAILED,
    PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED,
    PING_DEDUPE_STATUS_INVALID_SUPPRESSED,
    PING_DEDUPE_STATUS_RETAINED,
    PING_SUPPRESS_REASON_DUPLICATE_IDENTITY,
    PING_SUPPRESS_REASON_MISSING_IDENTITY,
    PING_SUPPRESS_REASON_NONE,
    PING_SUPPRESS_REASON_SESSION_ID_MISMATCH,
    STAGE30_8_3_DEDUPE_IDENTITY_KINDS,
    STAGE30_8_3_INDEX_BUILD_STATUS_VALUES,
    STAGE30_8_3_INDEX_SCHEMA_VERSION,
    STAGE30_8_3_MINOR_VERSION,
    STAGE30_8_3_PING_DEDUPE_STATUS_VALUES,
    STAGE30_8_3_PING_SUPPRESS_REASONS,
    Stage30_8DedupeIdentity,
    Stage30_8IndexedPingArtifact,
    Stage30_8SessionIndexBuildResult,
    Stage30_8SessionIndexRecord,
    has_dedupe_identity,
    indexed_ping_artifact_field_names,
    is_index_build_status,
    is_ping_dedupe_status,
    resolve_ping_dedupe_identity,
    session_index_build_result_field_names,
    session_index_record_field_names,
)


# ---------------------------------------------------------------------------
# 1. Version + schema identity
# ---------------------------------------------------------------------------


def test_minor_version_and_index_schema_version_pinned() -> None:
    assert STAGE30_8_3_MINOR_VERSION == "30.8.3"
    assert STAGE30_8_3_INDEX_SCHEMA_VERSION == (
        "stage30_8_v0_compact_session_index"
    )


# ---------------------------------------------------------------------------
# 2. Closed-set status tokens
# ---------------------------------------------------------------------------


def test_index_build_status_closed_set() -> None:
    assert STAGE30_8_3_INDEX_BUILD_STATUS_VALUES == (
        "BUILT",
        "EMPTY",
        "INVALID_INPUT",
        "READ_FAILED",
        "INDEX_FAILED",
    )
    for value in STAGE30_8_3_INDEX_BUILD_STATUS_VALUES:
        assert is_index_build_status(value)
    assert not is_index_build_status("WRITTEN")
    assert not is_index_build_status(None)
    assert not is_index_build_status(123)


def test_ping_dedupe_status_closed_set() -> None:
    assert STAGE30_8_3_PING_DEDUPE_STATUS_VALUES == (
        "RETAINED",
        "DUPLICATE_SUPPRESSED",
        "INVALID_SUPPRESSED",
    )
    for value in STAGE30_8_3_PING_DEDUPE_STATUS_VALUES:
        assert is_ping_dedupe_status(value)
    assert not is_ping_dedupe_status("KEPT")
    assert not is_ping_dedupe_status(None)


def test_ping_suppress_reasons_closed_set() -> None:
    assert STAGE30_8_3_PING_SUPPRESS_REASONS == (
        "NONE",
        "DUPLICATE_IDENTITY",
        "MISSING_IDENTITY",
        "SESSION_ID_MISMATCH",
    )
    assert PING_SUPPRESS_REASON_SESSION_ID_MISMATCH == "SESSION_ID_MISMATCH"


def test_dedupe_identity_kinds_closed_set_is_dedupe_key_and_none() -> None:
    # dedupe_key is the ONLY retained identity (spec Section 9); there is
    # deliberately NO ping_id kind.
    assert STAGE30_8_3_DEDUPE_IDENTITY_KINDS == (
        "dedupe_key",
        "none",
    )
    assert "ping_id" not in STAGE30_8_3_DEDUPE_IDENTITY_KINDS


def test_status_constants_distinct() -> None:
    statuses = {
        INDEX_BUILD_STATUS_BUILT,
        INDEX_BUILD_STATUS_EMPTY,
        INDEX_BUILD_STATUS_INVALID_INPUT,
        INDEX_BUILD_STATUS_READ_FAILED,
        INDEX_BUILD_STATUS_INDEX_FAILED,
    }
    assert len(statuses) == 5
    dedupe = {
        PING_DEDUPE_STATUS_RETAINED,
        PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED,
        PING_DEDUPE_STATUS_INVALID_SUPPRESSED,
    }
    assert len(dedupe) == 3


# ---------------------------------------------------------------------------
# 3. Dedupe identity resolution (the locked policy)
# ---------------------------------------------------------------------------


def test_resolve_uses_dedupe_key_only() -> None:
    identity = resolve_ping_dedupe_identity("dk-1")
    assert identity.kind == DEDUPE_IDENTITY_KIND_DEDUPE_KEY
    assert identity.value == "dk-1"
    assert has_dedupe_identity(identity)


def test_resolve_none_identity_when_dedupe_key_missing() -> None:
    # No usable dedupe_key -> the ``none`` identity. There is NO ping_id
    # fallback: a missing dedupe_key is never a retained identity.
    for dedupe_key in (None, "", 123, object(), {"x": 1}, ["y"]):
        identity = resolve_ping_dedupe_identity(dedupe_key)
        assert identity.kind == DEDUPE_IDENTITY_KIND_NONE
        assert identity.value is None
        assert not has_dedupe_identity(identity)


def test_resolve_takes_dedupe_key_argument_only() -> None:
    # The resolver signature is dedupe_key-only; ping_id is NOT a dedupe
    # identity axis.
    import inspect

    params = list(
        inspect.signature(resolve_ping_dedupe_identity).parameters
    )
    assert params == ["dedupe_key"]


# ---------------------------------------------------------------------------
# 4. Dedupe identity record: frozen, hashable, namespaced
# ---------------------------------------------------------------------------


def test_dedupe_identity_is_frozen() -> None:
    identity = Stage30_8DedupeIdentity(DEDUPE_IDENTITY_KIND_DEDUPE_KEY, "k")
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.value = "other"  # type: ignore[misc]


def test_dedupe_identity_equality_and_hash() -> None:
    a = resolve_ping_dedupe_identity("dk-1")
    b = resolve_ping_dedupe_identity("dk-1")
    assert a == b
    assert hash(a) == hash(b)
    seen = {a: "first"}
    assert b in seen


def test_dedupe_identity_kind_is_part_of_equality() -> None:
    # ``kind`` participates in equality / hashing, so a dedupe_key identity
    # is never equal to a (hypothetical) same-valued other-kind identity.
    by_key = Stage30_8DedupeIdentity(DEDUPE_IDENTITY_KIND_DEDUPE_KEY, "K")
    other = Stage30_8DedupeIdentity(DEDUPE_IDENTITY_KIND_NONE, "K")
    assert by_key != other
    seen = {by_key: "first"}
    assert other not in seen


# ---------------------------------------------------------------------------
# 5. Index records: frozen, equal-by-value, safe scalars
# ---------------------------------------------------------------------------


def _indexed_ping(**overrides: object) -> Stage30_8IndexedPingArtifact:
    kwargs = dict(
        session_id="sess-1",
        session_dir="/tmp/out/sess-1",
        artifact_filename="ping_artifact_0001.json",
        member_kind="compact_ping_artifact",
        ping_id="ping-1",
        dedupe_key="dk-1",
        identity_kind=DEDUPE_IDENTITY_KIND_DEDUPE_KEY,
        identity_value="dk-1",
        dedupe_status=PING_DEDUPE_STATUS_RETAINED,
        suppress_reason=PING_SUPPRESS_REASON_NONE,
    )
    kwargs.update(overrides)
    return Stage30_8IndexedPingArtifact(**kwargs)  # type: ignore[arg-type]


def test_indexed_ping_is_frozen_and_equal_by_value() -> None:
    a = _indexed_ping()
    b = _indexed_ping()
    assert a == b
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.dedupe_status = PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED  # type: ignore[misc]


def test_indexed_ping_duplicate_provenance_defaults_none() -> None:
    ping = _indexed_ping()
    assert ping.duplicate_of_session_id is None
    assert ping.duplicate_of_artifact_filename is None


def test_indexed_ping_duplicate_carries_provenance() -> None:
    dup = _indexed_ping(
        dedupe_status=PING_DEDUPE_STATUS_DUPLICATE_SUPPRESSED,
        suppress_reason=PING_SUPPRESS_REASON_DUPLICATE_IDENTITY,
        duplicate_of_session_id="sess-0",
        duplicate_of_artifact_filename="ping_artifact_0001.json",
    )
    assert dup.duplicate_of_session_id == "sess-0"
    assert dup.duplicate_of_artifact_filename == "ping_artifact_0001.json"


def test_invalid_suppressed_ping_shape() -> None:
    invalid = _indexed_ping(
        ping_id=None,
        dedupe_key=None,
        identity_kind=DEDUPE_IDENTITY_KIND_NONE,
        identity_value=None,
        dedupe_status=PING_DEDUPE_STATUS_INVALID_SUPPRESSED,
        suppress_reason=PING_SUPPRESS_REASON_MISSING_IDENTITY,
    )
    assert invalid.identity_kind == DEDUPE_IDENTITY_KIND_NONE
    assert invalid.dedupe_status == PING_DEDUPE_STATUS_INVALID_SUPPRESSED


def test_session_index_record_is_frozen() -> None:
    record = Stage30_8SessionIndexRecord(
        session_id="sess-1",
        session_dir="/tmp/out/sess-1",
        bundle_schema_version="stage30_8_v0_compact_session_bundle",
        ping_artifact_count=0,
        retained_ping_count=0,
        duplicate_suppressed_ping_count=0,
        invalid_suppressed_ping_count=0,
    )
    assert record.pings == ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.session_id = "other"  # type: ignore[misc]


def test_build_result_is_frozen_and_defaults() -> None:
    result = Stage30_8SessionIndexBuildResult(
        status=INDEX_BUILD_STATUS_EMPTY,
        reason="EMPTY",
        index_schema_version=STAGE30_8_3_INDEX_SCHEMA_VERSION,
        session_count=0,
        total_ping_count=0,
        retained_count=0,
        duplicate_suppressed_count=0,
        invalid_suppressed_count=0,
    )
    assert result.sessions == ()
    assert result.retained_pings == ()
    assert result.duplicate_pings == ()
    assert result.invalid_pings == ()
    assert result.blocked_session_dir is None
    assert result.read_failure_reason is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = INDEX_BUILD_STATUS_BUILT  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 6. Field-name helpers
# ---------------------------------------------------------------------------


def test_field_name_helpers() -> None:
    ping_fields = indexed_ping_artifact_field_names()
    for name in (
        "session_id",
        "session_dir",
        "artifact_filename",
        "ping_id",
        "dedupe_key",
        "identity_kind",
        "dedupe_status",
        "suppress_reason",
        "duplicate_of_session_id",
        "duplicate_of_artifact_filename",
    ):
        assert name in ping_fields

    session_fields = session_index_record_field_names()
    assert "pings" in session_fields
    assert "ping_artifact_count" in session_fields

    result_fields = session_index_build_result_field_names()
    for name in (
        "status",
        "retained_pings",
        "duplicate_pings",
        "invalid_pings",
        "blocked_session_dir",
        "read_failure_reason",
    ):
        assert name in result_fields
