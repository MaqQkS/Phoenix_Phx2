"""Stage 29.5.6 private ping migration context body injector.

Stage 29.5.6 is the narrow transport-wrapper substage that makes
the already-rendered Stage 29.5.5 migration context block visible
inside the operator-visible private Discord ping body. The
injector is OPT-IN, MODE-3-ONLY, and CONSUMED BY Stage 29.3 mode-3
via the new optional ``private_discord_body_injector`` kwarg on
``run_stage29_3_first_private_tradeable_smoke``. Default Stage
29.3 mode-3 behavior (no kwarg) is BYTE-EQUIVALENT to the
pre-Stage-29.5.6 code path.

The injector is composed of two cooperating classes:

  * ``Stage29_5_6PrivateDiscordBodyInjector`` -- the operator-
    facing factory. The constructor accepts exactly one keyword-
    only argument ``migration_source: object`` (a Stage 29.5.5
    recorder reference, duck-typed for the read-only
    ``recorded_entries`` tuple property). The injector exposes
    exactly one method ``wrap_transport(inner_transport: object)
    -> object`` returning a thin wrapper transport bound to the
    injector's stored recorder reference.

  * ``_Stage29_5_6WrappedTransport`` -- the module-private
    wrapper transport. Implements the Stage 28.6
    ``Stage28_6PrivateTransport`` shape (one method
    ``send_one_audited_post(*, webhook_identity, payload)``)
    without inheriting any Stage 28 class and without importing
    any Stage 28 module. On each ``send_one_audited_post`` call
    the wrapper:

      1. duck-types ``self._migration_source.recorded_entries``;
         on duck-type miss / empty tuple / non-tuple, forwards
         the operator-supplied payload through the inner
         transport unchanged;
      2. reads the LATEST recorded entry's ``rendered_block``;
      3. re-validates the rendered block via
         ``stage29_5_5_rendered_block_is_safe_for_serialization``
         (defense in depth against post-recording
         ``object.__setattr__`` mutation);
      4. extracts the rendered ``body_text`` string;
      5. computes ``len(payload["content"]) + 2 +
         len(body_text)``;
      6. if the projected combined length is within the locked
         ``STAGE29_5_6_CONTENT_MAX_CHARS`` (1900), appends the
         full ``body_text`` to a ``dict(payload)`` copy and
         forwards the COPY through the inner transport;
      7. else builds a deterministic compact migration-context
         block from already-revalidated rendered-block closed-
         set / display fields (``migration_evidence_status_display``,
         ``migration_evidence_source_trust_display``,
         ``post_migration_ath_verified_display``, plus the pinned
         ``filter_enforcement_status`` /
         ``informational_only`` / ``not_a_trading_verdict``
         safety tokens). If the projected ``len(existing) + 2 +
         len(compact_text)`` is within the cap, appends the
         compact block; else skips the append entirely (NEVER
         truncates a rendered field, NEVER appends raw JSON,
         NEVER invents a new semantic field);
      8. swallows every internal exception on every step
         (recorder read, validator, body assembly, copy build)
         and falls back to forwarding the ORIGINAL payload
         unchanged. The wrapper does NOT swallow exceptions
         raised by the inner transport itself.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched.
  * No outbound network. No urllib / requests / httpx / aiohttp /
    websockets / websocket / http.client / socket / grpc /
    asyncio import.
  * No third-party runtime dependency. Stdlib only (``typing``)
    plus the Stage 29.5.5 render-models module (for the
    ``stage29_5_5_rendered_block_is_safe_for_serialization``
    helper + the ``Stage29_5_5RenderedMigrationContextBlock``
    class) and the Stage 29.5 migration models (for the locked
    ``FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING``
    token re-export).
  * No Stage 27, Stage 28, Stage 29.3, or Stage 29.4 production
    module import.
  * No top-level Call (no implicit I/O at import time). The only
    admitted module-body Call shape is ``@dataclass(...)`` on
    class decorators; this module ships zero ``@dataclass``
    classes and zero module-body Calls.
  * No legacy / pre-PHX2 import path.
  * No Discord / Telegram / X / social / webhook / Helius /
    Chainstack / Birdeye / Pump.fun reference.
  * No enforcement / routing / trading / wallet / signer surface.

The wrapper never mutates the operator-supplied payload dict; it
always builds a fresh ``dict(payload)`` copy before assigning the
combined ``content`` string. The original payload reference and
its keys / values are forwarded byte-for-byte when the injector
skips the append (duck-type miss, empty entries, validator fail,
overflow, or any internal exception).

The wrapper never adds any top-level payload key other than
``content``; the wrapper never removes any existing top-level
payload key.

The wrapper never opens a network connection itself; the inner
transport's ``send_one_audited_post`` performs the only outbound
work, and only after the Stage 28.9 / Stage 28.4 readiness gates
have already approved the dispatch.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage29.stage29_5_5_render_models import (
    Stage29_5_5RenderedMigrationContextBlock,
    stage29_5_5_rendered_block_is_safe_for_serialization,
    stage29_5_5_value_carries_forbidden_substring,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
)


# ---------------------------------------------------------------------------
# Locked Stage 29.5.6 schema version + content cap
# ---------------------------------------------------------------------------


STAGE29_5_6_PRIVATE_DISCORD_BODY_INJECTOR_SCHEMA_VERSION: str = (
    "stage29_5_6_v0_private_discord_body_injector"
)


# Locked Stage 29.5.6 combined-content character cap. Mirrors the
# Stage 28.9 ``STAGE28_9_CONTENT_MAX_CHARS`` value (1900) so the
# combined dispatched body stays under the Stage 28.4 8 KiB JSON
# encoded payload cap. The constant is redeclared locally so this
# module does NOT import any Stage 28 module; the Stage 28 cap is
# the authoritative cap and the Stage 29.5.6 cap mirrors it
# byte-for-byte by integer-literal value.
STAGE29_5_6_CONTENT_MAX_CHARS: int = 1900


# Locked Stage 29.5.6 separator inserted between the Stage 28.9
# dispatched body and the Stage 29.5.5 rendered migration context
# block. The separator is exactly two newline characters; this
# matches the Stage 28.9 ``render_stage28_9_discord_content``
# header / body separator so the appended block reads as a
# contiguous section to a downstream operator viewer.
_STAGE29_5_6_BODY_SEPARATOR: str = "\n\n"


# Stage 29.5.6 re-exports the locked Stage 29.5 enforcement token
# verbatim through the manifest. Storing a reference here keeps
# the boundary scan / spec-lock test surface able to assert the
# token is preserved on the Stage 29.5.6 production source.
STAGE29_5_6_FILTER_ENFORCEMENT_STATUS_LOCKED: str = (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
)


# Locked Stage 29.5.6 compact migration context header. The
# compact block is the deterministic fallback the wrapper builds
# when the full Stage 29.5.5 ``body_text`` does not fit within
# the locked ``STAGE29_5_6_CONTENT_MAX_CHARS`` cap once appended
# to the operator-supplied Stage 28.9 body. The compact block is
# strictly shorter than the full block and uses only closed-set /
# display fields from the already-revalidated Stage 29.5.5
# rendered block; no new semantic field is invented.
_STAGE29_5_6_COMPACT_HEADER: str = "[MIGRATION CONTEXT]"


# ---------------------------------------------------------------------------
# Module-private wrapper transport
# ---------------------------------------------------------------------------


class _Stage29_5_6WrappedTransport:
    """Stage 29.5.6 module-private wrapper transport.

    Implements the Stage 28.6 ``Stage28_6PrivateTransport`` shape
    (one method ``send_one_audited_post(*, webhook_identity,
    payload)``) without inheriting any Stage 28 class and without
    importing any Stage 28 module. The wrapper holds a reference
    to the inner Stage 28.9 transport and to the Stage 29.5.5
    recorder; on each ``send_one_audited_post`` call it
    optionally appends the most recent recorded rendered block's
    ``body_text`` to a COPY of the operator-supplied payload's
    ``content`` field, then forwards the (possibly mutated) copy
    through the inner transport.

    Failure discipline:

      * Every internal step (recorder read, validator, copy
        build, content assembly) is wrapped in ``try`` / ``except
        Exception`` and falls back to forwarding the ORIGINAL
        payload through the inner transport unchanged.
      * The wrapper does NOT swallow exceptions raised by the
        inner transport itself (the Stage 28.9 / Stage 28.4
        transport exceptions flow through verbatim).

    The wrapper never mutates the operator-supplied payload
    dict.
    """

    __slots__ = (
        "_inner_transport",
        "_migration_source",
        "_calls_forwarded",
    )

    def __init__(
        self,
        *,
        inner_transport: object,
        migration_source: object,
    ) -> None:
        self._inner_transport: object = inner_transport
        self._migration_source: object = migration_source
        self._calls_forwarded: int = 0

    @property
    def calls_forwarded(self) -> int:
        """Return the count of inner-transport ``send_one_audited_post``
        calls forwarded by this wrapper. Pure / deterministic.
        """
        return self._calls_forwarded

    def send_one_audited_post(
        self,
        *,
        webhook_identity: str,
        payload: object,
    ) -> object:
        """Forward exactly one Stage 28.6 dispatch through the
        inner Stage 28.9 transport, optionally appending the
        most recent Stage 29.5.5 rendered migration context block
        to a copy of ``payload["content"]``.

        Pure forwarding: no retries, no batching, no sleep, no
        scheduling. The wrapper increments its forwarded-call
        counter once per invocation.
        """
        self._calls_forwarded += 1
        forwarded_payload = self._build_payload_with_optional_append(
            payload,
        )
        return self._inner_transport.send_one_audited_post(
            webhook_identity=webhook_identity,
            payload=forwarded_payload,
        )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _build_payload_with_optional_append(
        self,
        payload: object,
    ) -> object:
        """Return either the original ``payload`` (when no append
        is admissible) or a fresh ``dict(payload)`` copy whose
        ``content`` field carries the unchanged Stage 28.9 body
        plus a single ``\\n\\n`` separator plus EITHER the Stage
        29.5.5 rendered block's full ``body_text`` (when it fits
        the cap) OR a deterministic compact migration-context
        block built from already-revalidated rendered-block
        closed-set / display fields (when the full body_text
        would exceed the cap).

        Append precedence:

          1. Full ``body_text``: if
             ``len(existing) + 2 + len(body_text)`` is within the
             locked ``STAGE29_5_6_CONTENT_MAX_CHARS`` cap, append
             the full body_text verbatim.
          2. Compact fallback: else build the deterministic
             compact block via ``_build_compact_body_text``; if
             ``len(existing) + 2 + len(compact_text)`` is within
             the cap, append the compact block.
          3. Skip: else forward the original payload unchanged
             (NEVER truncate; NEVER append raw JSON; NEVER invent
             data).

        Non-raising on every internal failure path; the original
        payload is forwarded unchanged on any exception.
        """
        try:
            rendered_block = self._extract_safe_rendered_block()
            if rendered_block is None:
                return payload
            body_text = rendered_block.body_text
            if not isinstance(body_text, str) or body_text == "":
                return payload
            existing_content = self._extract_existing_content(
                payload,
            )
            if existing_content is None:
                return payload
            if not isinstance(payload, dict):
                # Stage 28.9 always passes a dict; defensive
                # fallback for any caller that passed a mapping
                # we cannot safely copy.
                return payload
            # Attempt 1: full rendered ``body_text``.
            full_combined_len = (
                len(existing_content)
                + len(_STAGE29_5_6_BODY_SEPARATOR)
                + len(body_text)
            )
            if full_combined_len <= STAGE29_5_6_CONTENT_MAX_CHARS:
                payload_copy: dict = dict(payload)
                payload_copy["content"] = (
                    existing_content
                    + _STAGE29_5_6_BODY_SEPARATOR
                    + body_text
                )
                return payload_copy
            # Attempt 2: compact fallback. Built from already-
            # revalidated closed-set / display fields on the
            # rendered block. Never truncates the full body_text;
            # never invents data; never appends raw JSON.
            compact_text = _build_compact_body_text(
                rendered_block,
            )
            if compact_text is None:
                return payload
            compact_combined_len = (
                len(existing_content)
                + len(_STAGE29_5_6_BODY_SEPARATOR)
                + len(compact_text)
            )
            if (
                compact_combined_len
                > STAGE29_5_6_CONTENT_MAX_CHARS
            ):
                # Even the compact block would overflow; skip
                # the append entirely. The operator may inspect
                # the Stage 29.5.5 side-channel artifact for the
                # full rendered block.
                return payload
            payload_copy = dict(payload)
            payload_copy["content"] = (
                existing_content
                + _STAGE29_5_6_BODY_SEPARATOR
                + compact_text
            )
            return payload_copy
        except Exception:
            # Any internal failure on the append path: forward
            # the ORIGINAL payload through the inner transport
            # unchanged. Never raise from the wrapper's own
            # logic. The inner transport's exceptions are NOT
            # swallowed here; they propagate from the caller of
            # ``send_one_audited_post``.
            return payload

    def _extract_safe_rendered_block(
        self,
    ) -> Optional[Stage29_5_5RenderedMigrationContextBlock]:
        """Return the latest Stage 29.5.5 recorded entry's
        ``rendered_block`` when it is a fully-validated safe-for-
        serialization block, otherwise ``None``.

        Non-raising. Returns ``None`` on every failure path:

          * ``migration_source`` is ``None``,
          * ``migration_source`` has no ``recorded_entries``
            attribute (duck-type miss),
          * ``recorded_entries`` is not a tuple OR is empty,
          * the latest entry's ``rendered_block`` is not a
            ``Stage29_5_5RenderedMigrationContextBlock`` instance,
          * the rendered block fails the Stage 29.5.5 closed-
            set / pinned-value / forbidden-substring validator.
        """
        try:
            if self._migration_source is None:
                return None
            entries_attr = getattr(
                self._migration_source,
                "recorded_entries",
                None,
            )
            if entries_attr is None:
                return None
            if not isinstance(entries_attr, tuple):
                return None
            if len(entries_attr) == 0:
                return None
            latest_entry = entries_attr[-1]
            rendered_block = getattr(
                latest_entry, "rendered_block", None,
            )
            if not isinstance(
                rendered_block,
                Stage29_5_5RenderedMigrationContextBlock,
            ):
                return None
            if not stage29_5_5_rendered_block_is_safe_for_serialization(
                rendered_block,
            ):
                return None
            return rendered_block
        except Exception:
            return None

    def _extract_existing_content(
        self,
        payload: object,
    ) -> Optional[str]:
        """Return the operator-supplied ``payload["content"]``
        string when it is safe to append to, otherwise ``None``.

        Non-raising. Returns ``None`` when ``payload`` is not a
        dict, when ``payload["content"]`` is missing, when the
        value is not a string, or when the value is empty.
        """
        try:
            if not isinstance(payload, dict):
                return None
            existing = payload.get("content")
            if not isinstance(existing, str):
                return None
            if existing == "":
                return None
            return existing
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Compact migration context body builder
# ---------------------------------------------------------------------------


def _build_compact_body_text(
    rendered_block: Stage29_5_5RenderedMigrationContextBlock,
) -> Optional[str]:
    """Return a deterministic compact migration-context body text
    built from already-revalidated rendered-block closed-set /
    display fields, or ``None`` on any failure path.

    The compact body uses ONLY the fields exposed by the Stage
    29.5.5 ``Stage29_5_5RenderedMigrationContextBlock`` dataclass
    and is shorter than the renderer's full ``body_text``. The
    builder NEVER invents a new semantic field, NEVER truncates a
    field value, and NEVER appends raw JSON. Every field used
    here is one of:

      * ``migration_evidence_status_display`` -- one of the 5
        Stage 29.5.5 closed-set status tokens,
      * ``migration_evidence_source_trust_display`` -- one of the
        6 Stage 29.5.5 closed-set source-trust tokens,
      * ``post_migration_ath_verified_display`` -- one of the 3
        Stage 29.5.5 closed-set ATH-verified tokens,
      * ``filter_enforcement_status`` -- pinned by the Stage 29.5
        projection contract to
        ``NOT_ACTIVE_STAGE_29_PENDING``.

    The two pinned-True flags ``informational_only`` and
    ``not_a_trading_verdict`` are emitted verbatim as lower-case
    ``true`` so a downstream operator viewer cannot misread the
    block as a trading verdict.

    Non-raising. Returns ``None`` if any internal step fails or
    if the joined compact text would carry a Stage 29.5.5
    forbidden substring (a paranoid final scan that defends
    against any future widening of the closed-set vocabulary).
    """
    try:
        if not isinstance(
            rendered_block,
            Stage29_5_5RenderedMigrationContextBlock,
        ):
            return None
        status_display = (
            rendered_block.migration_evidence_status_display
        )
        source_trust_display = (
            rendered_block.migration_evidence_source_trust_display
        )
        ath_verified_display = (
            rendered_block.post_migration_ath_verified_display
        )
        filter_status = rendered_block.filter_enforcement_status
        # Every value reaching this builder has already been
        # validated by ``stage29_5_5_rendered_block_is_safe_for_serialization``
        # (closed-set membership + forbidden-substring scan). The
        # defensive isinstance checks here protect against a
        # hand-crafted block reaching the builder via a code path
        # that bypassed the validator.
        for value in (
            status_display,
            source_trust_display,
            ath_verified_display,
            filter_status,
        ):
            if not isinstance(value, str):
                return None
            if value == "":
                return None
        lines = (
            _STAGE29_5_6_COMPACT_HEADER,
            "status: " + status_display,
            "evidence: " + source_trust_display,
            "ath_context: " + ath_verified_display,
            "filter_enforcement_status: " + filter_status,
            "informational_only: true",
            "not_a_trading_verdict: true",
        )
        compact_text = "\n".join(lines)
        # Paranoid final scan: every literal line above is a
        # constant, and every interpolated value comes from the
        # already-validated rendered block. The final scan
        # defends against future widenings of the closed-set
        # vocabulary that could introduce a forbidden substring.
        if stage29_5_5_value_carries_forbidden_substring(
            compact_text,
        ):
            return None
        return compact_text
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public injector class
# ---------------------------------------------------------------------------


class Stage29_5_6PrivateDiscordBodyInjector:
    """Stage 29.5.6 private Discord body migration context
    injector.

    Operator-facing factory. The constructor accepts exactly one
    keyword-only argument ``migration_source: object`` (typically
    a Stage 29.5.5 recorder reference, duck-typed for the
    read-only ``recorded_entries`` tuple property). The injector
    exposes exactly one method ``wrap_transport(inner_transport:
    object) -> object`` returning a thin wrapper transport bound
    to the injector's stored recorder reference.

    Construction is non-raising on every argument shape: a
    non-recorder ``migration_source`` (None, empty object, or a
    duck-type miss) is stored verbatim; the resulting wrapper
    will silently forward the unchanged payload through the
    inner transport on every dispatch.

    Stage 29.5.6 ships ZERO change to the Stage 27.5 private
    ping renderer / Stage 28.4 audited HTTP transport / Stage
    28.9 dispatch wrapper / Stage 28.2 dispatch ledger. The
    injector wraps the Stage 28.9 transport externally from the
    Stage 29.3 mode-3 path; it never inherits from any Stage 28
    class and it never imports any Stage 28 module.

    Stage 29.3 production source carries ZERO ``stage29_5*``
    import; the Stage 29.3 ``private_discord_body_injector``
    kwarg is annotated ``Optional[object]`` and Stage 29.3
    calls ``wrap_transport`` via duck typing only.
    """

    __slots__ = ("_migration_source",)

    def __init__(
        self,
        *,
        migration_source: object,
    ) -> None:
        self._migration_source: object = migration_source

    @property
    def bound_migration_source(self) -> object:
        """Return the recorder reference stored at construction
        time. Pure / deterministic.
        """
        return self._migration_source

    def wrap_transport(
        self,
        inner_transport: object,
    ) -> object:
        """Return a Stage 29.5.6 wrapper transport bound to the
        injector's stored ``migration_source`` and the supplied
        ``inner_transport``.

        The wrapper exposes the Stage 28.6
        ``Stage28_6PrivateTransport`` method signature
        ``send_one_audited_post(*, webhook_identity, payload)``
        without inheriting from any Stage 28 class. Stage 29.3
        mode-3 calls this method via duck typing only.

        Pure / deterministic. Non-raising on the ``inner_transport``
        argument shape: any object satisfies the wrapper's
        construction contract; the actual ``send_one_audited_post``
        call will raise only if the inner transport itself raises
        (the wrapper does NOT swallow inner-transport exceptions).
        """
        return _Stage29_5_6WrappedTransport(
            inner_transport=inner_transport,
            migration_source=self._migration_source,
        )

    def __repr__(self) -> str:
        return (
            "Stage29_5_6PrivateDiscordBodyInjector("
            "migration_source=<bound>)"
        )

    __str__ = __repr__


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = (
    "STAGE29_5_6_PRIVATE_DISCORD_BODY_INJECTOR_SCHEMA_VERSION",
    "STAGE29_5_6_CONTENT_MAX_CHARS",
    "STAGE29_5_6_FILTER_ENFORCEMENT_STATUS_LOCKED",
    "Stage29_5_6PrivateDiscordBodyInjector",
)
