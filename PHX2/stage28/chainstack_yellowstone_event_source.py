"""Stage 28.10 Chainstack Yellowstone event source.

Stage 28.10 ships an event source that:

  * accepts an injected ``Stage28_10ChainstackYellowstoneClient``
    (the deterministic Stage 28.10 fake in tests, the future real
    Chainstack / Yellowstone client at the operator boundary),
  * validates a caller-supplied
    ``Stage28_10ChainstackYellowstoneConfig`` and refuses
    malformed / unsafe configs BEFORE the client is touched,
  * drains up to ``max_events`` safe-shape payloads from the
    client (the bound is enforced by both the source and the
    client),
  * projects each payload into one ``Stage28_10NormalizedEvent``
    (a NamedTuple that structurally satisfies the Stage 27.3
    ``NormalizedEventLike`` Protocol and carries the Stage 28.10
    pair / pool / bonding-curve hint attributes),
  * is structurally compatible with the Stage 28.9
    ``Stage28_9ProviderEventSource`` Protocol via its
    ``iter_events(max_events)`` method.

The Stage 28.10 event source module imports only stdlib
(``typing``) plus the Stage 28.10 models module + the Stage 28.10
contracts module. It does NOT import Stage 21-27 production code,
does NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import Iterator, Optional

from PHX2.stage28.chainstack_yellowstone_contracts import (
    Stage28_10ChainstackYellowstoneClient,
    Stage28_10ChainstackYellowstoneClientError,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    Stage28_10ChainstackYellowstoneConfig,
    Stage28_10ChainstackYellowstoneError,
    Stage28_10ChainstackYellowstonePayload,
    Stage28_10InvalidNormalizedEventError,
    Stage28_10InvalidPayloadError,
    Stage28_10NormalizedEvent,
    build_normalized_event,
)


# ---------------------------------------------------------------------------
# Stage 28.10 event-source-specific error
# ---------------------------------------------------------------------------


class Stage28_10EventSourceError(
    Stage28_10ChainstackYellowstoneError,
):
    """Raised by the Stage 28.10 event source when readiness or
    arguments fail BEFORE the client is touched.

    Never carries a raw endpoint, token, username, password, or
    raw library traceback. The reason is a closed-set token.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 28.10 event source error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage 28.10 normalized-event-id derivation
# ---------------------------------------------------------------------------


def _derive_normalized_event_id(
    payload: Stage28_10ChainstackYellowstonePayload,
) -> str:
    """Project a payload onto a stable normalized event id string.

    The id is the upstream Yellowstone ``provider_event_id``
    prefixed with the Stage 28.10 stage marker so downstream
    consumers can see at a glance that the event flowed through
    the Stage 28.10 boundary. Pure / deterministic.
    """
    return f"stage28_10_{payload.provider_event_id}"


def _derive_raw_event_hash(
    payload: Stage28_10ChainstackYellowstonePayload,
) -> str:
    """Project a payload onto a stable raw-event-hash handle.

    The hash is NOT cryptographically derived; it is the upstream
    Yellowstone ``signature`` prefixed with the Stage 28.10 stage
    marker. The Stage 27.3 adapter treats the raw-event-hash as a
    stable ``raw_capture_ref`` only -- not the payload itself --
    so the prefix-stamp form is sufficient. Pure / deterministic.
    """
    return f"stage28_10_{payload.signature}"


# ---------------------------------------------------------------------------
# Payload -> Stage28_10NormalizedEvent projection
# ---------------------------------------------------------------------------


def project_payload_to_normalized_event(
    payload: Stage28_10ChainstackYellowstonePayload,
) -> Stage28_10NormalizedEvent:
    """Project one Stage 28.10 payload into one Stage 28.10
    normalized event.

    Pure / deterministic. The projection:

      * copies the upstream mint / event-type / observed-time
        verbatim,
      * derives a stable Stage-28.10-prefixed normalized event id
        from the upstream provider event id,
      * derives a stable Stage-28.10-prefixed raw-event-hash from
        the upstream signature,
      * carries the pair / pool / bonding-curve hints forward when
        the payload exposes them; missing hints stay ``None`` (no
        silent SOL promotion, no hint fabrication).

    Raises ``Stage28_10InvalidPayloadError`` when the payload is
    not a ``Stage28_10ChainstackYellowstonePayload``. Raises
    ``Stage28_10InvalidNormalizedEventError`` when the derived
    normalized event fails the safe-shape validation contract.
    """
    if not isinstance(
        payload, Stage28_10ChainstackYellowstonePayload,
    ):
        raise Stage28_10InvalidPayloadError(
            field_name="payload",
            reason="NOT_A_PAYLOAD_RECORD",
        )
    return build_normalized_event(
        event_id=_derive_normalized_event_id(payload),
        provider_event_id=payload.provider_event_id,
        provider_name=payload.provider_name,
        mint=payload.mint,
        event_type=payload.event_type,
        observed_at_utc=payload.observed_at_utc,
        raw_event_hash=_derive_raw_event_hash(payload),
        quote_mint=payload.quote_mint,
        pool_account=payload.pool_account,
        pool_program_id=payload.pool_program_id,
        base_mint=payload.base_mint,
        bonding_curve_program_id=None,
        bonding_curve_version_hint=(
            payload.bonding_curve_version_hint
        ),
        provider_quote_asset_hint=(
            payload.provider_quote_asset_hint
        ),
        provider_pair_type_hint=payload.provider_pair_type_hint,
        provider_bonding_curve_version_hint=(
            payload.provider_bonding_curve_version_hint
        ),
    )


