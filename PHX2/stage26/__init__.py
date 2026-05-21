"""PHX2 Stage 26 -- observe-only calibration / candidate-policy stage (spec-lock only at 26.0).

Stage 26 is the first PHX2 stage that consumes the deterministic,
redacted, hashed measurement evidence Stage 25 emits and projects it
into calibration surfaces and candidate (observe-only) policy
artifacts. Stage 26 is a calibration / candidate-policy layer; it is
NOT a new measurement layer. The measurement truth Stage 25 records
is the Stage 26 input contract, not a re-derivable side artifact.

Stage 26 NEVER blocks, gates, routes, dispatches, monetizes, opens a
database connection, opens a network socket, runs a live process,
mutates a Stage 25 artifact, or rewrites a Stage 25 measurement
status token. Every Stage 26 output is observe-only candidate
evidence for operator review until an explicit, later stage wires
approved candidates into enforcement.

What 26.0 ships:

  * The Stage 26 subtree scaffold (``PHX2/stage26/__init__.py``).
  * The Stage 26.0 spec-lock document
    (``PHX2/stage26/STAGE_26_0_SPEC_LOCK.md``) recording the locked
    sub-stage order, the locked 26.1 charter, the Stage 25 artifact
    requirements, the Stage 25 schema whitelist decision, the
    closed-set / deferred-status decision, the measurement-truth
    preservation rules, the forbidden boundaries, the corrected
    Stage 27+ roadmap, and the explicit statement that Stage 26.1
    implementation remains blocked until the ``stage-25-closed`` tag
    is created with explicit operator authorization.

What 26.0 deliberately does NOT ship:

  * any Stage 25 artifact reader -- reserved for Stage 26.1.
  * any calibration input contract record -- reserved for
    Stage 26.1.
  * any denominator / outcome-eligibility semantics -- reserved for
    Stage 26.2.
  * any calibration cohort builder -- reserved for Stage 26.3.
  * any threshold candidate generator -- reserved for Stage 26.4.
  * any observe-only policy candidate artifact -- reserved for
    Stage 26.5.
  * any operator review packet -- reserved for Stage 26.6.
  * any closure audit / Stage 27 handoff -- reserved for Stage 26.7.
  * any runner, writer, CLI, or live entrypoint.
  * any enforcement / dispatch / routing / Discord / Telegram /
    public / subscriber / X / social surface.
  * any reopening of the Stage 24 Axiom / global-fee / execution-fee
    decoder.

Hard import-boundary policy (to be enforced by Stage 26.1+ boundary
tests in ``PHX2/tests/stage26/``):

  * Stage 26 production code MUST NOT import Stage 21, Stage 22,
    Stage 23, or Stage 24 production modules.
  * Stage 26 production code MUST NOT import Stage 25 production
    code outside the locked schema/vocabulary whitelist
    (``PHX2.stage25.constants`` only).
  * Stage 26 production code MUST NOT import Stage 25 record
    classes, models, readers, writers, runners, builders, or
    measurement / reconciliation logic.
  * Stage 26 production code MUST NOT import any PHX2 runtime
    layer (``PHX2.db``, ``PHX2.repositories``, ``PHX2.config``,
    ``PHX2.models``, ``PHX2.services``, ``PHX2.dispatch``,
    ``PHX2.filters``, ``PHX2.integrations``, ``PHX2.renderers``,
    ``PHX2.scripts``, ``PHX2.analysis``).
  * Stage 26 production code MUST NOT import any network / RPC /
    messaging / DB / scheduler / secrets-management library.
  * Stage 26 production code MUST NOT read ``os.environ`` or
    ``os.getenv``.
  * Stage 26 production code MUST NOT contain a CLI entrypoint or
    ``__name__ == "__main__"`` guard.
  * Stage 26 production code MUST NOT perform top-level
    (import-time) file I/O.
  * Stage 26 production code MUST NOT mutate any Stage 25 artifact
    file.

26.0 is a spec-lock-only stage: no Stage 26 production logic ships
at this stage and no Stage 26 runtime symbols are exported here.
"""

from __future__ import annotations
