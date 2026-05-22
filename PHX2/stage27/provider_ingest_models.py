"""Stage 27.3 provider-ingest composition closed-set vocabularies
and immutable record shapes.

Stage 27.3 ships the in-memory model layer for provider-ingest
composition: the closed-set ``EVENT_KIND`` vocabulary the Stage
27.3 adapter projects upstream normalized events into, the
closed-set ``COMPOSITION_STATUS`` and ``COMPOSITION_REASON``
vocabularies the Stage 27.3 composer emits, and the two immutable
``NamedTuple`` records that flow through Stage 27.3 (a
``ProviderIngestInputRecord`` carrying only safe Stage 27.3-shaped
fields, and a ``ProviderIngestOutputRecord`` carrying the
deterministic composition output).

Stage 27.3 deliberately does NOT carry:

  * raw provider payload blobs (no field ever takes a raw payload),
  * secrets, webhook URLs, API keys (no field admits them),
  * Discord fields (no Discord surface ships in Stage 27.3),
  * price / ATH fields (Stage 27.4 surface, not Stage 27.3),
  * Stage 26 policy decisions (Stage 26 is evidence-only).

This module imports only stdlib (``typing``). It does NOT import
Stage 21-26 production code, does NOT import Stage 27.1 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 27.3 version axes
# ---------------------------------------------------------------------------


STAGE27_3_MINOR_VERSION: str = "27.3"
STAGE27_3_SCHEMA_VERSION: str = (
    "stage27_v0_provider_ingest_composition"
)


# ---------------------------------------------------------------------------
# event_kind closed set
# ---------------------------------------------------------------------------
#
# Stage 27.3 normalizes upstream provider/normalized event_type
# strings into this small closed set. Anything outside the set is
# represented as ``UNKNOWN_EVENT_KIND`` and is skipped by the
# composer (status ``SKIPPED_UNSUPPORTED_EVENT``).
#
# Stage 27.3 is deliberately tolerant: the adapter does not raise
# on an unknown event_type string -- the closed-set
# ``UNKNOWN_EVENT_KIND`` token carries the semantics, and the
# composer skips deterministically.


EVENT_KIND_SWAP: str = "SWAP"
EVENT_KIND_MIGRATION: str = "MIGRATION"
EVENT_KIND_MINT: str = "MINT"
EVENT_KIND_UNKNOWN: str = "UNKNOWN_EVENT_KIND"

EVENT_KIND_VALUES: tuple[str, ...] = (
    EVENT_KIND_SWAP,
    EVENT_KIND_MIGRATION,
    EVENT_KIND_MINT,
    EVENT_KIND_UNKNOWN,
)


# Event kinds that the Stage 27.3 composer treats as supported and
# attempts to classify. Anything outside this tuple yields the
# ``SKIPPED_UNSUPPORTED_EVENT`` composition status.
SUPPORTED_EVENT_KINDS: tuple[str, ...] = (
    EVENT_KIND_SWAP,
    EVENT_KIND_MIGRATION,
    EVENT_KIND_MINT,
)


# ---------------------------------------------------------------------------
# composition_status closed set
# ---------------------------------------------------------------------------


COMPOSITION_STATUS_COMPOSED: str = "COMPOSED"
COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT: str = (
    "SKIPPED_UNSUPPORTED_EVENT"
)
COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN: str = (
    "SKIPPED_MISSING_TOKEN"
)
COMPOSITION_STATUS_CLASSIFIED_UNKNOWN: str = (
    "CLASSIFIED_UNKNOWN"
)
COMPOSITION_STATUS_CLASSIFIED_DISAGREE: str = (
    "CLASSIFIED_DISAGREE"
)
COMPOSITION_STATUS_ERROR: str = "ERROR"

COMPOSITION_STATUS_VALUES: tuple[str, ...] = (
    COMPOSITION_STATUS_COMPOSED,
    COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN,
    COMPOSITION_STATUS_CLASSIFIED_UNKNOWN,
    COMPOSITION_STATUS_CLASSIFIED_DISAGREE,
    COMPOSITION_STATUS_ERROR,
)


# ---------------------------------------------------------------------------
# composition_reason closed set
# ---------------------------------------------------------------------------


COMPOSITION_REASON_OK: str = "OK"
COMPOSITION_REASON_UNSUPPORTED_EVENT_KIND: str = (
    "UNSUPPORTED_EVENT_KIND"
)
COMPOSITION_REASON_MISSING_TOKEN_MINT: str = (
    "MISSING_TOKEN_MINT"
)
COMPOSITION_REASON_PAIR_UNRESOLVED: str = "PAIR_UNRESOLVED"
COMPOSITION_REASON_PAIR_DISAGREE: str = "PAIR_DISAGREE"
COMPOSITION_REASON_ADAPTER_REJECTED_RAW_PAYLOAD: str = (
    "ADAPTER_REJECTED_RAW_PAYLOAD"
)
COMPOSITION_REASON_INVALID_INPUT_SHAPE: str = (
    "INVALID_INPUT_SHAPE"
)

COMPOSITION_REASON_VALUES: tuple[str, ...] = (
    COMPOSITION_REASON_OK,
    COMPOSITION_REASON_UNSUPPORTED_EVENT_KIND,
    COMPOSITION_REASON_MISSING_TOKEN_MINT,
    COMPOSITION_REASON_PAIR_UNRESOLVED,
    COMPOSITION_REASON_PAIR_DISAGREE,
    COMPOSITION_REASON_ADAPTER_REJECTED_RAW_PAYLOAD,
    COMPOSITION_REASON_INVALID_INPUT_SHAPE,
)


# ---------------------------------------------------------------------------
# Stage 27.3 redacted-payload sentinel
# ---------------------------------------------------------------------------
#
# Stage 27.3 never stores a raw provider payload blob on any
# record. If a caller still wants to record that a raw payload
# existed upstream (so that the artifact can be traced back to a
# Stage 22 raw capture later), the convention is to carry only the
# stable Stage 21 / 22 reference id (``raw_capture_ref``). For
# tests that synthesize an explicit redacted marker, the sentinel
# below is the locked Stage 27.3 token.

STAGE27_3_REDACTED_PAYLOAD_SENTINEL: str = (
    "STAGE27_3_RAW_PAYLOAD_REDACTED"
)


# ---------------------------------------------------------------------------
# Immutable record: provider-ingest input
# ---------------------------------------------------------------------------


class ProviderIngestInputRecord(NamedTuple):
    """Immutable Stage 27.3 provider-ingest input record.

    Carries only safe Stage 27.3-shaped fields projected from an
    upstream normalized provider event. No raw payload blob, no
    secret value, no webhook URL is ever populated on this record.

    Fields:

      * ``provider_id``                          -- caller-supplied
                                                    provider identifier
                                                    (safe to display).
      * ``provider_event_id``                    -- upstream provider
                                                    event id (safe to
                                                    display).
      * ``normalized_event_id``                  -- upstream normalized
                                                    event id (safe to
                                                    display).
      * ``event_kind``                           -- one of
                                                    ``EVENT_KIND_VALUES``.
      * ``observed_at_utc``                      -- ISO-8601 UTC string
                                                    (operator-observed
                                                    wall time).
      * ``token_mint``                           -- token mint string
                                                    (the base token
                                                    being observed).
      * ``pool_account``                         -- on-chain pool
                                                    account reference.
      * ``pool_program_id``                      -- on-chain pool
                                                    program id.
      * ``base_mint``                            -- base mint string
                                                    when disambiguating
                                                    base / quote sides.
      * ``quote_mint``                           -- pool-derived quote
                                                    mint string.
                                                    Unknown strings are
                                                    NEVER silently
                                                    promoted to SOL.
      * ``bonding_curve_program_id``             -- bonding-curve
                                                    program id.
      * ``bonding_curve_version_hint``           -- closed-set
                                                    BONDING_CURVE_VERSION
                                                    hint from on-chain
                                                    layout.
      * ``migration_event_quote_asset_hint``     -- closed-set
                                                    QUOTE_ASSET hint
                                                    from a migration
                                                    event.
      * ``provider_quote_asset_hint``            -- closed-set
                                                    QUOTE_ASSET hint
                                                    from provider
                                                    enrichment.
      * ``provider_pair_type_hint``              -- closed-set PAIR_TYPE
                                                    hint from provider
                                                    enrichment.
      * ``provider_bonding_curve_version_hint``  -- closed-set
                                                    BONDING_CURVE_VERSION
                                                    hint from provider
                                                    enrichment.
      * ``raw_capture_ref``                      -- short reference id
                                                    pointing at the
                                                    upstream Stage 22
                                                    raw capture (e.g. a
                                                    content hash or
                                                    artifact handle).
                                                    NEVER a payload
                                                    blob.
      * ``source_summary``                       -- short free-form
                                                    provenance summary
                                                    (safe to display).
                                                    Optional; the
                                                    Stage 27.3 boundary
                                                    test still pins
                                                    that this field is
                                                    not used to smuggle
                                                    a raw payload.
    """

    provider_id: Optional[str] = None
    provider_event_id: Optional[str] = None
    normalized_event_id: Optional[str] = None
    event_kind: str = EVENT_KIND_UNKNOWN
    observed_at_utc: Optional[str] = None
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
    raw_capture_ref: Optional[str] = None
    source_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable record: provider-ingest output
# ---------------------------------------------------------------------------


class ProviderIngestOutputRecord(NamedTuple):
    """Immutable Stage 27.3 provider-ingest composition output.

    Every field is a closed-set token, a closed-set reason code, a
    safe-to-display string copied from the input, or one of the
    explicit Stage 27.2 pair-classification result fields. No raw
    provider payload blob, no secret value, no webhook URL is ever
    populated on this record.

    Fields:

      * ``provider_id``                  -- copied from the input.
      * ``provider_event_id``            -- copied from the input.
      * ``normalized_event_id``          -- copied from the input.
      * ``event_kind``                   -- one of
                                            ``EVENT_KIND_VALUES``.
                                            Always reflects what the
                                            adapter / composer treated
                                            the event as -- e.g.
                                            ``UNKNOWN_EVENT_KIND`` for
                                            a skip.
      * ``observed_at_utc``              -- copied from the input.
      * ``token_mint``                   -- copied from the input.
      * ``quote_mint``                   -- copied from the input.
      * ``pair_quote_asset``             -- Stage 27.2 closed-set
                                            ``QUOTE_ASSET`` verdict.
      * ``pair_pair_type``               -- Stage 27.2 closed-set
                                            ``PAIR_TYPE`` verdict.
      * ``pair_bonding_curve_version``   -- Stage 27.2 closed-set
                                            ``BONDING_CURVE_VERSION``
                                            verdict.
      * ``pair_detection_status``        -- Stage 27.2 closed-set
                                            pair-detection status.
      * ``pair_detection_confidence``    -- Stage 27.2 closed-set
                                            pair-detection confidence.
      * ``pair_detection_reason``        -- Stage 27.2 closed-set
                                            pair-detection reason.
      * ``pair_live_policy``             -- Stage 27.2 closed-set
                                            live-policy decision.
                                            Classification policy
                                            only; Stage 27.3 does NOT
                                            send anything live.
      * ``pair_calibration_lane``        -- Stage 27.2 closed-set
                                            calibration lane.
                                            USDC and UNKNOWN MUST NOT
                                            map to ``EXISTING_SOL_LANE``.
      * ``raw_capture_ref``              -- copied from the input
                                            (provenance preserved).
      * ``source_summary``               -- copied from the input
                                            (provenance preserved).
      * ``composition_status``           -- one of
                                            ``COMPOSITION_STATUS_VALUES``.
      * ``composition_reason``           -- one of
                                            ``COMPOSITION_REASON_VALUES``.
      * ``schema_version``               -- locked Stage 27.3 schema
                                            version string
                                            (``STAGE27_3_SCHEMA_VERSION``).
    """

    provider_id: Optional[str]
    provider_event_id: Optional[str]
    normalized_event_id: Optional[str]
    event_kind: str
    observed_at_utc: Optional[str]
    token_mint: Optional[str]
    quote_mint: Optional[str]
    pair_quote_asset: str
    pair_pair_type: str
    pair_bonding_curve_version: str
    pair_detection_status: str
    pair_detection_confidence: str
    pair_detection_reason: str
    pair_live_policy: str
    pair_calibration_lane: str
    raw_capture_ref: Optional[str]
    source_summary: Optional[str]
    composition_status: str
    composition_reason: str
    schema_version: str


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 27.3 must never accept a field named anything secret-class
# or raw-payload-class on its input. Callers cannot pass these
# through the immutable ``NamedTuple`` schema (the NamedTuple has
# no such fields) but the helper below is kept for the boundary /
# adapter tests so a future refactor cannot silently widen the
# admitted field set.


FORBIDDEN_INPUT_FIELD_NAMES: tuple[str, ...] = (
    "raw_payload",
    "raw_payload_blob",
    "payload_summary",
    "payload",
    "secret",
    "api_key",
    "apikey",
    "token_secret",
    "webhook",
    "webhook_url",
    "discord_webhook",
    "discord_recipient",
    "private_key",
    "credentials",
)


def is_forbidden_input_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden input-field name.

    Pure / deterministic. Stage 27.3 uses this to reject any caller
    who tries to smuggle a raw payload blob into the ingest input.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_INPUT_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Public projector: input record provenance view (used by tests +
# downstream consumers that want only safe-to-display fields).
# ---------------------------------------------------------------------------


def ingest_input_provenance_view(
    record: ProviderIngestInputRecord,
) -> Mapping[str, Optional[str]]:
    """Return the provenance subset of an input record.

    The returned mapping carries ONLY the safe-to-display
    provenance fields (provider / event / capture refs). It never
    includes pair hints, mint strings, or pool fields.

    Pure / deterministic.
    """
    return {
        "provider_id": record.provider_id,
        "provider_event_id": record.provider_event_id,
        "normalized_event_id": record.normalized_event_id,
        "raw_capture_ref": record.raw_capture_ref,
        "source_summary": record.source_summary,
    }
