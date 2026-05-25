"""Stage 29.4 cross-pass in-memory soak dedupe index.

The Stage 29.4 soak orchestrator maintains a cross-pass dedupe
index in process memory only. The index is NEVER persisted to
disk, NEVER serialized across processes, NEVER written into any
artifact under the operator-supplied output directory, and NEVER
survives the Stage 29.4 soak call.

The index supports exactly one mutation operation
(``consume(key)``) that returns one of two closed-set dedupe
outcomes:

  * ``NEW`` -- the key was not present in the index at call time;
    the index records the key and the soak orchestrator may
    forward the candidate to the Stage 28.4 audited private
    transport (which then accepts / rejects independently).
  * ``DUPLICATE_SUPPRESSED_SOAK`` -- the key was already present
    in the index at call time; the soak orchestrator suppresses
    the duplicate and the Stage 28.4 audited private transport is
    NEVER invoked for this duplicate.

Stage 29.4 guarantees that no duplicate private operator ping is
ever sent within a single soak call; the dedupe layer is the sole
mechanism that enforces this guarantee. Dedupe semantics do NOT
extend across separate soak calls: two soak ceremonies are
independent because their in-memory indexes are constructed and
released within each call.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No Discord. No file I/O. No
    serialization. No persistence.
  * No third-party dependency. Stdlib only (``typing``).
  * The index NEVER carries a webhook URL, RPC endpoint, API key,
    bearer token, auth header, recipient / subscriber / paid-tier
    field, run_id, session_id, wall-clock timestamp, raw upstream
    payload, or raw exception string. It carries only Stage 29.4
    cross-pass dedupe key tuples (mint / pair / event-kind /
    ping-type / normalized event id) drawn from the locked
    allowlist.
  * ``repr()`` of the index exposes only a safe-shape size axis;
    the index NEVER renders its contents.
"""

from __future__ import annotations

from typing import Set, Tuple

from PHX2.stage29.stage29_4_soak_models import (
    DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK,
    DEDUPE_OUTCOME_NEW,
    Stage29_4InvalidDedupeKeyError,
    Stage29_4SoakDedupeKey,
    canonical_soak_dedupe_key_tuple,
)


class Stage29_4SoakDedupeIndex:
    """In-memory cross-pass dedupe index for the Stage 29.4 bounded
    short-session private soak.

    The index is constructed empty at the start of every soak call,
    populated by ``consume(...)`` calls during the loop, and
    garbage-collected at function return. The index does NOT
    expose any serialization surface; ``__repr__`` exposes only
    the current size as a safe counter axis.
    """

    __slots__ = ("_seen",)

    def __init__(self) -> None:
        # Each entry is a ``canonical_soak_dedupe_key_tuple``
        # projection of a ``Stage29_4SoakDedupeKey``. The set is
        # local to this instance; no module-level state is
        # touched.
        self._seen: Set[Tuple[str, str, str, str, str]] = set()

    def consume(self, key: Stage29_4SoakDedupeKey) -> str:
        """Consume one cross-pass dedupe key.

        Returns the closed-set ``DEDUPE_OUTCOME_NEW`` token when
        the key was not present at call time (and records the key
        for future passes), or
        ``DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK`` when the key
        was already present (and does NOT mutate the index).

        Raises ``Stage29_4InvalidDedupeKeyError`` when ``key`` is
        not a ``Stage29_4SoakDedupeKey``; the dedupe layer never
        accepts raw tuples or strings, only constructed key
        records that have already passed the soak-models
        allowlist.
        """
        if not isinstance(key, Stage29_4SoakDedupeKey):
            raise Stage29_4InvalidDedupeKeyError(
                field_name="key",
                reason="NOT_A_SOAK_DEDUPE_KEY",
            )
        tup = canonical_soak_dedupe_key_tuple(key)
        if tup in self._seen:
            return DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK
        self._seen.add(tup)
        return DEDUPE_OUTCOME_NEW

    def contains(self, key: Stage29_4SoakDedupeKey) -> bool:
        """Return ``True`` iff ``key`` has been recorded in this
        index. Pure / read-only; never mutates.
        """
        if not isinstance(key, Stage29_4SoakDedupeKey):
            raise Stage29_4InvalidDedupeKeyError(
                field_name="key",
                reason="NOT_A_SOAK_DEDUPE_KEY",
            )
        return canonical_soak_dedupe_key_tuple(key) in (
            self._seen
        )

    def size(self) -> int:
        """Return the number of distinct keys recorded in this
        index. Safe counter; non-negative.
        """
        return len(self._seen)

    def __repr__(self) -> str:
        # Exposes only the safe-shape size axis; never the keys.
        return (
            f"Stage29_4SoakDedupeIndex(size={len(self._seen)})"
        )


def build_dedupe_index() -> Stage29_4SoakDedupeIndex:
    """Construct a fresh empty Stage 29.4 cross-pass dedupe index.

    Returns a new instance on every call; the index is never
    cached / shared / persisted.
    """
    return Stage29_4SoakDedupeIndex()


__all__ = (
    "Stage29_4SoakDedupeIndex",
    "build_dedupe_index",
)
