"""Stage 27.3 provider-event adapter.

The adapter is the narrow seam where Stage 27.3 receives a
normalized provider event (shaped by the existing Stage 21 / 22
boundaries) and projects it into the Stage 27.3 ingest input
record. The adapter does NOT directly import Stage 21 or Stage 22
modules: it accepts any object that satisfies the
``NormalizedEventLike`` Protocol so the Stage 27 boundary scans
(which forbid Stage 21-26 imports from Stage 27 production
modules) stay intact.

The Protocol mirrors the Stage 21.2 ``NormalizedLiveEvent`` field
set (``event_id`` / ``provider_event_id`` / ``provider_name`` /
``mint`` / ``event_type`` / ``observed_at_utc`` / ``signature`` /
``raw_event_hash``). Stage 21 owns the upstream shape; Stage 27.3
owns the projection only. The adapter NEVER pulls the upstream
raw-payload blob across the boundary -- if the upstream object
exposes a ``payload_summary`` field that would smuggle a payload,
the adapter ignores it. The only payload-related field Stage 27.3
admits is the upstream ``raw_event_hash`` -- treated as a stable
``raw_capture_ref`` handle (NOT the payload itself).

Stage 27.3 does NOT:

  * read the process environment,
  * open any provider connection,
  * call Helius / gRPC / Birdeye / Discord / Telegram / X-social,
  * send anything live,
  * dedupe,
  * run a runner.

This module imports only stdlib (``typing``) plus Stage 27.2 and
Stage 27.3 production modules. It does NOT import Stage 21-26
production code, does NOT import Stage 27.1 production code, does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process environment,
does NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import Mapping, Optional, Protocol, runtime_checkable

from PHX2.stage27.pair_detection_models import (
    PairDetectionInputRecord,
)
from PHX2.stage27.provider_ingest_contracts import (
    Stage27ProviderIngestInvalidEventError,
    Stage27ProviderIngestRawPayloadRejectedError,
)
from PHX2.stage27.provider_ingest_models import (
    EVENT_KIND_MIGRATION,
    EVENT_KIND_MINT,
    EVENT_KIND_SWAP,
    EVENT_KIND_UNKNOWN,
    EVENT_KIND_VALUES,
    ProviderIngestInputRecord,
    is_forbidden_input_field_name,
)


# ---------------------------------------------------------------------------
# Normalized-event Protocol (Stage 21 / 22 shape mirror)
# ---------------------------------------------------------------------------


@runtime_checkable
class NormalizedEventLike(Protocol):
    """Structural shape Stage 27.3 expects from a normalized event.

    The Protocol mirrors the locked Stage 21.2 normalized event
    field set so a real Stage 21.2 ``NormalizedLiveEvent`` instance
    satisfies it without modification. Stage 27.3 does NOT depend
    on any Stage 21 implementation detail -- only on this
    structural contract.

    Expected fields:

      * ``event_id``               -- upstream normalized event id.
      * ``provider_event_id``      -- upstream provider event id.
      * ``provider_name``          -- upstream provider identifier.
      * ``mint``                   -- token mint string (the base
                                      token being observed).
      * ``event_type``             -- upstream event-type label.
                                      Stage 27.3 maps this onto
                                      its closed-set ``EVENT_KIND``.
      * ``observed_at_utc``        -- ISO-8601 UTC string.
      * ``raw_event_hash``         -- upstream raw-event content
                                      hash (used as a stable
                                      ``raw_capture_ref``, NOT a
                                      payload blob).
    """

    event_id: str
    provider_event_id: str
    provider_name: str
    mint: str
    event_type: str
    observed_at_utc: str
    raw_event_hash: str


# ---------------------------------------------------------------------------
# Event-type -> Stage 27.3 EVENT_KIND mapping
# ---------------------------------------------------------------------------
#
# Stage 27.3 owns its own normalized event-kind vocabulary so the
# upstream event-type literal alphabet (which may evolve through
# Stage 21.3+ real provider adapters) does not bleed into Stage
# 27.3's contract. The mapping below is the single seam.
#
# Note: ``fake_*`` event-type strings come from Stage 21.2's
# fake-only normalizer. Stage 27.3 treats them exactly the same as
# the corresponding real event-type would be treated, so the same
# Stage 27.3 composition shape applies to fake fixtures and to
# real provider events when they ship.


_EVENT_TYPE_TO_EVENT_KIND: Mapping[str, str] = {
    "swap": EVENT_KIND_SWAP,
    "fake_swap": EVENT_KIND_SWAP,
    "trade": EVENT_KIND_SWAP,
    "migration": EVENT_KIND_MIGRATION,
    "fake_migration": EVENT_KIND_MIGRATION,
    "pool_migration": EVENT_KIND_MIGRATION,
    "mint": EVENT_KIND_MINT,
    "fake_mint": EVENT_KIND_MINT,
    "token_mint_created": EVENT_KIND_MINT,
}


def classify_event_kind(event_type: object) -> str:
    """Project an upstream ``event_type`` string into the Stage 27.3
    ``EVENT_KIND`` closed set.

    Unknown / non-string / empty values resolve to
    ``EVENT_KIND_UNKNOWN``. Pure / deterministic.
    """
    if not isinstance(event_type, str) or event_type == "":
        return EVENT_KIND_UNKNOWN
    normalized = event_type.strip().lower()
    return _EVENT_TYPE_TO_EVENT_KIND.get(
        normalized, EVENT_KIND_UNKNOWN
    )


# ---------------------------------------------------------------------------
# Raw-payload-class field guard
# ---------------------------------------------------------------------------


def reject_raw_payload_fields(
    extra_fields: Optional[Mapping[str, object]] = None,
) -> None:
    """Raise if ``extra_fields`` carries any raw-payload-class key.

    Stage 27.3 explicitly refuses to admit raw provider payload
    blobs / secrets / webhook URLs into its ingest pipeline. If
    the caller passes an ``extra_fields`` mapping (e.g. provider
    enrichment side-band) the adapter validates every key against
    the locked forbidden-field-name vocabulary before merging.

    Pure / deterministic. Raises
    ``Stage27ProviderIngestRawPayloadRejectedError`` on first
    forbidden key.
    """
    if extra_fields is None:
        return
    if not isinstance(extra_fields, Mapping):
        raise Stage27ProviderIngestInvalidEventError(
            "extra_fields must be a Mapping",
            offending_type_name=type(extra_fields).__name__,
        )
    for key in extra_fields.keys():
        if is_forbidden_input_field_name(key):
            raise Stage27ProviderIngestRawPayloadRejectedError(
                str(key)
            )


# ---------------------------------------------------------------------------
# Normalized event -> Stage 27.3 ingest input
# ---------------------------------------------------------------------------


_REQUIRED_NORMALIZED_EVENT_FIELDS: tuple[str, ...] = (
    "event_id",
    "provider_event_id",
    "provider_name",
    "mint",
    "event_type",
    "observed_at_utc",
    "raw_event_hash",
)


def _safe_attr(value: object, name: str) -> Optional[str]:
    """Return ``getattr(value, name)`` as a string when possible.

    Returns ``None`` for missing / non-string / empty attributes.
    Never raises on a missing attribute -- the upstream Protocol
    is documented; absent fields fall through as ``None`` and the
    composer downstream decides what to do.
    """
    attr = getattr(value, name, None)
    if isinstance(attr, str) and attr != "":
        return attr
    return None


def _assert_event_like_shape(event_like: object) -> None:
    """Raise ``Stage27ProviderIngestInvalidEventError`` for a
    structurally-invalid event.

    Stage 27.3 tolerates missing optional fields (the composer
    handles missing-token / unsupported-kind deterministically),
    but it does NOT accept a non-object input (e.g. ``None``, a
    raw dict, a list, an int). The Protocol contract is structural;
    the check below verifies the required-field set is at least
    present as attributes (each may still be empty, in which case
    ``_safe_attr`` returns ``None``).
    """
    if event_like is None:
        raise Stage27ProviderIngestInvalidEventError(
            "event_like is None"
        )
    if isinstance(event_like, Mapping):
        # Stage 27.3 deliberately rejects raw dicts: the upstream
        # contract is a typed NormalizedEventLike. Accepting a dict
        # would create a path through which a raw payload could
        # smuggle in as a ``payload_summary`` / ``raw_payload`` key.
        raise Stage27ProviderIngestInvalidEventError(
            "event_like must be a NormalizedEventLike, not a Mapping",
            offending_type_name=type(event_like).__name__,
        )
    if isinstance(event_like, (list, tuple, set, str, int, float, bool)):
        raise Stage27ProviderIngestInvalidEventError(
            "event_like is not a NormalizedEventLike",
            offending_type_name=type(event_like).__name__,
        )
    for required in _REQUIRED_NORMALIZED_EVENT_FIELDS:
        if not hasattr(event_like, required):
            raise Stage27ProviderIngestInvalidEventError(
                f"event_like missing required field {required!r}",
                offending_type_name=type(event_like).__name__,
            )


def adapt_normalized_event_to_ingest_input(
    event_like: NormalizedEventLike,
    *,
    provider_id: Optional[str] = None,
    pool_account: Optional[str] = None,
    pool_program_id: Optional[str] = None,
    base_mint: Optional[str] = None,
    quote_mint: Optional[str] = None,
    bonding_curve_program_id: Optional[str] = None,
    bonding_curve_version_hint: Optional[str] = None,
    migration_event_quote_asset_hint: Optional[str] = None,
    provider_quote_asset_hint: Optional[str] = None,
    provider_pair_type_hint: Optional[str] = None,
    provider_bonding_curve_version_hint: Optional[str] = None,
    source_summary: Optional[str] = None,
    extra_fields: Optional[Mapping[str, object]] = None,
) -> ProviderIngestInputRecord:
    """Project a normalized event into a Stage 27.3 ingest input record.

    The caller supplies the Stage 27.3-specific provenance fields
    (``provider_id`` / pool / pair hints) as keyword arguments;
    Stage 27.3 does NOT pull these from the upstream event because
    the upstream Protocol does not own them. The Stage 27.3 ingest
    input is the canonical pair-detection input shape.

    Hard rules:

      * The upstream raw payload blob is NEVER copied -- the adapter
        uses only the upstream ``raw_event_hash`` as a stable
        ``raw_capture_ref`` handle.
      * Missing / non-string upstream fields fall through as
        ``None``; the composer downstream skips deterministically.
      * ``extra_fields`` carrying a raw-payload-class key is
        rejected outright via
        ``reject_raw_payload_fields``.
      * Unknown event-type strings resolve to
        ``EVENT_KIND_UNKNOWN``; the composer skips them.
      * The adapter never reads the process environment.

    Raises:

      * ``Stage27ProviderIngestInvalidEventError`` for a structurally
        invalid ``event_like`` (``None``, raw dict, list, scalar,
        or missing required attribute).
      * ``Stage27ProviderIngestRawPayloadRejectedError`` for an
        ``extra_fields`` mapping carrying a forbidden key.

    Pure / deterministic.
    """
    _assert_event_like_shape(event_like)
    reject_raw_payload_fields(extra_fields)

    event_kind = classify_event_kind(
        getattr(event_like, "event_type", None)
    )
    # ``classify_event_kind`` is closed-set; defensively re-check.
    if event_kind not in EVENT_KIND_VALUES:
        event_kind = EVENT_KIND_UNKNOWN

    return ProviderIngestInputRecord(
        provider_id=(
            provider_id
            if isinstance(provider_id, str) and provider_id != ""
            else _safe_attr(event_like, "provider_name")
        ),
        provider_event_id=_safe_attr(
            event_like, "provider_event_id"
        ),
        normalized_event_id=_safe_attr(event_like, "event_id"),
        event_kind=event_kind,
        observed_at_utc=_safe_attr(event_like, "observed_at_utc"),
        token_mint=_safe_attr(event_like, "mint"),
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        base_mint=base_mint,
        quote_mint=quote_mint,
        bonding_curve_program_id=bonding_curve_program_id,
        bonding_curve_version_hint=bonding_curve_version_hint,
        migration_event_quote_asset_hint=(
            migration_event_quote_asset_hint
        ),
        provider_quote_asset_hint=provider_quote_asset_hint,
        provider_pair_type_hint=provider_pair_type_hint,
        provider_bonding_curve_version_hint=(
            provider_bonding_curve_version_hint
        ),
        raw_capture_ref=_safe_attr(event_like, "raw_event_hash"),
        source_summary=source_summary,
    )


# ---------------------------------------------------------------------------
# Stage 27.3 ingest input -> Stage 27.2 pair-detection input
# ---------------------------------------------------------------------------


def adapt_ingest_input_to_pair_input(
    record: ProviderIngestInputRecord,
) -> PairDetectionInputRecord:
    """Project a Stage 27.3 ingest input into the Stage 27.2
    pair-detection input shape.

    The Stage 27.3 ingest input carries provider provenance + pair
    hints. Stage 27.2's pair-detection input carries only the pair-
    detection-relevant subset. This adapter is the seam where the
    two layers connect.

    Pure / deterministic.

    Raises ``Stage27ProviderIngestInvalidEventError`` if ``record``
    is not a ``ProviderIngestInputRecord``.
    """
    if not isinstance(record, ProviderIngestInputRecord):
        raise Stage27ProviderIngestInvalidEventError(
            "record must be a ProviderIngestInputRecord",
            offending_type_name=type(record).__name__,
        )
    return PairDetectionInputRecord(
        event_id=record.normalized_event_id,
        token_mint=record.token_mint,
        pool_account=record.pool_account,
        pool_program_id=record.pool_program_id,
        base_mint=record.base_mint,
        quote_mint=record.quote_mint,
        bonding_curve_program_id=record.bonding_curve_program_id,
        bonding_curve_version_hint=(
            record.bonding_curve_version_hint
        ),
        migration_event_quote_asset_hint=(
            record.migration_event_quote_asset_hint
        ),
        provider_quote_asset_hint=record.provider_quote_asset_hint,
        provider_pair_type_hint=record.provider_pair_type_hint,
        provider_bonding_curve_version_hint=(
            record.provider_bonding_curve_version_hint
        ),
        observed_at_utc=record.observed_at_utc,
        fetched_at_utc=None,
        source_payload_reference=record.raw_capture_ref,
    )
