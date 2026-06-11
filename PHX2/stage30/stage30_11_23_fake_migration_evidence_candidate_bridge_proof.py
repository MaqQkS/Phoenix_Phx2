"""Stage 30.11.23 fake discovered migration-evidence bridge proof.

Offline only. A thin, transport-AGNOSTIC driver that proves the end-to-end NON-manual
path: it takes an INJECTED iterable of Stage 29.5.7 sanitized migration-evidence
summaries (NEVER a hand-fed mint), runs the committed Stage 30.11.23 bridge to derive
the discovered-candidate ``events`` + trivial assembler + placeholder flattener +
mint-keyed Stage 30.11.9 evidence source, and feeds those four inputs into the
committed Stage 30.11.22 fake real-fed dry-run proof driver (over an INJECTED price
source + market-context source + ATH source transport + clocks + a recording FAKE
dispatch client + an in-memory dedupe ledger) -- proving a DISCOVERED candidate flows
end-to-end to a RECORDED would-send, NEVER a real send, with the candidate mint + the
migration anchor coming from the summary, NOT from a ``CURATED_MINT`` /
``CURATED_MIGRATION_TIME_UTC`` argument (there is none).

The summaries + the provider sources + the clocks + the bounded event source are
INJECTED, NOT built here -- so this committed proof imports NO Stage 21-29 module, NO
Stage 30.4.3 source, NO Stage 30.11.9 source, and NO Stage 30.11.16 real-send guard. It
opens NO socket, reads NO env, sends NO private message, calls NO real transport, and
writes NO file (the in-memory ledger persists nothing). The real Stage 29.5.7
migration-evidence producer (an out-of-repo capture) + the controlled live send remain
a SEPARATE, operator-authorized step this proof does NOT build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the committed Stage 30.11.23 bridge adapter (the bridge entrypoint)
    and the committed Stage 30.11.22 fake real-fed dry-run proof driver (which builds
    the dry-run defaults + runs the committed Stage 30.11.22 wrapper). No other PHX2
    module; no Stage 21-29 / Stage 30.4.3 source / Stage 30.11.9 source / Stage 30.11.16
    real-send guard import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No provider, transport-destination, or request-metadata reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; every timestamp / clock is
    caller-injected.
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from PHX2.stage30.stage30_11_22_fake_real_fed_dry_run_proof import (
    run_stage30_11_22_fake_real_fed_dry_run_proof,
)
from PHX2.stage30.stage30_11_23_migration_evidence_candidate_bridge_adapter import (
    build_real_fed_inputs_from_migration_evidence,
)


@dataclass(frozen=True)
class Stage30_11_23FakeRealFedDryRunProofResult:
    """The bridge inputs bundle + the rolled-up Stage 30.11.22 dry-run report + the
    recording FAKE client + the shared ledger, so a test can assert the bridge
    decisions, the discovered candidate / evidence consistency, the recorded would-send
    tally (NEVER a real send), the cross-run dedupe, and that the dispatched mint came
    from the summary (not a hand-fed ``CURATED_MINT``).

      * ``inputs`` -- the ``Stage30_11_23RealFedInputs`` bundle (carries the embedded
                      ``Stage30_11_23BridgeReport``).
      * ``report`` -- the embedded ``Stage30_11_22RealFedDryRunReport``.
      * ``client`` -- the recording FAKE dispatch client.
      * ``ledger`` -- the dedupe ledger (in-memory by default).
    """

    inputs: Any
    report: Any
    client: Any
    ledger: Any


def run_stage30_11_23_fake_real_fed_dry_run_proof(
    summaries: Iterable[object],
    *,
    price_source: object,
    market_context_source: object,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    now_seconds: object,
    created_at_utc: str,
    config: Optional[Any] = None,
    ledger: Optional[Any] = None,
    transport_client: Optional[Any] = None,
    max_summaries: Optional[int] = None,
    max_harvest: Optional[int] = None,
    candidate_id_prefix: Optional[str] = None,
    ath_timeout_seconds: int = 10,
    market_context_max_age_seconds: Optional[int] = None,
    ttl_seconds: Optional[int] = None,
) -> Stage30_11_23FakeRealFedDryRunProofResult:
    """Bridge the INJECTED ``summaries`` into real-fed inputs, then run the committed
    Stage 30.11.22 fake real-fed dry-run proof over them + the INJECTED provider sources
    + a recording FAKE dispatch client + the shared in-memory ledger; return
    ``(inputs, report, client, ledger)``.

    There is NO mint argument: the discovered candidate mint + the migration anchor come
    from the bridged summaries, NOT from a hand-fed ``CURATED_MINT`` /
    ``CURATED_MIGRATION_TIME_UTC``. With ``config`` / ``ledger`` / ``transport_client``
    defaulted, the committed Stage 30.11.22 proof builds the default bounded session
    config + a fresh in-memory ledger + a fresh recording FAKE client. Pure /
    deterministic apart from the injected sources' reads + the injected fake client's +
    ledger's recording side effects; reads no clock, no env, no network; constructs no
    provider transport, reserves no real dispatch, sends no private message, writes no
    file, runs no daemon / ``while`` loop.
    """
    build_kwargs = {}
    if max_summaries is not None:
        build_kwargs["max_summaries"] = max_summaries
    inputs = build_real_fed_inputs_from_migration_evidence(
        summaries, created_at_utc=created_at_utc, **build_kwargs
    )

    proof = run_stage30_11_22_fake_real_fed_dry_run_proof(
        inputs.events,
        assembler=inputs.assembler,
        record_flattener=inputs.record_flattener,
        evidence_source=inputs.evidence_source,
        price_source=price_source,
        market_context_source=market_context_source,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        now_seconds=now_seconds,
        created_at_utc=created_at_utc,
        config=config,
        ledger=ledger,
        transport_client=transport_client,
        max_harvest=max_harvest,
        candidate_id_prefix=candidate_id_prefix,
        ath_timeout_seconds=ath_timeout_seconds,
        market_context_max_age_seconds=market_context_max_age_seconds,
        ttl_seconds=ttl_seconds,
    )
    return Stage30_11_23FakeRealFedDryRunProofResult(
        inputs=inputs,
        report=proof.report,
        client=proof.client,
        ledger=proof.ledger,
    )


__all__ = (
    "Stage30_11_23FakeRealFedDryRunProofResult",
    "run_stage30_11_23_fake_real_fed_dry_run_proof",
)
