"""PHX2 Stage 14 offline historical shadow-policy replay package.

Stage 14 is an offline, artifact-only consumer of Stage 13's
recommendation outputs and Stage 12's per-decision long CSV. It
translates safe Stage 13 ADVANCE_AS_CANDIDATE rows into a draft set of
shadow BLOCK rules, replays them against historical alert decisions,
and writes a run directory of replay diagnostics so a human reviewer
(Stage 15) can audit what would have changed.

Stage 14 substrate locks:
  * Opens no DB connection. Reads only Stage 12 and Stage 13 filesystem
    artifacts.
  * Writes nothing to substrate, runtime, analysis tables, or any path
    outside the Stage 14 run directory.
  * Performs no network I/O, no Discord/Telegram/gRPC/websocket/API
    calls.
  * Does not mutate live config or thresholds, does not change alert
    behavior, does not score or run ML.
  * Emits no crossed/compound rules; the only allowed simulated action
    in v0 is SIMULATED_BLOCK.
  * Does not mutate Stage 12 or Stage 13 artifacts; output is confined
    to ``<output-root>/<UTC_timestamp>/``.
  * Manifest hardcodes ``safe_for_live_policy_consumption=false`` and
    shadow_policy_rules.json hardcodes ``runtime_consumable=false``.
  * Stage 14 reports what would have changed and highlights risk. It
    does NOT classify a rule or policy as good or bad. Human approval
    belongs in Stage 15; any hard-block promotion is Stage 16+.

The CLI entry point is ``PHX2.stage14.cli``. The pure orchestrator is
``PHX2.stage14.pipeline.run``.
"""
