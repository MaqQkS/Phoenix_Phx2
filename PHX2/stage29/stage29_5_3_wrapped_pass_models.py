"""Stage 29.5.3 wrapped-pass observation models.

Closed-set vocabularies + immutable frozen records the Stage
29.5.3 soak pass-entrypoint wrapper emits as side observations.

Two records are exported:

  * :class:`Stage29_5_3PendingPassObservation` -- the minimal
    pending record the wrapper appends inside ``__call__`` (no
    provider work, no composition, no artifact). It carries
    only the per-pass index, a safe-shape candidate base mint
    echo (or ``None``), and the soak output directory the
    operator handed in. The post-soak flush step reads each
    pending record and materializes a composed observation.
  * :class:`Stage29_5_3WrappedPassObservation` -- the composed
    record the wrapper materializes during the explicit
    ``flush_pending_observations()`` call. Identical schema
    surface as before; the dataclass validator is now tighter
    on ``candidate_base_mint`` (positive Solana base58 shape
    check that rejects URL-shaped strings, auth-header
    substrings, secret-key prefixes, whitespace, non-printable
    bytes, the equals sign, and forbidden URL host substrings).

Closed-set ``observation_status`` vocabulary (4 tokens):

  * ``NO_CANDIDATE_AXES``      -- the inner pass returned no
    dedupe-key candidate (or the dedupe key's token_mint failed
    the Stage 29.5.3 safe-shape validator); no Stage 29.5.2
    composition was run.
  * ``COMPOSED``               -- the wrapper successfully built
    candidate axes from the inner result's dedupe key, called
    ``run_stage29_5_2_offline_integration``, and captured the
    closed-set Stage 29.5 join / projection verdict.
  * ``COMPOSITION_REJECTED``   -- the Stage 29.5.2 composition
    raised on caller-shape / validator grounds; the flush
    swallowed the error and recorded the closed-set status.
    The inner Stage 29.4 pass result still flowed through
    verbatim.
  * ``PROVIDER_REJECTED``      -- the operator-supplied
    evidence-provider / ATH-context-provider raised; the flush
    swallowed the error and recorded the closed-set status.
    The inner Stage 29.4 pass result still flowed through
    verbatim.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched.
  * No network. No HTTP. No gRPC. No WebSocket. No socket. No
    file I/O at import or call time.
  * No third-party runtime dependency. Imports only stdlib
    (``dataclasses`` / ``pathlib`` / ``typing``) plus the Stage
    29.5 model surface for the locked enforcement / redaction
    tokens.
  * No top-level Call (no implicit I/O at import time).
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-26 import. No Stage 28 import. No Stage 29.3 /
    Stage 29.4 orchestrator import.
  * No Discord / Telegram / X / social / webhook / Helius /
    Chainstack / Birdeye / Dexscreener / Pump.fun reference.
  * No enforcement / routing / trading / wallet / signer surface.
  * ``filter_enforcement_status`` is locked verbatim to
    ``NOT_ACTIVE_STAGE_29_PENDING`` and any other value is
    rejected by the dataclass validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    REDACTION_STATUS_SAFE,
    is_stage29_5_measurement_status_value,
    is_stage29_5_migration_join_status_value,
    is_stage29_5_warning_code_value,
)


# ---------------------------------------------------------------------------
# Stage 29.5.3 schema version pin
# ---------------------------------------------------------------------------


STAGE29_5_3_OBSERVATION_SCHEMA_VERSION: str = (
    "stage29_5_3_wrapped_pass_observation_v0"
)


# ---------------------------------------------------------------------------
# Stage 29.5.3 safe-shape candidate base mint validator
# ---------------------------------------------------------------------------
#
# The Stage 29.5.3 wrapper observes a candidate base mint echo per
# pass. The echo is observational only — it is never used as a
# routing axis, a dispatch key, an authentication token, a
# webhook target, or a price source. Even so, the redaction
# discipline requires a positive base58 mint-like shape check
# that REJECTS:
#
#   * empty / whitespace / non-printable strings,
#   * URL-shaped strings (any character outside the base58
#     alphabet, including the colon and slash and dot
#     characters that appear in URL schemes / hosts / paths),
#   * auth-header substrings (the standard HTTP-spec header
#     prefixes are rejected because the space and colon
#     characters are not in the base58 alphabet),
#   * secret-key prefix shapes (the dash character is not in
#     the base58 alphabet),
#   * env-assignment shapes (the equals sign is not in the
#     base58 alphabet),
#   * webhook URL host substrings (forbidden URL hosts contain
#     dot characters that are not in the base58 alphabet),
#   * anything else that does not match the canonical Solana
#     base58 alphabet inside a [32, 64] length window.
#
# Standard Solana base58 alphabet (no 0, no O, no I, no l, no
# whitespace, no punctuation). The alphabet is stored as a plain
# ``str`` constant so module body remains Call-free at import
# time; ``ch in _STAGE29_5_3_BASE58_ALPHABET`` is O(n) over a
# 58-character string, which is negligible for the per-character
# membership check in the validator below.


_STAGE29_5_3_BASE58_ALPHABET: str = (
    "123456789"
    "ABCDEFGHJKLMNPQRSTUVWXYZ"
    "abcdefghijkmnopqrstuvwxyz"
)


_STAGE29_5_3_CANDIDATE_BASE_MINT_MIN_LEN: int = 32
_STAGE29_5_3_CANDIDATE_BASE_MINT_MAX_LEN: int = 64


def is_stage29_5_3_safe_candidate_base_mint(value: object) -> bool:
    """Return True iff ``value`` is a Solana base58 mint-like
    string of length [32, 64] using only the canonical base58
    alphabet.

    A positive shape check; rejects URL-shaped, auth-header,
    api-key-prefix, secret-key-prefix, whitespace, non-printable,
    and forbidden-URL-host substrings automatically because none
    of those characters lie inside the base58 alphabet (or the
    length is outside the [32, 64] window).
    """
    if not isinstance(value, str):
        return False
    n = len(value)
    if n < _STAGE29_5_3_CANDIDATE_BASE_MINT_MIN_LEN:
        return False
    if n > _STAGE29_5_3_CANDIDATE_BASE_MINT_MAX_LEN:
        return False
    if not value.isprintable():
        return False
    for ch in value:
        if ch not in _STAGE29_5_3_BASE58_ALPHABET:
            return False
    return True


# ---------------------------------------------------------------------------
# Closed-set: observation_status
# ---------------------------------------------------------------------------


OBSERVATION_STATUS_NO_CANDIDATE_AXES: str = (
    "NO_CANDIDATE_AXES"
)
OBSERVATION_STATUS_COMPOSED: str = "COMPOSED"
OBSERVATION_STATUS_COMPOSITION_REJECTED: str = (
    "COMPOSITION_REJECTED"
)
OBSERVATION_STATUS_PROVIDER_REJECTED: str = (
    "PROVIDER_REJECTED"
)


STAGE29_5_3_OBSERVATION_STATUS_VALUES: Tuple[str, ...] = (
    OBSERVATION_STATUS_NO_CANDIDATE_AXES,
    OBSERVATION_STATUS_COMPOSED,
    OBSERVATION_STATUS_COMPOSITION_REJECTED,
    OBSERVATION_STATUS_PROVIDER_REJECTED,
)


def is_stage29_5_3_observation_status_value(
    value: object,
) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE29_5_3_OBSERVATION_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Stage 29.5.3 exception hierarchy
# ---------------------------------------------------------------------------


class Stage29_5_3WrappedPassError(Exception):
    """Base type for Stage 29.5.3 wrapper-related validation
    errors.

    Module-local; not a subclass of any central PHX2 error
    registry. The constructor never carries a raw upstream
    payload, a raw env value, a raw URL, or a raw secret.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        if not isinstance(reason, str):
            raise ValueError(
                "Stage29_5_3WrappedPassError reason must be a "
                "string"
            )
        if not isinstance(detail, str):
            raise ValueError(
                "Stage29_5_3WrappedPassError detail must be a "
                "string"
            )
        super().__init__(
            f"{reason}: {detail}" if detail else reason
        )
        self.reason: str = reason
        self.detail: str = detail


