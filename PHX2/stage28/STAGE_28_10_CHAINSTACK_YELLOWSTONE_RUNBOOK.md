# Stage 28.10 Chainstack Yellowstone provider boundary runbook

Stage 28.10 is a post-Stage-28-closure, post-Stage-28.9 narrow
amendment that defines the protocol / fake / models surface for
a future real Chainstack Yellowstone gRPC provider client. Stage
28.10 is a **protocol / fake boundary only**.

Stage 28.10 ships NO real provider client, NO grpc / grpcio /
protobuf imports, NO generated pb2 / pb2_grpc stubs, NO real
network access, NO real Discord send, NO Stage 29 enforcement,
NO public routing, NO subscriber routing, NO paid tier routing,
NO Telegram, NO X / social, NO automated trading, NO wallet /
private-key / signer logic, NO position sizing, and NO trade
execution.

This runbook is a manual operator procedure. Nothing in this
document instructs a Python runtime to send anything live;
nothing in this document instructs a Python runtime to open a
real Chainstack connection. Every send that ever happens during
a future live provider session is driven by the caller-injected
Stage 28.4 audited transport wrapped by the Stage 28.9 private
webhook transport; the operator is responsible for the wrap-and-
go ceremony described in the Stage 28.9 runbook.

## 0. Scope marker

Stage 28.10 is **protocol / fake / models boundary only**.

The Stage 28.10 production tree defines:

* the sanitized payload model the future real provider client
  must project upstream Yellowstone events into,
* the closed-set provider-kind / auth-mode / quote-asset /
  pair-type / bonding-curve-version hint vocabularies,
* the immutable provider boundary config model + builder,
* a Protocol contract + a deterministic fake client for unit
  tests,
* a Stage 28.9-compatible event source that maps payloads onto
  Stage 28.10 normalized events (carrying the hint attributes),
* a hint-aware candidate assembler that forwards pair / pool /
  bonding-curve hints to the Stage 27 adapter so the existing
  Stage 27 chain does not lose hint evidence.

No real provider client lives under Stage 28.10. No grpc /
grpcio / protobuf import lives under Stage 28.10. No generated
``pb2`` / ``pb2_grpc`` stub lives under Stage 28.10.

## 1. No real provider calls in unit tests

Stage 28.10 unit tests use the deterministic fake client and the
deterministic fake price / ATH / migration sources via the Stage
27.6 ``Stage27_6Sources`` bundle. **No Stage 28.10 unit test
opens a real Chainstack connection.** **No Stage 28.10 unit test
sends a real Discord message.** **No Stage 28.10 unit test
imports grpc / grpcio / protobuf / generated pb2 / generated
pb2_grpc.**

The Stage 28.10 boundary test pins these prohibitions and the
Stage 28.10 contracts module exposes the
``Stage28_10ChainstackYellowstoneFakeClient`` (a pure-Python
NamedTuple-backed payload source) so the unit-test surface stays
network-free.

## 2. Required preconditions before any live Chainstack provider client

Before any future real Chainstack / Yellowstone gRPC provider
client may be wired into Stage 28.9 + Stage 28.10, the operator
MUST confirm:

1. **Pinned proto source.** The exact proto source for the real
   provider client must be pinned: the upstream ``.proto`` files
   must be pinned to a specific version, the proto generation
   command must be pinned in repo documentation, the generated
   ``*_pb2.py`` / ``*_pb2_grpc.py`` outputs must live OUTSIDE
   Stage 28.10 (they are NOT part of the Stage 28.10 production
   surface), and the dependency on ``grpcio`` / ``grpcio-tools``
   / ``protobuf`` must be documented in a separate dependency
   manifest. Stage 28.10 does NOT install or vendor these
   dependencies.
2. **Pinned version.** The exact provider client library version
   must be pinned (e.g. ``grpcio==1.66.x``) and the operator must
   record the exact resolved version in their session report.
3. **Pinned generation command.** The proto generation command
   (e.g. ``python -m grpc_tools.protoc -I=...``) must be pinned
   in repo documentation so the same generated stubs are
   reproducible.
4. **Explicit operator authorization.** A real-provider-client
   substage past Stage 28.10 requires explicit operator
   authorization on the substage scope and on the dependency
   install before any of the items above may land. Stage 28.10
   does NOT authorize the real-provider substage.

## 3. First live provider path (manual operator ceremony)

When the future real provider client lands (under explicit
operator authorization, in a separately authorized substage past
Stage 28.10), the operator MUST drive the first live provider
session through the following sequence:

1. **Readiness-only validation.** Construct the
   ``Stage28_10ChainstackYellowstoneConfig`` via
   ``build_chainstack_yellowstone_config(...)``. The config
   builder refuses unsafe labels, missing closed-set tokens, and
   non-positive bounds. **No provider call yet.** **No Discord
   send.**
2. **Provider-connect-only probe.** Wrap the real provider client
   in a connect-only smoke that opens the upstream connection,
   confirms the handshake completes, and immediately tears the
   connection down without subscribing to any event stream.
   **No event decode.** **No Discord send.**
3. **One-event decode dry run.** Subscribe to the upstream event
   stream long enough to decode exactly ONE Yellowstone event
   into a ``Stage28_10ChainstackYellowstonePayload``, confirm the
   payload validates against the Stage 28.10 model contract,
   tear the connection down. **No Discord send.**
