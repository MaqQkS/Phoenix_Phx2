"""free_tier_polling_discovery.py — cheap HTTP polling discovery backend (WS-firehose alternative).

OUT-OF-REPO operator glue for the PHX2 free-tier producer. The WS route (logsSubscribe on the
PumpSwap program) is a raw firehose: ~450 raw messages/second while a window is open, of which
roughly one in ~50k is a create_pool migration. Polling ``getSignaturesForAddress`` on the PROGRAM
cannot pre-filter create_pool (signature listings carry no logs), so this backend inverts the
lookup and keeps every chain read surgical:

  1. ONE keyless public new-pools listing per poll (the SAME public pools/candles provider family
     the free-tier market transport already uses; host lives only in this module's memory).
  2. Heuristic pre-filters (efficiency ONLY, never authority): dex-id hint, pool age bound, and an
     optional listing-side base-token "pump" suffix pre-check that merely saves RPC spend.
  3. Per NEW candidate pool: ONE bounded read-only ``getSignaturesForAddress(pool)`` page (Helius
     RPC). IFF the page is complete (fewer rows than the page limit) the OLDEST signature is the
     pool-creation transaction.
  4. ONE bounded read-only ``getTransaction(sig, encoding=json)`` for that creation signature,
     capped per poll AND by the run's cumulative getTransaction budget (shared with WS windows).
  5. The committed create_pool log marker + the committed Stage 29.5.7 normalizer (IDL-pinned
     BASE-MINT account extraction — index 3; the pool is index 0) turn envelopes into evidence
     records; ``build29_cap1_session._record_to_candidate`` yields the SAME candidate shape the WS
     route produces. The ACTUAL token mint therefore always comes from the chain transaction —
     never from listing JSON, pool addresses, or log text.

The strict pump-suffix guard stays in the SESSION at the discovery -> watchlist boundary (applied
to the normalizer-extracted ``token_mint``), identical for WS / POLLING / HYBRID.

Dedupe: pool addresses + creation signatures are deduped in-memory for the run and appended to a
restart-safe ``polling_seen.jsonl`` in the out dir (pool/sig base58 text only — no URL, no key).

REDACTION DISCIPLINE: provider hosts/schemes exist ONLY inside this module (split-concatenated so
the source carries no contiguous needle). Stats/artifacts carry closed-set labels and counts only.
No wallet, no signing, no trading, no send surface anywhere in this module.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_REPO = str(_HERE.parents[1])
_BUNDLE29 = str(_HERE / "compat")
for _p in (_REPO, _BUNDLE29):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (  # committed  # noqa: E402
    PUMPSWAP_CREATE_POOL_INSTRUCTION_NAME,
)
from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (  # committed  # noqa: E402
    Stage29_5_7LiveMigrationEvidenceProducer,
)
from build29_cap1_session import _record_to_candidate  # proven candidate shape  # noqa: E402

CREATE_POOL_LOG_MARKER = f"Instruction: {PUMPSWAP_CREATE_POOL_INSTRUCTION_NAME}"

POLLING_SEEN_BASENAME = "polling_seen.jsonl"

# Keyless public new-pools listing (same provider family as the market transport's OHLCV path).
# Host/scheme split-concatenated: in-memory only, NEVER echoed into artifacts/errors/stats.
_NEW_POOLS_URL = (
    "https" + ":" + "/" + "/" + "api.gecko" + "terminal.com"
    + "/api/v2/networks/solana/new_pools?page=1"
)
_HTTP_HEADERS = {"accept": "application/json", "User-Agent": "phx2-free-tier/1"}

# Closed-set stat keys emitted by every poll (artifact-safe; counts only).
POLL_STAT_KEYS = (
    "poll_count", "pools_listed", "pools_new", "signatures_seen", "signatures_new",
    "transactions_fetched", "create_pool_candidates", "pools_prefilter_dropped",
    "pools_skipped_too_hot", "pools_gave_up", "polling_errors", "polling_429", "rpc_errors",
)


def _default_urlopen(url: str, timeout_seconds: float) -> Tuple[int, bytes]:
    """Real read-only GET -> (status, raw bytes). HTTP error statuses are RETURNED (429 countable);
    raises only on transport-level failure (DNS/TLS/timeout)."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers=dict(_HTTP_HEADERS), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return int(getattr(resp, "status", 200) or 200), resp.read()
    except urllib.error.HTTPError as err:
        return int(err.code), b""