class Stage29_5_3MigrationEvidenceProviderError(
    Stage29_5_3WrappedPassError,
):
    """Raised by the Stage 29.5.3 operator-supplied migration-
    evidence provider when it cannot return a valid sequence of
    Stage 29.5 evidence records for the candidate base mint.

    The flush step catches this exception in non-strict mode and
    records ``observation_status=PROVIDER_REJECTED``; the inner
    Stage 29.4 pass result flows through verbatim regardless. In
    strict mode the flush propagates the exception.
    """


class Stage29_5_3SideChannelArtifactError(
    Stage29_5_3WrappedPassError,
):
    """Raised by the Stage 29.5.3 side-channel artifact writer
    when it cannot append a JSONL observation line to the soak
    output directory.

    In non-strict flush mode the wrapper swallows this exception
    so artifact write failures never affect the inner Stage 29.4
    pass result and never change the soak outcome. In strict
    flush mode the flush propagates the exception.
    """


# ---------------------------------------------------------------------------
# Stage 29.5.3 pending pass observation (recorded inside __call__)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5_3PendingPassObservation:
    """Immutable Stage 29.5.3 per-pass PENDING observation.

    The wrapper appends one of these records inside ``__call__``
    BEFORE returning the inner ``Stage29_4PassResult`` by
    identity. The record carries ONLY the inputs needed to later
    materialize a composed observation:

      * ``pass_index``           -- the 1-based pass index the
        Stage 29.4 orchestrator handed to ``__call__``.
      * ``candidate_base_mint``  -- ``None`` (when the inner pass
        had no dedupe key OR the dedupe key's ``token_mint``
        failed the Stage 29.5.3 base58 safe-shape validator) OR
        the safe-shape token mint echo.
      * ``soak_output_dir``      -- the soak output directory the
        operator passed to ``__call__``. Stored so the post-soak
        flush step can append the JSONL side-channel artifact
        line into the same directory the orchestrator used.

    The pending record carries NO provider call result, NO Stage
    29.5.2 composition, NO Stage 29.5 join / projection echo, NO
    timestamp, NO operator URL, NO operator secret, NO raw
    provider payload, NO raw exception string.

    The dataclass validator enforces:

      * ``pass_index`` is a positive int (never bool, never < 1).
      * ``candidate_base_mint`` is ``None`` OR a Solana base58
        mint-like string in the [32, 64] length window.
      * ``soak_output_dir`` is a :class:`pathlib.Path` instance.
    """

    pass_index: int
    candidate_base_mint: Optional[str]
    soak_output_dir: Path

    def __post_init__(self) -> None:
        if isinstance(self.pass_index, bool) or not (
            isinstance(self.pass_index, int)
        ):
            raise Stage29_5_3WrappedPassError(
                "PENDING_PASS_INDEX_NOT_INT",
                f"got {type(self.pass_index).__name__}",
            )
        if self.pass_index < 1:
            raise Stage29_5_3WrappedPassError(
                "PENDING_PASS_INDEX_NOT_POSITIVE",
                f"got {self.pass_index!r}",
            )
        if self.candidate_base_mint is not None:
            if not is_stage29_5_3_safe_candidate_base_mint(
                self.candidate_base_mint,
            ):
                raise Stage29_5_3WrappedPassError(
                    "PENDING_CANDIDATE_BASE_MINT_NOT_SAFE_SHAPE",
                )
        if not isinstance(self.soak_output_dir, Path):
            raise Stage29_5_3WrappedPassError(
                "PENDING_SOAK_OUTPUT_DIR_NOT_PATH",
            )


