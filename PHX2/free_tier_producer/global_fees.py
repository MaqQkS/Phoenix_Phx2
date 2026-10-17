"""Canonical per-mint Global Fees Paid telemetry (observe-only).

One tracker instance owns the canonical all-time global-fees-paid value for
every tracked mint.  The value rides the Token Overview response the paid
market scheduler ALREADY fetches during normal market enrichment (2026-07-28
capability probe: ``global_fees_paid`` is a top-level JSON number on the
overview ``data`` object and exactly equals the dedicated single-token fee
endpoint's ``alltime`` ``sum_global_fee_paid_amount_sol`` — the unit is
therefore contract-proven SOL and the interval is contract-proven all-time).
No additional provider request exists anywhere in this module.

Observe-only discipline:

  * never an eligibility, tier, scam, risk, structural, or dispatch input;
  * never a blocking call in the Telegram dispatch path;
  * never a production startup prerequisite;
  * merge by exact mint only; survives candidate snapshot replacement,
    candidate recreation, and scheduler handoff because every consumer reads
    the tracker snapshot rather than a transient dict;
  * a provider value regression (a later contract-valid observation strictly
    below the prior one) is disclosed, never silently maxed: both
    observations stay in the snapshot and the latest contract-valid
    observation is adopted (documented rule; no fabricated monotonicity).

Freshness is DISPLAY-ONLY: a valid value older than
``GLOBAL_FEES_DISPLAY_FRESH_SECONDS`` projects ``STALE`` and the Telegram
line is omitted, mirroring the existing ≤300s market-context compose
freshness contract (Stage 30.11.14).  It gates nothing else.

Every emitted label is provider-neutral (``PAID_MARKET_PRIMARY`` /
``TOKEN_OVERVIEW``): artifact values must stay clean of the provider-name
needle the runtime redaction scanner bans.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import threading
from typing import Any, Callable, Dict, Mapping, Optional, Tuple


GLOBAL_FEES_SCHEMA_VERSION = "phx2_global_fees_v1"

# ---- closed status set ----------------------------------------------------

GLOBAL_FEES_STATUS_VALID = "VALID"
GLOBAL_FEES_STATUS_FIELD_MISSING = "FIELD_MISSING"
GLOBAL_FEES_STATUS_VALUE_NULL = "VALUE_NULL"
GLOBAL_FEES_STATUS_VALUE_INVALID = "VALUE_INVALID"
GLOBAL_FEES_STATUS_VALUE_NEGATIVE = "VALUE_NEGATIVE"
GLOBAL_FEES_STATUS_VALUE_NONFINITE = "VALUE_NONFINITE"
GLOBAL_FEES_STATUS_STALE = "STALE"
GLOBAL_FEES_STATUS_PLAN_FORBIDDEN = "PLAN_FORBIDDEN"
GLOBAL_FEES_STATUS_RATE_LIMITED = "RATE_LIMITED"
GLOBAL_FEES_STATUS_PROVIDER_ERROR = "PROVIDER_ERROR"
GLOBAL_FEES_STATUS_NOT_REQUESTED = "NOT_REQUESTED"

GLOBAL_FEES_STATUS_TOKENS = (
    GLOBAL_FEES_STATUS_VALID,
    GLOBAL_FEES_STATUS_FIELD_MISSING,
    GLOBAL_FEES_STATUS_VALUE_NULL,
    GLOBAL_FEES_STATUS_VALUE_INVALID,
    GLOBAL_FEES_STATUS_VALUE_NEGATIVE,
    GLOBAL_FEES_STATUS_VALUE_NONFINITE,
    GLOBAL_FEES_STATUS_STALE,
    GLOBAL_FEES_STATUS_PLAN_FORBIDDEN,
    GLOBAL_FEES_STATUS_RATE_LIMITED,
    GLOBAL_FEES_STATUS_PROVIDER_ERROR,
    GLOBAL_FEES_STATUS_NOT_REQUESTED,
)

# ---- closed provenance sets ----------------------------------------------

GLOBAL_FEES_INTERVAL_ALLTIME = "alltime"
GLOBAL_FEES_SOURCE_PAID_MARKET_PRIMARY = "PAID_MARKET_PRIMARY"
#: Production endpoint source: the overview response the run already paid
#: for.  ``TOKEN_FEE_SINGLE`` exists in the closed set only so the probe
#: classification and artifacts can name the dedicated endpoint; no
#: production code path requests it.
GLOBAL_FEES_ENDPOINT_TOKEN_OVERVIEW = "TOKEN_OVERVIEW"
GLOBAL_FEES_ENDPOINT_TOKEN_FEE_SINGLE = "TOKEN_FEE_SINGLE"

GLOBAL_FEES_RAW_TYPE_NUMBER = "number"
GLOBAL_FEES_RAW_TYPE_STRING = "string"
GLOBAL_FEES_RAW_TYPE_NULL = "null"
GLOBAL_FEES_RAW_TYPE_BOOL = "bool"
GLOBAL_FEES_RAW_TYPE_OBJECT = "object"
GLOBAL_FEES_RAW_TYPE_ARRAY = "array"
GLOBAL_FEES_RAW_TYPE_MISSING = "missing"
GLOBAL_FEES_RAW_TYPE_OTHER = "other"

#: Display-only freshness bound (seconds).  Mirrors the existing ≤300s
#: market-context compose freshness contract; the Telegram line is omitted
#: beyond it.  NEVER an eligibility gate.
GLOBAL_FEES_DISPLAY_FRESH_SECONDS = 300.0
#: Small negative tolerance mirroring the reserve-display future-skew guard.
GLOBAL_FEES_MAX_FUTURE_SKEW_SECONDS = 5.0

GLOBAL_FEES_FIELD_NAME = "global_fees_paid"

GLOBAL_FEES_COVERAGE_NOTE = (
    "ALL_TIME_GLOBAL_FEES_SOL_FROM_EXISTING_OVERVIEW_SNAPSHOT")

# ---- dedicated-endpoint probe access verdicts (classification only) ------

GLOBAL_FEES_ACCESS_AVAILABLE = "AVAILABLE_ON_CURRENT_PLAN"
GLOBAL_FEES_ACCESS_PLAN_FORBIDDEN = "PLAN_FORBIDDEN"
GLOBAL_FEES_ACCESS_AUTH_FAILURE = "AUTH_FAILURE"
GLOBAL_FEES_ACCESS_RATE_LIMITED = "RATE_LIMITED"
GLOBAL_FEES_ACCESS_RESPONSE_INVALID = "RESPONSE_INVALID"


def classify_dedicated_fee_access(http_status: object) -> str:
    """Closed-set access verdict for a dedicated fee-endpoint probe status.

    Pure classification for probe artifacts and tests; production never
    requests the dedicated endpoint while the overview field is available.
    """

    if isinstance(http_status, bool) or not isinstance(http_status, int):
        return GLOBAL_FEES_ACCESS_RESPONSE_INVALID
    if http_status == 200:
        return GLOBAL_FEES_ACCESS_AVAILABLE
    if http_status == 403:
        return GLOBAL_FEES_ACCESS_PLAN_FORBIDDEN
    if http_status == 401:
        return GLOBAL_FEES_ACCESS_AUTH_FAILURE
    if http_status == 429:
        return GLOBAL_FEES_ACCESS_RATE_LIMITED
    return GLOBAL_FEES_ACCESS_RESPONSE_INVALID


def _http_status_class(status: object) -> Optional[str]:
    if isinstance(status, bool) or not isinstance(status, int):
        return None
    if 200 <= status <= 299:
        return "2XX"
    if 400 <= status <= 499:
        return "4XX"
    if 500 <= status <= 599:
        return "5XX"
    return None


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def classify_global_fees_value(
    value: object, *, field_present: bool
) -> Tuple[str, Optional[str], str]:
    """Classify one raw ``global_fees_paid`` value.

    Returns ``(status, canonical_sol_text_or_none, raw_type_token)``.  The
    2026-07-28 capability probe proved the provider emits a JSON number;
    strings are therefore NOT contract-proven and are rejected as
    ``VALUE_INVALID`` rather than silently coerced.  The value is SOL by
    contract (never lamports; no unit guessing).
    """

    if not field_present:
        return (GLOBAL_FEES_STATUS_FIELD_MISSING, None,
                GLOBAL_FEES_RAW_TYPE_MISSING)
    if value is None:
        return (GLOBAL_FEES_STATUS_VALUE_NULL, None,
                GLOBAL_FEES_RAW_TYPE_NULL)
    if isinstance(value, bool):
        return (GLOBAL_FEES_STATUS_VALUE_INVALID, None,
                GLOBAL_FEES_RAW_TYPE_BOOL)
    if isinstance(value, (int, float)):
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return (GLOBAL_FEES_STATUS_VALUE_NONFINITE, None,
                    GLOBAL_FEES_RAW_TYPE_NUMBER)
        if not parsed.is_finite():
            return (GLOBAL_FEES_STATUS_VALUE_NONFINITE, None,
                    GLOBAL_FEES_RAW_TYPE_NUMBER)
        if parsed < 0:
            return (GLOBAL_FEES_STATUS_VALUE_NEGATIVE, None,
                    GLOBAL_FEES_RAW_TYPE_NUMBER)
        return (GLOBAL_FEES_STATUS_VALID, _decimal_text(parsed),
                GLOBAL_FEES_RAW_TYPE_NUMBER)
    if isinstance(value, str):
        return (GLOBAL_FEES_STATUS_VALUE_INVALID, None,
                GLOBAL_FEES_RAW_TYPE_STRING)
    if isinstance(value, Mapping):
        return (GLOBAL_FEES_STATUS_VALUE_INVALID, None,
                GLOBAL_FEES_RAW_TYPE_OBJECT)
    if isinstance(value, (list, tuple)):
        return (GLOBAL_FEES_STATUS_VALUE_INVALID, None,
                GLOBAL_FEES_RAW_TYPE_ARRAY)
    return (GLOBAL_FEES_STATUS_VALUE_INVALID, None,
            GLOBAL_FEES_RAW_TYPE_OTHER)


def build_overview_global_fees_observation(
    *,
    mint: str,
    data: Mapping[str, Any],
    observed_at_utc: str,
    http_status_code: int = 200,
) -> Dict[str, Any]:
    """Project the fees field off an already-identity-checked overview body.

    Called by the paid transport on the same response that supplies market
    cap / liquidity / metadata — zero additional requests by construction.
    """

    field_present = GLOBAL_FEES_FIELD_NAME in data
    status, value_text, raw_type = classify_global_fees_value(
        data.get(GLOBAL_FEES_FIELD_NAME), field_present=field_present)
    return {
        "schema_version": GLOBAL_FEES_SCHEMA_VERSION,
        "token_mint": mint,
        "global_fees_status": status,
        "global_fees_paid_sol": value_text,
        "global_fees_raw_type": raw_type,
        "global_fees_interval": GLOBAL_FEES_INTERVAL_ALLTIME,
        "global_fees_source": GLOBAL_FEES_SOURCE_PAID_MARKET_PRIMARY,
        "global_fees_endpoint_source": GLOBAL_FEES_ENDPOINT_TOKEN_OVERVIEW,
        "global_fees_observed_at_utc": observed_at_utc,
        "global_fees_http_status_class": _http_status_class(http_status_code),
        "global_fees_request_reused": True,
    }


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


#: Closed mapping from the paid scheduler's provider failure reasons to the
#: observe-only failure statuses.  The scheduler's closed set carries no
#: 403-specific token (the overview endpoint is proven on-plan), so
#: ``PLAN_FORBIDDEN`` is reachable only through an explicit future mapping,
#: never guessed from an ambiguous reason.
_SCHEDULER_FAILURE_STATUS = {
    "PROVIDER_RATE_LIMIT": GLOBAL_FEES_STATUS_RATE_LIMITED,
}


class GlobalFeesTracker:
    """Merge-by-exact-mint canonical Global Fees state (observe-only)."""

    def __init__(
        self,
        *,
        now_iso_fn: Callable[[], str] = _default_now_iso,
        display_fresh_seconds: float = GLOBAL_FEES_DISPLAY_FRESH_SECONDS,
    ) -> None:
        self._now_iso = now_iso_fn
        self._display_fresh_seconds = max(1.0, float(display_fresh_seconds))
        self._lock = threading.Lock()
        self._state: Dict[str, Dict[str, Any]] = {}
        self._counters = {
            "global_fees_observations_total": 0,
            "global_fees_valid_observations": 0,
            "global_fees_invalid_observations": 0,
            "global_fees_provider_failures": 0,
            "global_fees_regressions_detected": 0,
            "global_fees_wrong_mint_rejected": 0,
        }

    # ---- internal -----------------------------------------------------

    def _entry(self, mint: str) -> Dict[str, Any]:
        return self._state.setdefault(mint, {
            "value_sol_text": None,
            "value_observed_at_utc": None,
            "value_raw_type": None,
            "value_http_status_class": None,
            "last_status": None,
            "last_failure_reason": None,
            "last_observed_at_utc": None,
            "last_raw_type": None,
            "observation_count": 0,
            "regression_detected": False,
            "regression_prior_value_sol_text": None,
            "regression_prior_observed_at_utc": None,
            "regression_observed_at_utc": None,
        })

    # ---- write paths --------------------------------------------------

    def observe_overview(self, mint: object, observation: object) -> bool:
        """Merge one transport-classified overview observation.

        Total by intent for the apply path: a malformed payload is counted
        and ignored, never raised.  Returns ``True`` when canonical state
        changed.
        """

        if not isinstance(mint, str) or not mint:
            return False
        if not isinstance(observation, Mapping):
            return False
        if observation.get("token_mint") != mint:
            with self._lock:
                self._counters["global_fees_wrong_mint_rejected"] += 1
            return False
        status = observation.get("global_fees_status")
        if status not in GLOBAL_FEES_STATUS_TOKENS:
            return False
        observed_at = observation.get("global_fees_observed_at_utc")
        raw_type = observation.get("global_fees_raw_type")
        status_class = observation.get("global_fees_http_status_class")
        with self._lock:
            entry = self._entry(mint)
            self._counters["global_fees_observations_total"] += 1
            entry["observation_count"] += 1
            entry["last_status"] = status
            entry["last_observed_at_utc"] = observed_at
            entry["last_raw_type"] = raw_type
            if status != GLOBAL_FEES_STATUS_VALID:
                self._counters["global_fees_invalid_observations"] += 1
                entry["last_failure_reason"] = status
                return False
            value_text = observation.get("global_fees_paid_sol")
            try:
                value = Decimal(str(value_text))
            except (InvalidOperation, ValueError, TypeError):
                self._counters["global_fees_invalid_observations"] += 1
                entry["last_failure_reason"] = GLOBAL_FEES_STATUS_VALUE_INVALID
                entry["last_status"] = GLOBAL_FEES_STATUS_VALUE_INVALID
                return False
            if not value.is_finite() or value < 0:
                self._counters["global_fees_invalid_observations"] += 1
                entry["last_failure_reason"] = GLOBAL_FEES_STATUS_VALUE_INVALID
                entry["last_status"] = GLOBAL_FEES_STATUS_VALUE_INVALID
                return False
            self._counters["global_fees_valid_observations"] += 1
            prior_text = entry["value_sol_text"]
            if prior_text is not None:
                try:
                    prior = Decimal(str(prior_text))
                except (InvalidOperation, ValueError):
                    prior = None
                if prior is not None and value < prior:
                    # Disclosed provider regression: keep both observations,
                    # adopt the latest contract-valid one, never re-max.
                    self._counters["global_fees_regressions_detected"] += 1
                    entry["regression_detected"] = True
                    entry["regression_prior_value_sol_text"] = prior_text
                    entry["regression_prior_observed_at_utc"] = entry[
                        "value_observed_at_utc"]
                    entry["regression_observed_at_utc"] = observed_at
            entry["value_sol_text"] = _decimal_text(value)
            entry["value_observed_at_utc"] = observed_at
            entry["value_raw_type"] = raw_type
            entry["value_http_status_class"] = status_class
            entry["last_failure_reason"] = None
            return True

    def observe_scheduler_failure(
        self, mint: object, *, failure_reason: object
    ) -> None:
        """Record an overview-plane provider failure (closed-set mapping).

        Never erases a previously observed valid value; only the failure
        telemetry fields move.
        """

        if not isinstance(mint, str) or not mint:
            return
        status = _SCHEDULER_FAILURE_STATUS.get(
            str(failure_reason), GLOBAL_FEES_STATUS_PROVIDER_ERROR)
        with self._lock:
            entry = self._entry(mint)
            self._counters["global_fees_provider_failures"] += 1
            entry["last_status"] = status
            entry["last_failure_reason"] = str(failure_reason)
            entry["last_observed_at_utc"] = self._now_iso()

    # ---- read paths ---------------------------------------------------

    def snapshot(self, mint: object) -> Dict[str, Any]:
        """Canonical candidate-facing Global Fees state for one exact mint.

        Freshness is projected at snapshot time: a valid value older than
        the display bound reports ``STALE`` (display-only fail-closed); the
        value and its provenance stay present for artifacts.
        """

        mint_text = mint if isinstance(mint, str) else ""
        now_iso = self._now_iso()
        now_epoch = _parse_iso_epoch(now_iso)
        with self._lock:
            entry = self._state.get(mint_text)
            base = {
                "schema_version": GLOBAL_FEES_SCHEMA_VERSION,
                "token_mint": mint_text,
                "global_fees_paid_sol": None,
                "global_fees_interval": GLOBAL_FEES_INTERVAL_ALLTIME,
                "global_fees_source": GLOBAL_FEES_SOURCE_PAID_MARKET_PRIMARY,
                "global_fees_endpoint_source": (
                    GLOBAL_FEES_ENDPOINT_TOKEN_OVERVIEW),
                "global_fees_status": GLOBAL_FEES_STATUS_NOT_REQUESTED,
                "global_fees_observed_at_utc": None,
                "global_fees_age_seconds": None,
                "global_fees_http_status_class": None,
                "global_fees_failure_reason": None,
                "global_fees_raw_type": None,
                "global_fees_request_reused": True,
                "global_fees_display_fresh_seconds": (
                    self._display_fresh_seconds),
                "global_fees_provider_coverage_note": (
                    GLOBAL_FEES_COVERAGE_NOTE),
                "global_fees_regression_detected": False,
                "global_fees_regression_prior_value_sol": None,
                "global_fees_regression_prior_observed_at_utc": None,
                "global_fees_regression_observed_at_utc": None,
                "global_fees_observation_count": 0,
                "observe_only": True,
            }
            if entry is None:
                return base
            base["global_fees_observation_count"] = entry["observation_count"]
            base["global_fees_regression_detected"] = entry[
                "regression_detected"]
            base["global_fees_regression_prior_value_sol"] = entry[
                "regression_prior_value_sol_text"]
            base["global_fees_regression_prior_observed_at_utc"] = entry[
                "regression_prior_observed_at_utc"]
            base["global_fees_regression_observed_at_utc"] = entry[
                "regression_observed_at_utc"]
            if entry["value_sol_text"] is None:
                # No contract-valid value yet: surface the last classification
                # or provider failure exactly as recorded.
                if entry["last_status"] is not None:
                    base["global_fees_status"] = entry["last_status"]
                base["global_fees_failure_reason"] = entry[
                    "last_failure_reason"]
                base["global_fees_observed_at_utc"] = entry[
                    "last_observed_at_utc"]
                base["global_fees_raw_type"] = entry["last_raw_type"]
                return base
            observed_iso = entry["value_observed_at_utc"]
            observed_epoch = _parse_iso_epoch(observed_iso)
            age: Optional[float] = None
            fresh = False
            if observed_epoch is not None and now_epoch is not None:
                age = round(now_epoch - observed_epoch, 3)
                fresh = (-GLOBAL_FEES_MAX_FUTURE_SKEW_SECONDS
                         <= age <= self._display_fresh_seconds)
            base["global_fees_paid_sol"] = entry["value_sol_text"]
            base["global_fees_status"] = (
                GLOBAL_FEES_STATUS_VALID if fresh
                else GLOBAL_FEES_STATUS_STALE)
            base["global_fees_observed_at_utc"] = observed_iso
            base["global_fees_age_seconds"] = age
            base["global_fees_http_status_class"] = entry[
                "value_http_status_class"]
            base["global_fees_failure_reason"] = entry["last_failure_reason"]
            base["global_fees_raw_type"] = entry["value_raw_type"]
            return base

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counters)


__all__ = (
    "GLOBAL_FEES_SCHEMA_VERSION",
    "GLOBAL_FEES_STATUS_VALID",
    "GLOBAL_FEES_STATUS_FIELD_MISSING",
    "GLOBAL_FEES_STATUS_VALUE_NULL",
    "GLOBAL_FEES_STATUS_VALUE_INVALID",
    "GLOBAL_FEES_STATUS_VALUE_NEGATIVE",
    "GLOBAL_FEES_STATUS_VALUE_NONFINITE",
    "GLOBAL_FEES_STATUS_STALE",
    "GLOBAL_FEES_STATUS_PLAN_FORBIDDEN",
    "GLOBAL_FEES_STATUS_RATE_LIMITED",
    "GLOBAL_FEES_STATUS_PROVIDER_ERROR",
    "GLOBAL_FEES_STATUS_NOT_REQUESTED",
    "GLOBAL_FEES_STATUS_TOKENS",
    "GLOBAL_FEES_INTERVAL_ALLTIME",
    "GLOBAL_FEES_SOURCE_PAID_MARKET_PRIMARY",
    "GLOBAL_FEES_ENDPOINT_TOKEN_OVERVIEW",
    "GLOBAL_FEES_ENDPOINT_TOKEN_FEE_SINGLE",
    "GLOBAL_FEES_DISPLAY_FRESH_SECONDS",
    "GLOBAL_FEES_MAX_FUTURE_SKEW_SECONDS",
    "GLOBAL_FEES_FIELD_NAME",
    "GLOBAL_FEES_COVERAGE_NOTE",
    "GLOBAL_FEES_ACCESS_AVAILABLE",
    "GLOBAL_FEES_ACCESS_PLAN_FORBIDDEN",
    "GLOBAL_FEES_ACCESS_AUTH_FAILURE",
    "GLOBAL_FEES_ACCESS_RATE_LIMITED",
    "GLOBAL_FEES_ACCESS_RESPONSE_INVALID",
    "classify_dedicated_fee_access",
    "classify_global_fees_value",
    "build_overview_global_fees_observation",
    "GlobalFeesTracker",
)
