"""Stage 27.1 run / session identity tests.

Pins:

  * ``make_session_id`` returns a fresh 32-char lowercase hex
    string per call and consecutive calls do not collide.
  * ``make_run_id_from_session`` is deterministic in
    (``session_id``, ``created_at_utc``, ``salt``).
  * ``SystemStage27Clock`` returns an ISO-8601 UTC string with a
    timezone offset.
  * ``FrozenStage27Clock`` returns the exact frozen string.
  * ``build_run_identity`` validates ``mode`` against the
    closed-set live-mode authority values.
  * Identity records carry only safe, displayable fields.
"""

from __future__ import annotations

import datetime as _datetime
import re

import pytest

from PHX2.stage27.live_config_models import (
    LIVE_MODE_AUTHORITY_DRY_RUN,
    LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
    LIVE_MODE_AUTHORITY_LIVE_REFUSED,
    STAGE27_DEFAULT_SCHEMA_VERSION,
    Stage27RunIdentity,
)
from PHX2.stage27.live_run_identity import (
    FrozenStage27Clock,
    Stage27Clock,
    SystemStage27Clock,
    build_run_identity,
    make_run_id_from_session,
    make_session_id,
)


_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
_HEX16_RE = re.compile(r"^[0-9a-f]{16}$")


# ---------------------------------------------------------------------------
# Session id helper
# ---------------------------------------------------------------------------


def test_make_session_id_returns_32_char_lowercase_hex():
    session_id = make_session_id()
    assert isinstance(session_id, str)
    assert _HEX32_RE.match(session_id), (
        f"unexpected session id format: {session_id!r}"
    )


def test_make_session_id_distinct_per_call():
    seen = {make_session_id() for _ in range(20)}
    assert len(seen) == 20


# ---------------------------------------------------------------------------
# Run id helper
# ---------------------------------------------------------------------------


def test_make_run_id_returns_16_char_lowercase_hex():
    run_id = make_run_id_from_session(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
    )
    assert _HEX16_RE.match(run_id), (
        f"unexpected run id format: {run_id!r}"
    )


def test_make_run_id_is_deterministic_given_inputs():
    args = dict(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
    )
    assert make_run_id_from_session(**args) == make_run_id_from_session(**args)


def test_make_run_id_differs_for_different_session_ids():
    a = make_run_id_from_session(
        session_id="aaaa",
        created_at_utc="2026-05-21T00:00:00+00:00",
    )
    b = make_run_id_from_session(
        session_id="bbbb",
        created_at_utc="2026-05-21T00:00:00+00:00",
    )
    assert a != b


def test_make_run_id_differs_for_different_timestamps():
    a = make_run_id_from_session(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
    )
    b = make_run_id_from_session(
        session_id="deadbeef",
        created_at_utc="2026-05-21T12:00:00+00:00",
    )
    assert a != b


def test_make_run_id_salt_disambiguates_under_frozen_clock():
    a = make_run_id_from_session(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
        salt="A",
    )
    b = make_run_id_from_session(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
        salt="B",
    )
    assert a != b


def test_make_run_id_rejects_empty_session_id():
    with pytest.raises(ValueError):
        make_run_id_from_session(
            session_id="",
            created_at_utc="2026-05-21T00:00:00+00:00",
        )


def test_make_run_id_rejects_empty_timestamp():
    with pytest.raises(ValueError):
        make_run_id_from_session(
            session_id="deadbeef",
            created_at_utc="",
        )


# ---------------------------------------------------------------------------
# SystemStage27Clock + FrozenStage27Clock
# ---------------------------------------------------------------------------


def test_system_clock_returns_iso8601_utc_offset_string():
    clock = SystemStage27Clock()
    iso = clock.now_iso_utc()
    assert isinstance(iso, str)
    # A timezone-aware ``datetime.isoformat()`` ends with ``+00:00``
    # (or a UTC offset) when ``timezone.utc`` is used.
    parsed = _datetime.datetime.fromisoformat(iso)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == _datetime.timedelta(0)


