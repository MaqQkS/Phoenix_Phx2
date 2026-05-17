"""Stage 21 config / secret loading boundary.

THIS IS THE ONLY STAGE 21 MODULE PERMITTED TO READ ``os.environ``
OR ``os.getenv``.

The Stage 21 import-boundary test
(``PHX2/tests/stage21/test_env_read_boundaries.py``) walks the
Stage 21 production tree and asserts that no other module imports
``os.environ`` or ``os.getenv``. Stage 21 runtime code receives
typed config / ``SecretRef`` / ``OperatorAllowlist`` /
``CredentialAttestation`` objects produced by this module.

Stage 21 loads in two modes:

  * ``FAKE`` (default in 21.1) -- the operator runs Stage 21
    locally without any real secrets configured. ``load_config``
    succeeds even when every secret env-var is unset; the
    resulting ``Stage21Config`` carries empty ``SecretRef``
    instances and the empty fail-closed allowlist.
  * ``LIVE`` / ``REPLAY`` -- reserved for later sub-stages. The
    loader will validate required-secret presence per-mode in
    those sub-stages; 21.1 itself never raises a missing-secret
    error because no runner exists to consume the live config.

The Stage 20 closure handoff (Section G) explicitly forbids
reading any environment variable that contains an API key or
webhook URL into the live preview path. This module honors that
by:

  1. Holding the raw values only inside the local ``_read_env``
     scope (closure-local, never assigned to a module global).
  2. Converting raw values to ``SecretRef`` immediately, then
     dropping the local reference.
  3. Exposing only ``SecretRef`` / attestation / allowlist /
     non-secret-string fields from ``Stage21Config``.

``Stage21Config.public_summary()`` returns a manifest-safe view
that callers can serialize without further redaction.
"""

from __future__ import annotations

import os
from typing import Mapping, NamedTuple, Optional

from PHX2.stage21.allowlist import OperatorAllowlist, parse_allowlist
from PHX2.stage21.constants import (
    DEFAULT_DRY_RUN,
    DEFAULT_LIVE_PRIVATE,
    ENV_VAR_ALLOWLIST_OPERATOR_IDS,
    ENV_VAR_DISCORD_WEBHOOK_URL,
    ENV_VAR_DRY_RUN,
    ENV_VAR_LIVE_PRIVATE,
    ENV_VAR_PROVIDER_API_KEY,
    ENV_VAR_PROVIDER_MODE,
    ENV_VAR_PROVIDER_RPC_URL,
    ENV_VAR_SINK_MODE,
    ENV_VAR_TELEGRAM_BOT_TOKEN,
    ENV_VAR_TELEGRAM_CHAT_ID,
    ProviderModeName,
    SAFE_FOR_PUBLIC_DISPATCH,
    SinkModeName,
    STAGE21_MINOR_VERSION,
    STAGE21_NON_SECRET_ENV_VARS,
    STAGE21_SECRET_ENV_VARS,
    STAGE21_VERSION,
    Stage21ErrorCode,
)
from PHX2.stage21.credential_attestation import (
    CredentialAttestation,
    attestation_from_secret_ref,
    build_attestation_bundle,
)
from PHX2.stage21.errors import Stage21ConfigError
from PHX2.stage21.secret_redaction import SecretRef, build_secret_ref


# ---------------------------------------------------------------------------
# Truthy / falsy env-var parsing
# ---------------------------------------------------------------------------


_TRUE_TOKENS: frozenset[str] = frozenset({
    "1", "true", "yes", "on",
})
_FALSE_TOKENS: frozenset[str] = frozenset({
    "0", "false", "no", "off", "",
})


def _parse_bool_env(name: str, raw: Optional[str], default: bool) -> bool:
    """Parse a non-secret bool-like env var.

    Returns ``default`` when ``raw`` is ``None``. Accepts a small
    closed set of truthy / falsy tokens (case-insensitive). Any
    other value raises ``Stage21ConfigError`` (E2101) with the
    offending env-var name in the detail; the value itself is NOT
    included in the detail because env values are treated as
    potentially-secret.
    """
    if raw is None:
        return default
    token = raw.strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    raise Stage21ConfigError(
        Stage21ErrorCode.E2101,
        detail=(
            f"env var {name!r} has an unrecognized boolean value "
            f"(expected one of 1/0/true/false/yes/no/on/off)"
        ),
    )


def _parse_provider_mode(name: str, raw: Optional[str]) -> ProviderModeName:
    """Parse the provider-mode env var; default to FAKE.

    Raises ``Stage21ConfigError`` (E2101) on an unknown value.
    """
    if raw is None or raw.strip() == "":
        return ProviderModeName.FAKE
    token = raw.strip().upper()
    try:
        return ProviderModeName(token)
    except ValueError:
        raise Stage21ConfigError(
            Stage21ErrorCode.E2101,
            detail=(
                f"env var {name!r} carries unknown provider mode "
                f"(expected one of "
                f"{[m.value for m in ProviderModeName]!r})"
            ),
        )


