"""Filter ABC and FilterContext.

Filters are observe-only classifiers consumed by
FilterEvaluationEngine. They read a FilterContext (decision + feature
snapshot) and produce a FilterResult. Filters must not raise on
missing inputs; they emit a MISSING result instead. ERROR rows are
constructed by the engine when a filter unexpectedly raises.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from PHX2.models import AlertDecision, FieldFeatures, FilterResult


@dataclass(frozen=True)
class FilterContext:
    """Inputs handed to Filter.evaluate by FilterEvaluationEngine."""

    alert_decision_id: int
    token_address: str
    as_of_time: datetime
    alert_decision: AlertDecision
    field_features: Optional[FieldFeatures]


class Filter(ABC):
    """Abstract base class for filters consumed by FilterEvaluationEngine."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier persisted as filter_evaluations.filter_name."""

    @property
    @abstractmethod
    def filter_version(self) -> str:
        """Algorithm version. Bump when scoring logic changes."""

    @property
    @abstractmethod
    def threshold_version(self) -> str:
        """Threshold-band version. Bump when label boundaries change."""

    @property
    @abstractmethod
    def known_limitations(self) -> List[str]:
        """Stable codes describing accepted gaps in this filter's coverage."""

    @abstractmethod
    def evaluate(self, context: FilterContext) -> FilterResult:
        """Compute a FilterResult from the given context.

        Must not raise for missing inputs; emit a MISSING result
        instead. The engine wraps unexpected exceptions into ERROR
        rows.
        """