4. **Stage 28.9 wrapper with tight caps.** After the three probes
   above succeed, wire the real provider client into the Stage
   28.9 ``run_stage28_9_live_provider_session`` call with the
   Stage 28.10 hint-aware candidate assembler, ``max_events=1``,
   ``max_dispatches=1``, an out-of-repo artifact directory, and
   the operator's explicit ``live_env_ready=True`` /
   ``live_operator_request=True`` decisions. The first private
   Discord ping may flow only at this step, after the explicit
   operator authorization, and only to the operator-private
   webhook.

Steps 1, 2, and 3 are network-touch ceremonies that do NOT send
Discord; only step 4 may send a Discord ping, and only under
explicit operator authorization.

## 4. Real pings require fresh price context

The Stage 28.10 hint-aware candidate assembler runs the existing
Stage 27 candidate chain (``assemble_live_candidate``). The Stage
27 chain refuses to render a tradeable private ping when the
injected Stage 27.4 price source returns ``UNAVAILABLE`` /
``SOURCE_ERROR`` (the rendered ping carries ``price_status =
UNAVAILABLE`` / ``SOURCE_ERROR``, the Stage 28.6 mapper projects
to ``CANDIDATE_PRICE_STATUS_MISSING``, and the Stage 28.6 runner
suppresses the dispatch via the ``PRICE_MISSING`` rule).

The Stage 27 chain refuses to render a tradeable private ping
when the injected price source returns a snapshot whose
``fetched_at_utc`` lies outside the configured staleness
threshold (the rendered ping carries ``price_status = STALE``,
the Stage 28.6 mapper projects to
``CANDIDATE_PRICE_STATUS_STALE``, and the Stage 28.6 runner
suppresses the dispatch via the ``PRICE_STALE`` rule).

Real pings therefore REQUIRE a real PRESENT fresh price snapshot
at dispatch time. **A missing price suppresses.** **A stale
price suppresses.**

Stage 28.10 production code does NOT ship a real Birdeye client.
The operator supplies the price source at the Stage 27.6
``Stage27_6Sources`` boundary; Stage 28.10 tests inject a
deterministic fake price source. Stage 28.10 production code
NEVER fakes a price; the injected source is the only price
authority.

## 5. UNKNOWN / DISAGREE / USDC observe-only suppressions remain

The Stage 28.10 hint-aware candidate assembler forwards the
upstream pair / pool / bonding-curve hints to
``adapt_normalized_event_to_ingest_input`` so the Stage 27 pair
classifier has hint evidence. With hint evidence present, a SOL
candidate reaches the SOL trusted lane via the existing Stage 27
``CONFIRMED`` / ``PROVIDER_ONLY`` rule, a USDC candidate reaches
the USDC observe-only lane via the existing Stage 27 USDC rule,
and a candidate with no resolvable pair stays in the UNKNOWN
suppression lane via the existing Stage 27 UNKNOWN rule.

The Stage 28.10 hint-aware candidate assembler NEVER invents a
SOL hint, NEVER invents a USDC hint, NEVER promotes UNKNOWN to
SOL, and NEVER promotes DISAGREE to a successful live-ready
verdict. The Stage 28.10 boundary tests pin these guarantees.

A candidate with no hint evidence stays UNKNOWN and is suppressed
by the existing Stage 28.6 ``UNKNOWN_PAIR_SUPPRESSED`` rule.

A candidate with conflicting hints stays DISAGREE and is
suppressed by the existing Stage 28.6 ``DISAGREE_PAIR_SUPPRESSED``
rule.

A candidate that classifies as USDC-quote reaches the existing
Stage 28.6 ``USDC_OBSERVE_ONLY`` lane.

## 6. Stage 29 enforcement pending

Stage 29 owns the approved / activated filter enforcement gate.
Stage 28.10 does NOT add an enforcement gate; Stage 28.10 does
NOT activate any Stage 26 policy candidate; Stage 28.10 does NOT
flip any Stage 27 suppression rule from observe-only to
allow-only.

Every Stage 28.10 candidate that reaches the Stage 28.9 mapper
carries the Stage 28.9 marker ``Filter enforcement:
NOT_ACTIVE_STAGE_29_PENDING`` on its rendered Discord payload
(Stage 28.9 owns the marker; Stage 28.10 inherits it via the
existing Stage 28.9 mapper). Operator MUST manually interpret
each ping until Stage 29 lands.

## 7. Forbidden surfaces

Stage 28.10 explicitly does NOT add:

* Stage 29 enforcement,
* public routing,
* subscriber routing,
* paid tiers,
* Telegram,
* X / social,
* automated trading,
* wallet / private-key / signer logic,
* position sizing,
* trade execution,
* dashboard / HTTP control server,
* daemon / systemd / watchdog / autorestart service,
* real Chainstack network calls,
* real Discord sends,
* grpc / grpcio / protobuf imports,
* generated pb2 / pb2_grpc stubs.

The full set is pinned in ``stage28_10_manifest.py``
(``STAGE28_10_FORBIDDEN_SURFACES``).

## 8. Operator interpretation reminder

Every Stage 28.10 candidate is a hint-aware bridge between the
future real Chainstack Yellowstone provider client and the
already-closed Stage 28.6 bounded private session runner. Stage
28.10 does not change the Stage 29 enforcement story; the Stage
29 approved / activated filter enforcement gate is NOT active.
Operator MUST manually interpret each ping; no automated decision
flows from a Stage 28.10 candidate. The Stage 28.9 marker
``Filter enforcement: NOT_ACTIVE_STAGE_29_PENDING`` continues to
ride on every payload header.