def _parse_sink_mode(name: str, raw: Optional[str]) -> SinkModeName:
    """Parse the sink-mode env var; default to FAKE."""
    if raw is None or raw.strip() == "":
        return SinkModeName.FAKE
    token = raw.strip().upper()
    try:
        return SinkModeName(token)
    except ValueError:
        raise Stage21ConfigError(
            Stage21ErrorCode.E2101,
            detail=(
                f"env var {name!r} carries unknown sink mode "
                f"(expected one of {[m.value for m in SinkModeName]!r})"
            ),
        )


# ---------------------------------------------------------------------------
# Typed Stage 21 config
# ---------------------------------------------------------------------------


class Stage21Config(NamedTuple):
    """Immutable, secret-safe Stage 21 configuration snapshot.

    Contains:
      * ``stage21_version`` / ``stage21_minor_version`` -- locked
        from ``PHX2.stage21.constants``; rebuilt from constants on
        every load so a constant bump is visible in the next run's
        summary.
      * ``provider_mode`` / ``sink_mode`` -- parsed enum values.
      * ``dry_run`` / ``live_private`` -- bool flags. Defaults
        come from ``DEFAULT_DRY_RUN`` / ``DEFAULT_LIVE_PRIVATE``.
      * ``safe_for_public_dispatch`` -- hardcoded to the literal
        Python ``False`` (the dispatch-side analog of Stage 20's
        ``SAFE_FOR_LIVE_DISPATCH``).
      * ``provider_api_key`` / ``provider_rpc_url`` /
        ``discord_webhook_url`` / ``telegram_bot_token`` /
        ``telegram_chat_id`` -- ``SecretRef`` instances. The raw
        values were dropped at load time.
      * ``allowlist`` -- parsed ``OperatorAllowlist``. Empty input
        produces the fail-closed allowlist.

    Production code reads ``Stage21Config`` via dependency
    injection. The class has no methods that expose raw secret
    values; ``public_summary()`` returns a manifest-safe mapping.
    """

    stage21_version: str
    stage21_minor_version: str
    provider_mode: ProviderModeName
    sink_mode: SinkModeName
    dry_run: bool
    live_private: bool
    safe_for_public_dispatch: bool
    provider_api_key: SecretRef
    provider_rpc_url: SecretRef
    discord_webhook_url: SecretRef
    telegram_bot_token: SecretRef
    telegram_chat_id: SecretRef
    allowlist: OperatorAllowlist

    def secret_refs(self) -> tuple[SecretRef, ...]:
        """Return the tuple of every Stage 21 ``SecretRef`` slot.

        Order is stable so attestation bundling produces
        byte-identical output across runs.
        """
        return (
            self.provider_api_key,
            self.provider_rpc_url,
            self.discord_webhook_url,
            self.telegram_bot_token,
            self.telegram_chat_id,
        )

    def credential_attestations(self) -> tuple[CredentialAttestation, ...]:
        """Return the bundled ``CredentialAttestation`` tuple.

        Re-uses ``build_attestation_bundle`` to guarantee the
        attestation set is sorted lexicographically by slot name.
        """
        return build_attestation_bundle(self.secret_refs())

    def public_summary(self) -> Mapping[str, object]:
        """Return a manifest-safe, deterministic summary mapping.

        Every value is non-secret. Stage 21 writers serialize
        ``public_summary()`` directly; tests assert no slot value
        ever leaks into the returned mapping.
        """
        return {
            "stage21_version": self.stage21_version,
            "stage21_minor_version": self.stage21_minor_version,
            "provider_mode": self.provider_mode.value,
            "sink_mode": self.sink_mode.value,
            "dry_run": self.dry_run,
            "live_private": self.live_private,
            "safe_for_public_dispatch": self.safe_for_public_dispatch,
            "credential_attestations": tuple(
                a.public_summary()
                for a in self.credential_attestations()
            ),
            "allowlist": {
                "recipients": self.allowlist.recipients,
                "fail_closed": self.allowlist.fail_closed,
                "count": len(self.allowlist.recipients),
            },
        }


# ---------------------------------------------------------------------------
# Public load entry points
# ---------------------------------------------------------------------------


