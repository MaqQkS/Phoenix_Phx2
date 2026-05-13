"""Stage 15 error code enumeration.

The Stage 15 error code set is closed:

  L01-L26: load-time validation errors
  A01-A04: approval-time validation errors

No other codes exist. Tests must assert the set is closed.

Three-tier exit discipline:

  Tier 1 (output-dir initialization failure):
    stderr only; no manifest; no log; exit non-zero.

  Tier 2 (load-time validation failure L01-L26):
    write stage15_run.log only (if possible); no manifest; exit non-zero.

  Tier 3 (approval-time validation failure A01-A04):
    write non-draft outputs + manifest with approval_status="VALIDATION_FAILED";
    NO approved_observe_only_policy_draft.json; exit non-zero.

Manifest existence means Stage 15 reached the artifact-writing phase. If
the manifest is absent, the run is invalid by definition.
"""

from __future__ import annotations


LOAD_TIME_ERROR_CODES: tuple[str, ...] = (
    "L01", "L02", "L03", "L04", "L05", "L06", "L07", "L08", "L09",
    "L10", "L11", "L12", "L13", "L14", "L15", "L16", "L17", "L18",
    "L19", "L20", "L21", "L22", "L23", "L24", "L25", "L26",
)

APPROVAL_TIME_ERROR_CODES: tuple[str, ...] = ("A01", "A02", "A03", "A04")

ALL_ERROR_CODES: frozenset[str] = frozenset(
    LOAD_TIME_ERROR_CODES + APPROVAL_TIME_ERROR_CODES
)


class Stage15Error(Exception):
    """Base for Stage 15 errors. Carries a closed-set error code."""

    code: str = ""

    def __init__(self, code: str, message: str) -> None:
        if code not in ALL_ERROR_CODES:
            raise ValueError(
                f"Stage15Error code {code!r} is not in the closed Stage 15 "
                f"error code set"
            )
        self.code = code
        super().__init__(f"[{code}] {message}")


class Stage15OutputDirError(Stage15Error):
    """Output-dir initialization failure (Tier 1).

    Raised when --output-dir cannot be safely initialized. No manifest
    or log gets written. The CLI prints to stderr and exits non-zero.
    """


class Stage15LoadTimeError(Stage15Error):
    """Load-time validation failure (Tier 2): L01-L26.

    Raised when one of L01-L26 fires. No manifest is written. A log
    file may be written if the output dir was already initialized.
    """

    def __init__(self, code: str, message: str) -> None:
        if code not in LOAD_TIME_ERROR_CODES:
            raise ValueError(
                f"Stage15LoadTimeError requires a load-time code "
                f"(L01-L26); got {code!r}"
            )
        super().__init__(code, message)


class Stage15ApprovalTimeError(Stage15Error):
    """Approval-time validation failure (Tier 3): A01-A04.

    Raised when one of A01-A04 fires for a specific operator decision.
    The Stage 15 driver collects these per-row rather than aborting on
    the first one, so the validation errors CSV can enumerate every
    problem at once. Non-draft outputs and a VALIDATION_FAILED manifest
    are still written.
    """

    def __init__(self, code: str, message: str) -> None:
        if code not in APPROVAL_TIME_ERROR_CODES:
            raise ValueError(
                f"Stage15ApprovalTimeError requires an approval-time code "
                f"(A01-A04); got {code!r}"
            )
        super().__init__(code, message)
