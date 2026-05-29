"""Stage 30.7.3 offline sanitized upstream ATH-evidence -> Stage 30.7 bridge.

Stage 30.7.3 ships the Stage-30-owned offline bridge that normalizes a
sanitized upstream ATH-evidence shape (the kind of safe scalar summary a
Stage 25 ATH candidate, a Stage 27.4 ATH context record, or a Stage 29.2
Birdeye ATH snapshot can be reduced to) into the Stage 30.7.1 ATH-context
evidence carrier, then reuses the EXISTING Stage 30.7.1 projection + Stage
30.7.2 compact adapter to produce the single safe compact ``ATH`` display
string (a ``$Y`` value or the literal ``Unknown``). This lets future code
feed sanitized upstream ATH context into the compact ping ``ATH`` token
WITHOUT importing any Stage 25 / 27 / 28 / 29 production module and WITHOUT
calling a live provider.

Stage 30 owns the compact ATH projection contract; the upstream sources
own the ATH-measurement semantics. The bridge reads the upstream evidence
SHAPE but Stage 30 maps it onto its own closed sets. Crucially, the bridge
imports NO Stage 25 / 27 / 28 / 29 production module: it consumes a
sanitized, duck-typed scalar input (a Stage-30-owned
``Stage30_7_3SanitizedUpstreamAthEvidence`` dataclass, any attribute-
bearing object, or a plain ``dict``) and reuses only the two Stage 30.7.1
sibling modules (the closed-set models + the Stage 30.7.2 compact adapter,
which itself wraps the Stage 30.7.1 pure projection). There is NO duplicate
projection logic here -- the honest-ATH decision order still lives entirely
in ``project_ath_context``.

The honesty caveat (Stage 30.7.0 spec lock): an upstream ATH is almost
always a PRICE all-time-high (the maximum observed price), not an observed
market cap, because no current source ships the circulating supply at the
historical peak. A faithful bridge of a real upstream price-ATH therefore
maps to a price-derived / no-observed-basis evidence and projects to
``Unknown`` -- which is the correct, conservative outcome. The bridge emits
a ``$Y`` value ONLY when the caller supplies an explicit observed-market-
cap USD basis on the sanitized evidence; the bridge never promotes a price
ATH to a known market cap.

Supported sanitized input fields (read by attribute, by ``dict`` key, or
off the Stage-30-owned dataclass), with upstream-name aliases:

  * value          <- ``ath_value``
  * unit           <- ``ath_unit``
  * source status  <- ``source_status`` then ``ath_status`` (Stage 27.4)
  * basis          <- ``basis`` then ``drawdown_basis`` (Stage 27.4)
  * redaction-safe <- ``redaction_safe``
  * source label   <- ``source_label`` then ``ath_source`` (Stage 27.4)
  * observed clock <- ``observed_at_utc`` then ``ath_observed_at_utc``

The bridge accepts ONLY sanitized scalar fields. It deliberately does NOT
read (and cannot carry) a raw provider payload, a raw transaction
signature, an event log, a source event ref, a provider URL / host, a
secret, an inbound-hook URL, or a Discord destination -- the
``Stage30_7AthContextEvidence`` it builds has no field for any of those. A
nested ``dict`` / ``list`` / ``bytes`` value is rejected (treated as a
missing value) so a raw nested provider object can never flow into the
evidence value slot.

Mapping (sanitized upstream shape -> Stage 30.7 closed sets):

  upstream source status     -> Stage 30.7 source_status
  ---------------------------------------------------------------------------
  PRESENT                    -> PRESENT
  UNAVAILABLE                -> UNAVAILABLE
  STALE                      -> STALE
  CONFLICTING                -> CONFLICTING
  ERROR / SOURCE_ERROR       -> ERROR
  NOT_APPLICABLE /
   UNSUPPORTED_PAIR /
   UNKNOWN / missing /
   unrecognized / non-str    -> UNAVAILABLE   (fail closed)

  upstream unit              -> Stage 30.7 ath_unit
  ---------------------------------------------------------------------------
  USD                        -> USD
  SOL                        -> SOL
  USDC                       -> UNKNOWN        (Stage 30.7.0 never authorized
                                                a USDC ATH display; conservative)
  UNKNOWN / missing /
   unrecognized / non-str    -> UNKNOWN

  upstream basis             -> Stage 30.7 basis
  ---------------------------------------------------------------------------
  ATH_MARKET_CAP_OBSERVED /
   MARKET_CAP_OBSERVED       -> ATH_MARKET_CAP_OBSERVED
  ATH_PRICE_DERIVED /
   PRICE_DERIVED             -> ATH_PRICE_DERIVED
  missing / unknown /
   unrecognized / non-str /
   Stage 27 drawdown_basis
   values (FROM_POST_..)     -> ATH_BASIS_NONE

  upstream redaction_safe    -> Stage 30.7 redaction_safe
  ---------------------------------------------------------------------------
  is exactly True            -> True
  missing / non-True         -> False          (preserves the Stage 30.7.1
                                                fail-closed redaction fix)

The Stage 30.7.1 projection then decides the display: only a PRESENT
source + positive finite value + compatible USD unit + observed-market-cap
basis + redaction_safe True yields ``ATH_KNOWN`` and a ``$Y`` value; every
other normalized evidence fails closed to ``Unknown``. The bridge is TOTAL:
``sanitized_ath_evidence_to_compact_text`` never raises and fails closed to
``Unknown`` for any malformed / nested / raw-like input.

This slice introduces NO drawdown / tier recomputation, NO live ATH probe,
NO renderer / models change, and NO orchestrator edit: the resolver built
by :func:`build_stage30_ath_resolver_from_sanitized_evidence` is the
drop-in object the EXISTING Stage 30.4.2 ``ath_context_resolver`` seam
(added at Stage 30.7.2) already consumes.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Stage 30.7 sibling modules imported read-only (the Stage 30.7.1 models
    + the Stage 30.7.2 compact ATH runtime adapter, which wraps the Stage
    30.7.1 pure projection).
  * No Stage 21-29 production-source import (the upstream ATH evidence is
    consumed as a sanitized duck-typed shape, never imported).
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No provider client, no Discord / Telegram / X / social reference.
  * No filesystem read / write, no database, no zstd.
  * No PHX1 import.
  * No network / env / filesystem I/O at import time (or ever).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PHX2.stage30.stage30_7_ath_context_models import (
    ATH_BASIS_MARKET_CAP_OBSERVED,
    ATH_BASIS_NONE,
    ATH_BASIS_PRICE_DERIVED,
    ATH_DISPLAY_UNKNOWN,
    ATH_SOURCE_STATUS_CONFLICTING,
    ATH_SOURCE_STATUS_ERROR,
    ATH_SOURCE_STATUS_PRESENT,
    ATH_SOURCE_STATUS_STALE,
    ATH_SOURCE_STATUS_UNAVAILABLE,
    ATH_UNIT_SOL,
    ATH_UNIT_UNKNOWN,
    ATH_UNIT_USD,
    STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
    Stage30_7AthContextEvidence,
)
from PHX2.stage30.stage30_7_compact_ath_runtime_adapter import (
    Stage30_7_2AthDisplayResolver,
    build_ath_text_from_evidence,
)


# ---------------------------------------------------------------------------
# Stage 30.7.3 minor version + safe source-family label
# ---------------------------------------------------------------------------


STAGE30_7_3_MINOR_VERSION: str = "30.7.3"


# Stage-30-owned default safe source-family label stamped onto the normalized
# evidence as provenance (NEVER echoed into the compact ATH projection; the
# compact ``ATH`` token is only a ``$Y`` value or the literal ``Unknown``).
STAGE30_7_3_SOURCE_LABEL: str = "sanitized_upstream_ath_evidence"


# ---------------------------------------------------------------------------
# Stage-30-owned mirror of the upstream ATH vocabulary (NOT imported)
# ---------------------------------------------------------------------------
#
# These mirror the upstream Stage 25 / 27.4 / 29.2 ATH status / unit / basis
# tokens the bridge recognizes. They are duplicated here as plain Stage-30-
# owned string literals precisely to preserve the no-Stage-25/27/29-import
# boundary: the bridge recognizes the upstream SHAPE without importing any
# Stage 25 / 27 / 28 / 29 module. If a future upstream spec renames these
# tokens, the divergence is caught by the Stage 30.7.3 mapping tests (which
# document the expected token strings), and an unrecognized token degrades
# conservatively (UNAVAILABLE source / UNKNOWN unit / ATH_BASIS_NONE basis)
# rather than overclaiming.


# Upstream source-status tokens recognized 1:1ish. (Stage 27.4 reports the
# source status on its ``ath_status`` field; Stage 25 on ``source_status``.)
UPSTREAM_ATH_SOURCE_STATUS_PRESENT: str = "PRESENT"
UPSTREAM_ATH_SOURCE_STATUS_UNAVAILABLE: str = "UNAVAILABLE"
UPSTREAM_ATH_SOURCE_STATUS_STALE: str = "STALE"
UPSTREAM_ATH_SOURCE_STATUS_CONFLICTING: str = "CONFLICTING"
UPSTREAM_ATH_SOURCE_STATUS_ERROR: str = "ERROR"
UPSTREAM_ATH_SOURCE_STATUS_SOURCE_ERROR: str = "SOURCE_ERROR"
# Recognized-but-fail-closed upstream statuses (degrade to UNAVAILABLE).
UPSTREAM_ATH_SOURCE_STATUS_NOT_APPLICABLE: str = "NOT_APPLICABLE"
UPSTREAM_ATH_SOURCE_STATUS_UNSUPPORTED_PAIR: str = "UNSUPPORTED_PAIR"
UPSTREAM_ATH_SOURCE_STATUS_UNKNOWN: str = "UNKNOWN"


# Upstream unit tokens. Stage 27.4 admits a USDC unit; Stage 30.7 does not
# (it is mapped to UNKNOWN -> Unknown, never silently treated as USD).
UPSTREAM_ATH_UNIT_USD: str = "USD"
UPSTREAM_ATH_UNIT_SOL: str = "SOL"
UPSTREAM_ATH_UNIT_USDC: str = "USDC"
UPSTREAM_ATH_UNIT_UNKNOWN: str = "UNKNOWN"


# Upstream basis tokens. The ``ATH_``-prefixed forms mirror the Stage 30.7
# basis names; the bare forms tolerate an upstream that omits the prefix.
UPSTREAM_ATH_BASIS_ATH_MARKET_CAP_OBSERVED: str = "ATH_MARKET_CAP_OBSERVED"
UPSTREAM_ATH_BASIS_MARKET_CAP_OBSERVED: str = "MARKET_CAP_OBSERVED"
UPSTREAM_ATH_BASIS_ATH_PRICE_DERIVED: str = "ATH_PRICE_DERIVED"
UPSTREAM_ATH_BASIS_PRICE_DERIVED: str = "PRICE_DERIVED"


# ---------------------------------------------------------------------------
# Closed mapping tables (upstream token -> Stage 30.7 closed-set token)
# ---------------------------------------------------------------------------
#
# Plain dict literals (no Call): a token absent from a map degrades to the
# fail-closed default in the corresponding ``_map_*`` helper. NOT_APPLICABLE
# / UNSUPPORTED_PAIR / UNKNOWN are deliberately absent from the source-status
# map (they degrade to UNAVAILABLE); USDC is deliberately absent from the
# unit map (it degrades to UNKNOWN); the Stage 27 ``drawdown_basis`` values
# are deliberately absent from the basis map (they degrade to
# ATH_BASIS_NONE).


_UPSTREAM_SOURCE_STATUS_MAP = {
    UPSTREAM_ATH_SOURCE_STATUS_PRESENT: ATH_SOURCE_STATUS_PRESENT,
    UPSTREAM_ATH_SOURCE_STATUS_UNAVAILABLE: ATH_SOURCE_STATUS_UNAVAILABLE,
    UPSTREAM_ATH_SOURCE_STATUS_STALE: ATH_SOURCE_STATUS_STALE,
    UPSTREAM_ATH_SOURCE_STATUS_CONFLICTING: ATH_SOURCE_STATUS_CONFLICTING,
    UPSTREAM_ATH_SOURCE_STATUS_ERROR: ATH_SOURCE_STATUS_ERROR,
    UPSTREAM_ATH_SOURCE_STATUS_SOURCE_ERROR: ATH_SOURCE_STATUS_ERROR,
}


_UPSTREAM_UNIT_MAP = {
    UPSTREAM_ATH_UNIT_USD: ATH_UNIT_USD,
    UPSTREAM_ATH_UNIT_SOL: ATH_UNIT_SOL,
}


_UPSTREAM_BASIS_MAP = {
    UPSTREAM_ATH_BASIS_ATH_MARKET_CAP_OBSERVED: ATH_BASIS_MARKET_CAP_OBSERVED,
    UPSTREAM_ATH_BASIS_MARKET_CAP_OBSERVED: ATH_BASIS_MARKET_CAP_OBSERVED,
    UPSTREAM_ATH_BASIS_ATH_PRICE_DERIVED: ATH_BASIS_PRICE_DERIVED,
    UPSTREAM_ATH_BASIS_PRICE_DERIVED: ATH_BASIS_PRICE_DERIVED,
}


# Alias chains read off the sanitized upstream shape (first present wins).
_VALUE_ALIASES: Tuple[str, ...] = ("ath_value",)
_UNIT_ALIASES: Tuple[str, ...] = ("ath_unit",)
_SOURCE_STATUS_ALIASES: Tuple[str, ...] = ("source_status", "ath_status")
_BASIS_ALIASES: Tuple[str, ...] = ("basis", "drawdown_basis")
_REDACTION_SAFE_ALIASES: Tuple[str, ...] = ("redaction_safe",)
_SOURCE_LABEL_ALIASES: Tuple[str, ...] = ("source_label", "ath_source")
_OBSERVED_AT_UTC_ALIASES: Tuple[str, ...] = (
    "observed_at_utc",
    "ath_observed_at_utc",
)


# Value types rejected as a missing value: a nested container can never be a
# scalar ATH value, and rejecting it keeps a raw nested provider object out
# of the evidence value slot.
_REJECTED_VALUE_TYPES = (dict, list, tuple, set, frozenset, bytes, bytearray)


# ---------------------------------------------------------------------------
# Sanitized upstream ATH evidence (Stage-30-owned canonical input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_7_3SanitizedUpstreamAthEvidence:
    """Stage-30-owned sanitized upstream ATH-evidence summary.

    The canonical scalar-shaped input the Stage 30.7.3 bridge accepts. It
    carries ONLY safe sanitized scalar fields; it has no field for a raw
    provider payload, a raw signature, an event log / source event ref, a
    provider URL / host, a secret, an inbound-hook URL, or a Discord
    destination, so a sanitized artifact can never smuggle a raw identifier
    through the bridge.

    The bridge also accepts any attribute-bearing object (read via
    ``getattr``) or a plain ``dict`` (read by key) exposing the same field
    names (or their upstream aliases ``ath_status`` / ``drawdown_basis`` /
    ``ath_source`` / ``ath_observed_at_utc``) -- so a caller may pass a
    sanitized copy of a Stage 27.4 ATH context record without the bridge
    importing Stage 27.

    Fields (all optional; an omitted / off-set field degrades conservatively
    to ``ATH: Unknown``):

      * ``ath_value``       -- candidate ATH value (numeric or decimal-text).
                              A nested container is rejected as missing.
      * ``ath_unit``        -- upstream unit token (``USD`` / ``SOL`` /
                              ``USDC`` / ``UNKNOWN`` / ...).
      * ``source_status``   -- upstream source-status token.
      * ``basis``           -- upstream ATH basis token.
      * ``redaction_safe``  -- ``bool``; only an explicit ``True`` trusts the
                              evidence. Default ``False`` (fail closed).
      * ``source_label``    -- optional short safe-shape source-family label
                              (provenance; never echoed into the compact
                              projection).
      * ``observed_at_utc`` -- optional caller-supplied ISO-8601 UTC string
                              (provenance; never echoed into the compact
                              projection).
    """

    ath_value: object = None
    ath_unit: Optional[str] = None
    source_status: Optional[str] = None
    basis: Optional[str] = None
    redaction_safe: bool = False
    source_label: Optional[str] = None
    observed_at_utc: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers (pure / total)
# ---------------------------------------------------------------------------


_MISSING = object()


def _get(evidence: object, name: str) -> object:
    """Read ``name`` off ``evidence`` by ``dict`` key (when ``evidence`` is a
    ``dict``) or by attribute (otherwise). Returns the module-private
    ``_MISSING`` sentinel when absent. Never raises.
    """
    try:
        if isinstance(evidence, dict):
            return evidence.get(name, _MISSING)
        return getattr(evidence, name, _MISSING)
    except Exception:  # noqa: BLE001 - any access failure => treat as missing
        return _MISSING


def _read_first(evidence: object, aliases: Tuple[str, ...]) -> object:
    """Return the first present (non-``_MISSING``) field among ``aliases``.

    A field that is present but ``None`` counts as present (so an explicit
    ``source_status=None`` does NOT fall through to ``ath_status``); only a
    truly absent field is skipped. Returns ``None`` when no alias is present.
    """
    for name in aliases:
        value = _get(evidence, name)
        if value is not _MISSING:
            return value
    return None


def _map_source_status(raw: object) -> str:
    """Map an upstream source-status token onto a Stage 30.7 source_status.

    Fail-closed default ``UNAVAILABLE`` for a missing / unrecognized /
    non-string / NOT_APPLICABLE / UNSUPPORTED_PAIR / UNKNOWN status.
    """
    if isinstance(raw, str):
        mapped = _UPSTREAM_SOURCE_STATUS_MAP.get(raw)
        if mapped is not None:
            return mapped
    return ATH_SOURCE_STATUS_UNAVAILABLE


def _map_unit(raw: object) -> str:
    """Map an upstream unit token onto a Stage 30.7 ath_unit.

    Fail-closed default ``UNKNOWN`` for a missing / unrecognized /
    non-string / USDC unit (USDC is never silently treated as USD).
    """
    if isinstance(raw, str):
        mapped = _UPSTREAM_UNIT_MAP.get(raw)
        if mapped is not None:
            return mapped
    return ATH_UNIT_UNKNOWN


def _map_basis(raw: object) -> str:
    """Map an upstream basis token onto a Stage 30.7 basis.

    Fail-closed default ``ATH_BASIS_NONE`` for a missing / unrecognized /
    non-string basis (including the Stage 27 ``drawdown_basis`` values,
    which are not ATH-measurement bases).
    """
    if isinstance(raw, str):
        mapped = _UPSTREAM_BASIS_MAP.get(raw)
        if mapped is not None:
            return mapped
    return ATH_BASIS_NONE


def _sanitize_value(raw: object) -> object:
    """Pass a scalar ATH value through; reject a nested container as missing.

    A ``dict`` / ``list`` / ``tuple`` / ``set`` / ``frozenset`` / ``bytes``
    / ``bytearray`` can never be a scalar ATH value and could carry a raw
    nested provider object, so it is dropped to ``None`` (the Stage 30.7.1
    projection then classifies it as a missing value -> ``Unknown``). Every
    other value (numeric / decimal-text / ``None`` / anything the projection
    can fail-close on) is passed through unchanged.
    """
    if isinstance(raw, _REJECTED_VALUE_TYPES):
        return None
    return raw


def _safe_str(raw: object) -> Optional[str]:
    """Return ``raw`` if it is a ``str`` (safe-shape provenance), else
    ``None``. Used for the inert ``source_label`` / ``observed_at_utc``
    provenance fields, which are never echoed into the compact projection.
    """
    if isinstance(raw, str):
        return raw
    return None


# ---------------------------------------------------------------------------
# Public: normalize a sanitized upstream shape -> Stage 30.7.1 evidence
# ---------------------------------------------------------------------------


def sanitized_ath_evidence_to_stage30_evidence(
    raw_evidence: object,
) -> Stage30_7AthContextEvidence:
    """Normalize a sanitized upstream ATH-evidence shape onto a Stage 30.7.1
    ``Stage30_7AthContextEvidence`` carrying Stage 30.7 closed-set tokens.

    See the module docstring for the full mapping table. The returned
    evidence carries only Stage 30.7 closed-set source_status / ath_unit /
    basis tokens, a fail-closed ``bool`` ``redaction_safe``, the passed-
    through (scalar-only) value, and optional safe-shape provenance.

    Total: never raises (a ``None`` / malformed / dict-like / attribute-
    bearing input all resolve through the alias reads + fail-closed maps).
    Never mutates ``raw_evidence``. ``raw_evidence is None`` resolves to an
    ``UNAVAILABLE`` / ``UNKNOWN`` / ``ATH_BASIS_NONE`` / not-redaction-safe
    evidence (which the Stage 30.7.1 projection renders ``Unknown``).
    """
    raw_value = _read_first(raw_evidence, _VALUE_ALIASES)
    raw_unit = _read_first(raw_evidence, _UNIT_ALIASES)
    raw_status = _read_first(raw_evidence, _SOURCE_STATUS_ALIASES)
    raw_basis = _read_first(raw_evidence, _BASIS_ALIASES)
    raw_redaction = _read_first(raw_evidence, _REDACTION_SAFE_ALIASES)
    raw_label = _read_first(raw_evidence, _SOURCE_LABEL_ALIASES)
    raw_observed = _read_first(raw_evidence, _OBSERVED_AT_UTC_ALIASES)

    return Stage30_7AthContextEvidence(
        ath_value=_sanitize_value(raw_value),
        ath_unit=_map_unit(raw_unit),
        source_status=_map_source_status(raw_status),
        basis=_map_basis(raw_basis),
        # Only an explicit True trusts the evidence (preserves the Stage
        # 30.7.1 fail-closed redaction fix).
        redaction_safe=(raw_redaction is True),
        source_label=_safe_str(raw_label),
        observed_at_utc=_safe_str(raw_observed),
    )


# ---------------------------------------------------------------------------
# Public: normalize a sanitized upstream shape -> compact ATH display text
# ---------------------------------------------------------------------------


def sanitized_ath_evidence_to_compact_text(
    raw_evidence: object,
    market_context_unit: str = STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
) -> str:
    """Normalize a sanitized upstream ATH-evidence shape and project it to
    the single safe compact ``ATH`` display string.

    Calls :func:`sanitized_ath_evidence_to_stage30_evidence` and then the
    EXISTING Stage 30.7.2 ``build_ath_text_from_evidence`` (which runs the
    Stage 30.7.1 ``project_ath_context`` + ``ath_projection_to_compact_text``
    -- no duplicate projection logic). Returns a ``$Y`` value ONLY for a
    PRESENT source + positive finite value + compatible USD unit + observed-
    market-cap basis + redaction_safe ``True``; every other input (price-
    derived, redaction-unsafe, SOL, non-PRESENT, unit-incompatible,
    malformed, nested / raw-like) resolves to the literal ``Unknown``.

    Pure / deterministic / offline / TOTAL: NEVER raises (fails closed to
    ``Unknown``), NEVER opens a network connection, reads the environment,
    calls a provider, or touches the filesystem.
    """
    try:
        evidence = sanitized_ath_evidence_to_stage30_evidence(raw_evidence)
        return build_ath_text_from_evidence(
            evidence, market_context_unit=market_context_unit
        )
    except Exception:  # noqa: BLE001 - any failure => Unknown (fail closed)
        return ATH_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# Public: build the Stage 30.7.2 runtime resolver from a sanitized shape
# ---------------------------------------------------------------------------


def build_stage30_ath_resolver_from_sanitized_evidence(
    *,
    raw_evidence: object,
    market_context_unit: str = STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
) -> Stage30_7_2AthDisplayResolver:
    """Build a Stage 30.7.2 ATH display resolver over a sanitized upstream
    ATH-evidence shape.

    The bridge first normalizes ``raw_evidence`` into a Stage 30.7.1
    ``Stage30_7AthContextEvidence`` (Stage 30 closed-set tokens), then wraps
    it in the EXISTING Stage 30.7.2 ``Stage30_7_2AthDisplayResolver``. The
    returned resolver is the drop-in object the Stage 30.4.2 orchestrator's
    opt-in ``ath_context_resolver`` seam (added at Stage 30.7.2) already
    consumes: its ``resolve_display_text(token_mint, observed_at_utc)``
    returns the single safe compact ``ATH`` display string (a ``$Y`` value
    or the literal ``Unknown``) for the normalized evidence. No orchestrator
    edit is required by this slice.
    """
    evidence = sanitized_ath_evidence_to_stage30_evidence(raw_evidence)
    return Stage30_7_2AthDisplayResolver(
        evidence=evidence,
        market_context_unit=market_context_unit,
    )


__all__ = (
    "STAGE30_7_3_MINOR_VERSION",
    "STAGE30_7_3_SOURCE_LABEL",
    # Upstream source-status vocabulary mirror.
    "UPSTREAM_ATH_SOURCE_STATUS_PRESENT",
    "UPSTREAM_ATH_SOURCE_STATUS_UNAVAILABLE",
    "UPSTREAM_ATH_SOURCE_STATUS_STALE",
    "UPSTREAM_ATH_SOURCE_STATUS_CONFLICTING",
    "UPSTREAM_ATH_SOURCE_STATUS_ERROR",
    "UPSTREAM_ATH_SOURCE_STATUS_SOURCE_ERROR",
    "UPSTREAM_ATH_SOURCE_STATUS_NOT_APPLICABLE",
    "UPSTREAM_ATH_SOURCE_STATUS_UNSUPPORTED_PAIR",
    "UPSTREAM_ATH_SOURCE_STATUS_UNKNOWN",
    # Upstream unit vocabulary mirror.
    "UPSTREAM_ATH_UNIT_USD",
    "UPSTREAM_ATH_UNIT_SOL",
    "UPSTREAM_ATH_UNIT_USDC",
    "UPSTREAM_ATH_UNIT_UNKNOWN",
    # Upstream basis vocabulary mirror.
    "UPSTREAM_ATH_BASIS_ATH_MARKET_CAP_OBSERVED",
    "UPSTREAM_ATH_BASIS_MARKET_CAP_OBSERVED",
    "UPSTREAM_ATH_BASIS_ATH_PRICE_DERIVED",
    "UPSTREAM_ATH_BASIS_PRICE_DERIVED",
    # Sanitized input + bridge functions.
    "Stage30_7_3SanitizedUpstreamAthEvidence",
    "sanitized_ath_evidence_to_stage30_evidence",
    "sanitized_ath_evidence_to_compact_text",
    "build_stage30_ath_resolver_from_sanitized_evidence",
)
