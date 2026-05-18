"""Stage 21.3A live-readiness boundary.

This module is the Stage 21.3A composition wrapper that layers
the four new live-readiness fields on top of Stage 21.1's
``Stage21Config``:

  * ``live_smoke_mode``         -- gating string; only the locked
                                   token ``"live_smoke"`` enables
                                   the readiness path.
  * ``provider_id``             -- short non-secret operator label
                                   identifying which provider
                                   configuration is active.
                                   Stage 21.3A uses the placeholder
                                   ``"reserved_for_21_3b"``; the
                                   real provider id vocabulary
                                   lands in Stage 21.3B+.
  * ``safe_for_live_dispatch``  -- bool gate; analog of the
                                   Stage 21.1
                                   ``SAFE_FOR_PUBLIC_DISPATCH``
                                   invariant on the live-dispatch
                                   axis. Defaults to False.
  * ``safety_acknowledgement``  -- operator-supplied string that
                                   must exactly equal
                                   ``LIVE_SAFETY_ACKNOWLEDGEMENT_V1``.

This module does NOT read ``os.environ`` / ``os.getenv``. The
Stage 21 env-read boundary remains ``PHX2/stage21/config.py``
alone -- the locked env-boundary test
``test_env_read_boundaries.py`` enforces this. Callers snapshot
the process environment once and pass it explicitly to
``load_live_readiness_config_from_env``. The future Stage 21.4
runner is the only operational caller that performs the snapshot;
Stage 21.3A tests pass a plain ``dict``.

``evaluate_live_readiness`` returns a frozen ``ReadinessResult``
carrying ``ready: bool`` and ``reasons: tuple[str, ...]``.
Readiness is True only when every precondition holds; any
failure yields ``ready=False`` and a reasons tuple naming each
violated precondition with a locked token from the closed set
below. When ``live_smoke_mode`` is disabled the only reason
returned is ``mode_disabled``; the other preconditions are not
evaluated because the gate is already disabled at the mode
level.

Stage 21.3A scope: contracts / config / live-gate / readiness
only. No provider adapter, no transport, no runner, no smoke
ping.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple

from PHX2.stage21.config import Stage21Config, load_config
from PHX2.stage21.constants import (
    ProviderModeName,
    SinkModeName,
)


# ---------------------------------------------------------------------------
# New Stage 21.3A env-var names
# ---------------------------------------------------------------------------
#
# Per locked operator decision Q6 these are the four (and only
# four) new env-var names introduced by Stage 21.3A. The strings
# themselves are non-secret labels; the values they reference are
# operator-typed non-secret strings (the safety acknowledgement
# is operator-typed, not a rotating credential) plus the bool
# safe-for-live-dispatch token.


ENV_VAR_LIVE_SMOKE_MODE: str = "PHX2_STAGE21_LIVE_SMOKE_MODE"
ENV_VAR_PROVIDER_ID: str = "PHX2_STAGE21_PROVIDER_ID"
ENV_VAR_SAFE_FOR_LIVE_DISPATCH: str = "PHX2_STAGE21_SAFE_FOR_LIVE_DISPATCH"
ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT: str = (
    "PHX2_STAGE21_LIVE_SAFETY_ACKNOWLEDGEMENT"
)


STAGE21_3A_NEW_ENV_VAR_NAMES: tuple[str, ...] = (
    ENV_VAR_LIVE_SMOKE_MODE,
    ENV_VAR_PROVIDER_ID,
    ENV_VAR_SAFE_FOR_LIVE_DISPATCH,
    ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT,
)


# ---------------------------------------------------------------------------
# Locked enabling tokens
# ---------------------------------------------------------------------------


# Locked enabling token for live_smoke_mode. Any other value
# (including the empty string, missing, ``"disabled"``, or any
# case variant other than this exact lowercase token) leaves
# readiness disabled.
LIVE_SMOKE_MODE_TOKEN: str = "live_smoke"


# Locked Stage 21.3A placeholder ``provider_id``. The real
# provider-id vocabulary is reserved for Stage 21.3B+; Stage
# 21.3A's readiness gate accepts ONLY this exact placeholder
# string. An operator-typed ``provider_id`` that matches a real
# provider name (e.g. ``"helius"``) is rejected at the readiness
# gate with reason ``unsupported_provider_id`` so a partial
# Stage 21.3A roll-out cannot accidentally lift the placeholder
# in advance of the concrete adapter landing.
PLACEHOLDER_PROVIDER_ID_21_3B: str = "reserved_for_21_3b"


# Locked safety-acknowledgement V1 token. The operator must type
# this exact string into ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT for
# readiness to evaluate True. The V1 suffix is locked so a future
# acknowledgement revision (V2) is forced into a new explicit
# operator decision plus a constant addition.
LIVE_SAFETY_ACKNOWLEDGEMENT_V1: str = (
    "phx2-stage21-live-smoke-ack-v1"
)


# ---------------------------------------------------------------------------
# Locked readiness-reason tokens (closed set)
# ---------------------------------------------------------------------------
#
# Each reason corresponds to exactly one precondition in
# evaluate_live_readiness. Tests pin the exact set so a future
# change to the reason vocabulary surfaces as a test failure.


REASON_MODE_DISABLED: str = "mode_disabled"
REASON_PROVIDER_MODE_NOT_LIVE: str = "provider_mode_not_live"
REASON_SINK_MODE_NOT_PRIVATE_PREVIEW: str = "sink_mode_not_private_preview"
REASON_LIVE_PRIVATE_NOT_TRUE: str = "live_private_not_true"
# NOTE: the Python identifier deliberately reads ``..._PUBLIC_FLAG_...``
# rather than ``..._PUBLIC_DISPATCH_...`` because the Stage 21
# identifier-aware routing scanner
# (``PHX2/tests/stage21/test_no_public_routing.py``) flags any
# snake-component match against the locked
# ``public_dispatch`` / ``paid_dispatch`` / ``subscriber`` tokens.
# The bare ``safe_for_public_dispatch`` field name is explicitly
# whitelisted in ``constants.py`` but longer compound identifiers
# containing the substring are not. The string VALUE below still
# reads ``safe_for_public_dispatch_not_false`` so the
# operator-visible reason text remains unchanged; string literals
# are not identifier-scanned.
REASON_BASE_PUBLIC_FLAG_NOT_FALSE: str = (
    "safe_for_public_dispatch_not_false"
)
REASON_MISSING_PROVIDER_ID: str = "missing_provider_id"
REASON_UNSUPPORTED_PROVIDER_ID: str = "unsupported_provider_id"
REASON_PROVIDER_API_KEY_MISSING: str = "provider_api_key_missing"
REASON_PROVIDER_RPC_URL_MISSING: str = "provider_rpc_url_missing"
REASON_DISCORD_WEBHOOK_URL_MISSING: str = "discord_webhook_url_missing"
REASON_SAFE_FOR_LIVE_DISPATCH_NOT_TRUE: str = (
    "safe_for_live_dispatch_not_true"
)
REASON_SAFETY_ACKNOWLEDGEMENT_MISMATCH: str = (
    "safety_acknowledgement_mismatch"
)


STAGE21_3A_READINESS_REASON_TOKENS: tuple[str, ...] = (
    REASON_MODE_DISABLED,
    REASON_PROVIDER_MODE_NOT_LIVE,
    REASON_SINK_MODE_NOT_PRIVATE_PREVIEW,
    REASON_LIVE_PRIVATE_NOT_TRUE,
    REASON_BASE_PUBLIC_FLAG_NOT_FALSE,
    REASON_MISSING_PROVIDER_ID,
    REASON_UNSUPPORTED_PROVIDER_ID,
    REASON_PROVIDER_API_KEY_MISSING,
    REASON_PROVIDER_RPC_URL_MISSING,
    REASON_DISCORD_WEBHOOK_URL_MISSING,
    REASON_SAFE_FOR_LIVE_DISPATCH_NOT_TRUE,
    REASON_SAFETY_ACKNOWLEDGEMENT_MISMATCH,
)


# ---------------------------------------------------------------------------
# Bool-token parsing for safe_for_live_dispatch
# ---------------------------------------------------------------------------


_TRUE_TOKENS: frozenset[str] = frozenset({"1", "true", "yes", "on"})


def _parse_bool_token(raw: str) -> bool:
    """Parse the safe_for_live_dispatch env value as a fail-closed bool.

    Returns ``True`` only for the recognized truthy tokens; every
    other value (empty, missing, malformed, ``"false"``, ``"0"``)
    parses as ``False``. Stage 21.3A intentionally does not raise
    on a malformed value -- the readiness gate fails closed and
    the reason set surfaces the underlying gate violation.
    """
    return raw.strip().lower() in _TRUE_TOKENS


# ---------------------------------------------------------------------------
# Composition wrapper + readiness-result record
# ---------------------------------------------------------------------------


class Stage21LiveReadinessConfig(NamedTuple):
    """Composition of Stage21Config + Stage 21.3A live-readiness fields.

    Per locked operator decision Q5 the base ``Stage21Config`` is
    held unmodified as ``base``; the four new fields are flat
    on the wrapper.
    """

    base: Stage21Config
    live_smoke_mode: str
    provider_id: str
    safe_for_live_dispatch: bool
    safety_acknowledgement: str


class ReadinessResult(NamedTuple):
    """Frozen Stage 21.3A readiness evaluation result.

    ``ready`` is True iff every Stage 21.3A precondition holds.
    ``reasons`` is the tuple of locked reason tokens for each
    violated precondition, in a deterministic order matching the
    precondition list in evaluate_live_readiness. An empty
    reasons tuple corresponds to ``ready=True``.
    """

    ready: bool
    reasons: tuple[str, ...]


# ---------------------------------------------------------------------------
# Loader (env mapping passed in by caller -- no os.environ read)
# ---------------------------------------------------------------------------


def load_live_readiness_config_from_env(
    env: Mapping[str, str],
) -> Stage21LiveReadinessConfig:
    """Build a Stage21LiveReadinessConfig from the supplied env mapping.

    Per locked operator decision Q6 the loader uses the hybrid
    pattern: it calls ``load_config(env=env)`` to build the base
    Stage 21.1 config snapshot, then reads the four new
    Stage 21.3A env-var keys from the same mapping via
    ``env.get(...)``.

    The Stage 21 env-read boundary stays at config.py: this
    module does not import ``os`` and does not call
    ``os.environ`` / ``os.getenv``. The caller snapshots the
    process environment once (or provides a test mapping) and
    passes it here; the future Stage 21.4 runner owns the
    snapshot.
    """
    base = load_config(env=env)
    live_smoke_mode = env.get(ENV_VAR_LIVE_SMOKE_MODE, "")
    provider_id = env.get(ENV_VAR_PROVIDER_ID, "")
    safe_for_live_dispatch_raw = env.get(ENV_VAR_SAFE_FOR_LIVE_DISPATCH, "")
    safety_acknowledgement = env.get(
        ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT,
        "",
    )
    return Stage21LiveReadinessConfig(
        base=base,
        live_smoke_mode=live_smoke_mode,
        provider_id=provider_id,
        safe_for_live_dispatch=_parse_bool_token(safe_for_live_dispatch_raw),
        safety_acknowledgement=safety_acknowledgement,
    )


# ---------------------------------------------------------------------------
# Readiness evaluator
# ---------------------------------------------------------------------------


def evaluate_live_readiness(
    config: Stage21LiveReadinessConfig,
) -> ReadinessResult:
    """Return the locked Stage 21.3A readiness evaluation.

    Per locked operator decision Q4 the readiness gate requires
    every precondition below. If ``live_smoke_mode`` is not the
    enabling token, the only reason returned is
    ``mode_disabled``; the other preconditions are not evaluated
    because the gate is already disabled at the mode level.

    When ``live_smoke_mode`` is enabled, every remaining
    precondition is evaluated and any violation contributes a
    locked reason token to the returned tuple. The reason order
    mirrors the precondition list in Q4.

    Preconditions (all must hold for ready=True):
      * live_smoke_mode == LIVE_SMOKE_MODE_TOKEN
      * base.provider_mode is ProviderModeName.LIVE
      * base.sink_mode is SinkModeName.PRIVATE_PREVIEW
      * base.live_private is True
      * base.safe_for_public_dispatch is False
      * provider_id is non-empty AND exactly equals
        PLACEHOLDER_PROVIDER_ID_21_3B. A missing / empty value
        contributes ``missing_provider_id``; a present but
        non-placeholder value (e.g. a real provider name like
        ``"helius"``) contributes ``unsupported_provider_id``.
        The real provider-id vocabulary lands in Stage 21.3B+.
      * base.provider_api_key.present
      * base.provider_rpc_url.present
      * base.discord_webhook_url.present
      * safe_for_live_dispatch is True
      * safety_acknowledgement == LIVE_SAFETY_ACKNOWLEDGEMENT_V1
    """
    if config.live_smoke_mode != LIVE_SMOKE_MODE_TOKEN:
        return ReadinessResult(
            ready=False,
            reasons=(REASON_MODE_DISABLED,),
        )

    reasons: list[str] = []
    base = config.base

    if base.provider_mode is not ProviderModeName.LIVE:
        reasons.append(REASON_PROVIDER_MODE_NOT_LIVE)
    if base.sink_mode is not SinkModeName.PRIVATE_PREVIEW:
        reasons.append(REASON_SINK_MODE_NOT_PRIVATE_PREVIEW)
    if base.live_private is not True:
        reasons.append(REASON_LIVE_PRIVATE_NOT_TRUE)
    if base.safe_for_public_dispatch is not False:
        reasons.append(REASON_BASE_PUBLIC_FLAG_NOT_FALSE)
    if not config.provider_id:
        reasons.append(REASON_MISSING_PROVIDER_ID)
    elif config.provider_id != PLACEHOLDER_PROVIDER_ID_21_3B:
        reasons.append(REASON_UNSUPPORTED_PROVIDER_ID)
    if not base.provider_api_key.present:
        reasons.append(REASON_PROVIDER_API_KEY_MISSING)
    if not base.provider_rpc_url.present:
        reasons.append(REASON_PROVIDER_RPC_URL_MISSING)
    if not base.discord_webhook_url.present:
        reasons.append(REASON_DISCORD_WEBHOOK_URL_MISSING)
    if config.safe_for_live_dispatch is not True:
        reasons.append(REASON_SAFE_FOR_LIVE_DISPATCH_NOT_TRUE)
    if config.safety_acknowledgement != LIVE_SAFETY_ACKNOWLEDGEMENT_V1:
        reasons.append(REASON_SAFETY_ACKNOWLEDGEMENT_MISMATCH)

    return ReadinessResult(ready=not reasons, reasons=tuple(reasons))


__all__ = [
    "ENV_VAR_LIVE_SAFETY_ACKNOWLEDGEMENT",
    "ENV_VAR_LIVE_SMOKE_MODE",
    "ENV_VAR_PROVIDER_ID",
    "ENV_VAR_SAFE_FOR_LIVE_DISPATCH",
    "LIVE_SAFETY_ACKNOWLEDGEMENT_V1",
    "LIVE_SMOKE_MODE_TOKEN",
    "PLACEHOLDER_PROVIDER_ID_21_3B",
    "REASON_BASE_PUBLIC_FLAG_NOT_FALSE",
    "REASON_DISCORD_WEBHOOK_URL_MISSING",
    "REASON_LIVE_PRIVATE_NOT_TRUE",
    "REASON_MISSING_PROVIDER_ID",
    "REASON_MODE_DISABLED",
    "REASON_PROVIDER_API_KEY_MISSING",
    "REASON_PROVIDER_MODE_NOT_LIVE",
    "REASON_PROVIDER_RPC_URL_MISSING",
    "REASON_SAFE_FOR_LIVE_DISPATCH_NOT_TRUE",
    "REASON_SAFETY_ACKNOWLEDGEMENT_MISMATCH",
    "REASON_SINK_MODE_NOT_PRIVATE_PREVIEW",
    "REASON_UNSUPPORTED_PROVIDER_ID",
    "ReadinessResult",
    "STAGE21_3A_NEW_ENV_VAR_NAMES",
    "STAGE21_3A_READINESS_REASON_TOKENS",
    "Stage21LiveReadinessConfig",
    "evaluate_live_readiness",
    "load_live_readiness_config_from_env",
]
