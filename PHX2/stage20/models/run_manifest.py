"""Stage 20 RunManifest model shape (NamedTuple).

Shape declaration only -- 20.2 will build a manifest dict from a
RunManifest instance and write it to disk. 20.1 declares the
typed record shape so the field set is locked.

Field provenance:

  * stage20_run_id              -- 16-hex SHA-256 prefix over
                                   the canonical input set (20.2
                                   derivation).
  * stage20_version             -- STAGE20_VERSION constant.
  * consumer_contract_version   -- CONSUMER_CONTRACT_VERSION
                                   constant.
  * mapping_version             -- MAPPING_VERSION constant.
  * run_timestamp_utc           -- per-run UTC timestamp, plumbed
                                   through from the injected
                                   Clock (or CLI scalar override
                                   in 20.2+).
  * stage18_input_dir           -- absolute path to the Stage 18
                                   run directory.
  * stage18_run_id              -- pulled from the Stage 18
                                   manifest.
  * stage18_manifest_sha256     -- SHA-256 of the Stage 18
                                   manifest.json as observed by
                                   Stage 20 (recomputed; same
                                   value as Stage 19 manifest's
                                   stage18_manifest_sha256 if
                                   Stage 18 was not tampered).
  * stage18_review_matrix_sha256 -- SHA-256 of the Stage 18
                                   review_matrix.csv as observed
                                   by Stage 20.
  * stage19_input_dir           -- absolute path to the Stage 19
                                   run directory.
  * stage19_run_id              -- pulled from the Stage 19
                                   manifest.
  * stage19_ledger_sha256       -- Optional[str]. Stage 20.1
                                   keeps this None because no
                                   source-of-truth hash for the
                                   ledger exists upstream
                                   (E2004 deferred). A later
                                   phase may populate it.
  * candidate_count             -- total PreviewCandidate rows
                                   produced by the run.
  * preview_eligible_count      -- subset of candidate_count whose
                                   eligibility_state is
                                   PREVIEW_ELIGIBLE.
  * safe_for_live_dispatch      -- always False in Stage 20 v0.
  * git_commit                  -- repo commit hash at run time.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


class RunManifest(NamedTuple):
    """Stage 20 run manifest record (shape only in 20.1)."""

    stage20_run_id: str
    stage20_version: str
    consumer_contract_version: str
    mapping_version: str
    run_timestamp_utc: str
    stage18_input_dir: str
    stage18_run_id: str
    stage18_manifest_sha256: str
    stage18_review_matrix_sha256: str
    stage19_input_dir: str
    stage19_run_id: str
    stage19_ledger_sha256: Optional[str]
    candidate_count: int
    preview_eligible_count: int
    safe_for_live_dispatch: bool
    git_commit: str


__all__ = ["RunManifest"]
