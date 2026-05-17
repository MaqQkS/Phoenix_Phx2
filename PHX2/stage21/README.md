# PHX2 Stage 21 -- First private live ping path (foundation)

Stage 21 is the first PHX2 stage that exists on the live-capable
side of the fence. **Stage 21.1** -- this commit -- builds only the
foundation. No real provider call, no real Discord/Telegram send,
no orchestrator, no runner, no `alert_decisions` polling loop, and
no dedupe/retry machinery are implemented in 21.1.

## 21.1 scope (what is in this commit)

1. Stage 21 subtree under `PHX2/stage21/` and
   `PHX2/tests/stage21/`.
2. Locked version, private-preview marker, and
   `SAFE_FOR_PUBLIC_DISPATCH` constants (hardcoded `False`).
3. Closed `E2100..E2199` / `W2100..W2199` Stage 21 code
   registry. No prior-stage code is reused.
4. Injectable UTC clock (`SystemClock`, `FrozenClock`,
   `default_clock`).
5. Single env-read chokepoint at `PHX2/stage21/config.py`.
   Every other Stage 21 module receives typed config / secret
   / attestation objects.
6. Secret redaction / fingerprinting helpers. Webhook URLs are
   secret-class. Values never appear in `repr`, `str`, logs,
   manifests, telemetry, errors, exception messages, snapshots,
   fixtures, or committed artifacts.
7. Typed credential attestation records (presence / optional
   length / `sha256[:12]` fingerprint).
8. Typed allowlist parser / model. Empty allowlist parses to a
   fail-closed model. No dispatch behavior is implemented.
9. Fakeable provider and transport contracts. The concrete live
   adapter and the concrete live transport are NOT implemented
   in 21.1.
10. Core Stage 21 typed records: `Stage21RunId`, `ProviderMode`,
    `SinkMode`, `PrivatePreviewMarker`.
11. Skeleton telemetry models + deterministic artifact writers
    that emit non-secret manifest-style payloads.

## 21.1 NON-scope (deferred to later sub-stages or Stage 22+)

- Any concrete provider adapter (Helius / gRPC / Birdeye / etc.)
- Any concrete Discord or Telegram sender
- A ping payload builder
- An `alert_decisions` read seam (Stage 21.2+)
- A candidate-to-ping mapper
- A live runner / orchestrator / health-check ping
- A dedupe / retry / backoff / provider-failover system
- Any subscriber / public / paid routing concept (forever
  forbidden in Stage 21; later stages own subscriber-side work)

## Hard rules Stage 21 inherits (locked at Stage 20 closure)

- Phoenix1 isolation. No `import phoenix1.*` anywhere in Stage 21.
- No reads from a live Phoenix1 database connection in Stage 21
  runtime.
- Stage 21 must not import `PHX2.stage17`, `PHX2.stage18`,
  `PHX2.stage19`, or `PHX2.stage20` (runtime).
- Stage 21 must not flip any safety flag to a true value in source.
- Stage 21 must not read any environment variable that contains
  an API key or webhook URL into the live preview path. Stage 21
  routes every such read through a single attestable boundary
  (`PHX2/stage21/config.py`) and exposes only fingerprinted views
  to the rest of the stage.

## Files in 21.1

```
PHX2/stage21/
  __init__.py
  README.md  (this file)
  constants.py
  errors.py
  clock.py
  config.py
  secret_redaction.py
  credential_attestation.py
  allowlist.py
  models.py
  provider_contracts.py
  transport_contracts.py
  telemetry_models.py
  telemetry_writers.py
  stage21_1_manifest.py

PHX2/tests/stage21/
  __init__.py
  test_constants.py
  test_errors.py
  test_clock.py
  test_config.py
  test_secret_redaction.py
  test_credential_attestation.py
  test_allowlist.py
  test_models.py
  test_provider_contracts.py
  test_transport_contracts.py
  test_telemetry_writers.py
  test_import_boundaries.py
  test_env_read_boundaries.py
  test_no_secret_leaks.py
  test_no_public_routing.py
  test_stage21_1_manifest.py
```

## Test command (21.1)

```
py -3 -m pytest -q --basetemp=./.pytest_basetmp_stage21_1 PHX2/tests/stage21/
```

The Stage 21 suite is fully self-contained: every test is local,
deterministic, and exercises no network and no real Discord/TG send.
