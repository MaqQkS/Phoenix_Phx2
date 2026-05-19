# Stage 22 Closure Audit

Stage 22.6 closure / handoff document. This is the audit-side
companion to `STAGE_22_OPERATOR_RUNBOOK.md`. It records the
state of Stage 22 at the point at which the operator runbook is
handed over and freezes the criteria that must hold before a
`stage-22-closed` tag is created.

This document is intentionally documentation-only. It does NOT
introduce any new Stage 22 production code, does NOT modify any
Stage 21 module, and does NOT create the `stage-22-closed` tag.

## 1. Stage 22 scope (locked)

Stage 22 is the ingestion-hardening stage of PHX2. Its single
deliverable is a bounded, fail-isolated, dedupe-aware, one-shot
private ingest path that the operator can run locally against
live provider keys and a private recipient.

Stage 22 covers:

  * adapter-shaped, sanitized provider fetch outcomes
    (`ProviderFetchOutcome`);
  * per-event decode isolation (`handle_provider_batch`);
  * raw capture writers (in-memory and JSONL append-only);
  * a dedupe ledger contract (in-memory and JSONL writers);
  * a Stage 22 private transport Protocol with a Stage 21
    Discord adapter wrapper;
  * a bounded one-shot ingest runner that composes the above
    seam with `max_provider_attempts == 1` and optional
    `max_events` / `max_dispatches` / `stop_after_first_dispatch`
    caps.

Stage 22 explicitly does NOT cover any of the following (each
remains a forbidden token in the Stage 22 boundary scanners):

  * filters / scoring / eligibility / Ante / holder / wallet
    gating;
  * ATH / Birdeye / price / migration measurement;
  * fee execution / Jito / Axiom / global fee model;
  * X / social ingestion or routing;
  * public Discord routing, subscriber routing, paid routing;
  * Telegram of any kind;
  * a long-running daemon, scheduler, orchestrator, run loop,
    or worker;
  * a retry execution layer (the retry decision token vocabulary
    is defined in 22.1 contracts but no executor is shipped).

## 2. Sub-stage map

| Sub-stage | Commit (short) | Subject |
|-----------|---------------|---------|
| 22.1 | a7bc962 | ingestion hardening contracts |
| 22.2 | c5d27a2 | dedupe ledger boundary |
| 22.3 | e096eb4 | raw capture boundary |
| 22.4 | 409eb34 | provider failure and malformed event isolation |
| 22.5 | 21afa9b | bounded private ingest runner |
| 22.6 | (this doc) | closure audit + operator runbook |

All five preceding sub-stages are committed on local `master`.
No tag named `stage-22-*` exists yet.

## 3. Stage 21 isolation criteria

Tag baseline:

  * `stage-21-closed` peels to commit
    `67e5453d2b4e7d9f59af4bd50fbc4718de35b0cc`.

Criterion: no file under `PHX2/stage21/` has been modified
between `stage-21-closed` and the current `HEAD`.

Verification: `git diff --stat stage-21-closed..HEAD -- PHX2/stage21/`
returns an empty diff. The only files changed since the Stage 21
tag are additions in `PHX2/stage22/` and `PHX2/tests/stage22/`.

Result: PASS.

## 4. Stage 22 production tree

Tracked Stage 22 production files (10 modules):

  * `PHX2/stage22/__init__.py`
  * `PHX2/stage22/constants.py`
  * `PHX2/stage22/errors.py`
  * `PHX2/stage22/ingest_contracts.py`
  * `PHX2/stage22/failure_classification.py`
  * `PHX2/stage22/dedupe_ledger.py`
  * `PHX2/stage22/raw_capture.py`
  * `PHX2/stage22/failure_handling.py`
  * `PHX2/stage22/bounded_live_runner.py`
  * `PHX2/stage22/live_composition.py`

## 5. Live wiring seam isolation

Criterion: `PHX2/stage22/live_composition.py` is the SINGLE
Stage 22 production module that imports any Stage 21 runtime
module (the Helius adapter, the live-readiness boundary, the
provider event decoder, the Discord private transport, the
transport contracts module).

