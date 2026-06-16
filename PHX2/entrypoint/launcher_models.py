"""Build #23 supervised-entrypoint launcher MODEL layer (pure, stdlib-only).

Build #23 wires a safe ``python main.py`` entrypoint to the already-proven,
out-of-repo supervised private operator flow. This module is the passive, pure,
stdlib-only MODEL layer for that thin launcher: the closed-set mode / action /
post-send vocabularies the entrypoint accepts, the durable-ledger baseline triple
(``sha256`` / ``size_bytes`` / ``line_count``) the operator asserts on every
supervised invocation, the redaction-safe launcher result record, the closed-set
launch-outcome vocabulary, and the pure safe-shape predicates the launcher
composes.

It carries NO behavior that sends, arms, injects a transport, reads a process
environment, opens a network connection, opens a database, writes a file,
reserves a dispatch, signs anything, or trades anything. The real supervised
ceremony -- preview, send-fake, durable dedupe forecast, interactive human
approval, the one-line arm flip, EXACTLY ONE private operator send, immediate
re-safe, the +1 ledger verification, and the baseline update -- remains a
SEPARATE, out-of-repo, explicitly operator-authorized flow this module does not
run and does not import.

The durable-ledger baseline triple semantics are EXACT and operator-owned:

  * ``sha256``     -- the durable JSONL ledger content digest (64 hex chars).
  * ``size_bytes`` -- the durable ledger size in bytes.
  * ``line_count`` -- the durable ledger line (JSONL record) count.

A successful next real send (owned by the out-of-repo supervisor, NOT by this
repo) advances ``line_count`` by exactly one, grows ``size_bytes`` by one
appended JSONL record (NOT by exactly one byte), and yields a NEW ``sha256`` that
becomes the new baseline. This module only PARSES + shape-checks the triple and
passes it through verbatim; it never computes a digest, reads the ledger, or
mutates it.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.x model leaves).
  * No ``os`` / ``subprocess`` / ``json`` import; no env read, no process spawn.
  * No network, no HTTP, no gRPC, no socket; no database; no filesystem write.
  * No url / host / credential / transport-destination reference; no public /
    subscriber / paid routing token in any handoff it shapes.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Build identity
# ---------------------------------------------------------------------------


BUILD_23_IDENTITY: str = "build23_supervised_entrypoint"


# ---------------------------------------------------------------------------
# Closed-set: supervised mode (exactly one accepted value)
# ---------------------------------------------------------------------------
#
# The entrypoint accepts ONE supervised mode token. There is deliberately no
# public / subscriber / paid mode to select -- routing stays private-operator-only
# and is owned downstream by the out-of-repo supervisor + the committed Stage
# 30.11.16 private-only transport guard.


MODE_PRIVATE_SUPERVISED: str = "private-supervised"

SUPPORTED_MODES: Tuple[str, ...] = (MODE_PRIVATE_SUPERVISED,)


def is_supported_mode(value: object) -> bool:
    """Return ``True`` iff ``value`` is the single supported supervised mode.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in SUPPORTED_MODES


# ---------------------------------------------------------------------------
# Closed-set: supervised action (exactly one per supervised invocation)
# ---------------------------------------------------------------------------
#
# Exactly one action per ``--mode private-supervised`` invocation. None of them
# sends from this repo: ``preflight-only`` and ``dry-run`` are no-send by
# definition, and ``live`` only LAUNCHES the out-of-repo supervisor (whose own
# interactive approval + arm flip gate the single real send).


ACTION_PREFLIGHT_ONLY: str = "preflight-only"
ACTION_DRY_RUN: str = "dry-run"
ACTION_LIVE: str = "live"

SUPPORTED_ACTIONS: Tuple[str, ...] = (
    ACTION_PREFLIGHT_ONLY,
    ACTION_DRY_RUN,
    ACTION_LIVE,
)


def is_supported_action(value: object) -> bool:
    """Return ``True`` iff ``value`` is a supported supervised action.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in SUPPORTED_ACTIONS


# ---------------------------------------------------------------------------
# Closed-set: post-send lifecycle (only "stop", only with --live)
# ---------------------------------------------------------------------------


POST_SEND_STOP: str = "stop"

SUPPORTED_POST_SEND: Tuple[str, ...] = (POST_SEND_STOP,)


def is_supported_post_send(value: object) -> bool:
    """Return ``True`` iff ``value`` is a supported post-send token.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in SUPPORTED_POST_SEND