# ---------------------------------------------------------------------------
# Stage 29.5.3 composed wrapped-pass observation record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5_3WrappedPassObservation:
    """Immutable Stage 29.5.3 per-pass observation.

    Captures the closed-set Stage 29.5.3 observation status, the
    pass index, the candidate base mint (when the inner pass
    yielded a dedupe key that passed the Stage 29.5.3 safe-shape
    validator), the Stage 29.5 join / projection echo fields, the
    Stage 29.5 warning-code tuple echo, the observation timestamp,
    and the locked
    ``filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING`` /
    ``redaction_status=SAFE`` axes.

    The record carries only closed-set tokens, safe-shape
    identifier echoes, and safe-shape ISO-8601 timestamps; no
    webhook URL, RPC endpoint, API key, bearer token, auth
    header, raw provider payload, or raw exception string is ever
    carried.

    Validators enforce:

      * ``observation_status`` ∈ closed-set
        :data:`STAGE29_5_3_OBSERVATION_STATUS_VALUES`.
      * ``pass_index`` is a positive int (never bool, never < 1).
      * ``candidate_base_mint`` is ``None`` OR a Solana base58
        mint-like string in the [32, 64] length window using
        only the canonical base58 alphabet (no URL, no
        auth-header substring, no api-key prefix, no secret-key
        prefix, no whitespace, no non-printable, no equals
        sign).
      * ``join_status_echoed`` is ``None`` OR a closed-set Stage
        29.5 ``migration_join_status`` token.
      * ``measurement_status_echoed`` is ``None`` OR a closed-set
        Stage 29.5 ``measurement_status`` token.
      * ``post_migration_ath_verified_echoed`` is ``None`` OR a
        bool.
      * Each token in ``warnings_echoed`` is a closed-set Stage
        29.5 warning code; the tuple carries no duplicates.
      * ``observed_at_utc`` is a printable non-empty string of
        bounded length.
      * ``filter_enforcement_status`` equals
        ``NOT_ACTIVE_STAGE_29_PENDING``.
      * ``redaction_status`` equals ``SAFE``.
      * ``schema_version`` equals the locked Stage 29.5.3 version
        string.
    """

    pass_index: int
    observation_status: str
    candidate_base_mint: Optional[str]
    join_status_echoed: Optional[str]
    measurement_status_echoed: Optional[str]
    post_migration_ath_verified_echoed: Optional[bool]
    warnings_echoed: Tuple[str, ...]
    observed_at_utc: str
    filter_enforcement_status: str = (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    redaction_status: str = REDACTION_STATUS_SAFE
    schema_version: str = (
        STAGE29_5_3_OBSERVATION_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if isinstance(self.pass_index, bool) or not (
            isinstance(self.pass_index, int)
        ):
            raise Stage29_5_3WrappedPassError(
                "PASS_INDEX_NOT_INT",
                f"got {type(self.pass_index).__name__}",
            )
        if self.pass_index < 1:
            raise Stage29_5_3WrappedPassError(
                "PASS_INDEX_NOT_POSITIVE",
                f"got {self.pass_index!r}",
            )
        if not is_stage29_5_3_observation_status_value(
            self.observation_status,
        ):
            raise Stage29_5_3WrappedPassError(
                "OBSERVATION_STATUS_NOT_CLOSED_SET",
                f"got {self.observation_status!r}",
            )
        if self.candidate_base_mint is not None:
            if not is_stage29_5_3_safe_candidate_base_mint(
                self.candidate_base_mint,
            ):
                raise Stage29_5_3WrappedPassError(
                    "CANDIDATE_BASE_MINT_NOT_SAFE_SHAPE",
                )
        if (
            self.join_status_echoed is not None
            and not is_stage29_5_migration_join_status_value(
                self.join_status_echoed,
            )
        ):
            raise Stage29_5_3WrappedPassError(
                "JOIN_STATUS_NOT_CLOSED_SET",
                f"got {self.join_status_echoed!r}",
            )
        if (
            self.measurement_status_echoed is not None
            and not is_stage29_5_measurement_status_value(
                self.measurement_status_echoed,
            )
        ):
            raise Stage29_5_3WrappedPassError(
                "MEASUREMENT_STATUS_NOT_CLOSED_SET",
                f"got {self.measurement_status_echoed!r}",
            )
        if (
            self.post_migration_ath_verified_echoed is not None
            and not isinstance(
                self.post_migration_ath_verified_echoed, bool,
            )
        ):
            raise Stage29_5_3WrappedPassError(
                "POST_MIGRATION_ATH_VERIFIED_NOT_BOOL",
            )
        if not isinstance(self.warnings_echoed, tuple):
            raise Stage29_5_3WrappedPassError(
                "WARNINGS_ECHOED_NOT_TUPLE",
            )
        seen: set = set()
        for code in self.warnings_echoed:
            if not is_stage29_5_warning_code_value(code):
                raise Stage29_5_3WrappedPassError(
                    "WARNING_CODE_NOT_CLOSED_SET",
                    f"got {code!r}",
                )
            if code in seen:
                raise Stage29_5_3WrappedPassError(
                    "WARNING_CODE_DUPLICATE",
                    f"duplicate {code!r}",
                )
            seen.add(code)
        if not isinstance(self.observed_at_utc, str):
            raise Stage29_5_3WrappedPassError(
                "OBSERVED_AT_UTC_NOT_STR",
            )
        if not self.observed_at_utc:
            raise Stage29_5_3WrappedPassError(
                "OBSERVED_AT_UTC_EMPTY",
            )
        if len(self.observed_at_utc) > 64:
            raise Stage29_5_3WrappedPassError(
                "OBSERVED_AT_UTC_TOO_LONG",
            )
        if not self.observed_at_utc.isprintable():
            raise Stage29_5_3WrappedPassError(
                "OBSERVED_AT_UTC_NOT_PRINTABLE",
            )
        if (
            self.filter_enforcement_status
            != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ):
            raise Stage29_5_3WrappedPassError(
                "FILTER_ENFORCEMENT_STATUS_NOT_LOCKED",
                f"got {self.filter_enforcement_status!r}",
            )
        if self.redaction_status != REDACTION_STATUS_SAFE:
            raise Stage29_5_3WrappedPassError(
                "REDACTION_STATUS_NOT_SAFE",
                f"got {self.redaction_status!r}",
            )
        if (
            self.schema_version
            != STAGE29_5_3_OBSERVATION_SCHEMA_VERSION
        ):
            raise Stage29_5_3WrappedPassError(
                "SCHEMA_VERSION_NOT_LOCKED",
                f"got {self.schema_version!r}",
            )


# ---------------------------------------------------------------------------
# Field-name pin tuple (used by canonical JSON projection)
# ---------------------------------------------------------------------------


STAGE29_5_3_OBSERVATION_FIELD_NAMES: Tuple[str, ...] = (
    "schema_version",
    "pass_index",
    "observation_status",
    "candidate_base_mint",
    "join_status_echoed",
    "measurement_status_echoed",
    "post_migration_ath_verified_echoed",
    "warnings_echoed",
    "observed_at_utc",
    "filter_enforcement_status",
    "redaction_status",
)


__all__ = (
    "STAGE29_5_3_OBSERVATION_SCHEMA_VERSION",
    "OBSERVATION_STATUS_NO_CANDIDATE_AXES",
    "OBSERVATION_STATUS_COMPOSED",
    "OBSERVATION_STATUS_COMPOSITION_REJECTED",
    "OBSERVATION_STATUS_PROVIDER_REJECTED",
    "STAGE29_5_3_OBSERVATION_STATUS_VALUES",
    "is_stage29_5_3_observation_status_value",
    "is_stage29_5_3_safe_candidate_base_mint",
    "Stage29_5_3WrappedPassError",
    "Stage29_5_3MigrationEvidenceProviderError",
    "Stage29_5_3SideChannelArtifactError",
    "Stage29_5_3PendingPassObservation",
    "Stage29_5_3WrappedPassObservation",
    "STAGE29_5_3_OBSERVATION_FIELD_NAMES",
)