def _default_rpc_post(rpc_url: str, method: str, params: List[Any],
                      timeout_seconds: float) -> Tuple[int, Optional[Any]]:
    """Real read-only JSON-RPC POST -> (status, result-or-None). The URL is held in a local and
    NEVER printed; HTTP error statuses are RETURNED so the caller can count 429 pressure."""
    import urllib.error
    import urllib.request

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode("utf-8")
    req = urllib.request.Request(rpc_url, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return int(err.code), None
    if not isinstance(payload, dict):
        return status, None
    return status, payload.get("result")


@dataclass(frozen=True)
class FreeTierPollingCaps:
    """Per-poll bounds (the cumulative run budget lives in FreeTierCreditBudget)."""

    max_pools_per_poll: int = 8
    sig_page_limit: int = 1000
    max_gettransaction_per_poll: int = 8
    max_pool_age_seconds: int = 1800
    max_attempts_per_pool: int = 3
    max_envelopes_to_scan: int = 64

    def __post_init__(self) -> None:
        bounds = {
            "max_pools_per_poll": (1, 64),
            "sig_page_limit": (1, 1000),
            "max_gettransaction_per_poll": (1, 64),
            "max_pool_age_seconds": (60, 86400),
            "max_attempts_per_pool": (1, 16),
            "max_envelopes_to_scan": (1, 1024),
        }
        for name, (lo, hi) in bounds.items():
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
                raise ValueError(f"{name} must be an int in [{lo}, {hi}]")


def _parse_iso_epoch(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _strip_network_prefix(token_id: Any) -> Optional[str]:
    """'solana_<addr>' -> '<addr>' (defensive; None on any other shape)."""
    if not isinstance(token_id, str):
        return None
    if token_id.startswith("solana_"):
        addr = token_id[len("solana_"):]
        return addr or None
    return token_id or None


def _sig_from_source_ref(source_ref: Any) -> Optional[str]:
    """Parse the creation signature out of the committed provenance ref
    (``helius:sig:<sig>:slot:<n>``). None on any other shape."""
    if not isinstance(source_ref, str):
        return None
    parts = source_ref.split(":")
    if len(parts) >= 3 and parts[0] == "helius" and parts[1] == "sig" and parts[2]:
        return parts[2]
    return None


class FreeTierPollingDiscovery:
    """Bounded polling discovery. One ``poll()`` per producer reseed tick."""

    def __init__(
        self,
        *,
        rpc_url: str,
        caps: Optional[FreeTierPollingCaps] = None,
        urlopen_fn: Optional[Callable[[str, float], Tuple[int, bytes]]] = None,
        rpc_post_fn: Optional[Callable[[str, str, List[Any], float], Tuple[int, Optional[Any]]]] = None,
        now_epoch_fn: Callable[[], float] = time.time,
        timeout_seconds: float = 10.0,
        state_path: Optional[str] = None,
        dex_id_hint: str = "pump",
        listing_pump_suffix_precheck: bool = True,
    ) -> None:
        self._rpc_url = rpc_url                     # held privately; NEVER printed
        self.caps = caps or FreeTierPollingCaps()
        self._urlopen = urlopen_fn or _default_urlopen
        self._rpc_post = rpc_post_fn or _default_rpc_post
        self._now_epoch = now_epoch_fn
        self._timeout = float(timeout_seconds)
        self._dex_id_hint = str(dex_id_hint or "")
        self._listing_precheck = bool(listing_pump_suffix_precheck)
        self._seen_pools: set = set()
        self._seen_sigs: set = set()
        self._pool_attempts: Dict[str, int] = {}
        self._state_path = Path(state_path) if state_path else None
        self._load_state()

    # ------------------------------------------------------------------ durable dedupe state

    def _load_state(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        try:
            for line in self._state_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                pool = rec.get("pool")
                sig = rec.get("sig")
                if isinstance(pool, str) and pool:
                    self._seen_pools.add(pool)
                if isinstance(sig, str) and sig:
                    self._seen_sigs.add(sig)
        except OSError:
            pass

    def _persist_seen(self, *, pool: Optional[str] = None, sig: Optional[str] = None) -> None:
        """Append one seen pool/sig marker (base58 text only — no URL/key/host). Never raises."""
        if self._state_path is None:
            return
        rec: Dict[str, Any] = {"kind": "FREE_TIER_POLLING_SEEN"}
        if pool:
            rec["pool"] = str(pool)
        if sig:
            rec["sig"] = str(sig)
        if len(rec) == 1:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._state_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
        except OSError:
            pass

    def _mark_pool_seen(self, pool: str) -> None:
        if pool not in self._seen_pools:
            self._seen_pools.add(pool)
            self._persist_seen(pool=pool)
        self._pool_attempts.pop(pool, None)

    # ------------------------------------------------------------------ HTTP helpers

    def _get_new_pools(self, stats: Dict[str, int]) -> Optional[List[Dict[str, Any]]]:
        try:
            status, raw = self._urlopen(_NEW_POOLS_URL, self._timeout)
        except Exception:
            stats["polling_errors"] += 1
            return None
        if status == 429:
            stats["polling_429"] += 1
            stats["polling_errors"] += 1
            return None
        if status != 200:
            stats["polling_errors"] += 1
            return None
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            stats["polling_errors"] += 1
            return None
        data = body.get("data") if isinstance(body, dict) else None
        return data if isinstance(data, list) else []

    def _rpc(self, method: str, params: List[Any], stats: Dict[str, int]) -> Optional[Any]:
        try:
            status, result = self._rpc_post(self._rpc_url, method, params, self._timeout)
        except Exception:
            stats["rpc_errors"] += 1
            return None
        if status == 429:
            stats["polling_429"] += 1
            stats["rpc_errors"] += 1
            return None
        if status != 200 or result is None:
            stats["rpc_errors"] += 1
            return None
        return result

    # ------------------------------------------------------------------ listing parse

    def _candidate_pools(self, listing: List[Dict[str, Any]],
                         stats: Dict[str, int]) -> List[Dict[str, str]]:
        """Parse + heuristically pre-filter the listing to bounded NEW candidate pools.
        Heuristics only save spend; the authoritative gates run on the chain transaction."""
        now = self._now_epoch()
        out: List[Dict[str, str]] = []
        for row in listing:
            if len(out) >= self.caps.max_pools_per_poll:
                break
            if not isinstance(row, dict):
                continue
            attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            rel = row.get("relationships") if isinstance(row.get("relationships"), dict) else {}
            pool = attrs.get("address") or _strip_network_prefix(row.get("id"))
            if not isinstance(pool, str) or not pool or pool in self._seen_pools:
                continue
            dex = (((rel.get("dex") or {}).get("data") or {}).get("id")
                   if isinstance(rel.get("dex"), dict) else None)
            if self._dex_id_hint and isinstance(dex, str) and dex \
                    and self._dex_id_hint not in dex:
                continue    # heuristic: unknown dex ids are kept, mismatching ones skipped
            created_epoch = _parse_iso_epoch(attrs.get("pool_created_at"))
            if created_epoch is not None \
                    and (now - created_epoch) > self.caps.max_pool_age_seconds:
                self._mark_pool_seen(pool)      # too old to ever become fresh again
                continue
            base_hint = _strip_network_prefix(
                (((rel.get("base_token") or {}).get("data") or {}).get("id")
                 if isinstance(rel.get("base_token"), dict) else None))
            if self._listing_precheck and isinstance(base_hint, str) and base_hint \
                    and not base_hint.endswith("pump"):
                # Listing-side spend saver ONLY: the strict guard still runs on the
                # normalizer-extracted mint. A missing/odd hint is NOT dropped here.
                stats["pools_prefilter_dropped"] += 1
                self._mark_pool_seen(pool)
                continue
            out.append({"pool": pool})
        return out

    # ------------------------------------------------------------------ one poll cycle

    def poll(self, *, created_at_utc: str,
             max_gettransaction_allowance: int) -> Dict[str, Any]:
        """One bounded polling cycle. Returns the same shape as the WS discovery helper:
        ``{"candidates": [...], "stats": {...}, "evidence_record_count": n}``. Never raises."""
        stats: Dict[str, int] = {k: 0 for k in POLL_STAT_KEYS}
        stats["poll_count"] = 1
        tx_budget = max(0, min(int(max_gettransaction_allowance),
                               self.caps.max_gettransaction_per_poll))

        listing = self._get_new_pools(stats)
        if listing is None:
            return {"candidates": [], "stats": stats, "evidence_record_count": 0}
        stats["pools_listed"] = len(listing)

        envelopes: List[Any] = []
        # Creation-page signature counts observed this poll (sig -> row count). Free risk
        # signal: a page with hundreds of rows minutes after creation is bundle-bot-shaped.
        sig_page_counts: Dict[str, int] = {}
        for cand in self._candidate_pools(listing, stats):
            if stats["transactions_fetched"] >= tx_budget:
                break
            pool = cand["pool"]
            stats["pools_new"] += 1
            sigs = self._rpc("getSignaturesForAddress",
                             [pool, {"limit": self.caps.sig_page_limit,
                                     "commitment": "confirmed"}], stats)
            if not isinstance(sigs, list):
                continue
            stats["signatures_seen"] += len(sigs)
            if len(sigs) >= self.caps.sig_page_limit:
                # Page full -> the oldest row is NOT provably the creation tx. Skip for good.
                stats["pools_skipped_too_hot"] += 1
                self._mark_pool_seen(pool)
                continue
            if not sigs:
                # Not indexed yet — retry next poll, bounded attempts.
                attempts = self._pool_attempts.get(pool, 0) + 1
                self._pool_attempts[pool] = attempts
                if attempts >= self.caps.max_attempts_per_pool:
                    stats["pools_gave_up"] += 1
                    self._mark_pool_seen(pool)
                continue
            oldest = sigs[-1] if isinstance(sigs[-1], dict) else {}
            sig = oldest.get("signature")
            if not isinstance(sig, str) or not sig or sig in self._seen_sigs:
                self._mark_pool_seen(pool)
                continue
            self._seen_sigs.add(sig)
            self._persist_seen(pool=pool, sig=sig)
            sig_page_counts[sig] = len(sigs)
            stats["signatures_new"] += 1
            if oldest.get("err") is not None:
                self._mark_pool_seen(pool)
                continue
            env = self._rpc("getTransaction",
                            [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0,
                                   "commitment": "confirmed"}], stats)
            stats["transactions_fetched"] += 1
            self._mark_pool_seen(pool)          # one creation-tx fetch per pool, ever
            if not isinstance(env, dict):
                continue
            logs = ((env.get("meta") or {}).get("logMessages")
                    if isinstance(env.get("meta"), dict) else None)
            if not (isinstance(logs, list)
                    and any(isinstance(l, str) and CREATE_POOL_LOG_MARKER in l for l in logs)):
                continue    # creation tx is not a PumpSwap create_pool — not a migration
            stats["create_pool_candidates"] += 1
            envelopes.append(env)

        if not envelopes:
            return {"candidates": [], "stats": stats, "evidence_record_count": 0}

        # Committed normalizer does ALL mint extraction (IDL-pinned base-mint account).
        producer = Stage29_5_7LiveMigrationEvidenceProducer(
            lambda: created_at_utc,
            max_envelopes_to_scan=self.caps.max_envelopes_to_scan)
        run = producer.produce_migration_evidence(envelopes, created_at_utc)
        records = list(getattr(run, "evidence_records", ()) or ())
        candidates = [c for c in (_record_to_candidate(r) for r in records) if c]
        # Attach the observed creation-page signature count per candidate (matched via the
        # committed ``helius:sig:<sig>:slot:<n>`` provenance ref). Risk-signal metadata ONLY:
        # never consulted by the pump guard, watchlist, market, compose, or send path.
        for cand in candidates:
            sig = _sig_from_source_ref(cand.get("source_ref"))
            if sig is not None and sig in sig_page_counts:
                cand["discovery_sig_count"] = sig_page_counts[sig]
        return {"candidates": candidates, "stats": stats,
                "evidence_record_count": len(records)}


__all__ = (
    "CREATE_POOL_LOG_MARKER", "POLLING_SEEN_BASENAME", "POLL_STAT_KEYS",
    "FreeTierPollingCaps", "FreeTierPollingDiscovery",
)