# ---------------------------------------------------------------------------
# The single owned env pointer + the handoff flag vocabulary
# ---------------------------------------------------------------------------
#
# The launcher resolves the out-of-repo supervisor command from exactly ONE
# pointer env var. This is a COMMAND POINTER, never a credential: it names where
# the supervisor lives, not any secret. The launcher reads no other env var.


SUPERVISOR_COMMAND_ENV: str = "PHX2_SUPERVISOR_CMD"


# The closed-set flags the launcher appends to the resolved supervisor command.
# Deliberately minimal: a mode echo, the chosen action, the operator's baseline
# assertion, and (only for --live) the post-send lifecycle. No routing, no arm,
# no transport, no credential flag is ever appended.
HANDOFF_MODE_FLAG: str = "--mode"
HANDOFF_ACTION_FLAG: str = "--action"
HANDOFF_BASELINE_FLAG: str = "--require-baseline"
HANDOFF_POST_SEND_FLAG: str = "--post-send"


# ---------------------------------------------------------------------------
# Routing / handoff safety denylists (used by the launcher to self-check its
# appended handoff tail; the operator-supplied command prefix is NOT scanned).
# ---------------------------------------------------------------------------


# Routing substrings that must never appear in the launcher's appended handoff
# tail. Their absence keeps the supervised path private-operator-only.
FORBIDDEN_ROUTING_TOKENS: Tuple[str, ...] = (
    "public",
    "subscriber",
    "paid",
    "broadcast",
    "audience",
    "everyone",
)


# Exact flag tokens the launcher must never append. Their absence guarantees the
# launcher never asks the supervisor to arm, inject a real transport, or carry an
# operator authorization sentinel -- that wiring stays entirely inside the
# out-of-repo supervisor. (Compared by exact element, so the legitimate
# ``--post-send`` flag is never mistaken for one of these.)
FORBIDDEN_HANDOFF_FLAGS: Tuple[str, ...] = (
    "--arm",
    "--authorize",
    "--authorization",
    "--inject-transport",
    "--transport",
    "--real-send",
    "--confirm-token",
)


# ---------------------------------------------------------------------------
# Closed-set: launch outcome
# ---------------------------------------------------------------------------
#
# Exactly one outcome per launch. ``SAFE_NOOP`` is the default no-mode status.
# ``INVOKED_SUPERVISOR`` is the only outcome on which the out-of-repo supervisor
# was reached (the child exit code is then relayed). Every ``REFUSED_*`` outcome
# is a fail-closed path on which NO subprocess was spawned and nothing was sent.


OUTCOME_SAFE_NOOP: str = "SAFE_NOOP"
OUTCOME_INVOKED_SUPERVISOR: str = "INVOKED_SUPERVISOR"
OUTCOME_REFUSED_INVALID_MODE: str = "REFUSED_INVALID_MODE"
OUTCOME_REFUSED_INVALID_ACTION: str = "REFUSED_INVALID_ACTION"
OUTCOME_REFUSED_INVALID_POST_SEND: str = "REFUSED_INVALID_POST_SEND"
OUTCOME_REFUSED_MALFORMED_BASELINE: str = "REFUSED_MALFORMED_BASELINE"
OUTCOME_REFUSED_SUPERVISOR_NOT_CONFIGURED: str = (
    "REFUSED_SUPERVISOR_NOT_CONFIGURED"
)
OUTCOME_REFUSED_UNSAFE_HANDOFF: str = "REFUSED_UNSAFE_HANDOFF"
OUTCOME_REFUSED_SUPERVISOR_INVOCATION_FAILED: str = (
    "REFUSED_SUPERVISOR_INVOCATION_FAILED"
)


