"""Stage 30.7.4 ATH context bridge closure-audit + handoff manifest.

Constants-only closure manifest. Pins the Stage 30.7.4 closure inventory
(the closure-audit doc basename, the handoff doc basename, this manifest
basename, and the four Stage 30.7.4 test basenames), the Stage 30.7
commit chain (the four 30.7.0..30.7.3 SHAs) plus the required parent /
current HEAD the closure builds on, the final compact proof line, the
final Stage 30.7 data path, the forbidden surfaces the closure slice
must not touch, and the next recommended stage.

Stage 30.7.4 is a CLOSURE AUDIT + HANDOFF slice, NOT a feature
implementation. It ships exactly two markdown documents + this
constants-only manifest + four test modules, and it widens exactly two
inventory-pin allowlists to admit those files. Stage 30.7.4 adds ZERO
runtime production code, edits NO renderer / compact models /
orchestrator, performs NO live provider call, NO Discord send, NO env
read, NO database migration, NO filesystem writer, NO zstd, NO
drawdown / tier recomputation, NO enforcement / public routing /
trading / wallet / social, imports NO Stage 25 / 27 / 28 / 29 (or Stage
29.5) production module, and performs NO commit / tag / push. Stage
30.7.4 does NOT begin Stage 30.8.

This manifest module is constants-only:

  * imports stdlib (``typing``) only,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no function / class definition,
  * contains no Call node (no implicit I/O at import time),
  * contains no runtime side effect.
"""

from __future__ import annotations

from typing import Tuple


# ---------------------------------------------------------------------------
# Minor version + locked closure basenames
# ---------------------------------------------------------------------------


STAGE30_7_4_MINOR_VERSION: str = "30.7.4"


STAGE30_7_4_CLOSURE_AUDIT_BASENAME: str = (
    "STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT.md"
)
STAGE30_7_4_HANDOFF_BASENAME: str = (
    "STAGE_30_7_ATH_CONTEXT_HANDOFF.md"
)
STAGE30_7_4_MANIFEST_BASENAME: str = "stage30_7_4_manifest.py"


# ---------------------------------------------------------------------------
# Stage 30.7 commit chain (the four landed substage commits)
# ---------------------------------------------------------------------------
#
# Pinned full SHAs of the four Stage 30.7 family commits. Stage 30.7.4
# (the closure slice) builds on top of the 30.7.3 commit; that SHA is
# both the last commit in the chain and the required parent / current
# HEAD for the closure slice.


STAGE30_7_0_COMMIT: str = "e5aa703cce3f3043d2ae9b35b2b8bc02be6fb09f"
STAGE30_7_1_COMMIT: str = "837a0588959f62c0e6cf059091557d43bf513b2e"
STAGE30_7_2_COMMIT: str = "ba71b6ea3efdb282d167a5760d2d31428612c04c"
STAGE30_7_3_COMMIT: str = "3d4c5bed1967c431a6001173e907dda0c528fc33"


STAGE30_7_COMMIT_CHAIN: Tuple[Tuple[str, str], ...] = (
    ("30.7.0", STAGE30_7_0_COMMIT),
    ("30.7.1", STAGE30_7_1_COMMIT),
    ("30.7.2", STAGE30_7_2_COMMIT),
    ("30.7.3", STAGE30_7_3_COMMIT),
)


# The required parent / current HEAD the Stage 30.7.4 closure builds on.
STAGE30_7_4_REQUIRED_PARENT_HEAD: str = STAGE30_7_3_COMMIT


# ---------------------------------------------------------------------------
# Final compact proof line + final data path
# ---------------------------------------------------------------------------
#
# The exact compact body state line the Stage 30.7 family produced fully
# offline (no Discord send, no live provider call). Asserted by both the
# 30.7.2 and 30.7.3 runtime-integration tests.


STAGE30_7_4_COMPACT_PROOF_LINE: str = (
    "• MC: $83k | ATH: $120k | Mig: Known"
)


# The complete Stage 30.7 ATH data path, in order.
STAGE30_7_4_FINAL_DATA_PATH: Tuple[str, ...] = (
    "sanitized ATH evidence",
    "Stage30_7AthContextEvidence",
    "project_ath_context(...)",
    "compact ATH text",
    "ath_mc_text",
    "compact ping body",
)


