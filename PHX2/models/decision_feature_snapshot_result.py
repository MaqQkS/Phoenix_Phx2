"""Result wrapper returned by DecisionFeatureSnapshotService.

Mirrors Stage 9's ``DecisionTrackingResult`` and Stage 10's
``DecisionFilterEvaluationResult`` conventions: pure return object, no
persistence and no I/O. Validation failures populate ``error`` with one
of the sentinel strings below and produce ``snapshot=None``;
``error=None`` indicates either a successful insert or an
already-recorded idempotent return (distinguished by
``already_recorded``).
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from PHX2.models.decision_score_features import DecisionScoreFeatures


# Sentinel error strings. Tests assert on the exact vocabulary; do not
# rephrase without bumping callers. Service docstrings cite these by
# name. See Stage 11 Locked Design Spec section 4.3.
ERROR_ALERT_DECISION_NOT_FOUND = "alert_decision_not_found"
ERROR_DECISION_TIME_MISSING = "alert_decision_missing_evaluated_at"
ERROR_DECISION_TYPE_NOT_WOULD_ALERT = "decision_type_not_would_alert"


@dataclass(frozen=True)
class DecisionFeatureSnapshotResult:
    """Wrapper returned by ``DecisionFeatureSnapshotService.snapshot_for_decision``.

    Branch shapes:

    * **Success:** ``snapshot`` populated, ``decision_score_features_id``
      populated, ``already_recorded=False``, ``error=None``.
      ``missing_reasons`` may be non-empty when ``data_status`` is
      ``PARTIAL`` (some upstream missing but the row was still written).
    * **Already recorded:** ``snapshot`` populated from the existing row,
      ``decision_score_features_id`` populated, ``already_recorded=True``,
      ``error=None``. ``missing_reasons`` reflects the persisted row.
    * **Validation failure:** ``snapshot=None``,
      ``decision_score_features_id=None``, ``error`` set to one of the
      three sentinels above, ``already_recorded=False``. No DB write.
    * **UNIQUE race during insert:** treated as Already-recorded after
      re-fetch.
    """

    alert_decision_id: int
    feature_version: str
    snapshot: Optional[DecisionScoreFeatures] = None
    decision_score_features_id: Optional[int] = None
    already_recorded: bool = False
    error: Optional[str] = None
    missing_reasons: Tuple[str, ...] = ()
