"""Stage 27.2 pair-detection immutable record shapes.

Stage 27.2 ships the in-memory record layer for the pair-detection
classifier skeleton. Every record is a frozen ``NamedTuple`` so the
classifier (and any future Stage 27.3+ consumer) can pass these
records around without any mutable global state, and so that
``repr()`` / ``str()`` of any record never carries a raw provider
payload blob -- because no field on any of these records is ever
populated with a raw provider payload value in the first place.

Record shapes:

  * ``PairDetectionInputRecord``   -- the immutable per-event input
                                      record carrying only normalized
                                      hints. Provider hint fields are
                                      closed-set tokens or known mint
                                      strings; raw payload blobs are
                                      not admitted.
  * ``PairDetectionEvidenceRecord`` -- a single per-source evidence
                                       record. The classifier emits
                                       one of these per evidence
                                       source.
  * ``PairDetectionOutputRecord``  -- the immutable classifier output
                                      record carrying closed-set
                                      tokens, evidence accounting,
                                      and live-policy / calibration-
                                      lane decisions.

This module imports only stdlib (``typing``). It does NOT import
Stage 21-26 production code, does NOT import any network / RPC /
messaging / DB / scheduler / secrets-management library, does NOT
read the process environment, does NOT define a CLI surface, and
contains no top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


class PairDetectionInputRecord(NamedTuple):
    """Immutable per-event pair-detection input.

    Every field is optional so the classifier can accept partial
    evidence from upstream stages without raising. Provider hint
    fields carry closed-set token strings or known mint strings;
    raw provider payload blobs are not admitted on this record.

    Fields:

      * ``event_id``                          -- caller-supplied
                                                 event id (safe to
                                                 display).
      * ``token_mint``                        -- token mint string
                                                 (e.g. the base token
                                                 being traded).
      * ``pool_account``                      -- on-chain pool account
                                                 reference (safe to
                                                 display).
      * ``pool_program_id``                   -- on-chain pool program
                                                 id reference.
      * ``base_mint``                         -- base mint string when
                                                 disambiguating
                                                 base / quote sides.
      * ``quote_mint``                        -- pool-derived quote
                                                 mint string. Matched
                                                 exactly; unknown
                                                 strings are NEVER
                                                 silently promoted
                                                 to SOL.
      * ``bonding_curve_program_id``          -- bonding-curve program
                                                 id reference.
      * ``bonding_curve_version_hint``        -- closed-set
                                                 BONDING_CURVE_VERSION
                                                 hint derived from
                                                 on-chain account
                                                 layout.
      * ``migration_event_quote_asset_hint``  -- closed-set
                                                 QUOTE_ASSET hint
                                                 derived from a
                                                 migration event.
      * ``provider_quote_asset_hint``         -- closed-set
                                                 QUOTE_ASSET hint
                                                 derived from provider
                                                 enrichment.
      * ``provider_pair_type_hint``           -- closed-set PAIR_TYPE
                                                 hint derived from
                                                 provider enrichment.
      * ``provider_bonding_curve_version_hint`` -- closed-set
                                                 BONDING_CURVE_VERSION
                                                 hint derived from
                                                 provider enrichment.
      * ``observed_at_utc``                   -- ISO-8601 UTC string
                                                 (operator-observed
                                                 wall time).
      * ``fetched_at_utc``                    -- ISO-8601 UTC string
                                                 (provider-fetch
                                                 wall time).
      * ``source_payload_reference``          -- a short string handle
                                                 (e.g. content hash
                                                 or artifact path)
                                                 pointing at the
                                                 upstream payload.
                                                 NEVER the payload
                                                 itself.
    """

    event_id: Optional[str] = None
    token_mint: Optional[str] = None
    pool_account: Optional[str] = None
    pool_program_id: Optional[str] = None
    base_mint: Optional[str] = None
    quote_mint: Optional[str] = None
    bonding_curve_program_id: Optional[str] = None
    bonding_curve_version_hint: Optional[str] = None
    migration_event_quote_asset_hint: Optional[str] = None
    provider_quote_asset_hint: Optional[str] = None
    provider_pair_type_hint: Optional[str] = None
    provider_bonding_curve_version_hint: Optional[str] = None
    observed_at_utc: Optional[str] = None
    fetched_at_utc: Optional[str] = None
    source_payload_reference: Optional[str] = None


class PairDetectionEvidenceRecord(NamedTuple):
    """Immutable per-source pair-detection evidence.

    One evidence record per evidence source that fires. The classifier
    aggregates the evidence list into a single
    ``PairDetectionOutputRecord``. Every field is a closed-set token
    string or a closed-set reason code; no raw payload blob is ever
    carried on an evidence record.

    Fields:

      * ``source``                          -- one of
                                               ``PAIR_DETECTION_SOURCE_VALUES``.
      * ``quote_asset_verdict``             -- one of
                                               ``QUOTE_ASSET_VALUES``,
                                               or ``None`` when the
                                               source did not opine.
      * ``pair_type_verdict``               -- one of
                                               ``PAIR_TYPE_VALUES``,
                                               or ``None``.
      * ``bonding_curve_version_verdict``   -- one of
                                               ``BONDING_CURVE_VERSION_VALUES``,
                                               or ``None``.
      * ``confidence``                      -- one of
                                               ``PAIR_DETECTION_CONFIDENCE_VALUES``.
      * ``reason``                          -- one of
                                               ``PAIR_DETECTION_REASON_VALUES``,
                                               or ``None``.
    """

    source: str
    quote_asset_verdict: Optional[str]
    pair_type_verdict: Optional[str]
    bonding_curve_version_verdict: Optional[str]
    confidence: str
    reason: Optional[str]


class PairDetectionOutputRecord(NamedTuple):
    """Immutable classifier output record.

    Every field is a closed-set token, a closed-set reason code, an
    integer accounting count, or the safe-to-display ``quote_mint``
    string that came in on the input. No raw provider payload blob
    is ever carried on this record.

    Fields:

      * ``quote_asset``                 -- one of
                                           ``QUOTE_ASSET_VALUES``.
      * ``quote_mint``                  -- the input ``quote_mint``
                                           string (safe to display)
                                           or ``None`` when the
                                           caller did not provide
                                           one.
      * ``pair_type``                   -- one of
                                           ``PAIR_TYPE_VALUES``.
      * ``bonding_curve_version``       -- one of
                                           ``BONDING_CURVE_VERSION_VALUES``.
      * ``pair_detection_status``       -- one of
                                           ``PAIR_DETECTION_STATUS_VALUES``.
      * ``pair_detection_confidence``   -- one of
                                           ``PAIR_DETECTION_CONFIDENCE_VALUES``.
      * ``pair_detection_reason``       -- one of
                                           ``PAIR_DETECTION_REASON_VALUES``.
      * ``evidence_count``              -- number of evidence records
                                           the classifier emitted.
      * ``disagreement_count``          -- number of distinct
                                           non-UNKNOWN quote-asset
                                           verdicts beyond the first
                                           (``0`` when all sources
                                           agree).
      * ``live_policy``                 -- one of
                                           ``LIVE_POLICY_VALUES``.
                                           Classification policy
                                           only; Stage 27.2 does NOT
                                           send anything live.
      * ``calibration_lane``            -- one of
                                           ``CALIBRATION_LANE_VALUES``.
                                           USDC and UNKNOWN MUST NOT
                                           map to
                                           ``EXISTING_SOL_LANE``.
    """

    quote_asset: str
    quote_mint: Optional[str]
    pair_type: str
    bonding_curve_version: str
    pair_detection_status: str
    pair_detection_confidence: str
    pair_detection_reason: str
    evidence_count: int
    disagreement_count: int
    live_policy: str
    calibration_lane: str
