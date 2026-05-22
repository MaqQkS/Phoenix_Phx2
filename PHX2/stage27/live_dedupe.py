"""Stage 27.6 run-local dry-run dedupe.

Stage 27.6 ships a minimal in-memory, run-local dedupe surface so the
bounded dry-run runner can avoid emitting two identical Stage 27.5
private-ping dry-run artifacts for the same provider event inside a
single run.

Stage 27.6 dedupe is DELIBERATELY minimal:

  * the dedupe ledger lives in process memory only,
  * it does NOT persist to disk, database, or any cross-run store,
  * it does NOT participate in any live anti-spam transport queue,
  * it does NOT decide a trading verdict,
  * it does NOT enforce a Stage 26 candidate policy,
  * it does NOT touch the network / RPC / messaging stack,
  * it does NOT read the process environment.

Dedupe key shape:

  * ``token_mint``           -- copied from the Stage 27.3 input.
  * ``pair_type``            -- closed-set Stage 27.2 ``PAIR_TYPE``
                                value (defaults to ``UNKNOWN`` when
                                Stage 27.3 has not classified yet).
  * ``event_kind``           -- closed-set Stage 27.3 ``EVENT_KIND``.
  * ``normalized_event_id``  -- safe-to-display upstream event id.
                                Falls back to ``provider_event_id``
                                when the normalized id is absent.

The key is a ``NamedTuple`` so ``hash`` / ``__eq__`` are free; the
dedupe set therefore tolerates ``None`` safely (``None`` matches
``None`` only).

This module imports only stdlib (``typing``). It does NOT import
Stage 21-26 production code, does NOT import Stage 27.1 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


STAGE27_6_DEDUPE_SCHEMA_VERSION: str = "stage27_v0_run_local_dedupe"


class Stage27_6DedupeKey(NamedTuple):
    """Immutable Stage 27.6 run-local dedupe key.

    Two events produce the same key iff they share the same
    ``token_mint``, ``pair_type``, ``event_kind``, and
    ``normalized_event_id`` (or fallback ``provider_event_id``).

    Stage 27.6 NEVER hashes a raw provider payload blob. The key is
    intentionally narrow so two distinct events with the same
    upstream id are still deduped, while two genuinely different
    events (different event ids on the same mint) are not collapsed.
    """

    token_mint: Optional[str]
    pair_type: str
    event_kind: str
    normalized_event_id: Optional[str]


def make_dedupe_key(
    *,
    token_mint: Optional[str],
    pair_type: str,
    event_kind: str,
    normalized_event_id: Optional[str],
    provider_event_id: Optional[str] = None,
) -> Stage27_6DedupeKey:
    """Return a deterministic ``Stage27_6DedupeKey`` for an event.

    Pure / deterministic. When ``normalized_event_id`` is ``None`` /
    empty the key falls back to ``provider_event_id`` so an upstream
    that omits the normalized id still gets a stable handle.

    The fallback NEVER promotes a missing id to a sentinel: when
    both ids are ``None`` the dedupe key carries ``None`` for the
    event-id slot, and callers that depend on dedupe to suppress
    spam must accept that an unidentified event will not be deduped
    against another unidentified event with a different shape.
    """
    if not isinstance(pair_type, str):
        raise TypeError(
            "make_dedupe_key requires a string pair_type"
        )
    if not isinstance(event_kind, str):
        raise TypeError(
            "make_dedupe_key requires a string event_kind"
        )
    chosen_event_id: Optional[str]
    if normalized_event_id is not None and normalized_event_id != "":
        chosen_event_id = normalized_event_id
    elif provider_event_id is not None and provider_event_id != "":
        chosen_event_id = provider_event_id
    else:
        chosen_event_id = None
    return Stage27_6DedupeKey(
        token_mint=token_mint,
        pair_type=pair_type,
        event_kind=event_kind,
        normalized_event_id=chosen_event_id,
    )


class Stage27_6RunLocalDedupe:
    """Stage 27.6 run-local dedupe ledger.

    Holds a single ``set[Stage27_6DedupeKey]`` for the lifetime of
    one dry-run runner invocation. Stage 27.6 NEVER persists the
    ledger; the runner discards it when the run ends.

    Stage 27.6 dedupe is NEVER:

      * a cross-run dedupe ledger,
      * a database table,
      * a Redis / KV store,
      * a public anti-spam transport queue,
      * a Stage 26 candidate enforcement gate.

    The class API is small on purpose: ``is_duplicate`` / ``record``
    / ``size`` / ``snapshot``. Adding more methods would invite
    feature creep beyond the locked Stage 27.6 dedupe scope.
    """

    __slots__ = ("_seen",)

    def __init__(self) -> None:
        self._seen: set[Stage27_6DedupeKey] = set()

    def is_duplicate(self, key: Stage27_6DedupeKey) -> bool:
        """Return ``True`` iff ``key`` has already been recorded."""
        if not isinstance(key, Stage27_6DedupeKey):
            raise TypeError(
                "is_duplicate requires a Stage27_6DedupeKey"
            )
        return key in self._seen

    def record(self, key: Stage27_6DedupeKey) -> bool:
        """Record ``key`` in the ledger.

        Returns ``True`` iff the key is newly recorded (i.e. it was
        not a duplicate). Returns ``False`` iff the key was already
        present (the ledger is not mutated again).
        """
        if not isinstance(key, Stage27_6DedupeKey):
            raise TypeError(
                "record requires a Stage27_6DedupeKey"
            )
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def size(self) -> int:
        """Return the number of distinct keys recorded so far."""
        return len(self._seen)

    def snapshot(self) -> tuple[Stage27_6DedupeKey, ...]:
        """Return a deterministic, immutable snapshot of recorded keys.

        Used by tests to assert the ledger contents. The returned
        tuple is sorted by the ``NamedTuple``'s natural order so two
        runs that record the same set of keys produce identical
        snapshots.
        """
        return tuple(sorted(self._seen))
