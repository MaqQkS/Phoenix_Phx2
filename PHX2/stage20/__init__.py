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

20.1 scope (this commit-scope only):

  * Locked types (NamedTuple shapes for PreviewCandidate,
    DecisionStep, FilterResult, RunManifest)
  * Locked constants (version strings, eligibility state enum,
    label-to-state mapping, error and warning code enums)
  * Input validators (E2001, E2002, E2003 active; E2004 deferred;
    E2005..E2010, E2022; W2001, W2004, W2005)
  * Injectable clock helper

20.1 deliberately does NOT write any artifact, build any
preview candidate, run any filter, or do anything Stage 21
related. Those scopes belong to 20.2, 20.3, and 20.4.
"""

from __future__ import annotations
