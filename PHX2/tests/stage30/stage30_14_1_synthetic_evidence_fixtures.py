"""Stage 30.14.1 synthetic Build 26.1 capture-evidence JSONL fixture builders.

TEST-ONLY. Pure builders that emit SYNTHETIC ``build26_capture_evidence.jsonl`` line objects
(dicts) carrying the locked 15-field Build 26.1 schema, plus helpers to render them as JSONL
text and write them to a pytest ``tmp_path``. This file lives OUTSIDE the Stage 30.14.1
production inventory and concentrates the synthetic ``SYNTHETIC_TEST_ONLY`` source token in
one auditable place so the production loader / verifier / models / manifest sources stay free
of it (mirrors the Stage 29.5.2 synthetic-fixtures discipline).

No real Build 26.1B artifact is ever copied into the repo; these are fabricated fixtures
only. Default axes are coherent with the committed Stage 30.11.13 proof constants (anchor /
observed-at) so a default record also DISPATCHES through the committed Stage 30.14.0 chain in
the replay-verifier test.

Discipline: pure functions; the only filesystem surface is ``write_jsonl`` (a test helper
writing to a caller-supplied ``tmp_path`` -- this module is never scanned as a production
module). Imports stdlib (``json`` / ``pathlib`` / ``typing``) + the Stage 30.14.1 models leaf
only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from PHX2.stage30.stage30_14_1_evidence_artifact_models import (
    BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION,
    build_expected_source_ref,
)


# ---------------------------------------------------------------------------
# Canonical synthetic axes (clearly fabricated; base58-safe; pump-suffix mints)
# ---------------------------------------------------------------------------


# 44-char base58 mints ending in the literal ``pump`` (a fabricated stand-in; never a real
# captured mint). 15 + 25 + 4 = 44 characters.
SYNTH_PUMP_MINT: str = "Synth26Evidence" + ("A" * 25) + "pump"
SYNTH_PUMP_MINT_SECOND: str = "Synth26Evidence" + ("B" * 25) + "pump"
# A base58 mint that does NOT end in the pump suffix (for the non-pump rejection test).
SYNTH_NON_PUMP_MINT: str = "Synth26Evidence" + ("A" * 25) + "fane"

SYNTH_POOL_ACCOUNT: str = "P" * 44
SYNTH_POOL_PROGRAM_ID: str = "G" * 44
SYNTH_QUOTE_MINT: str = "Q" * 44

# Coherent with the committed Stage 30.11.13 proof anchor / created-at so a default record
# dispatches through the committed chain (the migration anchor precedes the fake ATH window).
SYNTH_MIGRATION_EVENT_TIME_UTC: str = "2026-06-06T06:14:10Z"
SYNTH_OBSERVED_AT_UTC: str = "2026-06-07T07:06:40Z"

SYNTH_MIGRATION_SLOT: int = 318000000
SYNTH_MIGRATION_SIGNATURE: str = "build26-1c-synth-sig"
SYNTH_MIGRATION_SIGNATURE_SECOND: str = "build26-1c-synth-sig-2"

# Closed-set Stage 29.5 source tokens. The bare synthetic literal is confined to THIS
# test-only file; the default fixture uses the real HELIUS_WS token so it loads through the
# SAME path a real Build 26.1B artifact would.
SYNTH_SOURCE_HELIUS_WS: str = "HELIUS_WS"
SYNTH_SOURCE_SYNTHETIC_TEST_ONLY: str = "SYNTHETIC_TEST_ONLY"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_valid_evidence_obj(
    *,
    token_mint: str = SYNTH_PUMP_MINT,
    migration_source: str = SYNTH_SOURCE_HELIUS_WS,
    pool_account: str = SYNTH_POOL_ACCOUNT,
    pool_program_id: str = SYNTH_POOL_PROGRAM_ID,
    quote_mint: str = SYNTH_QUOTE_MINT,
    migration_event_time_utc: str = SYNTH_MIGRATION_EVENT_TIME_UTC,
    migration_slot: int = SYNTH_MIGRATION_SLOT,
    migration_signature: str = SYNTH_MIGRATION_SIGNATURE,
    observed_at_utc: str = SYNTH_OBSERVED_AT_UTC,
) -> Dict[str, Any]:
    """Return a VALID synthetic Build 26.1 capture-evidence line object (all 15 fields).

    ``source_ref`` is built from ``migration_signature`` + ``migration_slot`` so it always
    matches the loader's expected ``helius:sig:<sig>:slot:<slot>`` form; ``measurement_status
    = COMPLETE``, ``redaction_status = SAFE``, ``warnings = []`` (a proven complete
    migration). Caller overrides any axis to craft a rejection fixture.
    """
    return {
        "schema_version": BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION,
        "token_mint": token_mint,
        "migration_status": "PRESENT",
        "migration_source": migration_source,
        "pool_account": pool_account,
        "pool_program_id": pool_program_id,
        "quote_mint": quote_mint,
        "migration_event_time_utc": migration_event_time_utc,
        "migration_slot": migration_slot,
        "migration_signature": migration_signature,
        "source_ref": build_expected_source_ref(
            migration_signature, migration_slot
        ),
        "observed_at_utc": observed_at_utc,
        "measurement_status": "COMPLETE",
        "redaction_status": "SAFE",
        "warnings": [],
    }


def build_second_valid_evidence_obj(**overrides: Any) -> Dict[str, Any]:
    """Return a second VALID line object with a distinct mint + signature (for multi-record
    / dedupe fixtures). Caller overrides bleed through ``build_valid_evidence_obj``.
    """
    params: Dict[str, Any] = {
        "token_mint": SYNTH_PUMP_MINT_SECOND,
        "migration_signature": SYNTH_MIGRATION_SIGNATURE_SECOND,
    }
    params.update(overrides)
    return build_valid_evidence_obj(**params)


# ---------------------------------------------------------------------------
# Render + write helpers
# ---------------------------------------------------------------------------


def render_jsonl(objs: List[Dict[str, Any]]) -> str:
    """Render a list of line objects as JSONL text (one compact JSON object per line)."""
    return "".join(json.dumps(obj) + "\n" for obj in objs)


def write_jsonl(path: object, objs: List[Dict[str, Any]]) -> Path:
    """Write the rendered JSONL to ``path`` (a test ``tmp_path`` file) and return it.

    TEST helper only -- this fixtures module is never scanned as a Stage 30.14.1 production
    module, so its write surface is intentional and out of the production boundary.
    """
    target = Path(path)
    target.write_text(render_jsonl(objs), encoding="utf-8")
    return target


def write_raw_lines(path: object, lines: List[str]) -> Path:
    """Write arbitrary raw text lines (for malformed-JSONL fixtures) and return the path."""
    target = Path(path)
    target.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return target


__all__ = (
    "SYNTH_PUMP_MINT",
    "SYNTH_PUMP_MINT_SECOND",
    "SYNTH_NON_PUMP_MINT",
    "SYNTH_POOL_ACCOUNT",
    "SYNTH_POOL_PROGRAM_ID",
    "SYNTH_QUOTE_MINT",
    "SYNTH_MIGRATION_EVENT_TIME_UTC",
    "SYNTH_OBSERVED_AT_UTC",
    "SYNTH_MIGRATION_SLOT",
    "SYNTH_MIGRATION_SIGNATURE",
    "SYNTH_MIGRATION_SIGNATURE_SECOND",
    "SYNTH_SOURCE_HELIUS_WS",
    "SYNTH_SOURCE_SYNTHETIC_TEST_ONLY",
    "build_valid_evidence_obj",
    "build_second_valid_evidence_obj",
    "render_jsonl",
    "write_jsonl",
    "write_raw_lines",
)
