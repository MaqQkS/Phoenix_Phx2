# PHX2 Safety Contract

Stage 0 and Stage 1 establish boundaries before behavior. Stage 2 adds typed
settings and SQLite connection boundaries.

## Hard Rules

- Phoenix1 remains the live collector and baseline.
- PHX2 must not mutate Phoenix1 tables.
- PHX2 must not send Telegram or Discord alerts during dry-run scaffolding.
- PHX2 must not scan raw event tables at alert decision time once feature windows exist.
- Every future state mutation must flow through a PHX2 service owner and TelemetryService.

## Current Stage

This stage contains importable placeholders only. The files define names and ownership boundaries, not production behavior.

## Verification Outputs

PHX2 should prove behavior before live sending through:

- Dry-run database rows.
- Console summaries.
- CSV exports.
- Preview alert text files.
- Private Telegram and Discord test channels after explicit promotion.

Stage 2 includes placeholders for those boundaries and safe DB connection
helpers, but does not write schemas, send messages, or open network clients.

## Deferred Work

- DB schema creation and migrations.
- Read-only Phoenix1 database connections.
- Fee window materialization.
- ATH mutation rules.
- Alert eligibility rules.
- Filter labels.
- Score formulas.
- Alert rendering output.
- File preview, console, private channel, and live dispatch behavior.
- Outcome tracking.
