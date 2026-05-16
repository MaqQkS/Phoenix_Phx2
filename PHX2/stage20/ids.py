"""Stage 20.2 deterministic ID derivations.

Pure functions only -- no I/O, no clocks, no module-level state.
Each function takes its inputs explicitly so tests can pin a
canonical input vector and assert byte-stable outputs.

Hashing protocol (locked at 20.2):
  * SHA-256 over the UTF-8 encoded bytes of the concatenated
    input fields joined by the literal "|" character.
  * The hex digest is truncated to its first 16 hex characters
    (64 bits of collision resistance).
  * A short string prefix identifies the namespace
    ("stage20_", "cand_", "dec_").
  * If any input field contains the "|" separator, the function
    raises ``ValueError`` immediately. No sanitization recovery
    -- callers must supply fields that do not embed the
    separator. The closed-set inputs (run ids, ledger_row_id,
    locked decision_step_name values, fixed version strings)
    do not contain "|" in any normal pipeline state.

Per operator decision B2-c the minor-version axis
(``STAGE20_MINOR_VERSION`` = "20.2") is mixed into every ID
alongside the major-version axis (``STAGE20_VERSION``). Bumping
either axis re-derives every id.

Public surface:
  * ``derive_stage20_run_id``  -- 11 inputs, returns
                                  "stage20_" + 16-hex.
  * ``derive_candidate_id``    -- 4 inputs, returns "cand_" + 16-hex.
  * ``derive_decision_id``     -- 5 inputs, returns "dec_" + 16-hex.
"""

from __future__ import annotations

import hashlib


_FIELD_SEPARATOR: str = "|"


def _check_no_separator(*fields: str) -> None:
    """Raise ValueError if any field contains the "|" separator.

    The "|" character is the locked field delimiter in every ID
    derivation. Embedding it in a field would create ambiguity at
    the byte level (two distinct input tuples could hash to the
    same payload). Closed-set inputs never legitimately contain
    "|", so any occurrence is a programming error.
    """

    for field in fields:
        if _FIELD_SEPARATOR in field:
            raise ValueError(
                "ID-derivation field contains forbidden separator "
                f"{_FIELD_SEPARATOR!r}: {field!r}"
            )


def _sha256_hex16(payload: str) -> str:
    """Return the first 16 hex chars of SHA-256 over UTF-8 bytes."""

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:16]


def derive_stage20_run_id(
    *,
    stage18_run_id: str,
    stage18_manifest_sha256: str,
    stage18_review_matrix_sha256: str,
    stage19_run_id: str,
    stage19_ledger_sha256: str,
    stage19_manifest_sha256: str,
    stage20_version: str,
    stage20_minor_version: str,
    mapping_version: str,
    consumer_contract_version: str,
    generated_at_utc: str,
) -> str:
    """Derive the per-run stage20_run_id.

    Includes:
      * upstream run ids (stage18, stage19)
      * four input file hashes (stage18 manifest, stage18
        review_matrix, stage19 manifest, stage19 ledger)
      * Stage 20 version pair (major + minor per operator
        decision B2-c)
      * mapping_version, consumer_contract_version
      * generated_at_utc (the frozen clock value for the run)

    Returns:
        "stage20_" + first-16-hex of SHA-256 over the joined
        UTF-8 payload.
    """

    _check_no_separator(
        stage18_run_id,
        stage18_manifest_sha256,
        stage18_review_matrix_sha256,
        stage19_run_id,
        stage19_ledger_sha256,
        stage19_manifest_sha256,
        stage20_version,
        stage20_minor_version,
        mapping_version,
        consumer_contract_version,
        generated_at_utc,
    )
    payload = _FIELD_SEPARATOR.join((
        stage18_run_id,
        stage18_manifest_sha256,
        stage18_review_matrix_sha256,
        stage19_run_id,
        stage19_ledger_sha256,
        stage19_manifest_sha256,
        stage20_version,
        stage20_minor_version,
        mapping_version,
        consumer_contract_version,
        generated_at_utc,
    ))
    return "stage20_" + _sha256_hex16(payload)


def derive_candidate_id(
    *,
    stage19_run_id: str,
    source_ledger_row_id: str,
    stage20_version: str,
    stage20_minor_version: str,
) -> str:
    """Derive the per-(slice, operator) candidate_id.

    The candidate_id is stable across reruns over the same
    (stage19_run_id, source_ledger_row_id) — which themselves are
    deterministic outputs of Stage 19 — as long as the Stage 20
    version pair is unchanged.

    Returns:
        "cand_" + first-16-hex of SHA-256 over the joined payload.
    """

    _check_no_separator(
        stage19_run_id,
        source_ledger_row_id,
        stage20_version,
        stage20_minor_version,
    )
    payload = _FIELD_SEPARATOR.join((
        stage19_run_id,
        source_ledger_row_id,
        stage20_version,
        stage20_minor_version,
    ))
    return "cand_" + _sha256_hex16(payload)


def derive_decision_id(
    *,
    candidate_id: str,
    decision_step_index: int,
    decision_step_name: str,
    stage20_version: str,
    stage20_minor_version: str,
) -> str:
    """Derive a per-decision-row decision_id.

    Inputs:
      * candidate_id          -- foreign key to PreviewCandidate.
      * decision_step_index   -- 0-based contiguous index (int).
                                 Converted to str() before joining.
      * decision_step_name    -- locked vocabulary value (one of
                                 DECISION_STEP_NAMES_4 in 20.2).
      * stage20_version       -- run-level major version.
      * stage20_minor_version -- run-level minor version.

    Returns:
        "dec_" + first-16-hex of SHA-256 over the joined payload.
    """

    step_index_str = str(decision_step_index)
    _check_no_separator(
        candidate_id,
        step_index_str,
        decision_step_name,
        stage20_version,
        stage20_minor_version,
    )
    payload = _FIELD_SEPARATOR.join((
        candidate_id,
        step_index_str,
        decision_step_name,
        stage20_version,
        stage20_minor_version,
    ))
    return "dec_" + _sha256_hex16(payload)


__all__ = [
    "derive_candidate_id",
    "derive_decision_id",
    "derive_stage20_run_id",
]
