"""Neutral intermediate representation for a rendered PHX2 alert.

This module defines :class:`RenderedAlert`, the contract between the renderer
and any output adapter (plain text in 8A, Discord embed in 8C). The renderer
produces a ``RenderedAlert`` from a :class:`PHX2.renderers.context.RenderingContext`;
adapters consume one without ever touching the database, the network, or the
clock.

The disclaimer banner is held as a field on the dataclass — not generated
inside an adapter — so adapters cannot accidentally drop it.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from PHX2.models.enums import DataStatus, DecisionType


DRY_RUN_BANNER = "[PHX2 DRY RUN — DO NOT TRADE]"


class Severity(str, Enum):
    """Severity level for a rendered alert.

    Adapters key visual treatments off this (e.g., the future Discord adapter
    in 8C will pick an embed color from severity).
    """

    CLEAN = "clean"
    PARTIAL = "partial"
    ERROR = "error"
    INFO = "info"


# The engine writes one of: OK, PARTIAL, MISSING, ERROR to AlertDecision.data_status.
# Only PARTIAL maps to the renderer's PARTIAL severity bucket.
# MISSING and ERROR are handled via decision_type, not data_status.
# If the engine begins emitting new data_status values, update this set explicitly
# rather than mapping speculatively here.
PARTIAL_DATA_STATUSES = frozenset({DataStatus.PARTIAL})


def derive_severity(decision_type: DecisionType, data_status: DataStatus) -> Severity:
    """Return the severity for a decision/data_status combination.

    Rules:
    * ``ERROR`` decisions → ``Severity.ERROR``.
    * ``WOULD_ALERT`` with partial-or-worse data status → ``Severity.PARTIAL``.
    * ``WOULD_ALERT`` with clean (``OK``) data → ``Severity.CLEAN``.
    * ``SKIP`` and ``BLOCK`` → ``Severity.INFO``.
    """

    if decision_type == DecisionType.ERROR:
        return Severity.ERROR
    if decision_type == DecisionType.WOULD_ALERT:
        if data_status in PARTIAL_DATA_STATUSES:
            return Severity.PARTIAL
        return Severity.CLEAN
    return Severity.INFO


@dataclass(frozen=True)
class RenderedAlert:
    """Pure data carrying everything an adapter needs to format an alert.

    All section dicts are simple ``str → str`` maps so adapters do not have to
    re-format. Adapters MAY group or reorder fields, but they MUST NOT drop the
    banner or the missing_section.
    """

    banner: str
    severity: Severity
    decision_type: str
    tier_label: str | None
    headline: str
    alert_decision_id: Optional[int] = None
    token_section: Dict[str, str] = field(default_factory=dict)
    market_section: Dict[str, str] = field(default_factory=dict)
    ath_section: Dict[str, str] = field(default_factory=dict)
    field_section: Dict[str, str] = field(default_factory=dict)
    clock_section: Dict[str, str] = field(default_factory=dict)
    missing_section: List[str] = field(default_factory=list)
    footer: Dict[str, str] = field(default_factory=dict)