def load_config(
    env: Optional[Mapping[str, str]] = None,
) -> Stage21Config:
    """Build a ``Stage21Config`` from the environment.

    ``env`` defaults to ``os.environ``; tests pass a plain ``dict``
    to drive deterministic load paths without touching the real
    environment. The function is the ONLY Stage 21 entry point
    that reads ``os.environ`` / ``os.getenv``; every other Stage 21
    module receives the returned ``Stage21Config`` and reads from
    it.

    Stage 21.1 never raises a missing-secret error -- ``FAKE``
    mode loads cleanly without any secret env var set. The
    constructor does, however, raise ``Stage21ConfigError``
    (E2101) when a non-secret env value is malformed (e.g.
    unrecognized provider mode, non-bool ``DRY_RUN``).
    """
    source: Mapping[str, str]
    if env is None:
        # The single point of contact between Stage 21 and the
        # process environment. The copy isolates the loader from
        # any mid-load mutation of os.environ in tests.
        source = dict(os.environ)
    else:
        source = env

    return _build_config(source)


def load_config_for_fake_mode() -> Stage21Config:
    """Build a Stage 21 config explicitly for FAKE mode.

    Equivalent to ``load_config(env={})`` and used by tests and
    by future fake-runner harnesses. Stage 21.1 itself ships no
    runner, so this is a convenience alias only.
    """
    return _build_config({})


def _build_config(source: Mapping[str, str]) -> Stage21Config:
    """Construct a ``Stage21Config`` from a key/value mapping.

    Internal helper; ``load_config`` / ``load_config_for_fake_mode``
    are the public entry points. ``source`` is read once per slot
    and the raw values are converted to ``SecretRef`` instances
    before the function returns.
    """
    provider_mode_raw = source.get(ENV_VAR_PROVIDER_MODE)
    sink_mode_raw = source.get(ENV_VAR_SINK_MODE)
    dry_run_raw = source.get(ENV_VAR_DRY_RUN)
    live_private_raw = source.get(ENV_VAR_LIVE_PRIVATE)
    allowlist_raw = source.get(ENV_VAR_ALLOWLIST_OPERATOR_IDS)

    provider_mode = _parse_provider_mode(
        ENV_VAR_PROVIDER_MODE,
        provider_mode_raw,
    )
    sink_mode = _parse_sink_mode(ENV_VAR_SINK_MODE, sink_mode_raw)
    dry_run = _parse_bool_env(ENV_VAR_DRY_RUN, dry_run_raw, DEFAULT_DRY_RUN)
    live_private = _parse_bool_env(
        ENV_VAR_LIVE_PRIVATE,
        live_private_raw,
        DEFAULT_LIVE_PRIVATE,
    )
    allowlist = parse_allowlist(allowlist_raw)

    # Secret slots. Each call consumes the raw value and returns a
    # SecretRef; the raw value is never assigned to a longer-lived
    # local. ``source.get`` is read-only against the mapping copy
    # the loader took at entry.
    provider_api_key_ref = build_secret_ref(
        ENV_VAR_PROVIDER_API_KEY,
        source.get(ENV_VAR_PROVIDER_API_KEY),
    )
    provider_rpc_url_ref = build_secret_ref(
        ENV_VAR_PROVIDER_RPC_URL,
        source.get(ENV_VAR_PROVIDER_RPC_URL),
    )
    discord_webhook_url_ref = build_secret_ref(
        ENV_VAR_DISCORD_WEBHOOK_URL,
        source.get(ENV_VAR_DISCORD_WEBHOOK_URL),
    )
    telegram_bot_token_ref = build_secret_ref(
        ENV_VAR_TELEGRAM_BOT_TOKEN,
        source.get(ENV_VAR_TELEGRAM_BOT_TOKEN),
    )
    telegram_chat_id_ref = build_secret_ref(
        ENV_VAR_TELEGRAM_CHAT_ID,
        source.get(ENV_VAR_TELEGRAM_CHAT_ID),
    )

    return Stage21Config(
        stage21_version=STAGE21_VERSION,
        stage21_minor_version=STAGE21_MINOR_VERSION,
        provider_mode=provider_mode,
        sink_mode=sink_mode,
        dry_run=dry_run,
        live_private=live_private,
        safe_for_public_dispatch=SAFE_FOR_PUBLIC_DISPATCH,
        provider_api_key=provider_api_key_ref,
        provider_rpc_url=provider_rpc_url_ref,
        discord_webhook_url=discord_webhook_url_ref,
        telegram_bot_token=telegram_bot_token_ref,
        telegram_chat_id=telegram_chat_id_ref,
        allowlist=allowlist,
    )


def known_env_var_names() -> tuple[str, ...]:
    """Return every Stage 21 env-var name (sorted).

    Used by tests and by attestation tooling; the order is stable
    so the manifest can emit a deterministic "expected env vars"
    block. The set is the union of secret + non-secret names
    declared in ``PHX2.stage21.constants``.
    """
    return tuple(
        sorted(
            list(STAGE21_SECRET_ENV_VARS) + list(STAGE21_NON_SECRET_ENV_VARS)
        )
    )


__all__ = [
    "Stage21Config",
    "known_env_var_names",
    "load_config",
    "load_config_for_fake_mode",
]
