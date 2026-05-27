"""Stage 29.5.5 status display matrix tests.

Pins the full closed-set ``(measurement_status, migration_source,
post_migration_ath_verified)`` -> ``(migration_evidence_status_display,
migration_evidence_source_trust_display,
post_migration_ath_verified_display)`` mapping from Section 5
of the Stage 29.5.5 runbook.

The Stage 29.5.5 renderer NEVER promotes a ``COMPLETE``
projection with a ``SYNTHETIC_TEST_ONLY`` or ``UNKNOWN``
migration source to ``SOURCE_TRUSTED_ON_CHAIN``. This file pins
that invariant on dedicated cases.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    MEASUREMENT_STATUS_INVALID_MIGRATION,
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
    MIGRATION_JOIN_STATUS_NO_MATCH,
    MIGRATION_JOIN_STATUS_SOURCE_INVALID,
    MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    REDACTION_STATUS_SAFE,
    Stage29_5PrivatePingMigrationContext,
    WARNING_POST_MIGRATION_ATH_UNVERIFIED,
)
from PHX2.stage29.stage29_5_5_private_discord_migration_context_renderer import (
    render_private_discord_migration_context_block,
)
from PHX2.stage29.stage29_5_5_render_models import (
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_SYNTHETIC,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_CONFLICTING,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_INVALID,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_PARTIAL,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_NOT_VERIFIED,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED,
)


_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"
_MIGRATION_TS: str = "2026-01-01T00:00:05+00:00"


def _build_projection(
    *,
    measurement_status: str,
    migration_source: str,
    post_migration_ath_verified: bool | None = None,
    join_status_echoed: str | None = None,
    has_timestamp: bool = True,
    has_slot: bool = True,
    extra_warnings: tuple[str, ...] = (),
) -> Stage29_5PrivatePingMigrationContext:
    """Hand-build a Stage 29.5 projection for the renderer
    matrix tests.

    The Stage 29.5 projection validator allows any combination
    of (measurement_status, migration_source); this helper
    bypasses the natural projection function (which would only
    produce certain combinations) so the renderer's mapping can
    be exhaustively exercised.
    """
    if join_status_echoed is None:
        join_status_echoed = _DEFAULT_JOIN_STATUS[
            measurement_status
        ]
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=measurement_status,
        warnings=extra_warnings,
        migration_timestamp_utc=(
            _MIGRATION_TS if has_timestamp else None
        ),
        migration_slot=12345 if has_slot else None,
        migration_source=migration_source,
        post_migration_ath_verified=(
            post_migration_ath_verified
        ),
        join_status_echoed=join_status_echoed,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_OBSERVED_AT,
    )


_DEFAULT_JOIN_STATUS: dict[str, str] = {
    MEASUREMENT_STATUS_COMPLETE: MIGRATION_JOIN_STATUS_JOINED,
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT: (
        MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    ),
    MEASUREMENT_STATUS_MISSING_MIGRATION: (
        MIGRATION_JOIN_STATUS_NO_MATCH
    ),
    MEASUREMENT_STATUS_INVALID_MIGRATION: (
        MIGRATION_JOIN_STATUS_SOURCE_INVALID
    ),
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION: (
        MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES
    ),
}


# ---------------------------------------------------------------------------
# Section 5.1 — evidence_status_display
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("measurement_status", "expected_display"),
    [
        (
            MEASUREMENT_STATUS_COMPLETE,
            MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE,
        ),
        (
            MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
            MIGRATION_EVIDENCE_STATUS_DISPLAY_PARTIAL,
        ),
        (
            MEASUREMENT_STATUS_MISSING_MIGRATION,
            MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING,
        ),
        (
            MEASUREMENT_STATUS_INVALID_MIGRATION,
            MIGRATION_EVIDENCE_STATUS_DISPLAY_INVALID,
        ),
        (
            MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
            MIGRATION_EVIDENCE_STATUS_DISPLAY_CONFLICTING,
        ),
    ],
)
def test_evidence_status_display_mapping(
    measurement_status: str,
    expected_display: str,
) -> None:
    projection = _build_projection(
        measurement_status=measurement_status,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert (
        block.migration_evidence_status_display
        == expected_display
    )


# ---------------------------------------------------------------------------
# Section 5.2 — source_trust_display
# ---------------------------------------------------------------------------


_TRUST_MATRIX: tuple[tuple[str, str, str], ...] = (
    # COMPLETE branch
    (
        MEASUREMENT_STATUS_COMPLETE,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN,
    ),
    (
        MEASUREMENT_STATUS_COMPLETE,
        MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN,
    ),
    (
        MEASUREMENT_STATUS_COMPLETE,
        MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_SYNTHETIC,
    ),
    (
        MEASUREMENT_STATUS_COMPLETE,
        MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN,
    ),
    # PARTIAL branch
    (
        MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN,
    ),
    (
        MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN,
    ),
    (
        MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC,
    ),
    (
        MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    ),
    # MISSING branch (always NO_SOURCE regardless of token)
    (
        MEASUREMENT_STATUS_MISSING_MIGRATION,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    ),
    (
        MEASUREMENT_STATUS_MISSING_MIGRATION,
        MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    ),
    (
        MEASUREMENT_STATUS_MISSING_MIGRATION,
        MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    ),
    (
        MEASUREMENT_STATUS_MISSING_MIGRATION,
        MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    ),
    # INVALID branch
    (
        MEASUREMENT_STATUS_INVALID_MIGRATION,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN,
    ),
    (
        MEASUREMENT_STATUS_INVALID_MIGRATION,
        MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN,
    ),
    (
        MEASUREMENT_STATUS_INVALID_MIGRATION,
        MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC,
    ),
    (
        MEASUREMENT_STATUS_INVALID_MIGRATION,
        MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    ),
    # CONFLICTING branch
    (
        MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN,
    ),
    (
        MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
        MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN,
    ),
    (
        MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
        MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC,
    ),
    (
        MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
        MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    ),
)


@pytest.mark.parametrize(
    ("measurement_status", "migration_source", "expected_trust"),
    _TRUST_MATRIX,
)
def test_source_trust_display_mapping(
    measurement_status: str,
    migration_source: str,
    expected_trust: str,
) -> None:
    projection = _build_projection(
        measurement_status=measurement_status,
        migration_source=migration_source,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert (
        block.migration_evidence_source_trust_display
        == expected_trust
    )


# ---------------------------------------------------------------------------
# Section 5.3 — ath_verified_display
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("post_migration_ath_verified", "expected_display"),
    [
        (
            True,
            POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED,
        ),
        (
            False,
            POST_MIGRATION_ATH_VERIFIED_DISPLAY_NOT_VERIFIED,
        ),
        (
            None,
            POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN,
        ),
    ],
)
def test_ath_verified_display_mapping(
    post_migration_ath_verified: bool | None,
    expected_display: str,
) -> None:
    extra = ()
    if post_migration_ath_verified is not True:
        extra = (WARNING_POST_MIGRATION_ATH_UNVERIFIED,)
    projection = _build_projection(
        measurement_status=MEASUREMENT_STATUS_COMPLETE,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        post_migration_ath_verified=(
            post_migration_ath_verified
        ),
        extra_warnings=extra,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert (
        block.post_migration_ath_verified_display
        == expected_display
    )


# ---------------------------------------------------------------------------
# Critical safety pins (cannot promote unknown/synthetic to
# trusted on the COMPLETE branch)
# ---------------------------------------------------------------------------


def test_complete_with_unknown_source_does_not_render_as_trusted() -> None:
    projection = _build_projection(
        measurement_status=MEASUREMENT_STATUS_COMPLETE,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert (
        block.migration_evidence_source_trust_display
        != MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN
    )
    assert (
        block.migration_evidence_source_trust_display
        == MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN
    )


def test_complete_with_synthetic_source_does_not_render_as_trusted() -> None:
    projection = _build_projection(
        measurement_status=MEASUREMENT_STATUS_COMPLETE,
        migration_source=MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert (
        block.migration_evidence_source_trust_display
        != MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN
    )
    assert (
        block.migration_evidence_source_trust_display
        == MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_SYNTHETIC
    )


def test_only_complete_plus_trusted_source_can_render_trusted_on_chain() -> None:
    """Inverse pin: the renderer's
    ``MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN``
    output is REACHABLE only for the ``COMPLETE`` measurement
    status paired with ``HELIUS_WS`` or
    ``STAGE29_MIGRATION_ARTIFACT`` migration source. The trust
    matrix above enumerates these; this test guards against a
    regression that might admit a non-COMPLETE branch to
    TRUSTED_ON_CHAIN.
    """
    for (
        measurement_status,
        migration_source,
        expected_trust,
    ) in _TRUST_MATRIX:
        if (
            expected_trust
            == MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN
        ):
            assert (
                measurement_status
                == MEASUREMENT_STATUS_COMPLETE
            ), (
                f"Stage 29.5.5 trust matrix admits "
                f"TRUSTED_ON_CHAIN for non-COMPLETE status "
                f"{measurement_status!r} — regression"
            )
            assert migration_source in (
                MIGRATION_SOURCE_HELIUS_WS,
                MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
            ), (
                f"Stage 29.5.5 trust matrix admits "
                f"TRUSTED_ON_CHAIN for non-trusted source "
                f"{migration_source!r} — regression"
            )