# ---------------------------------------------------------------------------
# Stage 30.7.4 closure inventory (docs + manifest + tests)
# ---------------------------------------------------------------------------
#
# The NEW files Stage 30.7.4 adds under ``PHX2/stage30/`` on top of the
# already-allowed Stage 30.0..30.7.3 inventory: exactly the closure-audit
# doc + the handoff doc + this manifest. No Stage 30.7.5+ file.


STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4: Tuple[str, ...] = (
    STAGE30_7_4_CLOSURE_AUDIT_BASENAME,
    STAGE30_7_4_HANDOFF_BASENAME,
    STAGE30_7_4_MANIFEST_BASENAME,
)


STAGE30_7_4_TEST_BASENAMES: Tuple[str, ...] = (
    "test_stage_30_7_4_closure_audit.py",
    "test_stage_30_7_4_handoff.py",
    "test_stage_30_7_4_boundaries.py",
    "test_stage_30_7_4_manifest.py",
)


# The only NEW production .py Stage 30.7.4 adds is this constants-only
# manifest; the two docs are markdown. The boundary test scans this
# basename for forbidden imports / needles and proves it is
# constants-only.
STAGE30_7_4_SCANNED_PRODUCTION_BASENAMES: Tuple[str, ...] = (
    STAGE30_7_4_MANIFEST_BASENAME,
)


# Every non-PHX2 import in this manifest must be in this stdlib allowlist
# (the manifest is constants-only: it needs only ``__future__`` +
# ``typing``). The closure slice has NO PHX2 production import at all.
STAGE30_7_4_ALLOWED_STDLIB_IMPORTS: Tuple[str, ...] = (
    "__future__",
    "typing",
)


# ---------------------------------------------------------------------------
# Forbidden surfaces (documentation tuple)
# ---------------------------------------------------------------------------
#
# The surfaces the Stage 30.7.4 closure slice must not touch. These are
# plain documentation words (family / feature names), NOT secret / host /
# transport needle forms; the Stage 30.7.4 boundary test scans the
# scanned production .py against the Stage 30.7.0 split-literal needle
# vocabulary (the secret / host / transport forms) and against the
# forbidden runtime-import policy, never against these bare words.


STAGE30_7_4_FORBIDDEN_SURFACES: Tuple[str, ...] = (
    "runtime production code",
    "compact renderer edit",
    "compact models edit",
    "orchestrator edit",
    "live provider call",
    "Discord send",
    "network",
    "env read",
    "database migration",
    "filesystem writer",
    "zstd",
    "drawdown recomputation",
    "tier recomputation",
    "enforcement",
    "public routing",
    "trading",
    "wallet",
    "social",
    "Stage 25/27/28/29 production import",
    "Stage 29.5 production import",
    "Stage 30.7.5+ file",
    "commit",
    "tag",
    "push",
)


# ---------------------------------------------------------------------------
# Next recommended stage
# ---------------------------------------------------------------------------


STAGE30_7_4_NEXT_RECOMMENDED_STAGE: str = "30.8"
STAGE30_7_4_NEXT_RECOMMENDED_STAGE_TITLE: str = (
    "compact session artifact / storage readiness for 24/7 collection"
)


__all__ = (
    # Version + closure basenames.
    "STAGE30_7_4_MINOR_VERSION",
    "STAGE30_7_4_CLOSURE_AUDIT_BASENAME",
    "STAGE30_7_4_HANDOFF_BASENAME",
    "STAGE30_7_4_MANIFEST_BASENAME",
    # Commit chain + required parent HEAD.
    "STAGE30_7_0_COMMIT",
    "STAGE30_7_1_COMMIT",
    "STAGE30_7_2_COMMIT",
    "STAGE30_7_3_COMMIT",
    "STAGE30_7_COMMIT_CHAIN",
    "STAGE30_7_4_REQUIRED_PARENT_HEAD",
    # Final proof line + data path.
    "STAGE30_7_4_COMPACT_PROOF_LINE",
    "STAGE30_7_4_FINAL_DATA_PATH",
    # Closure inventory.
    "STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4",
    "STAGE30_7_4_TEST_BASENAMES",
    "STAGE30_7_4_SCANNED_PRODUCTION_BASENAMES",
    "STAGE30_7_4_ALLOWED_STDLIB_IMPORTS",
    # Forbidden surfaces + next stage.
    "STAGE30_7_4_FORBIDDEN_SURFACES",
    "STAGE30_7_4_NEXT_RECOMMENDED_STAGE",
    "STAGE30_7_4_NEXT_RECOMMENDED_STAGE_TITLE",
)
