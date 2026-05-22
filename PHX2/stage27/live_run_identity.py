"""Stage 27.1 run / session identity.

Stage 27.1 establishes the immutable per-run identity model:

  * ``session_id``       -- per logical operator session; safe to
                             display.
  * ``run_id``           -- per process invocation; deterministic
                             given (``session_id``, ``created_at_utc``,
                             optional ``salt``); safe to display.
  * ``created_at_utc``   -- ISO-8601 UTC timestamp string.
  * ``mode``             -- one of
                             ``LIVE_MODE_AUTHORITY_VALUES``.
  * ``stage`` / ``substage`` / ``schema_version`` -- stamped from
                             the locked Stage 27 version axes.

Determinism rules:

  * No module-level ``datetime.now()`` call. Time enters through
    an injected ``Stage27Clock`` protocol.
  * ``make_session_id()`` is the only non-deterministic helper
    (uses ``uuid.uuid4`` so a fresh session id is distinct per
    process). Callers that need a deterministic test session id
    must pass one explicitly.
  * ``make_run_id_from_session(...)`` is fully deterministic:
    given identical inputs it returns the same run_id.

This module imports only stdlib (``datetime`` / ``hashlib`` /
``typing`` / ``uuid``). It does NOT import Stage 21-26 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import uuid
from typing import Protocol

from PHX2.stage27.live_config_models import (
    LIVE_MODE_AUTHORITY_VALUES,
    STAGE27_DEFAULT_SCHEMA_VERSION,
    STAGE_NAME,
    STAGE_VERSION,
    Stage27RunIdentity,
)


# ---------------------------------------------------------------------------
# Clock protocol
# ---------------------------------------------------------------------------


class Stage27Clock(Protocol):
    """Minimal clock surface used by Stage 27.1.

    Implementations must return an ISO-8601 UTC timestamp string
    (e.g. ``"2026-05-21T12:34:56.789012+00:00"``). Stage 27 keeps
    the clock interface deliberately tiny so tests can inject a
    ``FrozenStage27Clock``.
    """

    def now_iso_utc(self) -> str:
        ...


class SystemStage27Clock:
    """Default ``Stage27Clock`` implementation: wall-clock UTC.

    Uses ``datetime.datetime.now(datetime.timezone.utc)`` and
    serializes via ``.isoformat()``. The default is intentionally
    boring; tests that need determinism inject
    ``FrozenStage27Clock`` instead.
    """

    def now_iso_utc(self) -> str:
        return _datetime.datetime.now(_datetime.timezone.utc).isoformat()


class FrozenStage27Clock:
    """Test-friendly ``Stage27Clock`` that always returns the same UTC string.

    Construct with an explicit ISO-8601 UTC string (e.g.
    ``"2026-05-21T00:00:00+00:00"``); every ``now_iso_utc()`` call
    returns that exact value.
    """

    def __init__(self, frozen_iso_utc: str) -> None:
        if not isinstance(frozen_iso_utc, str) or not frozen_iso_utc:
            raise ValueError(
                "FrozenStage27Clock requires a non-empty ISO-8601 string"
            )
        self._frozen: str = frozen_iso_utc

    def now_iso_utc(self) -> str:
        return self._frozen


# ---------------------------------------------------------------------------
# Identifier helpers
# ---------------------------------------------------------------------------


def make_session_id() -> str:
    """Return a fresh per-session identifier.

    Uses ``uuid.uuid4().hex`` so the id is a 32-character lowercase
    hex string with no separators -- safe to display, safe to put
    in filenames, and distinct per call. Stage 27.1 does not
    persist session ids; the caller is responsible for keeping the
    id alive across the session.
    """
    return uuid.uuid4().hex


def make_run_id_from_session(
    session_id: str,
    created_at_utc: str,
    *,
    salt: str = "",
) -> str:
    """Derive a deterministic run id from a session id + timestamp.

    The run id is a 16-character lowercase hex prefix of the
    sha256 of the canonical input. Deterministic: identical inputs
    yield the same run id. The salt argument is exposed for tests
    that want to construct several distinct run ids inside a
    single frozen-clock test.
    """
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string")
    if not isinstance(created_at_utc, str) or not created_at_utc:
        raise ValueError("created_at_utc must be a non-empty string")
    payload = f"{session_id}|{created_at_utc}|{salt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Identity builder
# ---------------------------------------------------------------------------


def build_run_identity(
    *,
    session_id: str,
    created_at_utc: str,
    mode: str,
    schema_version: str = STAGE27_DEFAULT_SCHEMA_VERSION,
    run_id_salt: str = "",
) -> Stage27RunIdentity:
    """Build an immutable ``Stage27RunIdentity``.

    Validates that ``mode`` is in
    ``LIVE_MODE_AUTHORITY_VALUES`` and that the supplied
    ``session_id`` / ``created_at_utc`` strings are non-empty.
    """
    if mode not in LIVE_MODE_AUTHORITY_VALUES:
        raise ValueError(
            f"mode must be one of {LIVE_MODE_AUTHORITY_VALUES!r}; "
            f"got {mode!r}"
        )
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string")
    if not isinstance(created_at_utc, str) or not created_at_utc:
        raise ValueError("created_at_utc must be a non-empty string")
    if not isinstance(schema_version, str) or not schema_version:
        raise ValueError("schema_version must be a non-empty string")
    run_id = make_run_id_from_session(
        session_id=session_id,
        created_at_utc=created_at_utc,
        salt=run_id_salt,
    )
    return Stage27RunIdentity(
        session_id=session_id,
        run_id=run_id,
        created_at_utc=created_at_utc,
        mode=mode,
        stage=STAGE_NAME,
        substage=STAGE_VERSION,
        schema_version=schema_version,
    )
