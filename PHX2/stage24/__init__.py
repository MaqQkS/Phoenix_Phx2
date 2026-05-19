"""PHX2 Stage 24 -- observe-only execution-fee and execution-quality primitives (foundation only at 24.1).

Stage 24 is the first PHX2 execution-primitive stage after the
Stage 23 observe-only filter closure. Stage 24 decodes per-
transaction evidence (compute budget, priority fee, Jito tip,
router / global-fee, execution quality) into deterministic,
redacted, hashed primitive records on disk. Stage 24 NEVER
blocks, gates, routes, dispatches, monetizes, opens a database
connection, opens a network socket, or runs a live process. The
job of Stage 24 is to take a Stage 24-shaped transaction
observation and emit deterministic execution primitives to disk.
Nothing more.

What 24.1 ships:

  * The Stage 24 subtree (``PHX2/stage24/``,
    ``PHX2/tests/stage24/``).
  * Locked Stage 24 version axes and closed-set token
    vocabularies for: primitive families, decoder statuses,
    data statuses, confidence levels, fee sources, route
    families, instruction locations, input kinds.
  * Locked Solana program ID literals: the ComputeBudget program
    ID, the System program ID, and the active / deprecated Axiom
    router program ID tuples.
  * Module-local ``Stage24Error`` hierarchy rooted at plain
    ``Exception``.
  * Typed ``NamedTuple`` records and contract surfaces:
    ``Stage24ExecutionInput``, ``Stage24ComputeBudgetResult``,
    ``Stage24PriorityFeeResult``, ``Stage24JitoTipResult``,
    ``Stage24RouterFeeResult``, ``Stage24ExecutionQualityResult``,
    ``Stage24ExecutionPrimitive``, ``Stage24RunnerResult``,
    ``Stage24ManifestFileEntry``, ``Stage24InputManifest``,
    ``Stage24ArtifactManifest``, ``Stage24Decoder`` Protocol.
  * Deterministic canonical-JSON hash helpers
    (``compute_execution_input_hash`` / ``compute_primitive_hash``
    / ``stage24_hash``).
  * Stage 24 input reader reading Stage 24-shaped decoded-tx
    JSONL artifacts from operator-supplied paths, with typed
    Stage 24 errors and redaction discipline.
  * Manifest helpers for input + artifact provenance.

What 24.1 deliberately does NOT ship:

  * any real decoder logic -- reserved for 24.2 / 24.3 / 24.4 /
    24.5.
  * ComputeBudget program instruction decoding -- reserved for
    Stage 24.2.
  * priority-fee derivation -- reserved for Stage 24.2.
  * Jito tip decoding -- reserved for Stage 24.3.
  * Axiom router candidate scaffold -- reserved for Stage 24.4.
  * confirmed Axiom / router / global-fee decoder -- reserved
    for Stage 24.5 (conditional on sanitized fixture evidence).
  * unified runner / artifact writer / decoder coverage CSV /
    rejections JSONL -- reserved for Stage 24.6.
  * closure audit and Stage 25 handoff doc -- reserved for
    Stage 24.7.
  * any alert dispatch, Discord / Telegram routing, or live
    alert behavior.
  * any DB writes or repository mutation.
  * any network / RPC / websocket call.
  * any CLI surface or long-running runner process.
  * any modification to Stage 21 / Stage 22 / Stage 23
    production / test files.
  * any env-read / network / DB / scheduler / secrets-management
    library usage.
  * any Phoenix1 import or transcription.

Hard import-boundary policy (enforced by the Stage 24 boundary
tests in ``PHX2/tests/stage24/``):

  * Stage 24 production code MUST NOT import Stage 21, Stage 22,
    or Stage 23 production modules.
  * Stage 24 production code MUST NOT import any PHX2 runtime
    layer (``PHX2.db``, ``PHX2.repositories``, ``PHX2.config``,
    ``PHX2.models``, ``PHX2.services``, ``PHX2.dispatch``,
    ``PHX2.filters``, ``PHX2.integrations``, ``PHX2.renderers``,
    ``PHX2.scripts``, ``PHX2.analysis``).
  * Stage 24 production code MUST NOT import Birdeye /
    Dexscreener / Migration / X / social modules (Stage 25 /
    Stage 27+ vocabulary).
  * Stage 24 production code MUST NOT import Discord / Telegram
    / public-routing modules.
  * Stage 24 production code MUST NOT import any network / RPC /
    messaging / DB / scheduler / secrets-management library.
  * Stage 24 production code MUST NOT read ``os.environ`` or
    ``os.getenv``.
  * Stage 24 production code MUST NOT write to disk outside an
    operator-supplied path the caller has constructed (Stage
    24.1 ships NO writer; this is a forward-looking invariant
    for the 24.6 artifact writer).
"""

from __future__ import annotations
