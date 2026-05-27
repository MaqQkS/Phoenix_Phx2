"""Stage 29.5.4 forbidden-surface scan over production source +
runbook.

Pins that the Stage 29.5.4 production source, manifest, and
runbook contain NO public / subscriber / paid-tier routing
identifier, NO Stage 26 enforcement activation identifier, NO
automated trading / position sizing / trade execution
identifier, NO wallet / private-key / signer identifier, and NO
Telegram / X / social sidecar identifier.

Also pins that ``filter_enforcement_status`` is locked to
``NOT_ACTIVE_STAGE_29_PENDING`` everywhere Stage 29.5.4 mentions
it.
"""

from __future__ import annotations

import re
from pathlib import Path


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"


_STAGE29_5_4_FILES: tuple[Path, ...] = (
    STAGE29_ROOT
    / "stage29_5_4_migration_context_source_adapter.py",
    STAGE29_ROOT / "stage29_5_4_manifest.py",
    STAGE29_ROOT
    / "STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_RUNBOOK.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# Word-boundary search; the runbook deliberately NAMES forbidden
# surfaces in scope lists, so we must look at identifiers (snake
# / camel case) not free prose. Identifier patterns use
# underscore-joined fragments.
_FORBIDDEN_IDENTIFIER_PATTERNS: tuple[str, ...] = (
    "public" + "_router",
    "subscriber" + "_router",
    "paid" + "_tier_router",
    "telegram" + "_sender",
    "telegram" + "_client",
    "x" + "_social",
    "social" + "_sidecar",
    "tweet" + "_ranking",
    "enforce" + "_policy",
    "approval" + "_gate",
    "auto" + "_trade",
    "position" + "_size",
    "trade" + "_executor",
    "wallet" + "_signer",
    "private" + "_key_loader",
    "buy" + "_signal",
    "sell" + "_signal",
    "execute" + "_trade",
    "control" + "_server",
    "http" + "_control_server",
    "auto" + "restart",
    "systemd" + "_unit",
    "dexscreener" + "_dispatch",
    "helius" + "_price",
    "bonding" + "_curve_decoder",
    "stage29_6" + "_",
    "stage_29_6" + "_",
)


def test_no_forbidden_identifier_pattern_in_stage29_5_4_files() -> None:
    for path in _STAGE29_5_4_FILES:
        source = _read(path)
        lower = source.lower()
        for needle in _FORBIDDEN_IDENTIFIER_PATTERNS:
            assert needle not in lower, (
                f"{path.name}: forbidden identifier substring "
                f"{needle!r} present in source"
            )


# Stage 29.5.4 source + runbook deliberately NAME several
# forbidden surfaces in scope lists with negative phrasing
# ("does not activate enforcement", "no subscriber routing").
# Substring-based active-voice scans collide with those negative
# mentions, so we rely on the closed-set identifier-pattern scan
# (above) to enforce the forbidden-surface discipline. This
# function intentionally leaves no active-voice substring scan.


def test_filter_enforcement_status_locked_in_adapter_and_manifest() -> None:
    """The locked filter_enforcement_status token must be
    referenced verbatim in the manifest. The adapter does not
    construct the token directly; it flows through the Stage
    29.5.2 offline integration result.
    """
    manifest_src = _read(_STAGE29_5_4_FILES[1])
    assert "NOT_ACTIVE_STAGE_29_PENDING" in manifest_src
    assert (
        "STAGE29_5_4_FILTER_ENFORCEMENT_STATUS_LOCKED"
        in manifest_src
    )


def test_runbook_describes_enforcement_as_not_active() -> None:
    src = _read(_STAGE29_5_4_FILES[2])
    assert "NOT_ACTIVE_STAGE_29_PENDING" in src


def test_no_new_env_name_in_stage29_5_4_files() -> None:
    """Stage 29.5.4 introduces ZERO new env names. The
    forbidden-surface tuple names the discipline; the source +
    runbook must NOT introduce any ``PHX2_STAGE29_5_4_*`` env
    name literal.
    """
    pattern = re.compile(r"PHX2_STAGE29_5_4_[A-Z0-9_]*=")
    for path in _STAGE29_5_4_FILES:
        source = _read(path)
        matches = pattern.findall(source)
        assert not matches, (
            f"{path.name}: forbidden Stage 29.5.4 env-name "
            f"literal(s) {matches!r}"
        )


def test_adapter_class_does_not_inherit_from_dispatch_or_wallet_types() -> None:
    """The adapter class is a pure Stage 27.4 ``MigrationContextSource``
    Protocol implementation. Its declaration must NOT inherit
    from a Discord / Telegram / wallet / signer / trade /
    dispatch / enforcement type.
    """
    src = _read(_STAGE29_5_4_FILES[0])
    # The adapter class declaration uses `class Stage29_5_4MigrationContextSourceAdapter:` (no base).
    # Pin that no inheritance from forbidden types is present.
    forbidden_base_names = (
        "Discord",
        "Telegram",
        "Wallet",
        "Signer",
        "Trade",
        "Dispatch",
        "Enforcement",
        "Router",
        "PublicTier",
        "SubscriberTier",
        "PaidTier",
    )
    # The class declaration line.
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(
            "class Stage29_5_4MigrationContextSourceAdapter"
        ):
            for forbidden in forbidden_base_names:
                assert forbidden not in stripped, (
                    f"Stage 29.5.4 adapter class declaration "
                    f"must not inherit from {forbidden!r}: "
                    f"{stripped!r}"
                )
            return
    raise AssertionError(
        "Stage29_5_4MigrationContextSourceAdapter class "
        "declaration not found in adapter source"
    )
