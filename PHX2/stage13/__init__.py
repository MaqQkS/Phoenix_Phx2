"""PHX2 Stage 13 policy_recommendation_builder package.

Stage 13 is an offline, evidence-only consumer of Stage 12's
run-directory artifacts. It reads four cohort CSVs plus the Stage 12
manifest, classifies each cohort into action/evidence/direction
buckets, and emits a sibling Stage 13 run directory of policy-review
artifacts.

L1-L14 substrate locks (see Stage 13 Locked Design Spec):
  * Opens no DB connection. Reads only Stage 12 filesystem artifacts.
  * Writes nothing to substrate, runtime, or analysis tables. Stage 13
    has zero DB connections in its call graph.
  * Does not recompute Stage 12's joins or import PHX2.analysis runtime
    modules.
  * Performs no network I/O.
  * Emits no specific threshold values. Direction + cohort identity only.
  * Emits no crossed-feature rules. Single-axis cohorts only.
  * Caps loosen-direction findings at HOLD_OBSERVE_ONLY.
  * Hardcodes safe_for_live_policy_consumption=false in manifest.

The CLI entry point is ``PHX2.stage13.cli``. The pure orchestrator is
``PHX2.stage13.pipeline.run``.
"""
