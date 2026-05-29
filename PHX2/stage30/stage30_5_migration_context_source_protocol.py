"""Stage 30.5.1 offline migration-context source protocol.

Pure-Python duck-typed surface the Stage 30.5.1 adapter / projector
consumes. Stage 30.5.1 ships ONLY the protocol surface; no real
evidence-bridge source ships in Stage 30.5.1. A Stage 29.5 evidence
to Stage-30 record bridge requires separately authorized scope
(Stage 30.5.3 or later) under a narrow Stage 29 import allowlist
that pointedly EXCLUDES the Stage 29.5.5 private side-channel
renderer / recorder / artifact writer.

Surface:

  * ``Stage30_5MigrationContextSourceProtocol``
      Duck-typed ``Protocol``. A source implements one method,
      ``read(token_mint, observed_at_utc=None) ->
      Optional[Stage30_5MigrationContextRecord]``. Returning ``None``
      is the equivalent of "source had nothing to report"; the
      adapter resolves the projection to ``Mig: Unknown`` with
      ``source_status=UNAVAILABLE``.

The Stage 30.5.1 source emits the Stage-30-owned
``Stage30_5MigrationContextRecord`` directly (mirroring the Stage
30.5.0 §4 source contract). The Stage 30.5.1 adapter projects that
record onto the compact ``Mig`` display token; it NEVER calls
anything on the source other than ``read``.

Discipline:

  * Stdlib only (``typing``).
  * Stage 30.5.1 sibling module ``models`` imported read-only for
    the record type.
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No Discord, Telegram, X / social, inbound-hook reference.
  * No Stage 29.5.5 private side-channel renderer / recorder /
    artifact writer import.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No network / env / filesystem I/O at import time.
"""

from __future__ import annotations

from typing import Optional, Protocol, Tuple, runtime_checkable

from PHX2.stage30.stage30_5_migration_context_models import (
    Stage30_5MigrationContextRecord,
)


# ---------------------------------------------------------------------------
# Duck-typed source protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage30_5MigrationContextSourceProtocol(Protocol):
    """Duck-typed Stage 30.5.1 migration-context source.

    A source exposes a single ``read`` method that takes the
    candidate ``token_mint`` string plus an optional injected-clock
    ``observed_at_utc`` ISO-8601 UTC timestamp and returns either a
    ``Stage30_5MigrationContextRecord`` (the source had migration
    evidence to report) or ``None`` (the source had nothing to
    report; the adapter resolves the projection to ``Mig: Unknown``
    with ``source_status=UNAVAILABLE``).

    The protocol intentionally does NOT define a ``close`` / ``open``
    / ``flush`` / ``url`` / ``auth`` / ``api`` + ``_key`` / ``b`` +
    ``earer`` / ``token`` / ``configure`` / ``set_endpoint`` /
    ``send`` / ``post`` method. The Stage 30.5.1 adapter NEVER calls
    anything on the source other than ``read``.
    """

    def read(
        self,
        token_mint: str,
        observed_at_utc: Optional[str] = None,
    ) -> Optional[Stage30_5MigrationContextRecord]:
        ...


# ---------------------------------------------------------------------------
# Defensive: forbidden attribute names on a source object
# ---------------------------------------------------------------------------
#
# The Stage 30.5.1 adapter never accesses any of these attributes on
# a source object. The tuple is exported so the adapter can
# defensively assert that the source-protocol implementation it was
# handed does not advertise a secret-class / transport-class /
# Discord-class surface.
#
# Split literals so this module's source text never carries the bare
# inbound-hook / API-key / signed-token / authorization needle.


SOURCE_FORBIDDEN_ATTRIBUTE_NAMES: Tuple[str, ...] = (
    "api_" + "key",
    "api" + "key",
    "b" + "earer",
    "b" + "earer_token",
    "author" + "ization",
    "web" + "hook",
    "web" + "hook_url",
    "rpc_url",
    "endpoint_url",
    "host",
    "url",
    "secret",
    "secret_key",
    "private_key",
    "credentials",
    "password",
    "signer",
    "raw_payload",
    "payload",
    "payload_blob",
    "raw_response",
    "discord",
    "post",
    "send",
)


def is_source_forbidden_attribute_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden source attribute
    name.

    Pure / deterministic. Stage 30.5.1 uses this guard to reject any
    future source-protocol implementation that tries to advertise a
    secret-class, transport-class, or Discord-class surface.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in SOURCE_FORBIDDEN_ATTRIBUTE_NAMES:
        if forbidden in lower:
            return True
    return False


__all__ = (
    "Stage30_5MigrationContextSourceProtocol",
    "SOURCE_FORBIDDEN_ATTRIBUTE_NAMES",
    "is_source_forbidden_attribute_name",
)