Verification: `PHX2/stage22/ingest_contracts.py` imports the
typed record `NormalizedLiveEvent` from
`PHX2.stage21.normalized_events`. This is a typed-record
re-export only; the imported name is a `NamedTuple` shape, not
a runtime collaborator. No other Stage 22 module imports any
Stage 21 module.

`PHX2/stage22/bounded_live_runner.py` imports nothing from
`PHX2.stage21`. The bounded runner's locked import allowlist is
asserted by `test_stage_22_5_boundaries.py::
test_bounded_live_runner_imports_are_within_locked_allowlist`.

Result: PASS.

## 6. Environment / I/O / clock / network surface

Criterion: no Stage 22 production module reads `os.environ` or
`os.getenv`, opens a network socket, performs file I/O on
import, or imports a clock / sleep / async / HTTP / DB module.

Verification: enforced per file by the Stage 22 boundary tests
(`test_stage_22_1_boundaries.py` through
`test_stage_22_5_boundaries.py`) and by
`test_env_read_boundaries.py`. The bounded runner has the
strictest allowlist; the live composition module is allowed
to import the Stage 21 live-readiness loader (which then reads
the caller-supplied env Mapping, not `os.environ`).

Result: PASS.

## 7. Routing / vocabulary boundary

Criterion: no Stage 22 production source contains an
identifier or string literal that names a forbidden routing
sink or wrong-stage concern: `telegram`, `axiom`, `jito`,
`scheduler`, `daemon`, `orchestrator`, `run_loop`, `worker`,
`eligibility`. Note: identifier-position uses of
`scheduler` / `daemon` / `worker` etc. are forbidden; the words
may appear inside docstrings only when describing what Stage 22
deliberately does NOT do.

Verification: `STAGE22_FORBIDDEN_VOCABULARY` in
`PHX2/stage22/constants.py`, asserted across every Stage 22
production module by the rolling boundary tests.

Result: PASS.

## 8. Secret-shape boundary

Criterion: no Stage 22 production source declares a
NamedTuple field with a secret-bearing name (`api_key`,
`webhook_url`, `rpc_url`, `raw_response_body`,
`exception_message`, `exception_repr`, `headers`,
`authorization`, `bearer`, `password`, `secret`, `credential`,
`private_key`, etc.); no Stage 22 production source contains
a URL-scheme literal, a Discord webhook host literal, or a
long hex / long base64 run.

Verification: enforced by `test_no_secret_leaks.py`.

Result: PASS.

## 9. Public-routing boundary

Criterion: no Stage 22 production source contains identifier or
string-literal references to public, subscriber, or paid
routing surfaces. The Stage 22 private transport contract is
the only dispatch seam in Stage 22.

Verification: enforced by `test_no_public_routing.py`.

Result: PASS.

## 10. Pre-existing untracked paths

The repository carried three pre-existing untracked paths at
the start of Stage 22 work:

  * `PHX2/.stage_17_inputs/`
  * `PHX2/docs/`
  * `ROADMAP.md`

Stage 22.1 through 22.5 did not touch, stage, commit, delete,
or move these paths. Stage 22.6 also does not touch them.

Verification: `git status --short` continues to show these
three entries as untracked alongside any new Stage 22.6 doc /
test files. None of the three appears in any Stage 22 commit
or in the Stage 22.6 working tree changes.

Result: PASS.

## 11. Test suite snapshot

Final reproduced Stage 22.6 counts (the closure numbers Codex
should compare against, including the Codex-driven fix-guard
tests added after the first audit pass):

  * Stage 22 test suite (`PHX2/tests/stage22`): **847 passed**.
  * Stage 21 test suite (`PHX2/tests/stage21`): **1032 passed**.
  * Full PHX2 suite (`PHX2/tests`): **5513 passed, 3 skipped**.
    The 3 skips are pre-existing (two require a Phoenix1
    sqlite database file under `PHX2/data/` that is absent in
    this test environment, and one Stage 10 FK-enforcement
    test is gated on a future pragma flip). None of the 3
    skips is introduced by Stage 22.6.

