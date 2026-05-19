"""PHX2 Stage 23 -- observe-only on-chain filter rebuild/import (foundation only at 23.1).

Stage 23 is the first clean PHX2 filter rebuild stage after the
Stage 22 ingestion-hardening close-out. Stage 23 evaluates and
labels Stage 22-shaped events, never blocks, routes, or
monetizes. The job of Stage 23 is to take Stage 22-shaped events
and emit deterministic, redacted, hashed filter evaluations to
disk. Nothing more.

What 23.1 ships:

  * The Stage 23 subtree (``PHX2/stage23/``,
    ``PHX2/tests/stage23/``).
  * Locked Stage 23 version axes and closed-set token
    vocabularies for: filter labels, data-status tokens, and
    filter families.
  * Module-local ``Stage23Error`` hierarchy rooted at plain
    ``Exception``.
  * Typed ``NamedTuple`` records and contract surfaces:
    ``Stage23FilterInput``, ``Stage23FilterResult``,
    ``Stage23FilterEvaluation``, ``Stage23InputManifest``,
    ``Stage23ArtifactManifest``, ``Stage23FilterFamily``,
    ``Stage23Filter`` Protocol.
  * Deterministic canonical-JSON hash helpers
    (``input_hash`` / ``evaluation_hash``).
  * ``Stage22InputReader`` reading Stage 22-shaped JSONL
    artifacts (``raw_capture.jsonl`` / ``dedupe.jsonl``) from
    operator-supplied paths, with typed Stage 23 errors and
    redaction discipline.
  * Manifest helpers for input + artifact provenance.

What 23.1 deliberately does NOT ship:

  * any filter logic (holder concentration, launch structure,
    wallet / source quality) -- reserved for Stage 23.2 / 23.3
    / 23.4.
  * any runner / scheduler / orchestrator.
  * any artifact writer (JSONL evaluations writer, summary CSV,
    reason-code CSV) -- reserved for Stage 23.5.
  * any alert dispatch / Discord / Telegram / public routing.
  * any enforcement / blocking / gating.
  * any ATH / migration / Birdeye / Dexscreener logic --
    reserved for Stage 25.
  * any Axiom / Jito tip / priority fee / global fee /
    compute-budget / execution-quality logic -- reserved for
    Stage 24.
  * any X API / social ranking / social intelligence logic --
    reserved for Stage 27+.
  * any modification to Stage 21 or Stage 22 production / test
    files.
  * any env-read / network / DB / scheduler / secrets-management
    library usage.
  * any CLI surface / ``__main__`` entrypoint.

Hard import-boundary policy (enforced by the Stage 23 boundary
tests in ``PHX2/tests/stage23/``):

  * Stage 23 production code MUST NOT import Stage 21 or Stage
    22 production modules.
  * Stage 23 production code MUST NOT import any PHX2 runtime
    layer (``PHX2.db``, ``PHX2.repositories``, ``PHX2.config``,
    ``PHX2.models``, ``PHX2.services``, ``PHX2.dispatch``,
    ``PHX2.filters``, ``PHX2.integrations``, ``PHX2.renderers``,
    ``PHX2.scripts``, ``PHX2.analysis``).
  * Stage 23 production code MUST NOT import Birdeye /
    Dexscreener / ATH / migration / Axiom / Jito / priority-fee
    / global-fee / execution-quality / X / social modules.
  * Stage 23 production code MUST NOT import Discord / Telegram
    / public-routing modules.
  * Stage 23 production code MUST NOT import any network / RPC
    / messaging / DB / scheduler / secrets-management library.
  * Stage 23 production code MUST NOT read ``os.environ`` /
    ``os.getenv``.
  * Stage 23 production code MUST NOT write to disk outside an
    operator-supplied path the caller has constructed (Stage
    23.1 ships NO writer; this is a forward-looking invariant
    for the 23.5 artifact writer).
"""

from __future__ import annotations
