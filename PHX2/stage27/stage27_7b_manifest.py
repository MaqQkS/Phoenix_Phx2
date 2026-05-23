"""Stage 27.7b private Discord smoke dispatch manifest.

Stage 27.7b is the first controlled private operator-only Discord
smoke pass on top of the Stage 27.0 -> 27.7a architecture. It ships
the private Discord sender boundary (``private_discord_sender.py``),
the dispatch result model layer (``private_discord_models.py``),
the controlled one-ping live smoke dispatch
(``live_smoke_dispatch.py``), and this manifest module. It ships
NO public router, NO subscriber router, NO paid tier surface, NO
Telegram / X-social, NO Stage 29 enforcement, NO automated trading,
and NO broad Discord community distribution surface.

This manifest module exposes the locked Stage 27.7b schema axes
and source-file basename inventories so downstream substages
(27.8+) can pin against them without re-deriving them from the
sender layer.

Exposed surface:

  * ``STAGE27_7B_MINOR_VERSION``                          -- ``"27.7b"``.
  * ``STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION``         -- locked
                                                              Stage 27.7b
                                                              dispatch
                                                              result
                                                              schema
                                                              version.
  * ``STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH``              -- locked
                                                              one-ping
                                                              smoke
                                                              bound.
  * ``STAGE27_7B_PRODUCTION_BASENAMES``                   -- locked
                                                              Stage 27.7b
                                                              production
                                                              source +
                                                              markdown
                                                              basename
                                                              set.
  * ``STAGE27_7B_PRODUCTION_PY_BASENAMES``                -- locked
                                                              Stage 27.7b
                                                              production
                                                              .py
                                                              basename
                                                              set.
  * ``STAGE27_7B_PRODUCTION_MD_BASENAMES``                -- locked
                                                              Stage 27.7b
                                                              production
                                                              .md
                                                              basename
                                                              set (empty
                                                              tuple --
                                                              Stage 27.7b
                                                              appends to
                                                              the existing
                                                              Stage 27.7a
                                                              docs and
                                                              does not
                                                              introduce a
                                                              new
                                                              markdown
                                                              file).
  * ``STAGE27_7B_TEST_BASENAMES``                         -- locked
                                                              Stage 27.7b
                                                              test file
                                                              basename
                                                              set.

This module imports only stdlib (``typing``) plus Stage 27.7b
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage27.live_smoke_dispatch import (
    STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH as _STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH,
)
from PHX2.stage27.private_discord_models import (
    STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION as _STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION,
    STAGE27_7B_MINOR_VERSION as _STAGE27_7B_MINOR_VERSION,
)


# Re-export for downstream pin sites.
STAGE27_7B_MINOR_VERSION: str = _STAGE27_7B_MINOR_VERSION
STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION: str = (
    _STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION
)
STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH: int = (
    _STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH
)


# ---------------------------------------------------------------------------
# Locked Stage 27.7b source-file basename inventories
# ---------------------------------------------------------------------------


STAGE27_7B_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "private_discord_models.py",
    "private_discord_sender.py",
    "live_smoke_dispatch.py",
    "stage27_7b_manifest.py",
)


# Stage 27.7b extends the existing Stage 27.7a docs in place with
# the locked Stage 27.7b sections rather than introducing a new
# markdown file. The Stage 27.7b .md inventory is therefore empty.
STAGE27_7B_PRODUCTION_MD_BASENAMES: tuple[str, ...] = ()


STAGE27_7B_PRODUCTION_BASENAMES: tuple[str, ...] = (
    STAGE27_7B_PRODUCTION_PY_BASENAMES
    + STAGE27_7B_PRODUCTION_MD_BASENAMES
)


STAGE27_7B_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_27_7b_private_discord_models.py",
    "test_stage_27_7b_private_discord_sender.py",
    "test_stage_27_7b_live_smoke_dispatch.py",
    "test_stage_27_7b_boundaries.py",
)
