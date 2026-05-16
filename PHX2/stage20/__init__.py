"""PHX2 Stage 20 -- preview eligibility from operator review ledger.

Stage 20 transforms a closed Stage 18 review packet plus a closed
Stage 19 operator review ledger into a typed preview eligibility
table, ordered decision steps, and an observe-only filter
scaffold. Stage 21 (the first real private ping path) is the
consumer; Stage 20 produces no live behavior on its own.

Stage 20 is observe-only:

  * SAFE_FOR_LIVE_DISPATCH = False is the hardcoded invariant.
  * Every Stage 20 emitter that touches a dispatch-relevant field
    is required to honor this constant; the defensive check in
    PHX2.stage20.input_validators surfaces an E2022 if it is ever
    flipped.

Stage 20 satisfies a hard import-boundary policy: forbidden from
importing PHX2.stage17, PHX2.stage18, or PHX2.stage19. Upstream
schema constants (Stage 18 review_matrix columns, Stage 19 ledger
columns, Stage 19 label vocabulary, Stage 19 manifest hash keys)
are hand-duplicated in PHX2.stage20.constants with source-path
comments. A drift in either upstream stage produces a loud
Stage 20 error (E2008 / E2009 / E2005) rather than a silent
re-aliasing.

Stage 20.1 scope (already locked):

  * Locked types (NamedTuple shapes for PreviewCandidate,
    DecisionStep, FilterResult, RunManifest).
  * Locked constants (version strings, eligibility state enum,
    label-to-state mapping, error and warning code enums).
  * Input validators (E2001, E2002, E2003 active; E2004 deferred;
    E2005..E2010, E2022; W2001, W2004, W2005).
  * Injectable clock helper.
  * 20.1 writes no artifact.

Stage 20.2 scope (built on top of 20.1):

  * Preview candidate builder
    (``PHX2.stage20.builder.build_candidate`` and
    ``PHX2.stage20.builder.build_all_candidates``):
    slice resolution, winning-row selection, label-to-state
    mapping (closed-set under
    ``LABEL_TO_STATE_MAPPING_V0``), per-candidate review-stale
    detection (W2006), multi-operator-per-slice flag.
  * 4-step decision sequence per candidate
    (``slice_resolved`` -> ``mapping_applied`` ->
    ``staleness_evaluated`` -> ``terminal``). Validates E2015,
    E2016, E2017 invariants.
  * Run orchestrator ``PHX2.stage20.runner.run_stage20_2`` drives
    ``validate_inputs``, builds candidates, validates uniqueness
    (E2011), builds and validates decision sequences (E2015 /
    E2016 / E2017), writes artifacts, assembles the manifest,
    and runs post-write reconciliation (E2023 row counts, E2025
    columns).
  * Output artifacts (per run, written into
    ``output_root/stage20_runs/<stage20_run_id>/``):
      - ``preview_candidates.csv``           (18 locked columns)
      - ``alert_eligibility_decisions.csv``  (10 locked columns)
      - ``README.md``                        (UTF-8, no BOM, no
                                              output SHA-256s)
      - ``stage20_run.log``                  (JSON Lines, 9 events)
      - ``manifest.json``                    (19 top-level keys;
                                              locks output SHA-256s,
                                              warnings, run ids)
  * Production-side determinism verifier
    ``PHX2.stage20.manifest_assembler.verify_run_determinism``
    backs E2020 by byte-comparing every artifact between two
    candidate run directories.
  * 20.2 wires error codes E2011, E2015..E2017, E2020, E2021,
    E2023..E2025 and warning codes W2002, W2006, W2007. Upstream
    W2001 / W2004 / W2005 are surfaced (not re-detected) in the
    manifest's ``warnings`` block.
  * 20.2 still emits NO live behavior; safe_for_live_dispatch
    remains the literal Python ``False`` everywhere.

Stage 20.3 (filter interface scaffolding) and beyond are out of
scope here. ``FilterResult`` is declared at 20.1 for shape
continuity; E2012 / E2013 / E2014 / W2003 stay reserved-but-
deferred until 20.3 wires them.
"""

from __future__ import annotations
