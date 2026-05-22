"""Stage 27.1 operator-config orchestrator.

Pure composition layer that:

  1. projects the injected ``env`` mapping through the Stage 27
     readiness boundary,
  2. resolves the two-factor LIVE-mode authority,
  3. builds the per-run identity using the injected clock,
  4. renders the redacted readiness summary,
  5. returns one immutable ``Stage27OperatorConfig`` record.

The orchestrator does NOT read the process environment directly.
``os.environ`` access is the exclusive domain of
``live_secrets_readiness``. The caller either passes ``env=None``
(which lets the readiness boundary fall through to
``os.environ``) or passes an explicit ``Mapping[str, str]`` (the
test path).

Two-factor LIVE resolution matrix:

  +--------------+-------------+----------------------+---------------+
  | env_flag_set | cli_request | live_secrets_present | resolved      |
  +==============+=============+======================+===============+
  | False        | False       | *                    | DRY_RUN       |
  | True         | False       | *                    | LIVE_REFUSED  |
  | False        | True        | *                    | LIVE_REFUSED  |
  | True         | True        | False                | LIVE_REFUSED  |
  | True         | True        | True                 | LIVE_ALLOWED  |
  +--------------+-------------+----------------------+---------------+

The DRY_RUN default does NOT require live secrets to be present.
LIVE_REFUSED is the deliberate fail-closed state for every other
configuration in which LIVE was requested but cannot be allowed.

This module imports only stdlib (``typing``) plus other Stage 27.1
production modules. It does NOT import Stage 21-26 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import Mapping, Optional

from PHX2.stage27.live_config_models import (
    LIVE_MODE_AUTHORITY_DRY_RUN,
    LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
    LIVE_MODE_AUTHORITY_LIVE_REFUSED,
    LIVE_MODE_REASON_BOTH_FACTORS_AND_SECRETS_OK,
    LIVE_MODE_REASON_DEFAULT_DRY_RUN,
    LIVE_MODE_REASON_LIVE_SECRETS_MALFORMED,
    LIVE_MODE_REASON_LIVE_SECRETS_MISSING,
    LIVE_MODE_REASON_ONE_FACTOR_CLI_ONLY,
    LIVE_MODE_REASON_ONE_FACTOR_ENV_ONLY,
    STAGE27_DEFAULT_SCHEMA_VERSION,
    STAGE27_LIVE_MODE_ALLOWED_NAME,
    Stage27LiveModeAuthority,
    Stage27OperatorConfig,
    Stage27SecretsReadinessReport,
)
from PHX2.stage27.live_run_identity import (
    Stage27Clock,
    build_run_identity,
    make_session_id,
)
from PHX2.stage27.live_secrets_readiness import (
    build_redacted_readiness_summary,
    detect_all_stage27_field_presence,
    env_flag_is_truthy_from_record,
)


def _env_flag_set_from_report(
    report: Stage27SecretsReadinessReport,
) -> bool:
    """Return ``True`` iff the ``PHX2_LIVE_MODE_ALLOWED`` record
    in ``report`` parses as a truthy bool literal.
    """
    for record in report.fields:
        if record.name == STAGE27_LIVE_MODE_ALLOWED_NAME:
            return env_flag_is_truthy_from_record(record)
    return False


def _resolve_live_mode_authority(
    *,
    env_flag_set: bool,
    cli_live_requested: bool,
    readiness: Stage27SecretsReadinessReport,
) -> Stage27LiveModeAuthority:
    """Apply the two-factor LIVE resolution matrix.

    Returns the resolved ``Stage27LiveModeAuthority`` with the
    closed-set ``reason_code`` describing how the resolver got
    there. The resolver never raises -- LIVE-refused is a
    first-class state, not an exception. Callers that prefer a
    hard failure on LIVE-refused can re-raise
    ``Stage27LiveModeFailedClosedError`` themselves.
    """
    live_secrets_present = readiness.all_required_live_present

    if not env_flag_set and not cli_live_requested:
        return Stage27LiveModeAuthority(
            resolved=LIVE_MODE_AUTHORITY_DRY_RUN,
            env_flag_set=False,
            cli_live_requested=False,
            required_live_secrets_present=live_secrets_present,
            reason_code=LIVE_MODE_REASON_DEFAULT_DRY_RUN,
        )

    if env_flag_set and not cli_live_requested:
        return Stage27LiveModeAuthority(
            resolved=LIVE_MODE_AUTHORITY_LIVE_REFUSED,
            env_flag_set=True,
            cli_live_requested=False,
            required_live_secrets_present=live_secrets_present,
            reason_code=LIVE_MODE_REASON_ONE_FACTOR_ENV_ONLY,
        )

    if cli_live_requested and not env_flag_set:
        return Stage27LiveModeAuthority(
            resolved=LIVE_MODE_AUTHORITY_LIVE_REFUSED,
            env_flag_set=False,
            cli_live_requested=True,
            required_live_secrets_present=live_secrets_present,
            reason_code=LIVE_MODE_REASON_ONE_FACTOR_CLI_ONLY,
        )

    # Both factors are set. Gate on secrets.
    if readiness.required_live_malformed:
        return Stage27LiveModeAuthority(
            resolved=LIVE_MODE_AUTHORITY_LIVE_REFUSED,
            env_flag_set=True,
            cli_live_requested=True,
            required_live_secrets_present=False,
            reason_code=LIVE_MODE_REASON_LIVE_SECRETS_MALFORMED,
        )
    if readiness.required_live_missing:
        return Stage27LiveModeAuthority(
            resolved=LIVE_MODE_AUTHORITY_LIVE_REFUSED,
            env_flag_set=True,
            cli_live_requested=True,
            required_live_secrets_present=False,
            reason_code=LIVE_MODE_REASON_LIVE_SECRETS_MISSING,
        )

    return Stage27LiveModeAuthority(
        resolved=LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
        env_flag_set=True,
        cli_live_requested=True,
        required_live_secrets_present=True,
        reason_code=LIVE_MODE_REASON_BOTH_FACTORS_AND_SECRETS_OK,
    )


def resolve_operator_config(
    *,
    clock: Stage27Clock,
    env: Optional[Mapping[str, str]] = None,
    cli_live_requested: bool = False,
    session_id: Optional[str] = None,
    schema_version: str = STAGE27_DEFAULT_SCHEMA_VERSION,
    run_id_salt: str = "",
) -> Stage27OperatorConfig:
    """Compose the Stage 27.1 operator config.

    Parameters:

      * ``clock``               -- the injected ``Stage27Clock``;
                                   the only source of wall time.
      * ``env``                 -- optional caller-supplied env
                                   mapping. ``None`` falls through
                                   to ``os.environ`` via the
                                   readiness boundary.
      * ``cli_live_requested``  -- ``True`` iff the operator
                                   passed an explicit LIVE
                                   argument for this run.
      * ``session_id``          -- optional caller-supplied
                                   session id; ``None`` generates
                                   a fresh ``uuid.uuid4`` hex.
      * ``schema_version``      -- stamped onto the run identity.
      * ``run_id_salt``         -- propagated to
                                   ``make_run_id_from_session`` so
                                   tests can distinguish multiple
                                   runs under one frozen clock.

    Returns an immutable ``Stage27OperatorConfig``. Never raises
    on LIVE-refused or on missing secrets.
    """
    readiness = detect_all_stage27_field_presence(env=env)
    env_flag_set = _env_flag_set_from_report(readiness)
    cli_flag = bool(cli_live_requested)

    authority = _resolve_live_mode_authority(
        env_flag_set=env_flag_set,
        cli_live_requested=cli_flag,
        readiness=readiness,
    )

    created_at_utc = clock.now_iso_utc()
    if session_id is None:
        session_id = make_session_id()

    identity = build_run_identity(
        session_id=session_id,
        created_at_utc=created_at_utc,
        mode=authority.resolved,
        schema_version=schema_version,
        run_id_salt=run_id_salt,
    )

    redacted_summary = build_redacted_readiness_summary(
        report=readiness,
        authority=authority,
        identity=identity,
    )

    return Stage27OperatorConfig(
        readiness=readiness,
        authority=authority,
        identity=identity,
        redacted_summary=redacted_summary,
    )
