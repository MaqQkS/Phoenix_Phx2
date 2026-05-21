"""PHX2 Stage 25 -- observe-only ATH / migration measurement foundation (architecture only at 25.1).

Stage 25 is the first PHX2 measurement-primitive stage after the
Stage 24 execution-primitive closure. Stage 25 derives migration
boundary and post-migration ATH measurements from operator-
supplied Stage 25-shaped JSONL observations and projects them
into deterministic, redacted, hashed measurement records. Stage
25 NEVER blocks, gates, routes, dispatches, monetizes, opens a
database connection, opens a network socket, or runs a live
process. The job of Stage 25 is to take Stage 25-shaped
observations and emit deterministic measurement records to disk
honestly -- with explicit status when data is missing,
ambiguous, partial, or single-source -- nothing more.

What 25.1 ships:

  * The Stage 25 subtree (``PHX2/stage25/``,
    ``PHX2/tests/stage25/``).
  * Locked Stage 25 version axes and closed-set token
    vocabularies for: measurement families, source families,
    source statuses, measurement statuses, confidence levels,
    rejection reasons, price-window kinds, ATH-candidate kinds,
    reconciliation statuses, quote denominations, input kinds.
  * Module-local ``Stage25Error`` hierarchy rooted at plain
    ``Exception``.
  * Typed ``NamedTuple`` records and contract surfaces:
    ``Stage25MeasurementInput``,
    ``Stage25MigrationObservation``,
    ``Stage25MigrationMeasurement``,
    ``Stage25PriceObservation``,
    ``Stage25PriceWindowObservation``,
    ``Stage25ATHCandidate``,
    ``Stage25ATHMeasurement``,
    ``Stage25SourceReconciliation``,
    ``Stage25MeasurementRejection``,
    ``Stage25UnifiedMeasurement``,
    ``Stage25RunnerResult`` (placeholder),
    plus Protocols: ``Stage25MigrationMeasurer``,
    ``Stage25ATHReconciler``,
    ``Stage25PriceObservationProjector``.
  * Deterministic canonical-JSON hash helpers
    (``canonical_json`` / ``stage25_hash`` /
    ``compute_observation_hash`` / ``compute_measurement_hash``
    / ``compute_candidate_hash`` /
    ``compute_reconciliation_hash``).
  * Stage 25 input reader reading Stage 25-shaped migration-
    observation and price-observation JSONL artifacts from
    operator-supplied paths, with typed Stage 25 errors and
    redaction discipline.
  * Manifest helpers for input + artifact provenance, including
    an optional Stage 24 manifest pin recorded by basename and
    SHA-256 only.

What 25.1 deliberately does NOT ship:

  * any real migration-measurement logic -- reserved for
    Stage 25.2+.
  * any real ATH-candidate construction or source-reconciliation
    logic -- reserved for Stage 25.3+.
  * unified offline runner / artifact writer -- reserved for
    Stage 25.5+.
  * any live API / RPC / websocket call.
  * any DB read or write.
  * any Discord / Telegram or other transport call.
  * any calibration / enforcement layer.
  * any X / social-intelligence surface.
  * any confirmed Axiom / global-fee decoder (Stage 24 surface).
  * any new execution-fee primitive (Stage 24 surface).
  * any direct Stage 22 raw-capture decoding -- Stage 25 reads
    Stage 25-shaped JSONL only.
  * any import from PHX2.stage21 / PHX2.stage22 / PHX2.stage23
    / PHX2.stage24 production code.

Hard import-boundary policy (enforced by the Stage 25 boundary
tests in ``PHX2/tests/stage25/``):

  * Stage 25 production code MUST NOT import Stage 21, Stage 22,
    Stage 23, or Stage 24 production modules.
  * Stage 25 production code MUST NOT import any PHX2 runtime
    layer (``PHX2.db``, ``PHX2.repositories``, ``PHX2.config``,
    ``PHX2.models``, ``PHX2.services``, ``PHX2.dispatch``,
    ``PHX2.filters``, ``PHX2.integrations``, ``PHX2.renderers``,
    ``PHX2.scripts``, ``PHX2.analysis``).
  * Stage 25 production code MUST NOT import any network / RPC /
    messaging / DB / scheduler / secrets-management library.
  * Stage 25 production code MUST NOT read ``os.environ`` or
    ``os.getenv``.
  * Stage 25 production code MUST NOT write to disk outside an
    operator-supplied path the caller has constructed (Stage
    25.1 ships NO writer; this is a forward-looking invariant
    for the Stage 25.5+ artifact writer).
"""

from __future__ import annotations
