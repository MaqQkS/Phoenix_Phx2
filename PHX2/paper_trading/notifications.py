"""Durable simulated-trade notifications; transport is explicitly injected.

This module has no delivery client, credential reader or network imports.
An event enters this outbox in the same commit as its paper transition.
"""
from __future__ import annotations

import hashlib


def _escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_notification(run_id, position, transition, ts_epoch):
    identity = f"{run_id}|{position.paper_trade_id}|{transition}"
    event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    labels = {"ENTRY": "ENTRY", "STAKE_RECOVERED": "STAKE RECOVERED",
              "FINAL_EXIT": "FINAL EXIT"}
    risk = position.risk_label_at_entry or "Unknown / unverified"
    lines = [f"<b>PHOENIX PAPER — {labels[transition]}</b>",
             f"<code>{_escape(position.mint)}</code>",
             f"Strategy: {_escape(position.strategy_name)}",
             "Simulation only · no live execution"]
    if transition == "ENTRY":
        lines.append(f"Simulated cost: ${position.cost_basis_usd:.2f}")
    elif transition == "STAKE_RECOVERED":
        recovered = position.strategy_state.get("initial_recovery_proceeds_usd", 0.0)
        lines.extend([f"Net proceeds recovered: ${recovered:.2f}",
                      f"Runner trail: {100 * (position.plan.trailing_stop_pct or 0):g}%"])
    else:
        lines.extend([f"Outcome: {_escape(position.status)}",
                      f"Reason: {_escape(position.reason_closed or 'Unknown')}",
                      f"Simulated realized P/L: ${position.realized_pnl_usd:+.2f}"])
    lines.append(f"Risk at entry: {_escape(risk)}")
    if position.latest_price_epoch is not None:
        lines.append(f"Quote age at decision: {max(0, ts_epoch - position.latest_price_epoch):g}s")
    else:
        lines.append("Quote time: unavailable")
    if position.status == "DATA_LOST":
        lines.append("Data unavailable · model haircut valuation from last observed quote")
    return {"event_id": event_id, "run_id": run_id,
            "paper_trade_id": position.paper_trade_id, "transition": transition,
            "ts_epoch": ts_epoch, "text": "\n".join(lines), "status": "PENDING",
            "attempts": 0, "destination_alias": None, "message_id": None,
            "next_attempt_epoch": 0.0}


class PaperNotificationOutbox:
    def __init__(self, engine):
        self.engine = engine

    def _transition(self, event_id, **changes):
        self.engine.begin_batch()
        try:
            self.engine.notification_events[event_id].update(changes)
            self.engine.commit_batch()
        except BaseException:
            self.engine.rollback_batch()
            raise

    def dispatch_pending(self, transport, *, authorized=False,
                         destination_alias=None, max_messages=1, max_attempts=3,
                         now_epoch=None, should_stop=None):
        """One attempt per eligible event; unknown delivery is operator-held.

        Authorization and a non-secret destination alias must be explicit.
        A transport call should itself have a bounded retry policy. No result
        detail or exception text is persisted, only recognized status codes.
        """
        engine = self.engine
        if not authorized or not isinstance(destination_alias, str) or not destination_alias:
            raise ValueError("PAPER_DELIVERY_NOT_ARMED")
        if engine._batch_active:
            raise RuntimeError("PAPER_DELIVERY_DURING_TRANSACTION")
        if not 1 <= max_messages <= 20 or not 1 <= max_attempts <= 3:
            raise ValueError("PAPER_DELIVERY_LIMIT_INVALID")
        now = float(now_epoch if now_epoch is not None else (
            engine.wall_clock() if engine.wall_clock else engine.now_epoch or 0.0))
        attempted = 0
        for event_id in list(engine.notification_events):
            if should_stop is not None and should_stop():
                break
            event = engine.notification_events[event_id]
            if event["status"] not in ("PENDING", "RETRYABLE"):
                continue
            if event["attempts"] >= max_attempts or event["next_attempt_epoch"] > now:
                continue
            if event["destination_alias"] not in (None, destination_alias):
                raise ValueError("PAPER_DELIVERY_DESTINATION_CHANGED")
            previous = {key: event[key] for key in ("status", "destination_alias", "attempts")}
            self._transition(event_id, status="IN_FLIGHT", destination_alias=destination_alias,
                             attempts=event["attempts"] + 1)
            if should_stop is not None and should_stop():
                # No send occurred. Preserve eligibility for an explicitly
                # armed later run without consuming its attempt budget.
                self._transition(event_id, **previous)
                break
            try:
                result = transport.send_html(event["text"])
                def field(name):
                    return result.get(name) if isinstance(result, dict) else getattr(result, name, None)
                category = field("transport_status")
                message_id = field("message_id")
                if (category == "SENT_OK" and field("ok") is True
                        and isinstance(message_id, int) and not isinstance(message_id, bool)
                        and message_id > 0):
                    outcome = "SENT"
                elif category in ("RATE_LIMITED", "MESSAGE_REJECTED", "MESSAGE_TOO_LONG",
                                  "AUTHENTICATION_FAILED", "CHAT_NOT_FOUND", "BOT_NOT_ALLOWED",
                                  "TRANSPORT_CLOSED"):
                    outcome = "RETRYABLE" if event["attempts"] < max_attempts else "REJECTED"
                else:
                    outcome = "UNKNOWN"
            except Exception:
                outcome, message_id = "UNKNOWN", None
            self._transition(event_id, status=outcome,
                             message_id=message_id if outcome == "SENT" else None,
                             next_attempt_epoch=now + min(300, 30 * event["attempts"]))
            attempted += 1
            if attempted >= max_messages:
                break
        return attempted