Pre-Stage-22.6 reference: the Stage 22 count was 812 at the
22.5 commit; Stage 22.6 adds 35 docs-only guard tests
(847 - 812 = 35). The first 22.6 audit pass shipped 28 of
those; the Codex-driven fix pass added 7 more guard tests
(3 for env-var-surface separation, 2 for the Path-vs-str
example, 2 for the path-typing notes) and finalised the
count at 847. The Stage 21 count is unchanged at 1032,
which is the closure invariant. The full PHX2 count moved
from 5506 to 5513 by the same +7 delta.

Environment notes:

  * pytest must be run with `--basetemp=PHX2/.pytest_tmp_*`
    on Windows hosts where the system temp directory has a
    restrictive ACL. The pattern is established by the
    existing `.gitignore` entry `.pytest_basetmp*/`; the
    Stage 22.6 rerun commands use the
    `PHX2/.pytest_tmp_stage22*` paths and clean them after
    the run.
  * The full PHX2 suite (5513 passed) requires `pandas` to
    collect the Stage 12 analysis tests. The project `.venv`
    used for the Stage 22.6 focused rerun is Python 3.12 and
    does not ship `pandas`; the full-suite number above was
    reproduced with the system Python 3.14 interpreter
    (`py -B -m pytest PHX2/tests`). Stage 22 and Stage 21
    suites do not require `pandas` and reproduce under both
    interpreters.

## 12. Stage 22.6 follow-up references

The Stage 22.5 Codex audit returned PASS WITH MINOR NOTES
(no required fixes). Stage 22.6 does not act on those notes
and does not change Stage 22.5 code; the minor notes remain
visible in the Codex audit trail and may be folded into a
future Stage 22.7 hygiene pass or into the Stage 23 baseline.

## 13. Pre-tag checklist

The `stage-22-closed` tag must NOT be created until ALL of the
following hold simultaneously:

  1. Stage 22 test suite: green (current snapshot: 847 passed).
  2. Stage 21 test suite: green and unchanged at 1032.
  3. `git diff --stat stage-21-closed..HEAD -- PHX2/stage21/`
     returns empty.
  4. No file in `PHX2/stage22/` contains a real provider key,
     webhook URL, recipient id, bearer token, or private key.
  5. `git status --short` shows only the three known
     pre-existing untracked paths plus the Stage 22.6
     deliverables.
  6. Operator runbook
     `PHX2/stage22/STAGE_22_OPERATOR_RUNBOOK.md` has been
     reviewed by the operator and a smoke run has been
     executed locally with bounded caps and verified to
     produce a private Discord ping plus a raw-capture and
     dedupe artifact in ignored paths.
  7. Codex closure audit on Stage 22.6 has returned PASS or
     PASS WITH MINOR NOTES.
  8. The operator has explicitly authorised the tag.

Until step 8 is reached, do not create `stage-22-closed`, do
not push the branch, and do not amend any of the 22.1 - 22.5
commits.

## 14. Stage 23 / 24 / 25 handoff

After Stage 22 closes, the next three stages are:

  * Stage 23 -- filter / eligibility / scoring layer. Operates
    on the dedupe-deduped envelope stream produced by the
    Stage 22 bounded runner; introduces the gating vocabulary
    that Stage 22 deliberately omits.
  * Stage 24 -- execution-side hardening for the fee /
    Jito / Axiom / global-fee model. No Stage 22 module is
    permitted to grow execution-side vocabulary.
  * Stage 25 -- ATH / Birdeye / migration-measurement
    hardening. Owns the price-side correctness invariants
    Stage 22 does not pretend to satisfy. The Stage 22.5
    private ping body intentionally omits all ATH / price /
    filter / fee / X / social fields; Stage 25 is the
    earliest stage at which any such field is allowed near
    a dispatch sink.

These three stages are deferred. Stage 22.6 does not begin any
of them.
