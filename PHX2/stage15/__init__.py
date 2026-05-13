"""Stage 15 operator approval layer.

Offline governance layer between Stage 14 shadow policy replay and
Stage 16 runtime observe-only wiring. Stage 15 does ONE job:

  Takes a Stage 14 run directory, joins Stage 14 shadow rules against
  a human-authored operator review CSV, validates the review against
  strict safety rules, and emits a frozen auditable approval artifact.

Stage 15 is NOT runtime, NOT live, NOT hard-blocking, NOT policy
enforcement. It produces an approval DRAFT only. Stage 16 will later
produce any runtime-consumable observe-only derivative artifact.

The warning-flag contract: Stage 14 owns warning classification.
Stage 15 reads warning_flags directly from Stage 14's
``impact_summary_by_rule.csv`` and passes them through verbatim.
Stage 15 does not derive, recompute, or interpret warning flags.
"""

from PHX2.stage15.errors import (
    Stage15Error,
    Stage15LoadTimeError,
    Stage15ApprovalTimeError,
    Stage15OutputDirError,
)

__all__ = [
    "Stage15Error",
    "Stage15LoadTimeError",
    "Stage15ApprovalTimeError",
    "Stage15OutputDirError",
]
