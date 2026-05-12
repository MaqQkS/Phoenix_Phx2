"""Stage 13 test-fixture helpers.

Provides ``write_stage12_run`` for building synthetic Stage 12 run
directories in tests. Stage 13 fixtures are deliberately
hand-constructed rather than spawned from Stage 12's pipeline so the
test surface remains independent of Stage 12 runtime behavior.

The fixture builders match the Stage 12 schema (per STEP 0 S0-3): the
canonical column tail, the locked tier_name values ("T1", "T2", "T3"),
and the confidence_flag value domain ("low_confidence", "caveat",
"standard").
"""
