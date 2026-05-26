"""Stage 29.5.3 side-channel artifact writer.

Append-only JSONL writer the Stage 29.5.3 soak pass-entrypoint
wrapper uses to persist one observation line per pass into a
single locked basename (``stage29_5_3_migration_context.jsonl``)
under the operator-supplied soak output directory.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched.
  * No network. No HTTP. No gRPC. No WebSocket. No socket.
  * Stdlib only (``json`` / ``pathlib`` / ``typing``).
  * No top-level Call (no implicit I/O at import time).
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-26 import. No Stage 28 import. No Stage 29.3 /
    Stage 29.4 orchestrator import.
  * No Discord / Telegram / X / social / webhook / Helius /
    Chainstack / Birdeye / Dexscreener / Pump.fun reference.

Artifact shape:

  Each line is a single JSON object encoded with sorted keys +
  no extra whitespace + an LF terminator. The encoding is
  deterministic: same observation -> byte-equal line. The line
  carries only closed-set tokens, the safe-shape candidate base
  mint echo, the safe-shape ATH-verified echo, the warning code
  tuple (as a JSON array), and the locked
  ``filter_enforcement_status`` / ``redaction_status`` /
  ``schema_version`` axes.

  No webhook URL, RPC endpoint, API key, bearer token, auth
  header, raw provider payload, or raw exception string is ever
  carried.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from PHX2.stage29.stage29_5_3_wrapped_pass_models import (
    STAGE29_5_3_OBSERVATION_FIELD_NAMES,
    Stage29_5_3SideChannelArtifactError,
    Stage29_5_3WrappedPassObservation,
)


# ---------------------------------------------------------------------------
# Stage 29.5.3 locked side-channel artifact basename
# ---------------------------------------------------------------------------


STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME: str = (
    "stage29_5_3_migration_context.jsonl"
)


# ---------------------------------------------------------------------------
# Projection helpers
# ---------------------------------------------------------------------------


def observation_to_dict(
    observation: Stage29_5_3WrappedPassObservation,
) -> Dict[str, Any]:
    """Project a Stage 29.5.3 wrapped-pass observation into a
    deterministic-shape dict suitable for canonical JSON
    encoding.

    The projection echoes the dataclass fields in a closed-set
    field-name order pinned by
    :data:`STAGE29_5_3_OBSERVATION_FIELD_NAMES`. The
    ``warnings_echoed`` tuple is projected into a JSON-friendly
    ``list``; every other field flows through unchanged.

    Raises :class:`Stage29_5_3SideChannelArtifactError` when
    ``observation`` is not a
    :class:`Stage29_5_3WrappedPassObservation`.
    """
    if not isinstance(
        observation, Stage29_5_3WrappedPassObservation,
    ):
        raise Stage29_5_3SideChannelArtifactError(
            "OBSERVATION_NOT_STAGE29_5_3_WRAPPED_PASS_OBSERVATION",
        )
    projected: Dict[str, Any] = {}
    for name in STAGE29_5_3_OBSERVATION_FIELD_NAMES:
        value = getattr(observation, name)
        if name == "warnings_echoed":
            projected[name] = list(value)
        else:
            projected[name] = value
    return projected


def encode_observation_jsonl_line(
    observation: Stage29_5_3WrappedPassObservation,
) -> str:
    """Encode ``observation`` as a single JSONL line (one JSON
    object terminated with ``\\n``).

    Deterministic: ``json.dumps(..., sort_keys=True,
    separators=(',', ':'), ensure_ascii=False)`` + an LF byte.
    """
    projected = observation_to_dict(observation)
    return (
        json.dumps(
            projected,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    )


# ---------------------------------------------------------------------------
# Append-only JSONL writer
# ---------------------------------------------------------------------------


def append_stage29_5_3_migration_context_observation(
    *,
    soak_output_dir: Path,
    observation: Stage29_5_3WrappedPassObservation,
) -> Path:
    """Append one Stage 29.5.3 observation JSONL line to the
    locked side-channel artifact under ``soak_output_dir``.

    Returns the absolute path to the JSONL file. Raises
    :class:`Stage29_5_3SideChannelArtifactError` on caller-shape
    failures (non-Path ``soak_output_dir``, non-observation
    ``observation``, missing directory). Lets :class:`OSError`
    propagate from the underlying file open / write so the
    wrapper's outer ``except (OSError, ...)`` swallow path can
    capture write-time failures distinctly from caller-shape
    failures.
    """
    if not isinstance(soak_output_dir, Path):
        raise Stage29_5_3SideChannelArtifactError(
            "SOAK_OUTPUT_DIR_NOT_PATH",
        )
    if not isinstance(
        observation, Stage29_5_3WrappedPassObservation,
    ):
        raise Stage29_5_3SideChannelArtifactError(
            "OBSERVATION_NOT_STAGE29_5_3_WRAPPED_PASS_OBSERVATION",
        )
    if not soak_output_dir.exists():
        raise Stage29_5_3SideChannelArtifactError(
            "SOAK_OUTPUT_DIR_DOES_NOT_EXIST",
        )
    if not soak_output_dir.is_dir():
        raise Stage29_5_3SideChannelArtifactError(
            "SOAK_OUTPUT_DIR_NOT_A_DIRECTORY",
        )
    target = (
        soak_output_dir
        / STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME
    )
    line = encode_observation_jsonl_line(observation)
    with target.open("a", encoding="utf-8", newline="") as fh:
        fh.write(line)
    return target


__all__ = (
    "STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME",
    "observation_to_dict",
    "encode_observation_jsonl_line",
    "append_stage29_5_3_migration_context_observation",
)