SUPPORTED_OUTCOMES: Tuple[str, ...] = (
    OUTCOME_SAFE_NOOP,
    OUTCOME_INVOKED_SUPERVISOR,
    OUTCOME_REFUSED_INVALID_MODE,
    OUTCOME_REFUSED_INVALID_ACTION,
    OUTCOME_REFUSED_INVALID_POST_SEND,
    OUTCOME_REFUSED_MALFORMED_BASELINE,
    OUTCOME_REFUSED_SUPERVISOR_NOT_CONFIGURED,
    OUTCOME_REFUSED_UNSAFE_HANDOFF,
    OUTCOME_REFUSED_SUPERVISOR_INVOCATION_FAILED,
)


def is_launch_outcome(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set launch outcome.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in SUPPORTED_OUTCOMES


# Process exit codes the entrypoint maps outcomes onto. Argparse usage errors use
# its own code 2; a fail-closed launcher refusal uses EXIT_REFUSED; an invoked
# supervisor relays the child's own exit code verbatim.
EXIT_OK: int = 0
EXIT_REFUSED: int = 3


# ---------------------------------------------------------------------------
# Baseline triple (sha256 / size_bytes / line_count)
# ---------------------------------------------------------------------------


BASELINE_SHA256_HEX_LEN: int = 64


@dataclass(frozen=True)
class BaselineTriple:
    """Immutable durable-ledger baseline assertion.

    Carries ONLY the three operator-owned scalars the supervisor verifies the
    durable JSONL ledger against before arming, and re-verifies (advanced by one
    appended record) after a successful send:

      * ``sha256``     -- the 64-hex-char ledger content digest (case preserved).
      * ``size_bytes`` -- the ledger size in bytes (a non-negative int).
      * ``line_count`` -- the ledger line / JSONL record count (a non-negative
                          int).

    No secret, no url, no host, no payload. This record never computes the digest
    and never reads or mutates the ledger.
    """

    sha256: str
    size_bytes: int
    line_count: int


def _is_hex64(value: object) -> bool:
    """Return ``True`` iff ``value`` is a 64-char ASCII hex string (either case).

    Pure / total; never raises.
    """
    if not isinstance(value, str) or len(value) != BASELINE_SHA256_HEX_LEN:
        return False
    for ch in value:
        if "0" <= ch <= "9":
            continue
        if "a" <= ch <= "f":
            continue
        if "A" <= ch <= "F":
            continue
        return False
    return True


def _is_canonical_decimal_int(value: object) -> bool:
    """Return ``True`` iff ``value`` is a canonical non-negative decimal int
    string (ASCII digits only, no sign, no leading zero except a lone ``"0"``).

    Canonical form guarantees the parsed triple passes back through unchanged.
    Pure / total; never raises.
    """
    if not isinstance(value, str) or value == "":
        return False
    for ch in value:
        if not ("0" <= ch <= "9"):
            return False
    if len(value) > 1 and value[0] == "0":
        return False
    return True


def parse_baseline_triple(raw: object) -> Optional[BaselineTriple]:
    """Parse ``"<sha256>:<size_bytes>:<line_count>"`` into a ``BaselineTriple``,
    or return ``None`` (fail closed) on ANY shape violation.

    Requires exactly three colon-separated parts, a 64-hex-char ``sha256`` (case
    preserved), and canonical non-negative decimal ``size_bytes`` / ``line_count``.
    Pure / total; never raises. Computes no digest, reads no ledger.
    """
    if not isinstance(raw, str):
        return None
    parts = raw.split(":")
    if len(parts) != 3:
        return None
    sha, size_text, line_text = parts
    if not _is_hex64(sha):
        return None
    if not _is_canonical_decimal_int(size_text):
        return None
    if not _is_canonical_decimal_int(line_text):
        return None
    return BaselineTriple(
        sha256=sha,
        size_bytes=int(size_text),
        line_count=int(line_text),
    )


def baseline_passthrough(triple: BaselineTriple) -> str:
    """Render a ``BaselineTriple`` back to its exact
    ``"<sha256>:<size_bytes>:<line_count>"`` passthrough string.

    Round-trips a value produced by ``parse_baseline_triple`` byte-for-byte. Pure.
    """
    return f"{triple.sha256}:{triple.size_bytes}:{triple.line_count}"


def redacted_baseline(triple: BaselineTriple) -> str:
    """Render a redaction-safe display form of a ``BaselineTriple``.

    Shows only the first 8 and last 8 hex chars of the digest (never the full
    digest) plus the two counts -- safe for human-readable summaries. Pure.
    """
    sha = triple.sha256
    return f"{sha[:8]}..{sha[-8:]}:{triple.size_bytes}:{triple.line_count}"


# ---------------------------------------------------------------------------
# Immutable model: the per-launch result (redaction-safe)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LauncherResult:
    """Immutable, redaction-safe result of one launcher call.

    Carries ONLY closed-set tokens, safe flags, the redacted baseline display,
    the exact baseline passthrough (the operator's own assertion -- not a
    secret), the resolved handoff argv (for verification; its only non-flag value
    is the operator-supplied baseline), and the relayed child exit code. It holds
    NO credential, NO url, NO transport destination, and NO secret.

      * ``outcome``               -- one of ``SUPPORTED_OUTCOMES``.
      * ``mode`` / ``action``     -- the echoed (sanitized) request tokens.
      * ``baseline_display``      -- the redacted baseline (never the full digest).
      * ``baseline_passthrough``  -- the exact ``sha256:size_bytes:line_count``
                                     forwarded to the supervisor (``""`` when the
                                     baseline was malformed / not reached).
      * ``supervisor_configured`` -- whether the command pointer resolved.
      * ``invoked``               -- ``True`` ONLY for ``INVOKED_SUPERVISOR``.
      * ``child_exit_code``       -- the relayed supervisor exit code, or ``None``
                                     when no subprocess was spawned.
      * ``handoff_argv``          -- the resolved argv (empty until built).
    """

    outcome: str
    mode: str
    action: str
    baseline_display: str
    baseline_passthrough: str
    supervisor_configured: bool
    invoked: bool
    child_exit_code: Optional[int]
    handoff_argv: Tuple[str, ...]


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def baseline_triple_field_names() -> Tuple[str, ...]:
    """Return the baseline-triple field names as a tuple."""
    return tuple(f.name for f in fields(BaselineTriple))


def launcher_result_field_names() -> Tuple[str, ...]:
    """Return the launcher-result field names as a tuple."""
    return tuple(f.name for f in fields(LauncherResult))


__all__ = (
    # Build identity.
    "BUILD_23_IDENTITY",
    # Modes.
    "MODE_PRIVATE_SUPERVISED",
    "SUPPORTED_MODES",
    "is_supported_mode",
    # Actions.
    "ACTION_PREFLIGHT_ONLY",
    "ACTION_DRY_RUN",
    "ACTION_LIVE",
    "SUPPORTED_ACTIONS",
    "is_supported_action",
    # Post-send.
    "POST_SEND_STOP",
    "SUPPORTED_POST_SEND",
    "is_supported_post_send",
    # Env pointer + handoff flags.
    "SUPERVISOR_COMMAND_ENV",
    "HANDOFF_MODE_FLAG",
    "HANDOFF_ACTION_FLAG",
    "HANDOFF_BASELINE_FLAG",
    "HANDOFF_POST_SEND_FLAG",
    # Safety denylists.
    "FORBIDDEN_ROUTING_TOKENS",
    "FORBIDDEN_HANDOFF_FLAGS",
    # Outcomes + exit codes.
    "OUTCOME_SAFE_NOOP",
    "OUTCOME_INVOKED_SUPERVISOR",
    "OUTCOME_REFUSED_INVALID_MODE",
    "OUTCOME_REFUSED_INVALID_ACTION",
    "OUTCOME_REFUSED_INVALID_POST_SEND",
    "OUTCOME_REFUSED_MALFORMED_BASELINE",
    "OUTCOME_REFUSED_SUPERVISOR_NOT_CONFIGURED",
    "OUTCOME_REFUSED_UNSAFE_HANDOFF",
    "OUTCOME_REFUSED_SUPERVISOR_INVOCATION_FAILED",
    "SUPPORTED_OUTCOMES",
    "is_launch_outcome",
    "EXIT_OK",
    "EXIT_REFUSED",
    # Baseline triple.
    "BASELINE_SHA256_HEX_LEN",
    "BaselineTriple",
    "parse_baseline_triple",
    "baseline_passthrough",
    "redacted_baseline",
    # Result.
    "LauncherResult",
    # Field-name helpers.
    "baseline_triple_field_names",
    "launcher_result_field_names",
)
