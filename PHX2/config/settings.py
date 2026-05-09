"""Typed PHX2 settings.

Stage 2 defines safe configuration boundaries only. It does not load Phoenix1
runtime config, create schemas, open network clients, or send alerts.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple

from PHX2.models.enums import DispatchMode


class RuntimeMode(str, Enum):
    """Supported PHX2 runtime modes."""

    DRY_RUN = "dry_run"
    PRIVATE_OUTPUT = "private_output"
    LIVE = "live"


@dataclass(frozen=True)
class Phoenix1ReadOnlyDbSettings:
    """Phoenix1 database path used for read-only baseline access."""

    path: str = "data/bot.db"


@dataclass(frozen=True)
class PHX2DryRunDbSettings:
    """PHX2 dry-run database path.

    Stage 2 may open this database connection, but it creates no tables.
    """

    path: str = "data/phx2_dryrun.db"


@dataclass(frozen=True)
class FeatureWindowSettings:
    """Feature window configuration for later fee/event materialization."""

    fee_windows_seconds: Tuple[int, ...] = (60, 300, 900, 1800, 3600)


@dataclass(frozen=True)
class OutcomeWindowSettings:
    """Outcome measurement windows for later research exports."""

    outcome_windows_seconds: Tuple[int, ...] = (300, 900, 1800, 3600, 14400, 86400)


@dataclass(frozen=True)
class ScoreVersionSettings:
    """Version marker for future observe-only scoring."""

    score_version: str = "score_v0_observe_only"


@dataclass(frozen=True)
class DispatchSettings:
    """Future dispatch configuration.

    The default is disabled. Stage 2 implements no sending behavior.
    """

    dispatch_mode: DispatchMode = DispatchMode.DISABLED


@dataclass(frozen=True)
class PHX2Settings:
    """Top-level PHX2 settings with dry-run defaults."""

    runtime_mode: RuntimeMode = RuntimeMode.DRY_RUN
    dry_run: bool = True
    phoenix1_db: Phoenix1ReadOnlyDbSettings = field(
        default_factory=Phoenix1ReadOnlyDbSettings
    )
    phx2_db: PHX2DryRunDbSettings = field(default_factory=PHX2DryRunDbSettings)
    feature_windows: FeatureWindowSettings = field(default_factory=FeatureWindowSettings)
    outcome_windows: OutcomeWindowSettings = field(default_factory=OutcomeWindowSettings)
    score: ScoreVersionSettings = field(default_factory=ScoreVersionSettings)
    dispatch: DispatchSettings = field(default_factory=DispatchSettings)
