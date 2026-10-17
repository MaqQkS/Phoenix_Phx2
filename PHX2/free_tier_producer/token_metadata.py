"""Canonical per-mint token metadata state (2026-07-28 alert-quality remediation).

One resolver instance owns the canonical (name, symbol) identity for every
tracked mint.  Metadata merges in from sources PHX2 ALREADY fetches — the
restart-backfill admission payload, the paid market overview plane, the
backfill fresh-market gate, and restored watch state — and can never be lost
through tracker recreation, candidate snapshot replacement, pair refresh,
provenance merge, scheduler handoff, or Telegram composition, because every
consumer reads the resolver snapshot rather than a transient dict.

The resolver never performs a network request itself and never blocks: the
only dispatch-path interaction is ``pre_dispatch_defer_reason``, a bounded
(attempt- and wall-clock-capped) "wait one recheck tick" signal for a
candidate whose enrichment is still in flight.
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
import unicodedata
from typing import Any, Callable, Dict, Optional


METADATA_STATUS_RESOLVED = "RESOLVED"
METADATA_STATUS_PENDING = "PENDING"
METADATA_STATUS_UNAVAILABLE = "UNAVAILABLE"

METADATA_SCHEMA_VERSION = "phx2_token_metadata_v1"

#: Bounded pre-dispatch wait: an otherwise-dispatchable candidate whose
#: metadata enrichment is still pending may be deferred at most this many
#: recheck ticks and never beyond this wall-clock window measured from the
#: first resolution attempt.  Exhaustion is terminal for waiting (the alert
#: proceeds with the unavailable-identity title), never for enrichment itself.
METADATA_PRE_DISPATCH_MAX_DEFERRALS = 2
METADATA_PRE_DISPATCH_MAX_WAIT_SECONDS = 120.0

METADATA_DEFER_REASON = "METADATA_RESOLUTION_PENDING"

TOKEN_NAME_MAX_CHARACTERS = 64
TOKEN_TICKER_MAX_CHARACTERS = 16

_NULL_LIKE = frozenset({"???", "UNKNOWN", "N/A", "NULL", "NONE", "UNDEFINED"})


def _sanitize(value: object, *, limit: int) -> Optional[str]:
    """Mirror of the delivery-layer metadata sanitizer (kept in test lockstep)."""

    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFC", value)
    without_controls = "".join(
        char for char in normalized
        if not unicodedata.category(char).startswith("C"))
    safe = " ".join(without_controls.split()).strip()
    if not safe or safe.upper() in _NULL_LIKE:
        return None
    bounded = safe[:max(1, int(limit))].strip()
    return bounded or None


def sanitize_token_name(value: object) -> Optional[str]:
    return _sanitize(value, limit=TOKEN_NAME_MAX_CHARACTERS)


def sanitize_token_symbol(value: object) -> Optional[str]:
    sanitized = _sanitize(value, limit=TOKEN_TICKER_MAX_CHARACTERS)
    if sanitized is None:
        return None
    stripped = sanitized.lstrip("$").strip()
    return stripped or None


def _parse_iso_epoch(value: object) -> Optional[float]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).timestamp()


def _default_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TokenMetadataResolver:
    """Merge-only-improve canonical metadata state, keyed by exact mint."""

    def __init__(
        self,
        *,
        now_iso_fn: Callable[[], str] = _default_now_iso,
        max_pre_dispatch_deferrals: int = METADATA_PRE_DISPATCH_MAX_DEFERRALS,
        max_pre_dispatch_wait_seconds: float = (
            METADATA_PRE_DISPATCH_MAX_WAIT_SECONDS),
    ) -> None:
        self._now_iso = now_iso_fn
        self._max_deferrals = max(0, int(max_pre_dispatch_deferrals))
        self._max_wait_seconds = max(0.0, float(max_pre_dispatch_wait_seconds))
        self._lock = threading.Lock()
        self._state: Dict[str, Dict[str, Any]] = {}
        self._counters = {
            "metadata_merge_attempts_total": 0,
            "metadata_resolved_mints": 0,
            "metadata_pre_dispatch_deferrals_total": 0,
        }

    # ---- internal -----------------------------------------------------

    def _entry(self, mint: str) -> Dict[str, Any]:
        return self._state.setdefault(mint, {
            "token_name": None,
            "token_symbol": None,
            "metadata_source": None,
            "metadata_first_requested_at": None,
            "metadata_resolved_at": None,
            "metadata_attempt_count": 0,
            "metadata_failure_reason": None,
            "metadata_deferral_count": 0,
            "metadata_sources_attempted": [],
        })

    @staticmethod
    def _resolved(entry: Dict[str, Any]) -> bool:
        return bool(entry["token_name"] or entry["token_symbol"])

    def _note_source(self, entry: Dict[str, Any], source: str) -> None:
        sources = entry["metadata_sources_attempted"]
        if source not in sources:
            sources.append(source)

    # ---- write paths --------------------------------------------------

    def merge(
        self,
        mint: object,
        *,
        token_name: object = None,
        token_symbol: object = None,
        source: str,
    ) -> bool:
        """Attempt to improve the canonical state; returns True on any change.

        Merge-only-improve: an existing resolved field is never overwritten by
        a later source, so a stale snapshot can never displace enriched state.
        A merge attempt with no usable fields records the attempt (and a
        failure reason) without erasing anything.
        """

        if not isinstance(mint, str) or not mint:
            return False
        name = sanitize_token_name(token_name)
        symbol = sanitize_token_symbol(token_symbol)
        now = self._now_iso()
        with self._lock:
            entry = self._entry(mint)
            self._counters["metadata_merge_attempts_total"] += 1
            entry["metadata_attempt_count"] += 1
            if entry["metadata_first_requested_at"] is None:
                entry["metadata_first_requested_at"] = now
            self._note_source(entry, str(source))
            was_resolved = self._resolved(entry)
            changed = False
            if name is not None and entry["token_name"] is None:
                entry["token_name"] = name
                changed = True
            if symbol is not None and entry["token_symbol"] is None:
                entry["token_symbol"] = symbol
                changed = True
            if changed:
                entry["metadata_failure_reason"] = None
                if entry["metadata_source"] is None:
                    entry["metadata_source"] = str(source)
                if not was_resolved and self._resolved(entry):
                    entry["metadata_resolved_at"] = now
                    self._counters["metadata_resolved_mints"] += 1
            elif not self._resolved(entry):
                entry["metadata_failure_reason"] = (
                    "SOURCE_FIELDS_EMPTY_OR_INVALID")
            return changed

    def note_request(self, mint: object) -> None:
        """Record that enrichment is in flight without any field payload."""

        if not isinstance(mint, str) or not mint:
            return
        with self._lock:
            entry = self._entry(mint)
            if entry["metadata_first_requested_at"] is None:
                entry["metadata_first_requested_at"] = self._now_iso()

    # ---- read paths ---------------------------------------------------

    def _status_locked(self, entry: Dict[str, Any]) -> str:
        if self._resolved(entry):
            return METADATA_STATUS_RESOLVED
        if entry["metadata_deferral_count"] >= self._max_deferrals:
            return METADATA_STATUS_UNAVAILABLE
        first = _parse_iso_epoch(entry["metadata_first_requested_at"])
        now = _parse_iso_epoch(self._now_iso())
        if (first is not None and now is not None
                and now - first > self._max_wait_seconds):
            return METADATA_STATUS_UNAVAILABLE
        return METADATA_STATUS_PENDING

    def snapshot(self, mint: object) -> Dict[str, Any]:
        """Canonical candidate-facing metadata state for one exact mint."""

        mint_text = mint if isinstance(mint, str) else ""
        with self._lock:
            entry = self._state.get(mint_text)
            if entry is None:
                return {
                    "schema_version": METADATA_SCHEMA_VERSION,
                    "token_mint": mint_text,
                    "token_name": None,
                    "token_symbol": None,
                    "metadata_status": METADATA_STATUS_PENDING,
                    "metadata_source": None,
                    "metadata_first_requested_at": None,
                    "metadata_resolved_at": None,
                    "metadata_attempt_count": 0,
                    "metadata_failure_reason": None,
                    "metadata_sources_attempted": [],
                    "validated": False,
                }
            status = self._status_locked(entry)
            return {
                "schema_version": METADATA_SCHEMA_VERSION,
                "token_mint": mint_text,
                "token_name": entry["token_name"],
                "token_symbol": entry["token_symbol"],
                "metadata_status": status,
                "metadata_source": entry["metadata_source"],
                "metadata_first_requested_at": entry[
                    "metadata_first_requested_at"],
                "metadata_resolved_at": entry["metadata_resolved_at"],
                "metadata_attempt_count": entry["metadata_attempt_count"],
                "metadata_failure_reason": entry["metadata_failure_reason"],
                "metadata_sources_attempted": list(
                    entry["metadata_sources_attempted"]),
                # The delivery adapter requires an explicit validation flag
                # before it will use canonical metadata for the title.
                "validated": status == METADATA_STATUS_RESOLVED,
            }

    def pre_dispatch_defer_reason(self, mint: object) -> Optional[str]:
        """Bounded wait signal for an otherwise-dispatchable candidate.

        Returns ``METADATA_RESOLUTION_PENDING`` while a short deferral is
        still allowed (enrichment in flight, wall-clock window open, deferral
        budget remaining); ``None`` means compose must proceed now with
        whatever identity state exists.  Never raises.
        """

        if not isinstance(mint, str) or not mint:
            return None
        with self._lock:
            entry = self._entry(mint)
            if self._resolved(entry):
                return None
            now = self._now_iso()
            if entry["metadata_first_requested_at"] is None:
                entry["metadata_first_requested_at"] = now
            if entry["metadata_deferral_count"] >= self._max_deferrals:
                return None
            first = _parse_iso_epoch(entry["metadata_first_requested_at"])
            now_epoch = _parse_iso_epoch(now)
            if (first is None or now_epoch is None
                    or now_epoch - first > self._max_wait_seconds):
                return None
            entry["metadata_deferral_count"] += 1
            self._counters["metadata_pre_dispatch_deferrals_total"] += 1
            return METADATA_DEFER_REASON

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counters)


__all__ = (
    "METADATA_STATUS_RESOLVED",
    "METADATA_STATUS_PENDING",
    "METADATA_STATUS_UNAVAILABLE",
    "METADATA_SCHEMA_VERSION",
    "METADATA_PRE_DISPATCH_MAX_DEFERRALS",
    "METADATA_PRE_DISPATCH_MAX_WAIT_SECONDS",
    "METADATA_DEFER_REASON",
    "TOKEN_NAME_MAX_CHARACTERS",
    "TOKEN_TICKER_MAX_CHARACTERS",
    "sanitize_token_name",
    "sanitize_token_symbol",
    "TokenMetadataResolver",
)