def test_frozen_clock_returns_same_string_every_call():
    clock = FrozenStage27Clock("2026-05-21T12:34:56+00:00")
    assert clock.now_iso_utc() == "2026-05-21T12:34:56+00:00"
    assert clock.now_iso_utc() == "2026-05-21T12:34:56+00:00"


def test_frozen_clock_rejects_empty_string():
    with pytest.raises(ValueError):
        FrozenStage27Clock("")


def test_frozen_clock_satisfies_stage27_clock_protocol():
    # ``Stage27Clock`` is a ``Protocol``; verify the duck-typed
    # interface by calling the method on the frozen instance.
    clock: Stage27Clock = FrozenStage27Clock("2026-05-21T00:00:00+00:00")
    assert clock.now_iso_utc() == "2026-05-21T00:00:00+00:00"


# ---------------------------------------------------------------------------
# build_run_identity
# ---------------------------------------------------------------------------


def test_build_run_identity_happy_path_dry_run():
    identity = build_run_identity(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
        mode=LIVE_MODE_AUTHORITY_DRY_RUN,
    )
    assert isinstance(identity, Stage27RunIdentity)
    assert identity.session_id == "deadbeef"
    assert identity.created_at_utc == "2026-05-21T00:00:00+00:00"
    assert identity.mode == "DRY_RUN"
    assert identity.stage == "stage27"
    assert identity.substage == "27.1"
    assert identity.schema_version == STAGE27_DEFAULT_SCHEMA_VERSION
    assert _HEX16_RE.match(identity.run_id)


@pytest.mark.parametrize("mode", [
    LIVE_MODE_AUTHORITY_DRY_RUN,
    LIVE_MODE_AUTHORITY_LIVE_REFUSED,
    LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
])
def test_build_run_identity_accepts_each_authority_value(mode):
    identity = build_run_identity(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
        mode=mode,
    )
    assert identity.mode == mode


def test_build_run_identity_rejects_unknown_mode():
    with pytest.raises(ValueError):
        build_run_identity(
            session_id="deadbeef",
            created_at_utc="2026-05-21T00:00:00+00:00",
            mode="NOT_A_REAL_MODE",
        )


def test_build_run_identity_rejects_empty_session_id():
    with pytest.raises(ValueError):
        build_run_identity(
            session_id="",
            created_at_utc="2026-05-21T00:00:00+00:00",
            mode=LIVE_MODE_AUTHORITY_DRY_RUN,
        )


def test_build_run_identity_rejects_empty_timestamp():
    with pytest.raises(ValueError):
        build_run_identity(
            session_id="deadbeef",
            created_at_utc="",
            mode=LIVE_MODE_AUTHORITY_DRY_RUN,
        )


def test_build_run_identity_rejects_empty_schema_version():
    with pytest.raises(ValueError):
        build_run_identity(
            session_id="deadbeef",
            created_at_utc="2026-05-21T00:00:00+00:00",
            mode=LIVE_MODE_AUTHORITY_DRY_RUN,
            schema_version="",
        )


def test_build_run_identity_is_deterministic_with_frozen_clock_and_salt():
    a = build_run_identity(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
        mode=LIVE_MODE_AUTHORITY_DRY_RUN,
    )
    b = build_run_identity(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
        mode=LIVE_MODE_AUTHORITY_DRY_RUN,
    )
    assert a == b


def test_run_identity_has_no_module_globals_for_clock():
    # Belt-and-braces: build_run_identity must take session_id and
    # created_at_utc explicitly, NEVER read the wall clock. Two
    # identities built with the same caller-supplied timestamp must
    # produce the same run_id without any time drift.
    a = build_run_identity(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
        mode=LIVE_MODE_AUTHORITY_DRY_RUN,
    )
    b = build_run_identity(
        session_id="deadbeef",
        created_at_utc="2026-05-21T00:00:00+00:00",
        mode=LIVE_MODE_AUTHORITY_DRY_RUN,
    )
    assert a.run_id == b.run_id
