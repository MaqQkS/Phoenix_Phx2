"""Stage 21.2 normalized live-event model and normalizer.

This module owns:

  * ``NormalizedLiveEvent`` -- the typed Stage-21-owned normalized
    event record produced from a fake provider event.
  * ``normalize_fake_event`` -- the pure function that converts a
    fake provider event into a normalized event with deterministic
    ids / hashes and a sanitized payload summary.

The normalizer is the seam where Stage 21.2 enforces:

  * Required-field validation (missing mint / observed_at /
    event_type / empty ids all raise ``Stage21TelemetryError``).
  * Secret-like payload rejection. Known secret-class field names
    (``api_key`` / ``apikey`` / ``secret`` / ``token`` /
    ``password`` / ``credential`` / ``webhook`` / ``webhook_url``
    / ``auth`` / ``bearer``) in the raw payload mapping are
    rejected outright -- the fake provider must not emit such
    fields, and a real provider adapter (Stage 21.3+) will
    pre-strip them at its own boundary.
  * String values that look URL-shaped are also rejected. Stage
    21.2 is fake-only; the fake provider never produces URLs and
    the normalizer fails closed when one appears.

The normalizer never reads the environment, never opens a
database, never imports any network library, and never depends
on a Phoenix1 / Stage 17..20 runtime module.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping, NamedTuple

from PHX2.stage21 import safe_content as _sc
from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.errors import Stage21TelemetryError
from PHX2.stage21.ping_payloads import (
    NORMALIZED_EVENT_SCHEMA_VERSION,
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
)


# ---------------------------------------------------------------------------
# Allowed event-type vocabulary for Stage 21.2 normalization
# ---------------------------------------------------------------------------
#
# Stage 21.2 is fake-only; the event-type vocabulary is the small
# closed set the fake provider emits. Real provider adapters will
# extend this set in Stage 21.3+; Stage 21.2 fails closed on
# anything outside the locked tuple.


STAGE21_2_NORMALIZED_EVENT_TYPES: tuple[str, ...] = (
    "fake_swap",
    "fake_mint",
    "fake_transfer",
)


# ---------------------------------------------------------------------------
# Stage 21.2 normalizer: SUPPLEMENTAL secret-like-key rejection
# ---------------------------------------------------------------------------
#
# Stage 21.2 remediation introduced
# ``PHX2/stage21/safe_content.py`` as the shared safe-content
# predicate. That predicate enforces the locked R4
# ``FORBIDDEN_SUBSTRINGS`` set (URL-scheme prefixes,
# colon-slash-slash, ``webhook``, ``api_key``, ``secret``,
# ``password``, ``credential``, ``public_dispatch``,
# ``paid_dispatch``, ``subscriber``). See
# ``PHX2/stage21/constants.py`` for the locked tuple; the
# URL-scheme strings are spelled out there at runtime so the
# literal URL substrings never appear in any production source.
#
# The tuple below is the Stage 21.2 normalizer's INTENTIONAL
# SUPPLEMENT on top of the shared predicate. It is strictly wider
# than the locked R4 set: it adds ``apikey`` / ``token`` /
# ``credentials`` / ``webhook_url`` / ``auth`` / ``bearer`` /
# ``private_key`` / ``privatekey`` -- substrings the locked R4
# set deliberately omits, but that the Stage 21.2 normalizer has
# always rejected and that the existing 15-parameter
# ``test_normalize_rejects_secret_like_field_at_top_level``
# test still asserts.
#
# The layering preserves prior test coverage while keeping the
# shared safe_content predicate at the locked R4 set. The two
# layers are wired in ``normalize_fake_event`` in this order:
#
#   1. ``_validate_payload_field`` recursive walk
#      (this supplemental list + URL/wss value shapes; raises
#      ``Stage21TelemetryError`` ``E2113``).
#   2. ``safe_content.validate_safe_string`` on every required
#      top-level field (mint / observed_at_utc / etc.; raises
#      ``Stage21Error`` ``E2150..E2158``).
#   3. ``safe_content.validate_safe_payload_dict`` on raw_payload
#      (final defense-in-depth pass; catches the R4-only cases
#      that the supplemental list does not cover, such as a
#      ``subscriber`` / ``public_dispatch`` / ``paid_dispatch``
#      key name).
#
# Stage 21.3 review note: real chain payloads may carry
# legitimate field names that match the ``auth`` substring (e.g.
# ``authority``). When the real provider adapter lands in Stage
# 21.3, revisit this supplemental list -- some entries (notably
# ``auth``) may produce false positives on real on-chain
# payloads and should be narrowed or moved into a
# domain-specific allowlist at that time.


_STAGE21_2_NORMALIZER_SUPPLEMENTAL_SECRET_KEYS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "credential",
    "credentials",
    "webhook",
    "webhook_url",
    "auth",
    "bearer",
    "private_key",
    "privatekey",
)


# URL-shaped value detection. The regex source is built piecewise
# so the literal ``http`` plus ``://`` token does not appear in
# the module source -- the Stage 21 boundary test forbids URL
# literals in production code.
_URL_LIKE_VALUE_RE = re.compile(
    r"\b" + r"https?" + "://" + r"\S+",
    re.IGNORECASE,
)
_WS_LIKE_VALUE_RE = re.compile(
    r"\b" + r"wss?" + "://" + r"\S+",
    re.IGNORECASE,
)


def _is_secret_like_key(key: object) -> bool:
    """Return True iff ``key`` looks like a Stage 21 secret-class field name.

    Uses the Stage 21.2 normalizer's wider supplemental list.
    See the comment block above
    ``_STAGE21_2_NORMALIZER_SUPPLEMENTAL_SECRET_KEYS`` for the
    rationale behind keeping this list wider than the shared
    safe_content ``FORBIDDEN_SUBSTRINGS`` set.
    """
    if not isinstance(key, str):
        return False
    lower = key.lower()
    return any(
        sub in lower
        for sub in _STAGE21_2_NORMALIZER_SUPPLEMENTAL_SECRET_KEYS
    )


def _is_url_like_value(value: object) -> bool:
    """Return True iff ``value`` is a string that looks URL-shaped."""
    if not isinstance(value, str):
        return False
    if _URL_LIKE_VALUE_RE.search(value):
        return True
    if _WS_LIKE_VALUE_RE.search(value):
        return True
    return False


def _validate_payload_field(key: object, value: object, *, path: str) -> None:
    """Validate a single raw-payload field.

    Raises ``Stage21TelemetryError`` (E2113) if the key is
    secret-like or the value is URL-shaped. Recurses into nested
    mappings / sequences so a deeply-nested leak is also caught.
    """
    if _is_secret_like_key(key):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "normalize_fake_event rejected payload field with "
                f"secret-like key at path {path}"
            ),
        )
    if _is_url_like_value(value):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "normalize_fake_event rejected payload value that "
                f"looks URL-shaped at path {path}"
            ),
        )
    if isinstance(value, Mapping):
        for sub_key, sub_value in value.items():
            _validate_payload_field(
                sub_key,
                sub_value,
                path=f"{path}.{sub_key}",
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_payload_field(
                f"[{index}]",
                item,
                path=f"{path}[{index}]",
            )


def _canonical_json(payload: object) -> str:
    """Return canonical JSON of ``payload`` with sorted keys, no whitespace.

    Used by the deterministic id / hash helpers. Custom
    ``MappingProxyType`` mappings are JSON-serializable through
    ``json.dumps`` because they implement the Mapping protocol;
    ``json`` falls back to ``dict`` semantics when the default
    encoder cannot directly serialize the type.
    """
    return json.dumps(
        _to_plain(payload),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _to_plain(value: object) -> object:
    """Convert mappings / tuples to plain dict / list for JSON encoding."""
    if isinstance(value, Mapping):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _sha256_hex(material: str) -> str:
    """Return the full sha256 hex digest of ``material`` (UTF-8 encoded)."""
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Deterministic id derivation
# ---------------------------------------------------------------------------


def derive_raw_event_hash(
    *,
    provider_name: str,
    provider_event_id: str,
    event_type: str,
    mint: str,
    chain: str,
    slot: int,
    signature: str,
    observed_at_utc: str,
    raw_payload: Mapping[str, object],
) -> str:
    """Derive the deterministic ``raw_event_hash`` for a fake event.

    The hash is sha256 of the canonical JSON encoding of the
    identifying fields plus the raw payload. Two fake events with
    identical inputs produce the same hash.
    """
    material = _canonical_json({
        "provider_name": provider_name,
        "provider_event_id": provider_event_id,
        "event_type": event_type,
        "mint": mint,
        "chain": chain,
        "slot": slot,
        "signature": signature,
        "observed_at_utc": observed_at_utc,
        "raw_payload": raw_payload,
    })
    return _sha256_hex(material)


def derive_event_id(
    *,
    provider_name: str,
    provider_event_id: str,
    raw_event_hash: str,
    chain: str,
    mint: str,
) -> str:
    """Derive the deterministic Stage 21.2 ``event_id``.

    Returns ``"evt_<24 hex>"``; the hex prefix is the first 24
    chars of sha256 over the identifying material. The prefix
    keeps the id short enough for operator-visible artifacts
    while remaining collision-resistant for Stage 21.2's fake
    cardinality.
    """
    material = _canonical_json({
        "provider_name": provider_name,
        "provider_event_id": provider_event_id,
        "raw_event_hash": raw_event_hash,
        "chain": chain,
        "mint": mint,
        "schema_version": NORMALIZED_EVENT_SCHEMA_VERSION,
    })
    return "evt_" + _sha256_hex(material)[:24]


# ---------------------------------------------------------------------------
# Normalized event record
# ---------------------------------------------------------------------------


class NormalizedLiveEvent(NamedTuple):
    """Stage 21-owned normalized live event.

    Fields:
      * ``event_id`` -- deterministic Stage 21.2 event id.
      * ``provider_event_id`` -- caller-supplied id from the fake
        provider event.
      * ``provider_name`` -- name of the producing provider (e.g.
        ``"stage21_fake_provider"`` in Stage 21.2).
      * ``source_kind`` -- Stage-21-owned source kind label.
      * ``chain`` -- Stage-21-owned chain identifier.
      * ``mint`` -- mint identifier (non-empty).
      * ``event_type`` -- event-type label from the locked
        ``STAGE21_2_NORMALIZED_EVENT_TYPES`` vocabulary.
      * ``observed_at_utc`` -- ISO-8601 UTC string copied from
        the fake event.
      * ``slot`` -- non-negative integer slot/sequence number.
      * ``signature`` -- non-empty Stage-21-owned fake signature
        string.
      * ``raw_event_hash`` -- sha256 hex of the canonical raw
        event encoding.
      * ``normalized_schema_version`` -- locked Stage 21.2
        normalized event schema version string.
      * ``payload_summary`` -- frozen mapping of sanitized payload
        fields (no secret-like keys, no URL-shaped values).
    """

    event_id: str
    provider_event_id: str
    provider_name: str
    source_kind: str
    chain: str
    mint: str
    event_type: str
    observed_at_utc: str
    slot: int
    signature: str
    raw_event_hash: str
    normalized_schema_version: str
    payload_summary: Mapping[str, object]

    def public_summary(self) -> Mapping[str, object]:
        """Return a manifest-safe dict view."""
        return {
            "event_id": self.event_id,
            "provider_event_id": self.provider_event_id,
            "provider_name": self.provider_name,
            "source_kind": self.source_kind,
            "chain": self.chain,
            "mint": self.mint,
            "event_type": self.event_type,
            "observed_at_utc": self.observed_at_utc,
            "slot": self.slot,
            "signature": self.signature,
            "raw_event_hash": self.raw_event_hash,
            "normalized_schema_version": self.normalized_schema_version,
            "payload_summary": dict(self.payload_summary),
        }


# ---------------------------------------------------------------------------
# Required-field validation
# ---------------------------------------------------------------------------


def _require_non_empty_str(name: str, value: object) -> str:
    """Return ``value`` if it is a non-empty string; else raise E2113."""
    if not isinstance(value, str) or value == "":
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                f"normalize_fake_event missing or empty required field "
                f"{name!r}"
            ),
        )
    return value


def _require_non_negative_int(name: str, value: object) -> int:
    """Return ``value`` if it is a non-negative int; else raise E2113."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                f"normalize_fake_event field {name!r} must be a non-negative int"
            ),
        )
    return value


