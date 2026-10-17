"""Small authenticated singleton-state stores used by production sidecars.

The repository already has a strong authenticated/generational checkpoint
format in :mod:`checkpoint_envelope`.  This module exposes the same load,
quarantine and publish-after-readback mechanics for new singleton documents
without coupling them to the older RPC-recovery implementation.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from PHX2.free_tier_producer import checkpoint_envelope as _cpe


class AuthenticatedStateWriteError(RuntimeError):
    """The authenticated state could not be durably published."""


class AuthenticatedSingletonStore:
    """Base class for one-record authenticated checkpoint documents.

    Subclasses provide kind-specific classification, restoration and record
    projection.  A quarantined primary/backup pair is a permanent write lock
    for the lifetime of the object; it is never treated as empty state.
    """

    checkpoint_kind = ""
    schema_version = ""
    record_kind = ""

    def __init__(
        self,
        *,
        primary_path: object,
        now_iso_fn: Callable[[], str] = _cpe.utc_now_iso,
    ) -> None:
        self._primary = Path(primary_path)
        self._backup = self._primary.with_name(self._primary.name + ".bak")
        self._now_iso = now_iso_fn
        self._lock = threading.RLock()
        self._generation = 0
        self._envelope_digest: Optional[str] = None
        self._created_at: Optional[str] = None
        self._quarantined = False
        self._quarantine_reason: Optional[str] = None
        self._write_locked = False
        self.load_result = _cpe.CheckpointLoadResult(
            checkpoint_kind=self.checkpoint_kind
        )

    def classify(self, path: object) -> _cpe.FileClassification:
        raise NotImplementedError

    def restore_record(self, record: Mapping[str, Any]) -> None:
        raise NotImplementedError

    def current_record(self) -> Dict[str, Any]:
        raise NotImplementedError

    @property
    def primary_path(self) -> Path:
        return self._primary

    @property
    def backup_path(self) -> Path:
        return self._backup

    @property
    def quarantined(self) -> bool:
        return self._quarantined

    @property
    def quarantine_reason(self) -> Optional[str]:
        return self._quarantine_reason

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def envelope_digest(self) -> Optional[str]:
        return self._envelope_digest

    def load(self) -> _cpe.CheckpointLoadResult:
        with self._lock:
            primary = self.classify(self._primary)
            backup = self.classify(self._backup)
            decision = _cpe.resolve_checkpoint_pair(primary, backup)
            result = _cpe.CheckpointLoadResult(
                checkpoint_kind=self.checkpoint_kind,
                checkpoint_status=decision.status,
                checkpoint_primary_status=primary.state,
                checkpoint_backup_status=backup.state,
                checkpoint_recovered_from_backup=decision.recovered_from_backup,
                checkpoint_quarantined=decision.quarantined,
                checkpoint_quarantine_reason=decision.quarantine_reason,
                checkpoint_files_found=(
                    primary.state != _cpe.FILE_MISSING
                    or backup.state != _cpe.FILE_MISSING
                ),
                checkpoint_source_selected=decision.selected,
                checkpoint_last_validated_at_utc=self._now_iso(),
            )
            if decision.status == _cpe.CHECKPOINT_NOT_FOUND:
                self.load_result = result
                return result
            if decision.quarantined:
                self._quarantined = True
                self._quarantine_reason = decision.quarantine_reason
                self._write_locked = True
                self.load_result = result
                return result
            selected = primary if decision.selected == "primary" else backup
            matching = [
                record
                for record in (selected.records or [])
                if record.get("record_kind") == self.record_kind
            ]
            if len(matching) != 1:
                self._quarantined = True
                self._quarantine_reason = _cpe.QUARANTINE_RECORD_COUNT_MISMATCH
                self._write_locked = True
                result.checkpoint_quarantined = True
                result.checkpoint_status = _cpe.CHECKPOINT_QUARANTINED
                result.checkpoint_quarantine_reason = self._quarantine_reason
                self.load_result = result
                return result
            self.restore_record(matching[0])
            self._generation = (
                int(selected.header.get("generation") or 0)
                if selected.header
                else 0
            )
            self._envelope_digest = (
                selected.envelope_digest if selected.header else None
            )
            self._created_at = (
                selected.header.get("created_at_utc")
                if selected.header
                else None
            )
            result.checkpoint_generation = self._generation
            result.checkpoint_records_validated = 1
            self.load_result = result
            return result

    def persist(self) -> None:
        with self._lock:
            self._persist_record_locked(self.current_record())

    def _persist_record_locked(self, record: Dict[str, Any]) -> None:
        if self._write_locked:
            raise AuthenticatedStateWriteError(
                self._quarantine_reason or "AUTHENTICATED_STATE_WRITE_LOCKED"
            )
        now = self._now_iso()
        record = dict(record)
        record["record_digest"] = _cpe.build_record_digest(
            self.checkpoint_kind, record
        )
        header = _cpe.build_envelope_header(
            checkpoint_kind=self.checkpoint_kind,
            schema_version=self.schema_version,
            payload_encoding=_cpe.PAYLOAD_ENCODING_DOCUMENT,
            generation=self._generation + 1,
            record_digests=[record["record_digest"]],
            created_at_utc=self._created_at or now,
            updated_at_utc=now,
            previous_generation_digest=self._envelope_digest,
            source_id=self._primary.name,
        )
        try:
            _cpe.write_checkpoint_generation_resilient(
                primary_path=self._primary,
                backup_path=self._backup,
                header=header,
                records=[record],
                classify=lambda path: self.classify(path),
            )
        except (_cpe.CheckpointWriteError, OSError) as exc:
            raise AuthenticatedStateWriteError(
                type(exc).__name__
            ) from exc
        self._generation = int(header["generation"])
        self._envelope_digest = str(header["envelope_digest"])
        self._created_at = self._created_at or now


__all__ = (
    "AuthenticatedSingletonStore",
    "AuthenticatedStateWriteError",
)
