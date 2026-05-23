"""Stage 28.5 CLI status-line formatter.

This module provides the pure, redaction-safe Stage 28.5 CLI
status-line formatter. The formatter consumes a Stage 28.5
``Stage28_5CliStatusLineModel`` and returns a single compact
one-line string suitable for operator-visible status reporting
on the terminal.

The formatter:

  * is pure -- no I/O, no print, no logging, no terminal
    colours, no scheduling, no thread / async / subprocess use,
  * is deterministic -- the same model maps to the same string,
  * carries only safe-to-display closed-set tokens + non-negative
    counter values + safe-shape run / session identifiers (the
    model layer already enforces this; the formatter never copies
    raw upstream caller material),
  * returns a string that contains no newline character (so the
    caller can append it to a log line without breaking the
    log's line-orientation),
  * is independent of the heartbeat / health-snapshot / final-
    summary writers (sibling Stage 28.5 modules) -- the formatter
    is the only Stage 28.5 surface that emits a human-facing
    status line.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network, no HTTP, no gRPC, no Discord, no Telegram, no X /
    social, no provider client.
  * No retry / backoff / failure classification.
  * No audited HTTP transport (Stage 28.4).
  * No runner / no longer-session smoke harness.
  * No sleep / no scheduling / no queue / no thread / no async /
    no subprocess.
  * No filesystem I/O. The formatter never opens / writes / reads
    a file.
  * No print. The formatter returns the formatted string; calling
    code chooses whether to write it to stdout / a log file /
    elsewhere.

This module imports only the Stage 28.5 models module. It does
NOT import Stage 21-27 production code, does NOT import Stage
28.1 / 28.2 / 28.3a / 28.3b / 28.4 production code, does NOT
import any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface (it ships no ``__main__`` block), and
contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage28.health_status_models import (
    STAGE28_5_CLI_STATUS_SCHEMA_VERSION,
    Stage28_5CliStatusLineModel,
    Stage28_5HealthStatusError,
)


# ---------------------------------------------------------------------------
# CLI status-line constants
# ---------------------------------------------------------------------------


# Locked Stage 28.5 CLI status-line prefix. The literal is
# distinctive (``PHX2[28.5]``) so a terminal reader can recognise
# the line at a glance; it carries no URL, no host name, no
# secret material.
CLI_STATUS_LINE_PREFIX: str = "PHX2[28.5]"


# Maximum length of the formatted status line. The cap exists so
# a misconfigured / pathological caller cannot emit an unbounded
# string. Caller-supplied identifiers are already capped to
# 64 chars by ``is_safe_identifier``; the remaining content is
# fixed-width closed-set tokens + small integer counters, so the
# locked maximum is generous.
CLI_STATUS_LINE_MAX_LENGTH: int = 1024


# ---------------------------------------------------------------------------
# CLI formatter exception (module-local)
# ---------------------------------------------------------------------------


class Stage28_5CliStatusLineError(Stage28_5HealthStatusError):
    """Raised when ``format_cli_status_line(...)`` is called with
    an argument that is not a Stage 28.5 CLI status-line model or
    that produces a line exceeding the locked maximum length.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 28.5 CLI status-line error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


def format_cli_status_line(
    model: Stage28_5CliStatusLineModel,
) -> str:
    """Format a Stage 28.5 CLI status-line model into a compact
    single-line operator-visible status string.

    The returned string:

      * starts with the locked ``CLI_STATUS_LINE_PREFIX``,
      * carries the safe run / session identifiers,
      * carries the closed-set aggregate health status,
      * carries the closed-set provider / price / dispatch /
        ledger / transport / artifact statuses,
      * carries the small set of operator-visible counters
        (events, pings rendered, dispatch ok / fail, retries,
        duplicates / ambiguous / unknown-pair / disagree-pair /
        USDC-observe-only / stale / missing / malformed
        suppressions),
      * carries the closed-set stop reason,
      * carries the closed-set redaction status,
      * contains no newline character,
      * is at most ``CLI_STATUS_LINE_MAX_LENGTH`` characters.
    """
    if not isinstance(model, Stage28_5CliStatusLineModel):
        raise Stage28_5CliStatusLineError(
            reason="NOT_A_CLI_STATUS_LINE_MODEL",
        )
    if model.schema_version != STAGE28_5_CLI_STATUS_SCHEMA_VERSION:
        raise Stage28_5CliStatusLineError(
            reason="UNKNOWN_CLI_STATUS_SCHEMA_VERSION",
        )
    parts: tuple[str, ...] = (
        CLI_STATUS_LINE_PREFIX,
        f"run={model.run_id}",
        f"sess={model.session_id}",
        f"health={model.health_status}",
        f"provider={model.provider_status}",
        f"price={model.price_status}",
        f"dispatch={model.dispatch_status}",
        f"ledger={model.ledger_status}",
        f"transport={model.transport_status}",
        f"artifact={model.artifact_status}",
        f"events={model.event_count}",
        f"pings={model.ping_rendered_count}",
        f"dispatch_ok={model.dispatch_success_count}",
        f"dispatch_fail={model.dispatch_failure_count}",
        f"retries={model.retry_count}",
        f"dup_sup={model.duplicate_suppressed_count}",
        f"amb_sup={model.ambiguous_suppressed_count}",
        f"unk_pair_sup={model.unknown_pair_suppressed_count}",
        f"dis_pair_sup={model.disagree_pair_suppressed_count}",
        f"usdc_obs={model.usdc_observe_only_count}",
        f"stale={model.stale_price_count}",
        f"missing={model.missing_price_count}",
        f"malformed={model.malformed_event_count}",
        f"stop={model.stop_reason}",
        f"redaction={model.redaction_status}",
    )
    line = " ".join(parts)
    if "\n" in line or "\r" in line:
        raise Stage28_5CliStatusLineError(
            reason="LINE_CONTAINS_NEWLINE_OR_CR",
        )
    if len(line) > CLI_STATUS_LINE_MAX_LENGTH:
        raise Stage28_5CliStatusLineError(
            reason="LINE_EXCEEDS_MAX_LENGTH",
        )
    return line


__all__ = (
    "CLI_STATUS_LINE_PREFIX",
    "CLI_STATUS_LINE_MAX_LENGTH",
    "Stage28_5CliStatusLineError",
    "format_cli_status_line",
)