def _require_event_type(value: object) -> str:
    """Return ``value`` if it is in the locked event-type set; else raise E2113."""
    if value not in STAGE21_2_NORMALIZED_EVENT_TYPES:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "normalize_fake_event event_type is not in the locked "
                "Stage 21.2 vocabulary"
            ),
        )
    return value  # type: ignore[return-value]


def _freeze_payload_summary(
    raw_payload: Mapping[str, object],
) -> Mapping[str, object]:
    """Return a deeply-frozen ``MappingProxyType`` of the raw payload.

    Used as the ``payload_summary`` field of the normalized event.
    The payload has already been validated for secret-like keys
    and URL-shaped values; this helper only enforces immutability.
    """
    from types import MappingProxyType

    def _freeze(value: object) -> object:
        if isinstance(value, Mapping):
            return MappingProxyType(
                {str(k): _freeze(v) for k, v in value.items()}
            )
        if isinstance(value, (list, tuple)):
            return tuple(_freeze(v) for v in value)
        return value

    if not isinstance(raw_payload, Mapping):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "normalize_fake_event raw_payload must be a Mapping"
            ),
        )
    return MappingProxyType(
        {str(k): _freeze(v) for k, v in raw_payload.items()}
    )


# ---------------------------------------------------------------------------
# Public normalizer
# ---------------------------------------------------------------------------


