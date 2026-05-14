"""Stage 17 test fixture builders.

These helpers insert canonical evaluations/outcomes/alert-decisions
directly via raw parameterized SQL. They deliberately do NOT use the
Stage 16B repository class (the conftest bootstraps schema only).
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# alert_decisions
# ---------------------------------------------------------------------------


def insert_alert_decision(
    connection: sqlite3.Connection,
    *,
    decision_id: int,
    token_address: str = "TOKEN_AAA",
    evaluated_at: str = "2026-05-13T12:00:00+00:00",
    decision_type: str = "would_alert",
    would_alert: int = 1,
    tier_name: Optional[str] = "tier_a",
    tier_index: Optional[int] = 0,
    primary_reason: str = "test_primary_reason",
    blocked: int = 0,
    skipped: int = 0,
    ath_status: str = "unknown",
    ath_confidence: str = "low",
    policy_version: str = "test_policy_v0",
    created_at: str = "2026-05-13T12:00:00+00:00",
    data_status: str = "COMPLETE",
) -> int:
    """Insert a single alert_decisions row.

    Returns ``decision_id`` (the caller-chosen PK) for convenience.
    """

    connection.execute(
        """
        INSERT INTO alert_decisions (
            id, token_address, evaluated_at, decision_type,
            tier_index, tier_name, primary_reason, would_alert,
            blocked, skipped, ath_status, ath_confidence,
            policy_version, created_at, data_status
        ) VALUES (
            :id, :token_address, :evaluated_at, :decision_type,
            :tier_index, :tier_name, :primary_reason, :would_alert,
            :blocked, :skipped, :ath_status, :ath_confidence,
            :policy_version, :created_at, :data_status
        )
        """,
        {
            "id": decision_id,
            "token_address": token_address,
            "evaluated_at": evaluated_at,
            "decision_type": decision_type,
            "tier_index": tier_index,
            "tier_name": tier_name,
            "primary_reason": primary_reason,
            "would_alert": would_alert,
            "blocked": blocked,
            "skipped": skipped,
            "ath_status": ath_status,
            "ath_confidence": ath_confidence,
            "policy_version": policy_version,
            "created_at": created_at,
            "data_status": data_status,
        },
    )
    connection.commit()
    return decision_id


# ---------------------------------------------------------------------------
# observe_only_policy_evaluations
# ---------------------------------------------------------------------------


def insert_evaluation(
    connection: sqlite3.Connection,
    *,
    alert_decision_id: int,
    policy_hash: str,
    rule_id: str,
    evaluation_status: str,
    tier_name_snapshot: Optional[str] = "tier_a",
    unevaluable_reason: Optional[str] = None,
    evaluated_at_utc: str = "2026-05-13T12:00:00+00:00",
    created_at_utc: str = "2026-05-13T12:00:00+00:00",
    predicate_snapshot_json: str = "{}",
) -> None:
    """Insert one observe_only_policy_evaluations row.

    Derives matched / would_have_blocked / unevaluable_reason from the
    declared ``evaluation_status`` so the row satisfies the schema
    CHECK constraints automatically.
    """

    if evaluation_status == "MATCHED":
        matched = 1
        would_have_blocked = 1
        reason = None
    elif evaluation_status == "NOT_MATCHED":
        matched = 0
        would_have_blocked = 0
        reason = None
    elif evaluation_status == "UNEVALUABLE":
        matched = 0
        would_have_blocked = 0
        reason = unevaluable_reason or "missing_input"
    else:
        raise ValueError(
            f"unsupported evaluation_status: {evaluation_status!r}"
        )

    connection.execute(
        """
        INSERT INTO observe_only_policy_evaluations (
            alert_decision_id, tier_name_snapshot, policy_hash,
            rule_id, evaluation_status, matched, would_have_blocked,
            unevaluable_reason, predicate_snapshot_json,
            evaluated_at_utc, created_at_utc
        ) VALUES (
            :alert_decision_id, :tier_name_snapshot, :policy_hash,
            :rule_id, :evaluation_status, :matched, :would_have_blocked,
            :unevaluable_reason, :predicate_snapshot_json,
            :evaluated_at_utc, :created_at_utc
        )
        """,
        {
            "alert_decision_id": alert_decision_id,
            "tier_name_snapshot": tier_name_snapshot,
            "policy_hash": policy_hash,
            "rule_id": rule_id,
            "evaluation_status": evaluation_status,
            "matched": matched,
            "would_have_blocked": would_have_blocked,
            "unevaluable_reason": reason,
            "predicate_snapshot_json": predicate_snapshot_json,
            "evaluated_at_utc": evaluated_at_utc,
            "created_at_utc": created_at_utc,
        },
    )
    connection.commit()


# ---------------------------------------------------------------------------
# outcome_windows
# ---------------------------------------------------------------------------


def insert_outcome_window(
    connection: sqlite3.Connection,
    *,
    alert_decision_id: int,
    window_seconds: int,
    token_address: str = "TOKEN_AAA",
    data_status: str = "COMPLETE",
    max_return_multiple: Optional[float] = 2.5,
    max_drawdown_from_peak_pct: Optional[float] = -10.0,
    time_to_max_return_seconds: Optional[float] = 60.0,
    hit_2x: Optional[int] = 1,
    hit_3x: Optional[int] = 0,
    hit_5x: Optional[int] = 0,
    window_start_time: str = "2026-05-13T12:00:00+00:00",
    window_end_time: str = "2026-05-13T12:05:00+00:00",
    created_at: str = "2026-05-13T12:05:00+00:00",
) -> None:
    """Insert one outcome_windows row matching the Stage 9 schema."""

    connection.execute(
        """
        INSERT INTO outcome_windows (
            alert_decision_id, token_address, window_seconds,
            window_start_time, window_end_time, max_return_multiple,
            max_drawdown_from_peak_pct, time_to_max_return_seconds,
            hit_2x, hit_3x, hit_5x, data_status, created_at
        ) VALUES (
            :alert_decision_id, :token_address, :window_seconds,
            :window_start_time, :window_end_time, :max_return_multiple,
            :max_drawdown_from_peak_pct, :time_to_max_return_seconds,
            :hit_2x, :hit_3x, :hit_5x, :data_status, :created_at
        )
        """,
        {
            "alert_decision_id": alert_decision_id,
            "token_address": token_address,
            "window_seconds": window_seconds,
            "window_start_time": window_start_time,
            "window_end_time": window_end_time,
            "max_return_multiple": max_return_multiple,
            "max_drawdown_from_peak_pct": max_drawdown_from_peak_pct,
            "time_to_max_return_seconds": time_to_max_return_seconds,
            "hit_2x": hit_2x,
            "hit_3x": hit_3x,
            "hit_5x": hit_5x,
            "data_status": data_status,
            "created_at": created_at,
        },
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Higher-level convenience: populate a small canonical scenario
# ---------------------------------------------------------------------------


def seed_canonical_scenario(
    db_path,
    *,
    policy_hash: str = "ph_canonical",
    rule_id: str = "rule_a",
    tier_name: Optional[str] = "tier_a",
    matched_ids: Iterable[int] = (1, 2, 3, 4, 5),
    not_matched_ids: Iterable[int] = (6, 7, 8, 9, 10),
    window_seconds: int = 300,
    matched_hits: int = 1,
    not_matched_hits: int = 4,
) -> None:
    """Seed a small canonical scenario into a Stage 17 fixture DB.

    Each id gets one alert_decisions row in WOULD_ALERT scope, one
    evaluation row (MATCHED or NOT_MATCHED depending on the id
    bucket), and one outcome_windows row at the requested
    ``window_seconds``. ``matched_hits`` / ``not_matched_hits`` set
    the count of hit_2x=1 within each bucket so tests can pin
    matched-vs-not_matched rate differences.
    """

    matched_ids = list(matched_ids)
    not_matched_ids = list(not_matched_ids)
    connection = sqlite3.connect(str(db_path))
    try:
        for did in matched_ids + not_matched_ids:
            insert_alert_decision(
                connection,
                decision_id=did,
                tier_name=tier_name,
            )
        for idx, did in enumerate(matched_ids):
            insert_evaluation(
                connection,
                alert_decision_id=did,
                policy_hash=policy_hash,
                rule_id=rule_id,
                evaluation_status="MATCHED",
                tier_name_snapshot=tier_name,
            )
            insert_outcome_window(
                connection,
                alert_decision_id=did,
                window_seconds=window_seconds,
                hit_2x=1 if idx < matched_hits else 0,
            )
        for idx, did in enumerate(not_matched_ids):
            insert_evaluation(
                connection,
                alert_decision_id=did,
                policy_hash=policy_hash,
                rule_id=rule_id,
                evaluation_status="NOT_MATCHED",
                tier_name_snapshot=tier_name,
            )
            insert_outcome_window(
                connection,
                alert_decision_id=did,
                window_seconds=window_seconds,
                hit_2x=1 if idx < not_matched_hits else 0,
            )
    finally:
        connection.close()
