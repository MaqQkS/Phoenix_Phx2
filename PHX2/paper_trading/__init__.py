"""PHX2 paper trading engine (simulation only).

Replays PHX2 candidate/ping artifact JSONL streams through one or more named
strategies with realistic position sizing, and writes append-only paper
ledgers plus dashboard-ready summary artifacts.

Everything in this package is virtual bookkeeping over already-recorded (or
freshly observed) market context records. The package holds no credentials,
builds no transactions, and moves no funds of any kind.
"""

PAPER_TRADING_VERSION = "phx2_paper_v1"

__all__ = ["PAPER_TRADING_VERSION"]
