"""Stage 29.3 ``MigrationContextSource`` adapter that returns a
deterministic ``MIGRATION_SOURCE_UNKNOWN`` snapshot for every
``token_mint``.

Stage 29 does NOT ship a real migration-context source. The Stage
29.0 spec lock explicitly defers migration evidence to a future
operator-authorized substage; until that lands the Stage 29.3
chain still needs ``Stage27_6Sources.migration_source`` populated
so the Stage 27.4 measurement-context reader can call
``read_migration_context`` without raising.

This adapter satisfies the Stage 27.4 ``MigrationContextSource``
Protocol with the most conservative possible answer: every mint
returns a ``MigrationSourceSnapshot`` with:

  * ``migration_event_id``      = None
  * ``migration_timestamp_utc`` = None
  * ``migration_source``        = ``MIGRATION_SOURCE_UNKNOWN``
  * ``source_event_ref``        = None
  * ``raw_capture_ref``         = None

The Stage 27.4 reader will then emit a measurement-context with
``migration_status=MISSING`` for SOL / USDC pairs (or
``UNSUPPORTED_PAIR`` for non-supported pair types), and the
existing Stage 27 chain continues to classify the candidate
through its standard pair / price branches. Stage 29.2 Birdeye
ATH derivation does not require a migration anchor (the Stage
29.2 ATH source's ``migration_timestamp_utc`` parameter is
``None`` by construction, which yields
``window_starts_post_migration=null`` per the Stage 29.2
contract).

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched.
  * No network. No HTTP. No gRPC. No file I/O at import or call
    time.
  * No sleep. No backoff execution. No scheduling. No queue. No
    threads. No async. No subprocess.
  * The adapter NEVER fabricates a migration event id or a
    migration timestamp; the snapshot's optional slots stay
    ``None``.
  * No raw secret value, no PHX1 / ``Phoenix_Bot`` import.

This module imports only stdlib (``typing``) plus the Stage 27.4
Protocol surface (``MigrationSourceSnapshot``) + the Stage 27.4
migration-context vocabulary (``MIGRATION_SOURCE_UNKNOWN``). It
does NOT import any Stage 28 module, any Stage 29.0-29.2
production module, any network / RPC / messaging / DB /
scheduler / secrets-management library, and contains no top-level
I/O.
"""

from __future__ import annotations

from PHX2.stage27.migration_context_models import (
    MIGRATION_SOURCE_UNKNOWN,
)
from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
)


class Stage29_3NoMigrationEvidenceSource:
    """Stage 27.4 ``MigrationContextSource`` Protocol
    implementation that returns a deterministic
    ``MIGRATION_SOURCE_UNKNOWN`` snapshot for every mint.

    Pure / deterministic. No state. No side effects. The same
    instance can be shared across the Stage 29.3 ceremony AND
    across offline tests; both will receive identical responses.
    """

    def read_migration_snapshot(
        self, token_mint: str,
    ) -> MigrationSourceSnapshot:
        """Return the deterministic ``MIGRATION_SOURCE_UNKNOWN``
        snapshot.

        The ``token_mint`` argument is accepted to satisfy the
        Stage 27.4 Protocol shape but is intentionally unused:
        Stage 29.3 has no real migration evidence to offer for
        any mint.
        """
        # ``token_mint`` is intentionally unused by Stage 29.3.
        _ = token_mint
        return MigrationSourceSnapshot(
            migration_event_id=None,
            migration_timestamp_utc=None,
            migration_source=MIGRATION_SOURCE_UNKNOWN,
            source_event_ref=None,
            raw_capture_ref=None,
        )


__all__ = (
    "Stage29_3NoMigrationEvidenceSource",
)
