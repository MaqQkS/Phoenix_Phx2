# PHX2

PHX2 is the clean modular fork of Phoenix. Stage 0 and Stage 1 are scaffold-only.
Stage 2 adds typed settings and safe database connection boundaries.

Current guarantees:

- No Phoenix1 files are imported or modified by this package.
- No database schemas are created.
- No Phoenix1 database writes are performed.
- No network calls are made.
- No Telegram or Discord messages are sent.
- Field, Score, and Clock modules exist as placeholders only.
- Score formulas are intentionally absent until raw feature capture is designed.

The package is meant to grow in dry-run mode first, writing only to a PHX2 database once schemas are explicitly implemented in a later stage.

Future dry-run verification outputs:

- PHX2 dry-run database rows.
- Console summaries.
- CSV exports.
- Preview alert text files.
- Later private Telegram and Discord test channels.

Stage 2 opens Phoenix1 only through SQLite read-only URI mode and opens PHX2 only through a separate dry-run database path. It does not implement writers, schemas, network clients, or sends.
