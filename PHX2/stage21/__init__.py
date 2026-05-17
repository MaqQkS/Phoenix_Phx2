"""PHX2 Stage 21 -- first private live ping path (foundation only at 21.1).

Stage 21 is the first PHX2 stage that exists on the live-capable
side of the fence. Stage 21.1 -- this commit -- builds only the
foundation for that path; no real provider call, no real Discord/TG
send, no orchestrator, no runner, no alert-decisions polling loop,
and no dedupe/retry machinery are implemented here. Those belong to
later Stage 21 sub-stages and to Stage 22.

What 21.1 ships:

  * The Stage 21 subtree (PHX2/stage21/, PHX2/tests/stage21/).
  * Locked Stage 21 version constants, private-preview marker
    constants, and the locked-default ``SAFE_FOR_PUBLIC_DISPATCH``
    invariant (literal Python ``False``).
  * Closed Stage 21 error / warning code registry in the
    ``E2100..E2199`` / ``W2100..W2199`` range. No reuse of any
    Stage 7..20 code is allowed.
  * Injectable UTC clock helper (``Clock`` / ``SystemClock`` /
    ``FrozenClock``) mirroring the Stage 20 convention. No module
    outside ``PHX2/stage21/clock.py`` is permitted to call
    ``datetime.utcnow()`` or ``datetime.now(timezone.utc)``.
  * A single env-read chokepoint (``PHX2/stage21/config.py``).
    Every other Stage 21 module receives typed config /
    ``SecretRef`` / ``CredentialAttestation`` objects. The
    Stage 20 closure handoff (Section G) forbids reading any
    environment variable that contains an API key or webhook URL
    from inside the live preview path itself; 21.1 honors that by
    routing all reads through this one module and exposing only
    fingerprinted / redacted views of secret values to the rest
    of the stage.
  * Secret redaction / fingerprinting helpers. Webhook URLs are
    treated as secret-class. Values themselves never appear in
    ``repr``, ``str``, logs, manifests, telemetry, errors, exception
    messages, snapshots, fixtures, or committed artifacts.
  * Typed credential attestation records (presence /
    optional length / sha256[:12] fingerprint; never the value).
  * Typed allowlist parser / model with fail-closed semantics for
    the empty-allowlist case. No dispatch behavior is implemented
    in 21.1.
  * Fakeable provider and transport contracts. The concrete live
    adapter and the concrete live transport are NOT implemented in
    21.1. Tests construct fake implementations directly against
    the contracts without importing any network library.
  * Core Stage 21 typed records (run id metadata,
    ``ProviderMode``, ``SinkMode``, ``PrivatePreviewMarker``).
  * Skeleton telemetry models / artifact writers used by later
    sub-stages.

What 21.1 deliberately does NOT ship (each is reserved for a later
Stage 21 sub-stage or Stage 22+):

  * any concrete provider adapter
  * any concrete private-preview transport sender
  * a ping payload builder
  * a Stage 20 alert-eligibility read seam
  * a candidate-to-ping mapper
  * a live runner / orchestrator / health-check ping
  * a dedupe / retry / backoff / provider-failover system
  * any non-private routing concept

Hard import-boundary policy (enforced by the Stage 21 boundary
tests in ``PHX2/tests/stage21/``):

  * Stage 21 production code MUST NOT import ``phoenix1`` or any
    submodule (Phoenix1 isolation, locked at Stage 20 closure).
  * Stage 21 production code MUST NOT import any of
    ``PHX2.stage17``, ``PHX2.stage18``, ``PHX2.stage19``, or
    ``PHX2.stage20`` (runtime). Upstream constants are
    re-declared locally where needed, mirroring the Stage 18
    -> Stage 19 -> Stage 20 duplication discipline.
  * Stage 21 production code MUST NOT reference the Phoenix1
    sqlite filename or any Phoenix1 DB path.
  * Stage 21 production code MUST NOT introduce any non-private
    routing token. The locked forbidden-token tuple lives in
    ``PHX2/stage21/constants.py``; the test in
    ``test_no_public_routing.py`` asserts absence.

Stage 21.1 emits no live behavior. The literal Python ``False``
value of ``SAFE_FOR_PUBLIC_DISPATCH`` is the dispatch-side analog
of Stage 20's ``SAFE_FOR_LIVE_DISPATCH``; both gates remain ``False``
in source until the operator explicitly flips them in a future
sub-stage with its own design lock.
"""

from __future__ import annotations
