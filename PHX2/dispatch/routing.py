"""Flat routing lookup for the dispatcher.

A :data:`RoutingConfig` maps a (decision_type, severity) pair to the ordered
list of sink names that should receive the rendered alert. Severity keys are
the values of :class:`PHX2.renderers.rendered_alert.Severity` enum members
expressed as their ``.name`` (uppercase, e.g. ``"CLEAN"``, ``"PARTIAL"``,
``"INFO"``, ``"ERROR"``).

The lookup never raises; an unconfigured combination returns ``[]``.
"""

from typing import Dict, List, Set

from PHX2.models.enums import DecisionType
from PHX2.renderers.rendered_alert import Severity


RoutingConfig = Dict[str, Dict[str, List[str]]]


VALID_DECISION_TYPES = frozenset(dt.value for dt in DecisionType)
VALID_SEVERITIES = frozenset(s.name for s in Severity)


def resolve_sinks(
    config: RoutingConfig,
    decision_type: str,
    severity: str,
) -> List[str]:
    """Return the configured sink names for the given combination.

    Returns an empty list if either ``decision_type`` or ``severity`` is not
    configured. Callers can distinguish "no sinks configured" from "sink list
    explicitly empty" by inspecting ``config`` directly.
    """

    bucket = config.get(decision_type)
    if bucket is None:
        return []
    sinks = bucket.get(severity)
    if sinks is None:
        return []
    return list(sinks)


def validate_routing_config(
    routing: RoutingConfig,
    registered_sink_names: Set[str],
) -> None:
    """Validate a routing config at Dispatcher construction.

    Raises ValueError with a precise message if the config contains:
      - an unknown decision_type key (must be DecisionType.value)
      - an unknown severity key (must be Severity.name)
      - a sink name not in registered_sink_names
      - a malformed structure (severity_map not a dict, sink list not a list)

    This catches stringly-typed drift at construction time, before any
    decision is evaluated.
    """

    errors: List[str] = []
    for decision_type, severity_map in routing.items():
        if decision_type not in VALID_DECISION_TYPES:
            errors.append(
                f"unknown decision_type {decision_type!r}; "
                f"valid: {sorted(VALID_DECISION_TYPES)}"
            )
            continue
        if not isinstance(severity_map, dict):
            errors.append(
                f"routing[{decision_type!r}] must be dict, "
                f"got {type(severity_map).__name__}"
            )
            continue
        for severity, sink_list in severity_map.items():
            if severity not in VALID_SEVERITIES:
                errors.append(
                    f"unknown severity {severity!r} under decision_type {decision_type!r}; "
                    f"valid: {sorted(VALID_SEVERITIES)}"
                )
                continue
            if not isinstance(sink_list, list):
                errors.append(
                    f"routing[{decision_type!r}][{severity!r}] must be list, "
                    f"got {type(sink_list).__name__}"
                )
                continue
            for sink_name in sink_list:
                if sink_name not in registered_sink_names:
                    errors.append(
                        f"unknown sink {sink_name!r} in routing[{decision_type!r}][{severity!r}]; "
                        f"registered: {sorted(registered_sink_names)}"
                    )
    if errors:
        raise ValueError(
            "Invalid routing config:\n  " + "\n  ".join(errors)
        )
