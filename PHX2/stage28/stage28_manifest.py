"""Stage 28-wide closure manifest.

Stage 28.8 is the closure-only pass of Stage 28. This module is
the Stage 28-wide manifest that pins the locked Stage 28
substage list, the per-substage commit SHAs, the production /
doc / test inventory, the closure-evidence filenames, the
forbidden-surface vocabulary, the tag policy, and the Stage 28
no-secrets / no-network / no-live-send declarations.

This module is **constants-only**. It:

  * imports only stdlib (``typing``),
  * imports no Stage 28 implementation module,
  * imports no Stage 29 module,
  * reads no process environment variable,
  * opens no network connection,
  * writes no file,
  * makes no git call,
  * creates no tag,
  * contains no top-level Call (no implicit I/O at import time),
  * contains no runtime side effect.

The Stage 28.8 closure / handoff / manifest / boundary tests
pin the locked content of this module so a downstream reader
can rely on the inventory without re-deriving it from the rest
of the tree.

Stage 28.8 ships NO Stage 29 implementation, NO enforcement,
NO public routing, NO subscriber routing, NO paid tier routing,
NO Telegram, NO X / social, NO automated trading, NO wallet /
private-key / signer logic, NO position sizing, NO trade
execution, NO dashboard / HTTP control server, NO daemon /
systemd / watchdog / autorestart service, NO live smoke
automation, and NO ``stage-28-closed`` tag.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 28 identity + schema version
# ---------------------------------------------------------------------------


STAGE28_ID: str = "stage28"
STAGE28_STATUS: str = "READY_FOR_OPERATOR_REVIEW"
STAGE28_MANIFEST_SCHEMA_VERSION: str = (
    "stage28_closure_manifest_v0"
)


# ---------------------------------------------------------------------------
# Substage inventory
# ---------------------------------------------------------------------------


STAGE28_SUBSTAGE_IDS: tuple[str, ...] = (
    "28.0",
    "28.1",
    "28.2",
    "28.3a",
    "28.3b",
    "28.4",
    "28.5",
    "28.6",
    "28.7",
    "28.8",
)


STAGE28_SUBSTAGE_TITLES: tuple[tuple[str, str], ...] = (
    ("28.0", "spec lock / reliability charter"),
    ("28.1", "provider-neutral config wrapper"),
    ("28.2", "restart-safe dispatch ledger"),
    ("28.3a", "failure classification contracts"),
    ("28.3b", "bounded retry policy contracts"),
    ("28.4", "audited private Discord HTTP transport"),
    (
        "28.5",
        "heartbeat / health snapshot / CLI status artifacts",
    ),
    ("28.6", "bounded private session runner"),
    (
        "28.7",
        (
            "longer-session smoke harness + controlled live "
            "smoke runbook"
        ),
    ),
    ("28.8", "closure audit + Stage 29 handoff"),
)


# ---------------------------------------------------------------------------
# Commit inventory (per-substage SHA, all local-only on master)
# ---------------------------------------------------------------------------


# The Stage 28 commits below are all on the local ``master``
# branch. No ``stage-28-closed`` tag exists and no Stage 28
# commit has been pushed to any remote. Stage 28.8
# implementation must not create the ``stage-28-closed`` tag or
# push any commit.
STAGE28_COMMIT_SHAS: tuple[tuple[str, str], ...] = (
    ("28.0", "9f94c98b3116cfe141f8835c7e9e5da5ecfb4413"),
    ("28.1", "2300678561de94230549eadabb9445814cdb9d96"),
    ("28.2", "5a91334c45d8574f480600fd9c5a8d42498f9438"),
    ("28.3a", "2d942636a1d42ec651b1115ede447e19a89f3049"),
    ("28.3b", "c6271d7f14f160e4cf5517e6091b0fbe205226df"),
    ("28.4", "0a05b92b582334932906a2cba5bbc65bf991168c"),
    ("28.5", "bd923482e990021d69b368b3ca79d32a786ec56b"),
    ("28.6", "36d44b551272c3c257da761c27c3196e6889e177"),
    ("28.7", "ea9e741bd62bf8b5d2dcd8acd7d2cd61dc979c86"),
    # The Stage 28.8 commit SHA is the commit that ships this
    # manifest, the closure audit, the Stage 29 handoff, and the
    # Stage 28.8 closure / handoff / manifest / boundary tests.
    # The placeholder below is intentional; the operator records
    # the actual SHA in the commit report after Stage 28.8
    # lands. Stage 28.8 implementation code and tests must not
    # rewrite this placeholder.
    ("28.8", "TO_BE_FILLED_BY_COMMIT_REPORT"),
)


# ---------------------------------------------------------------------------
# Production-file inventory (per substage; basenames only)
# ---------------------------------------------------------------------------


STAGE28_0_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "__init__.py",
    "STAGE_28_0_SPEC_LOCK.md",
)


STAGE28_1_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "provider_neutral_models.py",
    "provider_neutral_config.py",
    "provider_neutral_readiness.py",
    "stage28_1_manifest.py",
)


STAGE28_2_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "dispatch_ledger_models.py",
    "dispatch_ledger.py",
    "stage28_2_manifest.py",
)


STAGE28_3A_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "failure_classification_models.py",
    "failure_classification.py",
    "stage28_3a_manifest.py",
)


STAGE28_3B_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "retry_policy_models.py",
    "retry_policy.py",
    "stage28_3b_manifest.py",
)


STAGE28_4_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "audited_http_transport_models.py",
    "audited_http_transport.py",
    "stage28_4_manifest.py",
)


STAGE28_5_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "health_status_models.py",
    "heartbeat_writer.py",
    "health_snapshot_writer.py",
    "cli_status_line.py",
    "stage28_5_manifest.py",
)


STAGE28_6_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "session_runner_models.py",
    "bounded_private_session_runner.py",
    "stage28_6_manifest.py",
)


STAGE28_7_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "longer_session_smoke_harness.py",
    "stage28_7_manifest.py",
)


STAGE28_7_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md",
    "STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md",
)


# Stage 28.8 production / doc / test surface.
STAGE28_8_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_CLOSURE_AUDIT.md",
    "STAGE_29_HANDOFF.md",
)


STAGE28_8_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "stage28_manifest.py",
)


STAGE28_8_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_8_closure_audit.py",
    "test_stage_28_8_stage29_handoff.py",
    "test_stage_28_8_manifest.py",
    "test_stage_28_8_boundaries.py",
)


# Union of every Stage 28 production / doc basename admitted
# under ``PHX2/stage28/`` at Stage 28.8.
STAGE28_ALL_PRODUCTION_BASENAMES: tuple[str, ...] = (
    STAGE28_0_PRODUCTION_BASENAMES
    + STAGE28_1_PRODUCTION_BASENAMES
    + STAGE28_2_PRODUCTION_BASENAMES
    + STAGE28_3A_PRODUCTION_BASENAMES
    + STAGE28_3B_PRODUCTION_BASENAMES
    + STAGE28_4_PRODUCTION_BASENAMES
    + STAGE28_5_PRODUCTION_BASENAMES
    + STAGE28_6_PRODUCTION_BASENAMES
    + STAGE28_7_PRODUCTION_BASENAMES
    + STAGE28_7_DOC_BASENAMES
    + STAGE28_8_PRODUCTION_BASENAMES
    + STAGE28_8_DOC_BASENAMES
)


# ---------------------------------------------------------------------------
# Closure evidence filenames
# ---------------------------------------------------------------------------


STAGE28_CLOSURE_EVIDENCE_BASENAMES: tuple[str, ...] = (
    "STAGE_28_0_SPEC_LOCK.md",
    "STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md",
    "STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md",
    "STAGE_28_CLOSURE_AUDIT.md",
    "STAGE_29_HANDOFF.md",
    "stage28_manifest.py",
)


# ---------------------------------------------------------------------------
# Forbidden surfaces (Stage 28 must never ship any of these)
# ---------------------------------------------------------------------------


STAGE28_FORBIDDEN_SURFACES: tuple[str, ...] = (
    "Stage 29 implementation",
    "enforcement",
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X / social",
    "automated trading",
    "wallet / private-key / signer logic",
    "position sizing",
    "trade execution",
    "dashboard / HTTP control server",
    "daemon / systemd / watchdog / autorestart service",
    "live smoke automation",
)


# Forbidden Stage 28 basenames -- if any of these appears under
# ``PHX2/stage28/`` the closure manifest's contract is broken.
STAGE28_FORBIDDEN_BASENAMES: tuple[str, ...] = (
    "public_router.py",
    "subscriber_router.py",
    "paid_tier_router.py",
    "live_router.py",
    "telegram_sender.py",
    "telegram_client.py",
    "x_social.py",
    "social_sidecar.py",
    "tweet_ranking.py",
    "social_scoring.py",
    "enforcement_gate.py",
    "enforcement.py",
    "enforce_policy.py",
    "auto_trade.py",
    "position_sizer.py",
    "trade_executor.py",
    "wallet_signer.py",
    "private_key_loader.py",
    "discord_bot.py",
    "slash_commands.py",
    "subscriber_models.py",
    "subscriber_db.py",
    "dashboard.py",
    "http_control_server.py",
    "control_server.py",
    "watchdog.py",
    "autorestart.py",
    "daemon.py",
    "systemd_unit.py",
)


# ---------------------------------------------------------------------------
# Tag policy
# ---------------------------------------------------------------------------


STAGE28_CLOSURE_TAG_NAME: str = "stage-28-closed"
STAGE28_TAG_POLICY: tuple[str, ...] = (
    (
        "The stage-28-closed tag must only be created after "
        "explicit operator authorization."
    ),
    (
        "Stage 28.8 implementation must not create the "
        "stage-28-closed tag."
    ),
    (
        "Stage 28.8 implementation must not push any Stage 28 "
        "commit."
    ),
    (
        "The Stage 28.8 manifest, closure audit, Stage 29 "
        "handoff, and Stage 28.8 tests must not call git tag, "
        "git push, or any equivalent git mutation."
    ),
    (
        "The stage-28-closed tag must be an annotated tag "
        "pointing at the Stage 28.8 commit; lightweight tags "
        "are not acceptable."
    ),
)


# ---------------------------------------------------------------------------
# No-secrets / no-network / no-live-send declarations
# ---------------------------------------------------------------------------


STAGE28_NO_SECRETS_DECLARATIONS: tuple[str, ...] = (
    (
        "Stage 28 production records never carry a webhook URL, "
        "provider endpoint, RPC URL, API key, bearer token, "
        "auth header, wallet seed, private key, or raw exception "
        "string."
    ),
    (
        "Stage 28 reads no process environment variable outside "
        "the Stage 28.1 readiness wrapper "
        "(provider_neutral_readiness.py)."
    ),
    (
        "Stage 28 redaction tokens are distinct per substage so "
        "a leak scan for one substage cannot collide with "
        "another."
    ),
)


STAGE28_NO_NETWORK_DECLARATIONS: tuple[str, ...] = (
    (
        "Stage 28 production code imports no network / RPC / "
        "messaging / scheduler / threading / asyncio / "
        "subprocess library outside the Stage 28.4 audited "
        "transport (audited_http_transport.py)."
    ),
    (
        "Stage 28.4 is the lone module allowed to import "
        "urllib.request / urllib.error and to reach Discord's "
        "private-operator webhook over HTTP."
    ),
    (
        "Stage 28.6 / 28.7 runners and harnesses use the Stage "
        "28.6 fake transport in tests; no Stage 28 test sends "
        "a real Discord message."
    ),
)


STAGE28_NO_LIVE_SEND_DECLARATIONS: tuple[str, ...] = (
    (
        "The Stage 28.7 longer-session smoke harness is "
        "offline-only. Its smoke summary record always sets "
        "live_send_attempted=False and live_send_count=0."
    ),
    (
        "The Stage 28.7 controlled live smoke runbook is a "
        "manual operator procedure documented in markdown; no "
        "Stage 28 production code performs an automatic live "
        "send."
    ),
    (
        "Stage 28.8 does not add any live-send callable, "
        "live-send automation, scheduler, or daemon."
    ),
)


# ---------------------------------------------------------------------------
# Self-describing top-level exports
# ---------------------------------------------------------------------------


__all__ = (
    "STAGE28_ID",
    "STAGE28_STATUS",
    "STAGE28_MANIFEST_SCHEMA_VERSION",
    "STAGE28_SUBSTAGE_IDS",
    "STAGE28_SUBSTAGE_TITLES",
    "STAGE28_COMMIT_SHAS",
    "STAGE28_0_PRODUCTION_BASENAMES",
    "STAGE28_1_PRODUCTION_BASENAMES",
    "STAGE28_2_PRODUCTION_BASENAMES",
    "STAGE28_3A_PRODUCTION_BASENAMES",
    "STAGE28_3B_PRODUCTION_BASENAMES",
    "STAGE28_4_PRODUCTION_BASENAMES",
    "STAGE28_5_PRODUCTION_BASENAMES",
    "STAGE28_6_PRODUCTION_BASENAMES",
    "STAGE28_7_PRODUCTION_BASENAMES",
    "STAGE28_7_DOC_BASENAMES",
    "STAGE28_8_DOC_BASENAMES",
    "STAGE28_8_PRODUCTION_BASENAMES",
    "STAGE28_8_TEST_BASENAMES",
    "STAGE28_ALL_PRODUCTION_BASENAMES",
    "STAGE28_CLOSURE_EVIDENCE_BASENAMES",
    "STAGE28_FORBIDDEN_SURFACES",
    "STAGE28_FORBIDDEN_BASENAMES",
    "STAGE28_CLOSURE_TAG_NAME",
    "STAGE28_TAG_POLICY",
    "STAGE28_NO_SECRETS_DECLARATIONS",
    "STAGE28_NO_NETWORK_DECLARATIONS",
    "STAGE28_NO_LIVE_SEND_DECLARATIONS",
)
