"""Rendering context and the only DB-touching component of the renderer.

:class:`RenderingContext` is a frozen, fully pre-fetched bundle of everything
:class:`PHX2.renderers.alert_renderer.AlertRenderer` needs. The context object
itself is pure data and reusable by any adapter.

:class:`RenderingContextAssembler` is the *only* place in the renderer module
tree allowed to import repositories. It is a fan-out fetcher: given an
``AlertDecision`` and a reference time, it loads the small set of related rows
and packs them into a context. Missing rows (deleted, never written) collapse
to ``None`` — the assembler never raises on absent data.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from PHX2.db.repositories import (
    ATHRepository,
    ClockFeatureRepository,
    FieldFeatureRepository,
    PriceObservationRepository,
    TokenSequenceRepository,
)
from PHX2.models import (
    AlertDecision,
    ATHEvent,
    ATHState,
    ClockFeatures,
    FieldFeatures,
    PriceObservation,
    TokenSequenceState,
)


@dataclass(frozen=True)
class RenderingContext:
    """Frozen snapshot of all data needed to render one alert decision.

    ``as_of_time`` is supplied by the caller and is the reference time the
    renderer uses for every relative-age calculation. The renderer never reads
    the wall clock; if ``as_of_time`` is wrong, the rendered durations will be
    wrong, but the renderer remains deterministic.

    ``alert_decision_id`` is the integer primary key of the just-committed
    AlertDecision row. The renderer copies it onto the produced RenderedAlert
    so adapters and sinks can reference the decision by its real id rather
    than reaching back into ``key_feature_snapshot``.
    """

    alert_decision: AlertDecision
    as_of_time: datetime
    alert_decision_id: Optional[int] = None
    token_sequence_state: Optional[TokenSequenceState] = None
    price_observation: Optional[PriceObservation] = None
    ath_event: Optional[ATHEvent] = None
    ath_state: Optional[ATHState] = None
    field_features: Optional[FieldFeatures] = None
    clock_features: Optional[ClockFeatures] = None


class RenderingContextAssembler:
    """Build a :class:`RenderingContext` from one ``AlertDecision``.

    This is a fan-out fetcher, not a service layer. It takes existing
    repositories via constructor injection and performs simple by-id /
    by-token-address lookups. It never writes to the database, never makes
    network calls, and never raises on missing source rows — instead, the
    relevant context slot is left ``None``.
    """

    def __init__(
        self,
        token_sequence: TokenSequenceRepository,
        price_observations: PriceObservationRepository,
        ath: ATHRepository,
        field_features: FieldFeatureRepository,
        clock_features: ClockFeatureRepository,
    ) -> None:
        self.token_sequence = token_sequence
        self.price_observations = price_observations
        self.ath = ath
        self.field_features = field_features
        self.clock_features = clock_features

    def assemble(
        self,
        alert_decision: AlertDecision,
        as_of_time: datetime,
        alert_decision_id: Optional[int] = None,
    ) -> RenderingContext:
        token_address = alert_decision.token_address

        token_state = self.token_sequence.get(token_address)
        ath_state = self.ath.get_state(token_address)

        price_observation = None
        if alert_decision.price_observation_id is not None:
            price_observation = self.price_observations.get_by_id(
                alert_decision.price_observation_id
            )

        ath_event = None
        if alert_decision.ath_event_id is not None:
            ath_event = self.ath.get_event_by_id(alert_decision.ath_event_id)

        field_features = None
        if alert_decision.field_features_id is not None:
            field_features = self.field_features.get_by_id(
                alert_decision.field_features_id
            )

        clock_features = None
        if alert_decision.clock_features_id is not None:
            clock_features = self.clock_features.get_by_id(
                alert_decision.clock_features_id
            )

        return RenderingContext(
            alert_decision=alert_decision,
            as_of_time=as_of_time,
            alert_decision_id=alert_decision_id,
            token_sequence_state=token_state,
            price_observation=price_observation,
            ath_event=ath_event,
            ath_state=ath_state,
            field_features=field_features,
            clock_features=clock_features,
        )
