"""Database boundary placeholders for PHX2.

Uses PEP 562 (``__getattr__`` at module level) to lazily load the
``PHX2.db.connection`` / ``PHX2.db.migrations`` / ``PHX2.db.repositories``
submodules only when a barrel attribute is first accessed. Importing
the ``PHX2.db`` package itself (or any sibling submodule whose import
chain transits through this package -- e.g.
``from PHX2.db.migrations import apply_stage16b_schema``) therefore
loads NONE of the submodules eagerly.

Audit re-finding HIGH (Stage 16B sidecar boundary): importing
``PHX2.stage16b.migrations`` was leaking ``PHX2.config.settings``
(via the previously-eager ``from PHX2.db.connection import ...`` line)
and ``PHX2.models`` (via the previously-eager
``from PHX2.db.repositories import ...`` line) here. Both eager imports
were unconditional side effects of importing the ``PHX2.db`` package.
PEP 562 moves them to first-attribute-access, so the only consumers
that pay the transitive load are those who actually use the barrel
names. Direct submodule imports
(``from PHX2.db.connection import get_phx2_connection``) remain
unchanged.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # type-checker-only resolution of the public attribute surface
    from PHX2.db.connection import (
        get_phoenix1_readonly_connection,
        get_phx2_connection,
    )
    from PHX2.db.migrations import (
        apply_stage4_schema,
        apply_stage5a_schema,
        apply_stage5c1_schema,
        apply_stage9_alert_decision_extension,
        apply_stage9_outcome_windows_recreate,
        apply_stage9_schema,
        migrate_phx2_schema,
    )
    from PHX2.db.repositories import (
        ATHRepository,
        AlertDecisionRepository,
        ClockFeatureRepository,
        DispatchEventRepository,
        FeeWindowRepository,
        FieldFeatureRepository,
        FilterEvaluationRepository,
        MigrationEventRepository,
        OutcomeWindowRepository,
        PriceCurvePointRepository,
        PriceObservationRepository,
        RawPumpSwapEventRepository,
        RepositoryContract,
        RepositoryRegistry,
        ScoreFeatureRepository,
        TokenSequenceRepository,
        repository_registry,
    )


# Map each barrel attribute name to the submodule that owns it. Used by
# ``__getattr__`` to lazily load the submodule on first access.
_LAZY_ATTRS_BY_MODULE: dict[str, tuple[str, ...]] = {
    "PHX2.db.connection": (
        "get_phoenix1_readonly_connection",
        "get_phx2_connection",
    ),
    "PHX2.db.migrations": (
        "apply_stage4_schema",
        "apply_stage5a_schema",
        "apply_stage5c1_schema",
        "apply_stage9_alert_decision_extension",
        "apply_stage9_outcome_windows_recreate",
        "apply_stage9_schema",
        "migrate_phx2_schema",
    ),
    "PHX2.db.repositories": (
        "ATHRepository",
        "AlertDecisionRepository",
        "ClockFeatureRepository",
        "DispatchEventRepository",
        "FeeWindowRepository",
        "FieldFeatureRepository",
        "FilterEvaluationRepository",
        "MigrationEventRepository",
        "OutcomeWindowRepository",
        "PriceCurvePointRepository",
        "PriceObservationRepository",
        "RawPumpSwapEventRepository",
        "RepositoryContract",
        "RepositoryRegistry",
        "ScoreFeatureRepository",
        "TokenSequenceRepository",
        "repository_registry",
    ),
}


_ATTR_TO_MODULE: dict[str, str] = {
    name: module
    for module, names in _LAZY_ATTRS_BY_MODULE.items()
    for name in names
}


__all__ = sorted(_ATTR_TO_MODULE)


def __getattr__(name: str):
    """PEP 562 lazy submodule loader.

    Triggered when a caller accesses an attribute on the package that is
    not yet in the package's ``__dict__``. Imports the responsible
    submodule on first access and caches the resolved attribute back
    into ``globals()`` so subsequent lookups skip this function.
    """

    module_name = _ATTR_TO_MODULE.get(name)
    if module_name is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        )
    submodule = importlib.import_module(module_name)
    value = getattr(submodule, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Combine the package's own ``__dict__`` with the lazy attribute
    names so ``dir(PHX2.db)`` reflects the full public surface."""

    return sorted(set(globals().keys()) | set(_ATTR_TO_MODULE.keys()))
