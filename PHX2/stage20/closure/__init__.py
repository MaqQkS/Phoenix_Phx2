"""PHX2 Stage 20.4 -- closure audit + Stage 21 handoff layer.

Stage 20.4 is a read-only closure stage. It validates an
operator-specified Stage 20.2 + Stage 20.3 run pair (by hash,
schema, and lineage), audits the ``PHX2/stage20/`` source tree
for forbidden imports / cross-stage violations / unsafe-dispatch
tokens, and emits a deterministic eight-file closure packet to
``<output_root>/stage20_closure_runs/<run_id>/``.

What Stage 20.4 will NOT do (locked):

  * Run pytest (operator supplies test results as input).
  * Invoke git (no subprocess, no pygit2, no shell-out).
  * Create the ``stage-20-closed`` tag.
  * Touch network, env vars, ``.env``, providers, Discord,
    Telegram, or sqlite3.
  * Mutate Stage 20.2 or Stage 20.3 artifacts (read-only access
    only; opens use mode "r" / "rb").
  * Touch ``PHX2/.stage_17_inputs/``, ``PHX2/docs/``, or
    ``ROADMAP.md``.
  * Implement any Stage 21 functionality.
  * Push to remote.

Phoenix1 departure note:
  Stage 20.4 contains zero Phoenix1 imports or references in
  production paths. Phoenix1 appears only as a forbidden-module
  entry in the auditor's deny list.

Boundary discipline (mirrors the 20.1 hand-duplication
precedent):
  ``PHX2.stage20.closure`` does NOT import from
  ``PHX2.stage20`` outside of constants and types it redeclares
  locally in ``PHX2.stage20.closure.constants`` and
  ``PHX2.stage20.closure.models``. The local clock helper is
  ``PHX2.stage20.closure.clock_helper``; the wider
  ``PHX2.stage20.clock`` module is intentionally NOT imported.

Known limitations (v0):

  * Operator must supply both ``run1`` and ``run2`` test result
    blocks; a single-run mode is reserved (W2020) but not
    implemented.
  * Closure does not run pytest; the test results carried in
    ``operator_test_results`` are a consistency-validated
    snapshot only.
  * The annotated tag ``stage-20-closed`` is recommended in
    the handoff doc as a MANUAL operator step. Stage 20.4 will
    not create the tag itself.
"""

from __future__ import annotations
