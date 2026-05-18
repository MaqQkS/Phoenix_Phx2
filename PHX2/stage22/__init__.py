"""PHX2 Stage 22 -- bounded live ingestion hardening (foundation only at 22.1).

Stage 22 sits beside Stage 21's first private live ping path and
hardens the ingest seam Stage 21 stopped short of. Stage 22.1 --
this commit -- ships only the *contracts and models* for that
hardening pass; no runtime behavior is introduced here.

What 22.1 ships:

  * The Stage 22 subtree (``PHX2/stage22/``, ``PHX2/tests/stage22/``).
  * Locked Stage 22 version axes and closed-set token vocabularies
    for: provider failure labels, status classes, upstream error
    types, malformed event reasons, retry decisions, dedupe
    outcomes, and ingest runner outcomes.
  * Module-local ``Stage22ContractError`` hierarchy rooted at
    plain ``Exception``. Stage 22.1 does NOT extend the Stage 21
    closed E2100/W2100 code registry and does NOT activate the
    reserved Stage 21 ``E2140`` / ``E2141`` ledger codes.
  * Typed ``NamedTuple`` records: ``ProviderFetchOutcome``,
    ``ProviderFailureRecord``, ``MalformedEventRecord``,
    ``IngestEventKey``, ``IngestEventEnvelope``, ``DedupeOutcome``,
    ``RetryCap``, ``RetryDecision``, ``Stage22IngestResult``.
  * Fakeable ``Protocol`` contracts: ``DedupeLedger`` (with
    ``check_and_record`` + ``mark_dispatched``) and
    ``RawCaptureWriter`` (with ``capture`` / ``capture_malformed``
    / ``capture_provider_failure``).
  * Pure ``classify_failure`` mapping
    ``(status_class, upstream_error_type)`` to a closed-set
    ``PROVIDER_FAILURE_LABELS`` token.

What 22.1 deliberately does NOT ship (each is reserved for a
later Stage 22 sub-stage or a strictly later stage):

  * any JSONL writer (capture or dedupe ledger)
  * any in-memory or SQLite dedupe ledger implementation
  * any raw capture writer implementation
  * any bounded ingest runner / scheduler / daemon / orchestrator
  * any retry execution / backoff sleep / reconnect behaviour
  * any real provider/transport/network client construction
  * any CLI surface / scratch script / ``__main__`` entrypoint
  * any modification to Stage 21 production or test files
  * any filter / Ante / holder / wallet / ATH / X / Telegram /
    monetization concern (those are Stage 23+ territory)

Hard import-boundary policy (enforced by the Stage 22 boundary
tests in ``PHX2/tests/stage22/``):

  * Stage 22 production code MUST NOT import ``phoenix1`` or any
    submodule.
  * Stage 22 production code MUST NOT import any of
    ``PHX2.stage17``, ``PHX2.stage18``, ``PHX2.stage19``,
    ``PHX2.stage20``.
  * Stage 22 production code MUST NOT import any PHX2 runtime
    layer (``PHX2.db``, ``PHX2.repositories``, ``PHX2.config``,
    ``PHX2.models``, ``PHX2.services``, ``PHX2.dispatch``, ...).
  * Stage 22 production code MUST NOT import the Stage 21
    fake-path modules (``fake_provider``, ``fake_transport``,
    ``live_path_simulator``), the Stage 21.3B Helius adapter, the
    Stage 21.3C Discord private transport, the Stage 21.4 private
    smoke runner, the Stage 21 env-read seam (``config``), or the
    Stage 21.3A live-readiness boundary.
  * Stage 22 production code MUST NOT import any network / RPC /
    messaging / DB / scheduler / secrets-management library.
  * Stage 22 production code MUST NOT read ``os.environ`` /
    ``os.getenv``. Stage 22.1 has NO env-reading module; the
    future Stage 22 runner will receive a typed config snapshot
    from a separately-defined seam.
  * Stage 22 production code MUST NOT introduce any non-private
    routing token. The locked Stage 22 forbidden-routing tuple
    lives in ``PHX2/stage22/constants.py``; the test in
    ``test_no_public_routing.py`` asserts absence.

Stage 22.1 emits no live behavior. Every record in this stage is
a typed, deterministic, secret-safe in-memory shape that future
Stage 22 sub-stages (and the eventual bounded runner) MUST
satisfy.
"""

from __future__ import annotations
