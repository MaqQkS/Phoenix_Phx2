"""Core Stage 21 typed records.

The records here are the in-memory shapes Stage 21 sub-stages
exchange. 21.1 ships the foundation set; 21.2+ may add new
records additively. Existing record fields and orderings are
locked once they appear here.

Records:
  * ``Stage21RunId`` -- typed run identifier carrying enough
    provenance for a later sub-stage to record a per-run trace
    without re-deriving the version axes.
  * ``ProviderMode`` / ``SinkMode`` -- typed wrappers around the
    enum names declared in ``PHX2.stage21.constants``. They exist
    as their own types (rather than the enum values directly) so
    additional provenance can be attached later without breaking
    callers.
  * ``PrivatePreviewMarker`` -- the locked banner-token bundle
    that every Stage 21 preview ping MUST carry. The marker
    asserts the rendered payload remains non-actionable.

The Stage 21 import-boundary policy forbids any of these records
from triggering a network call on construction. The
``PrivatePreviewMarker`` constructor in particular re-asserts the
locked banner tokens; tests verify the marker cannot be mutated
into a state where ``safe_for_public_dispatch`` is true.
"""

from __future__ import annotations

from typing import NamedTuple

from PHX2.stage21.constants import (
    PRIVATE_PREVIEW_BANNER_TEXT,
    PRIVATE_PREVIEW_DO_NOT_FORWARD_TEXT,
    PRIVATE_PREVIEW_OPERATOR_ONLY_TEXT,
    PRIVATE_PREVIEW_REQUIRED_TOKENS,
    SAFE_FOR_PUBLIC_DISPATCH,
    STAGE21_MINOR_VERSION,
    STAGE21_VERSION,
    ProviderModeName,
    SinkModeName,
)


class Stage21RunId(NamedTuple):
    """Typed Stage 21 run identifier.

    Carries:
      * ``run_id`` -- opaque hex string the caller supplies. The
        Stage 21 telemetry writer trusts the caller (typically a
        future runner) to produce a deterministic id;
        ``Stage21RunId`` does not generate one itself in 21.1.
      * ``stage21_version`` / ``stage21_minor_version`` -- captured
        at construction time from ``PHX2.stage21.constants`` so the
        id record carries the version axes that produced it.
      * ``generated_at_utc_iso`` -- ISO-8601 UTC string produced by
        the caller from an injected clock. Stage 21.1 does not
        emit a runner-generated id, so this field is included for
        shape only.

    ``Stage21RunId`` is intentionally opaque. Tests construct one
    directly with a deterministic ``run_id``; the runner will
    populate it from a hash of input artifacts plus a clock-derived
    suffix in a later sub-stage.
    """

    run_id: str
    stage21_version: str
    stage21_minor_version: str
    generated_at_utc_iso: str

    @classmethod
    def of(
        cls,
        *,
        run_id: str,
        generated_at_utc_iso: str,
    ) -> "Stage21RunId":
        """Construct a Stage 21 run id with version axes locked from constants.

        Tests prefer this constructor over the default ``NamedTuple``
        constructor because it pins ``stage21_version`` /
        ``stage21_minor_version`` to the live constants without
        threading them through every test fixture.
        """
        return cls(
            run_id=run_id,
            stage21_version=STAGE21_VERSION,
            stage21_minor_version=STAGE21_MINOR_VERSION,
            generated_at_utc_iso=generated_at_utc_iso,
        )


class ProviderMode(NamedTuple):
    """Typed wrapper around a ``ProviderModeName`` enum value.

    The wrapper exists so the Stage 21 contracts can carry provider
    mode metadata as a typed record rather than the raw enum value.
    Future sub-stages may add provenance fields (e.g. the source
    that selected the mode) without breaking call sites.
    """

    name: ProviderModeName

    @classmethod
    def fake(cls) -> "ProviderMode":
        return cls(name=ProviderModeName.FAKE)


class SinkMode(NamedTuple):
    """Typed wrapper around a ``SinkModeName`` enum value.

    Same shape pattern as ``ProviderMode``; the wrapper is the
    Stage 21 contract type the dispatcher and provider consume.
    """

    name: SinkModeName

    @classmethod
    def fake(cls) -> "SinkMode":
        return cls(name=SinkModeName.FAKE)


class PrivatePreviewMarker(NamedTuple):
    """Locked banner-token bundle for every Stage 21 preview ping.

    Stage 21 preview renderings carry the banner text, the
    operator-only token, and the do-not-forward token, plus the
    explicit ``safe_for_public_dispatch`` boolean. The boolean is
    locked to the literal Python ``False`` value sourced from
    ``PHX2.stage21.constants.SAFE_FOR_PUBLIC_DISPATCH``; the
    factory ``locked()`` is the only supported way to construct
    the marker.

    Stage 21.1 ships only the marker type. The renderer that
    embeds the marker into a rendered message is Stage 21.2 scope.
    """

    banner_text: str
    operator_only_text: str
    do_not_forward_text: str
    required_tokens: tuple[str, ...]
    safe_for_public_dispatch: bool

    @classmethod
    def locked(cls) -> "PrivatePreviewMarker":
        """Return the marker with every token sourced from constants.

        The factory is the only supported constructor. Tests
        construct via ``locked()`` and assert the returned tuple
        matches ``PRIVATE_PREVIEW_REQUIRED_TOKENS`` field-by-field.
        ``safe_for_public_dispatch`` is the literal Python
        ``False`` -- flipping it requires bumping
        ``STAGE21_VERSION`` and is a Stage 21 sub-stage decision.
        """
        return cls(
            banner_text=PRIVATE_PREVIEW_BANNER_TEXT,
            operator_only_text=PRIVATE_PREVIEW_OPERATOR_ONLY_TEXT,
            do_not_forward_text=PRIVATE_PREVIEW_DO_NOT_FORWARD_TEXT,
            required_tokens=PRIVATE_PREVIEW_REQUIRED_TOKENS,
            safe_for_public_dispatch=SAFE_FOR_PUBLIC_DISPATCH,
        )


__all__ = [
    "PrivatePreviewMarker",
    "ProviderMode",
    "SinkMode",
    "Stage21RunId",
]