# ---------------------------------------------------------------------------
# Stage 28.10 event source
# ---------------------------------------------------------------------------


class Stage28_10ChainstackYellowstoneEventSource:
    """Stage 28.10 Chainstack Yellowstone event source.

    Construction:

      * ``config`` -- ``Stage28_10ChainstackYellowstoneConfig``
                       constructed via
                       ``build_chainstack_yellowstone_config(...)``
                       (the constructor refuses unsafe values).
      * ``client`` -- any object satisfying the
                       ``Stage28_10ChainstackYellowstoneClient``
                       Protocol; tests inject the deterministic
                       ``Stage28_10ChainstackYellowstoneFakeClient``.

    The source's ``iter_events`` method:

      * honours ``max_events`` exactly (the cap is the smaller of
        the caller-supplied ``max_events`` and
        ``config.max_events``),
      * refuses ``max_events <= 0`` with a typed
        ``Stage28_10EventSourceError``,
      * yields a stream of ``Stage28_10NormalizedEvent`` objects
        (which structurally satisfy the Stage 27.3
        ``NormalizedEventLike`` Protocol),
      * swallows per-payload typed projection errors deterministically
        (the offending payload is skipped, the source continues),
      * never opens a network connection itself (the injected
        client owns transport),
      * never reads the process environment,
      * never echoes a raw endpoint / token / username / password
        on any record or exception.
    """

    def __init__(
        self,
        *,
        config: Stage28_10ChainstackYellowstoneConfig,
        client: Stage28_10ChainstackYellowstoneClient,
    ) -> None:
        if not isinstance(
            config, Stage28_10ChainstackYellowstoneConfig,
        ):
            raise Stage28_10EventSourceError("CONFIG_NOT_A_CONFIG")
        if not hasattr(client, "iter_yellowstone_events"):
            raise Stage28_10EventSourceError(
                "CLIENT_MISSING_ITER_METHOD"
            )
        self._config: Stage28_10ChainstackYellowstoneConfig = (
            config
        )
        self._client: Stage28_10ChainstackYellowstoneClient = (
            client
        )
        self._iter_count: int = 0
        self._payloads_seen: int = 0
        self._normalized_yielded: int = 0
        self._payloads_skipped_malformed: int = 0
        self._last_client_error_reason: Optional[str] = None

    @property
    def iter_count(self) -> int:
        return self._iter_count

    @property
    def payloads_seen(self) -> int:
        return self._payloads_seen

    @property
    def normalized_yielded(self) -> int:
        return self._normalized_yielded

    @property
    def payloads_skipped_malformed(self) -> int:
        return self._payloads_skipped_malformed

    @property
    def last_client_error_reason(self) -> Optional[str]:
        return self._last_client_error_reason

    @property
    def config(self) -> Stage28_10ChainstackYellowstoneConfig:
        return self._config

    def iter_events(
        self, *, max_events: int,
    ) -> Iterator[Stage28_10NormalizedEvent]:
        if (
            isinstance(max_events, bool)
            or not isinstance(max_events, int)
        ):
            raise Stage28_10EventSourceError(
                "MAX_EVENTS_NOT_INT"
            )
        if max_events <= 0:
            raise Stage28_10EventSourceError(
                "MAX_EVENTS_NOT_POSITIVE"
            )
        effective_bound = min(max_events, self._config.max_events)
        if effective_bound <= 0:
            raise Stage28_10EventSourceError(
                "EFFECTIVE_BOUND_NOT_POSITIVE"
            )
        self._iter_count += 1
        try:
            payload_iter = self._client.iter_yellowstone_events(
                max_events=effective_bound,
            )
        except Stage28_10ChainstackYellowstoneClientError as err:
            # Typed client-readiness failure (e.g. transport hiccup
            # at iteration setup). The Stage 28.10 source records
            # the reason and yields nothing for this invocation;
            # the bounded Stage 28.6 + Stage 28.9 orchestration
            # absorbs the empty stream deterministically.
            self._last_client_error_reason = err.reason
            return
        yielded = 0
        for payload in payload_iter:
            if yielded >= effective_bound:
                return
            self._payloads_seen += 1
            if not isinstance(
                payload,
                Stage28_10ChainstackYellowstonePayload,
            ):
                self._payloads_skipped_malformed += 1
                continue
            try:
                normalized = project_payload_to_normalized_event(
                    payload,
                )
            except (
                Stage28_10InvalidPayloadError,
                Stage28_10InvalidNormalizedEventError,
            ):
                self._payloads_skipped_malformed += 1
                continue
            yielded += 1
            self._normalized_yielded += 1
            yield normalized


__all__ = (
    "Stage28_10EventSourceError",
    "Stage28_10ChainstackYellowstoneEventSource",
    "project_payload_to_normalized_event",
)