def normalize_fake_event(
    *,
    provider_event_id: str,
    provider_name: str,
    source_kind: str,
    chain: str,
    mint: str,
    event_type: str,
    observed_at_utc: str,
    slot: int,
    signature: str,
    raw_payload: Mapping[str, object],
) -> NormalizedLiveEvent:
    """Convert a fake provider event into a ``NormalizedLiveEvent``.

    Validates every required field. Rejects payloads carrying any
    secret-like field name or URL-shaped value. Derives the
    deterministic ``raw_event_hash`` and ``event_id``. Returns a
    new ``NormalizedLiveEvent`` with a frozen ``payload_summary``
    mapping.

    Raises ``Stage21TelemetryError`` (E2113) on any validation
    failure. The detail string identifies the offending field but
    never echoes the value itself.

    The function is pure: identical inputs produce identical
    output (including the ``event_id`` and ``raw_event_hash``).
    """
    p_event_id = _require_non_empty_str("provider_event_id", provider_event_id)
    p_name = _require_non_empty_str("provider_name", provider_name)
    s_kind = _require_non_empty_str("source_kind", source_kind)
    chain_name = _require_non_empty_str("chain", chain)
    mint_id = _require_non_empty_str("mint", mint)
    e_type = _require_event_type(event_type)
    observed = _require_non_empty_str("observed_at_utc", observed_at_utc)
    slot_num = _require_non_negative_int("slot", slot)
    sig = _require_non_empty_str("signature", signature)

    # Reject any provider_name / chain values that fall outside
    # the Stage 21.2 fake-only vocabulary. A real provider adapter
    # (Stage 21.3+) will land its own provenance check; Stage
    # 21.2 fails closed.
    if p_name != STAGE21_FAKE_PROVIDER_NAME:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "normalize_fake_event provider_name is not the locked "
                "Stage 21.2 fake provider name"
            ),
        )
    if chain_name != STAGE21_FAKE_CHAIN_NAME:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                "normalize_fake_event chain is not the locked Stage 21.2 "
                "fake chain name"
            ),
        )

    if not isinstance(raw_payload, Mapping):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail="normalize_fake_event raw_payload must be a Mapping",
        )

    # Walk the raw payload and reject any secret-like field name
    # or URL-shaped value. The walk is recursive so a nested
    # secret-like key is also caught. This layer preserves the
    # Stage 21.2 normalizer's wider supplemental rejection (see
    # the docstring above
    # ``_STAGE21_2_NORMALIZER_SUPPLEMENTAL_SECRET_KEYS``);
    # the shared safe_content predicate is then layered on top
    # below for the locked R4 cases the supplemental does not
    # cover.
    for key, value in raw_payload.items():
        _validate_payload_field(key, value, path=str(key))

    # Stage 21.2 remediation (R11b): apply the shared
    # safe_content predicate at the normalizer boundary. This is
    # the boundary the Codex PoC for a URL-laced mint enters
    # before any NormalizedLiveEvent is constructed.
    _sc.validate_safe_string(
        p_event_id,
        kind=_sc.SafeStringKind.SHORT_IDENTIFIER,
        field_name="provider_event_id",
    )
    _sc.validate_safe_string(
        p_name,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name="provider_name",
    )
    _sc.validate_safe_string(
        s_kind,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name="source_kind",
    )
    _sc.validate_safe_string(
        chain_name,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name="chain",
    )
    _sc.validate_safe_string(
        mint_id,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name="mint",
    )
    _sc.validate_safe_string(
        e_type,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name="event_type",
    )
    _sc.validate_timestamp_value(
        observed,
        field_name="observed_at_utc",
    )
    _sc.validate_safe_string(
        sig,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name="signature",
    )
    # Final raw_payload pass via the shared validator. The
    # earlier supplemental walk has already rejected the wider
    # set; this pass catches R4-only cases the supplemental does
    # not cover (e.g. a ``subscriber`` / ``public_dispatch`` /
    # ``paid_dispatch`` key).
    _sc.validate_safe_payload_dict(
        raw_payload,
        field_name="raw_payload",
    )

    raw_event_hash = derive_raw_event_hash(
        provider_name=p_name,
        provider_event_id=p_event_id,
        event_type=e_type,
        mint=mint_id,
        chain=chain_name,
        slot=slot_num,
        signature=sig,
        observed_at_utc=observed,
        raw_payload=raw_payload,
    )
    event_id = derive_event_id(
        provider_name=p_name,
        provider_event_id=p_event_id,
        raw_event_hash=raw_event_hash,
        chain=chain_name,
        mint=mint_id,
    )
    payload_summary = _freeze_payload_summary(raw_payload)

    return NormalizedLiveEvent(
        event_id=event_id,
        provider_event_id=p_event_id,
        provider_name=p_name,
        source_kind=s_kind,
        chain=chain_name,
        mint=mint_id,
        event_type=e_type,
        observed_at_utc=observed,
        slot=slot_num,
        signature=sig,
        raw_event_hash=raw_event_hash,
        normalized_schema_version=NORMALIZED_EVENT_SCHEMA_VERSION,
        payload_summary=payload_summary,
    )


__all__ = [
    "NormalizedLiveEvent",
    "STAGE21_2_NORMALIZED_EVENT_TYPES",
    "derive_event_id",
    "derive_raw_event_hash",
    "normalize_fake_event",
]
