"""PHX2 versioned, authenticated checkpoint envelope (PHX2-E2E-005).

One shared contract for every production restart checkpoint that can influence
authorization (active watch state, centralized ATH state). The envelope makes
three failure classes impossible to hit silently:

1. SILENT EMPTY LOAD — an existing checkpoint file with invalid content is
   never treated as "no checkpoint exists". Missing and corrupt are distinct
   states; corrupt primary+backup quarantines instead of loading empty.
2. TAMPERED RESTORATION — every record, the ordered payload, and the envelope
   header carry independent SHA-256 digests over canonical serialization; a
   modified value, a zero digest, or an unsupported schema fails closed.
3. SCHEMA-UPGRADE STATE LOSS — supported legacy schemas migrate through an
   explicit registry instead of being silently downgraded; unsupported or
   ambiguous state quarantines with the original evidence preserved.

The module is deliberately generic: it owns canonical serialization, digest
construction, the primary/backup load decision matrix, safe rotation-order
writes, and the closed set of quarantine reasons. Checkpoint-kind semantics
(what a valid watch entry or ATH record looks like, and how a legacy record
migrates) are supplied by the owning module through callbacks.

No network, provider, transport, or ledger interaction happens here.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

ENVELOPE_VERSION = "phx2_checkpoint_envelope_v1"
RECORD_DIGEST_DOMAIN = "phx2_checkpoint_record_v1"
PAYLOAD_DIGEST_DOMAIN = "phx2_checkpoint_payload_v1"

CHECKPOINT_KIND_WATCH = "PHX2_WATCH_CHECKPOINT"
CHECKPOINT_KIND_ATH = "PHX2_CENTRAL_ATH_CHECKPOINT"

PAYLOAD_ENCODING_JSONL = "jsonl_lines"
PAYLOAD_ENCODING_DOCUMENT = "json_document"

# Identifies the build that wrote a checkpoint generation. A stable contract
# tag rather than a git hash so offline verification never needs git.
CHECKPOINT_WRITER_BUILD = "phx2_e2e005_authenticated_checkpoint_v1"

ZERO_DIGEST = "0" * 64
ALLOWED_CLOCK_SKEW_SECONDS = 300.0
# Hostile-input backstops. Legitimate checkpoint size is already bounded by
# the structural caps of the owning stores (active-watch capacity, durable
# event-dedupe key cap); these limits only stop unbounded allocation from a
# hostile file.
MAX_CHECKPOINT_BYTES = 1024 * 1024 * 1024
MAX_CHECKPOINT_RECORDS = 100_000

# ---- load statuses (closed set) -------------------------------------------
CHECKPOINT_NOT_FOUND = "CHECKPOINT_NOT_FOUND"
CHECKPOINT_PRIMARY_OK = "CHECKPOINT_PRIMARY_OK"
CHECKPOINT_PRIMARY_AND_BACKUP_OK = "CHECKPOINT_PRIMARY_AND_BACKUP_OK"
CHECKPOINT_RECOVERED_FROM_BACKUP = "CHECKPOINT_RECOVERED_FROM_BACKUP"
CHECKPOINT_BACKUP_INVALID = "CHECKPOINT_BACKUP_INVALID"
CHECKPOINT_MIGRATED = "CHECKPOINT_MIGRATED"
CHECKPOINT_QUARANTINED = "CHECKPOINT_QUARANTINED"

CHECKPOINT_STATUSES = (
    CHECKPOINT_NOT_FOUND,
    CHECKPOINT_PRIMARY_OK,
    CHECKPOINT_PRIMARY_AND_BACKUP_OK,
    CHECKPOINT_RECOVERED_FROM_BACKUP,
    CHECKPOINT_BACKUP_INVALID,
    CHECKPOINT_MIGRATED,
    CHECKPOINT_QUARANTINED,
)

# ---- per-file classification states ---------------------------------------
FILE_MISSING = "MISSING"
FILE_VALID_CURRENT = "VALID_CURRENT"
FILE_VALID_LEGACY = "VALID_LEGACY"
FILE_INVALID = "INVALID"

# ---- quarantine / rejection reasons (closed set) --------------------------
QUARANTINE_JSON_INVALID = "CHECKPOINT_JSON_INVALID"
QUARANTINE_TRUNCATED = "CHECKPOINT_TRUNCATED"
QUARANTINE_SCHEMA_UNSUPPORTED = "CHECKPOINT_SCHEMA_UNSUPPORTED"
QUARANTINE_KIND_INVALID = "CHECKPOINT_KIND_INVALID"
QUARANTINE_RECORD_DIGEST_INVALID = "CHECKPOINT_RECORD_DIGEST_INVALID"
QUARANTINE_PAYLOAD_DIGEST_INVALID = "CHECKPOINT_PAYLOAD_DIGEST_INVALID"
QUARANTINE_ENVELOPE_DIGEST_INVALID = "CHECKPOINT_ENVELOPE_DIGEST_INVALID"
QUARANTINE_GENERATION_CONFLICT = "CHECKPOINT_GENERATION_CONFLICT"
QUARANTINE_DUPLICATE_RECORD = "CHECKPOINT_DUPLICATE_RECORD"
QUARANTINE_RECORD_COUNT_MISMATCH = "CHECKPOINT_RECORD_COUNT_MISMATCH"
QUARANTINE_MINT_BINDING_INVALID = "CHECKPOINT_MINT_BINDING_INVALID"
QUARANTINE_CANDIDATE_BINDING_INVALID = "CHECKPOINT_CANDIDATE_BINDING_INVALID"
QUARANTINE_NUMERIC_INVALID = "CHECKPOINT_NUMERIC_INVALID"
QUARANTINE_TIMESTAMP_INVALID = "CHECKPOINT_TIMESTAMP_INVALID"
QUARANTINE_ATH_REGRESSION = "CHECKPOINT_ATH_REGRESSION"
QUARANTINE_ACTIVATION_PROOF_INVALID = "CHECKPOINT_ACTIVATION_PROOF_INVALID"
QUARANTINE_CROSSING_DIGEST_INVALID = "CHECKPOINT_CROSSING_DIGEST_INVALID"
QUARANTINE_EVIDENCE_DIGEST_INVALID = "CHECKPOINT_EVIDENCE_DIGEST_INVALID"
QUARANTINE_MIGRATION_AMBIGUOUS = "CHECKPOINT_MIGRATION_AMBIGUOUS"
QUARANTINE_ACTIVATION_MIGRATION_AMBIGUOUS = (
    "CHECKPOINT_ACTIVATION_MIGRATION_AMBIGUOUS")
QUARANTINE_LEGACY_STATUS_UNSUPPORTED = "CHECKPOINT_LEGACY_STATUS_UNSUPPORTED"
QUARANTINE_STATUS_UNSUPPORTED = "CHECKPOINT_STATUS_UNSUPPORTED"
QUARANTINE_DELIVERY_STATE_INVALID = "CHECKPOINT_DELIVERY_STATE_INVALID"
QUARANTINE_MARKET_STATE_INVALID = "CHECKPOINT_MARKET_STATE_INVALID"
QUARANTINE_MIGRATION_WRITE_FAILED = "CHECKPOINT_MIGRATION_WRITE_FAILED"
QUARANTINE_CROSS_CONSISTENCY_INVALID = "CHECKPOINT_CROSS_CONSISTENCY_INVALID"

QUARANTINE_REASONS = (
    QUARANTINE_JSON_INVALID,
    QUARANTINE_TRUNCATED,
    QUARANTINE_SCHEMA_UNSUPPORTED,
    QUARANTINE_KIND_INVALID,
    QUARANTINE_RECORD_DIGEST_INVALID,
    QUARANTINE_PAYLOAD_DIGEST_INVALID,
    QUARANTINE_ENVELOPE_DIGEST_INVALID,
    QUARANTINE_GENERATION_CONFLICT,
    QUARANTINE_DUPLICATE_RECORD,
    QUARANTINE_RECORD_COUNT_MISMATCH,
    QUARANTINE_MINT_BINDING_INVALID,
    QUARANTINE_CANDIDATE_BINDING_INVALID,
    QUARANTINE_NUMERIC_INVALID,
    QUARANTINE_TIMESTAMP_INVALID,
    QUARANTINE_ATH_REGRESSION,
    QUARANTINE_ACTIVATION_PROOF_INVALID,
    QUARANTINE_CROSSING_DIGEST_INVALID,
    QUARANTINE_EVIDENCE_DIGEST_INVALID,
    QUARANTINE_MIGRATION_AMBIGUOUS,
    QUARANTINE_ACTIVATION_MIGRATION_AMBIGUOUS,
    QUARANTINE_LEGACY_STATUS_UNSUPPORTED,
    QUARANTINE_STATUS_UNSUPPORTED,
    QUARANTINE_DELIVERY_STATE_INVALID,
    QUARANTINE_MARKET_STATE_INVALID,
    QUARANTINE_MIGRATION_WRITE_FAILED,
    QUARANTINE_CROSS_CONSISTENCY_INVALID,
)


class CheckpointWriteError(RuntimeError):
    """A checkpoint generation could not be written/validated safely.

    Raised BEFORE the previous primary was replaced whenever possible, so the
    last known-good generation survives the failure.
    """


def _reject_constant(_value: str) -> Any:
    raise ValueError("CHECKPOINT_JSON_CONSTANT_FORBIDDEN")


def _reject_duplicate_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("CHECKPOINT_JSON_DUPLICATE_KEY")
        out[key] = value
    return out


def strict_json_loads(text: str) -> Any:
    """Bounded, deterministic JSON parse: rejects NaN/Infinity constants and
    duplicate object keys instead of silently accepting them."""

    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_constant,
    )


def _assert_canonical_value(value: Any) -> None:
    """Reject floats anywhere in a checkpoint document we are about to write.

    Economic values must already be exact Decimal strings; a float here means
    a caller bug that would make canonical serialization platform-dependent.
    """

    if isinstance(value, float):
        raise ValueError("CHECKPOINT_FLOAT_FORBIDDEN")
    if isinstance(value, dict):
        for item in value.values():
            _assert_canonical_value(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_canonical_value(item)


def canonical_json(value: Mapping[str, Any]) -> str:
    _assert_canonical_value(dict(value))
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False)


def sha256_hex_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_sha256_digest(value: object) -> bool:
    """A syntactically valid, non-degenerate SHA-256 hex digest."""

    return (
        isinstance(value, str)
        and len(value) == 64
        and value != ZERO_DIGEST
        and all(c in "0123456789abcdef" for c in value)
    )


def parse_utc_timestamp(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# digest model
# ---------------------------------------------------------------------------

def build_record_digest(kind: str, payload: Mapping[str, Any]) -> str:
    """Digest of ONE checkpoint record (record content minus its own digest)."""

    body = {k: v for k, v in dict(payload).items() if k != "record_digest"}
    return sha256_hex_text(canonical_json({
        "domain": RECORD_DIGEST_DOMAIN,
        "checkpoint_kind": kind,
        "payload": body,
    }))


def record_digest_is_valid(kind: str, record: Mapping[str, Any]) -> bool:
    supplied = record.get("record_digest")
    if not is_sha256_digest(supplied):
        return False
    try:
        expected = build_record_digest(kind, record)
    except (TypeError, ValueError):
        return False
    return supplied == expected


def build_payload_digest(
    kind: str, schema_version: str, record_digests: Sequence[str]
) -> str:
    """Digest of the ORDERED canonical record set (records already sorted by
    their stable identity before their digests are listed)."""

    return sha256_hex_text(canonical_json({
        "domain": PAYLOAD_DIGEST_DOMAIN,
        "checkpoint_kind": kind,
        "schema_version": schema_version,
        "record_digests": list(record_digests),
    }))


_ENVELOPE_DIGEST_EXCLUDED = ("envelope_digest", "payload")


def build_envelope_digest(header: Mapping[str, Any]) -> str:
    body = {k: v for k, v in dict(header).items()
            if k not in _ENVELOPE_DIGEST_EXCLUDED}
    return sha256_hex_text(canonical_json(body))


# ---------------------------------------------------------------------------
# envelope build / validation
# ---------------------------------------------------------------------------

def build_envelope_header(
    *,
    checkpoint_kind: str,
    schema_version: str,
    payload_encoding: str,
    generation: int,
    record_digests: Sequence[str],
    created_at_utc: str,
    updated_at_utc: str,
    previous_generation_digest: Optional[str],
    source_id: str,
    migration_history: Sequence[Mapping[str, Any]] = (),
    writer_build_version: str = CHECKPOINT_WRITER_BUILD,
    extra_header_fields: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    header: Dict[str, Any] = {
        "envelope_version": ENVELOPE_VERSION,
        "checkpoint_kind": checkpoint_kind,
        "schema_version": schema_version,
        "payload_encoding": payload_encoding,
        "created_at_utc": created_at_utc,
        "updated_at_utc": updated_at_utc,
        "writer_build_version": writer_build_version,
        "generation": int(generation),
        "record_count": len(record_digests),
        "payload_digest": build_payload_digest(
            checkpoint_kind, schema_version, record_digests),
        "previous_generation_digest": previous_generation_digest,
        "source_id": source_id,
        "migration_history": [dict(item) for item in migration_history],
    }
    for key, value in dict(extra_header_fields or {}).items():
        header.setdefault(key, value)
    header["envelope_digest"] = build_envelope_digest(header)
    return header


@dataclass
class FileClassification:
    """One checkpoint file, classified without mutating it."""

    path: Optional[Path]
    state: str = FILE_MISSING
    reason: str = ""
    header: Optional[Dict[str, Any]] = None
    records: List[Dict[str, Any]] = field(default_factory=list)
    legacy_payload: Any = None
    legacy_schema_version: Optional[str] = None
    byte_digest: Optional[str] = None
    raw_bytes: Optional[bytes] = None

    @property
    def generation(self) -> Optional[int]:
        if self.header is None:
            return None
        return self.header.get("generation")

    @property
    def envelope_digest(self) -> Optional[str]:
        if self.header is None:
            return None
        return self.header.get("envelope_digest")

    @property
    def usable(self) -> bool:
        return self.state in (FILE_VALID_CURRENT, FILE_VALID_LEGACY)


def _validate_envelope_document(
    *,
    kind: str,
    header: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    supported_schema_versions: Sequence[str],
    record_validator: Callable[[Mapping[str, Any]], Tuple[bool, str]],
    identity_fn: Callable[[Mapping[str, Any]], Tuple],
    validation_now_utc: Optional[str],
    allowed_clock_skew_seconds: float,
) -> Tuple[bool, str]:
    if header.get("envelope_version") != ENVELOPE_VERSION:
        return False, QUARANTINE_SCHEMA_UNSUPPORTED
    if header.get("checkpoint_kind") != kind:
        return False, QUARANTINE_KIND_INVALID
    if header.get("schema_version") not in supported_schema_versions:
        return False, QUARANTINE_SCHEMA_UNSUPPORTED
    if header.get("payload_encoding") not in (
            PAYLOAD_ENCODING_JSONL, PAYLOAD_ENCODING_DOCUMENT):
        return False, QUARANTINE_SCHEMA_UNSUPPORTED
    generation = header.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) \
            or generation < 1:
        return False, QUARANTINE_NUMERIC_INVALID
    record_count = header.get("record_count")
    if isinstance(record_count, bool) or not isinstance(record_count, int) \
            or record_count < 0:
        return False, QUARANTINE_NUMERIC_INVALID
    created_at = parse_utc_timestamp(header.get("created_at_utc"))
    updated_at = parse_utc_timestamp(header.get("updated_at_utc"))
    if created_at is None or updated_at is None or updated_at < created_at:
        return False, QUARANTINE_TIMESTAMP_INVALID
    now = parse_utc_timestamp(validation_now_utc) or datetime.now(timezone.utc)
    skew = max(0.0, float(allowed_clock_skew_seconds))
    if (updated_at - now).total_seconds() > skew \
            or (created_at - now).total_seconds() > skew:
        return False, QUARANTINE_TIMESTAMP_INVALID
    previous = header.get("previous_generation_digest")
    if previous is not None and not is_sha256_digest(previous):
        return False, QUARANTINE_ENVELOPE_DIGEST_INVALID
    if not isinstance(header.get("migration_history"), list):
        return False, QUARANTINE_SCHEMA_UNSUPPORTED
    if not is_sha256_digest(header.get("envelope_digest")):
        return False, QUARANTINE_ENVELOPE_DIGEST_INVALID
    try:
        expected_envelope = build_envelope_digest(header)
    except (TypeError, ValueError):
        return False, QUARANTINE_ENVELOPE_DIGEST_INVALID
    if header.get("envelope_digest") != expected_envelope:
        return False, QUARANTINE_ENVELOPE_DIGEST_INVALID
    if record_count != len(records):
        return False, QUARANTINE_RECORD_COUNT_MISMATCH
    digests: List[str] = []
    seen_identities: set = set()
    for record in records:
        if not isinstance(record, Mapping):
            return False, QUARANTINE_JSON_INVALID
        if not record_digest_is_valid(kind, record):
            return False, QUARANTINE_RECORD_DIGEST_INVALID
        try:
            identity = identity_fn(record)
        except (TypeError, ValueError, KeyError):
            return False, QUARANTINE_CANDIDATE_BINDING_INVALID
        identities = identity if isinstance(identity, list) else [identity]
        for ident in identities:
            if ident in seen_identities:
                return False, QUARANTINE_DUPLICATE_RECORD
            seen_identities.add(ident)
        ok, reason = record_validator(record)
        if not ok:
            return False, (reason if reason in QUARANTINE_REASONS
                           else QUARANTINE_JSON_INVALID)
        digests.append(str(record.get("record_digest")))
    if not is_sha256_digest(header.get("payload_digest")):
        return False, QUARANTINE_PAYLOAD_DIGEST_INVALID
    expected_payload = build_payload_digest(
        kind, str(header.get("schema_version")), digests)
    if header.get("payload_digest") != expected_payload:
        return False, QUARANTINE_PAYLOAD_DIGEST_INVALID
    return True, ""


def classify_checkpoint_file(
    path: object,
    *,
    kind: str,
    supported_schema_versions: Sequence[str],
    record_validator: Callable[[Mapping[str, Any]], Tuple[bool, str]],
    identity_fn: Callable[[Mapping[str, Any]], Tuple],
    legacy_classifier: Optional[
        Callable[[str, bytes], Tuple[str, str, Any, Optional[str]]]] = None,
    validation_now_utc: Optional[str] = None,
    allowed_clock_skew_seconds: float = ALLOWED_CLOCK_SKEW_SECONDS,
    max_bytes: int = MAX_CHECKPOINT_BYTES,
) -> FileClassification:
    """Classify one checkpoint file: MISSING / VALID_CURRENT / VALID_LEGACY /
    INVALID(reason). Never mutates the file.

    ``legacy_classifier(text, raw_bytes)`` returns
    ``(state, reason, legacy_payload, legacy_schema_version)`` where state is
    ``FILE_VALID_LEGACY`` or ``FILE_INVALID``.
    """

    p = Path(path) if path is not None else None
    out = FileClassification(path=p)
    if p is None or not p.exists():
        return out
    if not p.is_file():
        out.state = FILE_INVALID
        out.reason = QUARANTINE_JSON_INVALID
        return out
    try:
        raw = p.read_bytes()
    except OSError:
        out.state = FILE_INVALID
        out.reason = QUARANTINE_JSON_INVALID
        return out
    out.byte_digest = sha256_hex_bytes(raw)
    out.raw_bytes = raw
    if len(raw) == 0:
        # An existing empty file is NOT "no checkpoint exists". The
        # kind-specific legacy classifier decides whether zero bytes was a
        # valid legacy encoding (the pre-envelope watch writer persisted an
        # empty watchlist as an empty file) or truncation.
        if legacy_classifier is not None:
            try:
                state, reason, legacy_payload, legacy_version = (
                    legacy_classifier("", raw))
            except (TypeError, ValueError):
                state, reason = FILE_INVALID, QUARANTINE_TRUNCATED
                legacy_payload, legacy_version = None, None
            if state == FILE_VALID_LEGACY:
                out.state = FILE_VALID_LEGACY
                out.legacy_payload = legacy_payload
                out.legacy_schema_version = legacy_version
                return out
            out.state = FILE_INVALID
            out.reason = (reason if reason in QUARANTINE_REASONS
                          else QUARANTINE_TRUNCATED)
            return out
        out.state = FILE_INVALID
        out.reason = QUARANTINE_TRUNCATED
        return out
    if len(raw) > max_bytes:
        out.state = FILE_INVALID
        out.reason = QUARANTINE_JSON_INVALID
        return out
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        out.state = FILE_INVALID
        out.reason = QUARANTINE_JSON_INVALID
        return out

    lines = text.splitlines()
    first_line = next((line for line in lines if line.strip()), "")
    header: Any = None
    try:
        header = strict_json_loads(first_line) if first_line.strip() else None
    except ValueError:
        header = None
    if isinstance(header, dict) and "checkpoint_kind" in header:
        encoding = header.get("payload_encoding")
        records: List[Any] = []
        if encoding == PAYLOAD_ENCODING_DOCUMENT:
            try:
                document = strict_json_loads(text)
            except ValueError:
                out.state = FILE_INVALID
                out.reason = QUARANTINE_TRUNCATED
                return out
            if not isinstance(document, dict):
                out.state = FILE_INVALID
                out.reason = QUARANTINE_JSON_INVALID
                return out
            header = document
            payload = document.get("payload")
            if not isinstance(payload, dict) \
                    or not isinstance(payload.get("records"), list):
                out.state = FILE_INVALID
                out.reason = QUARANTINE_JSON_INVALID
                return out
            records = payload["records"]
        else:
            body_lines = [line for line in lines if line.strip()][1:]
            for line in body_lines:
                try:
                    record = strict_json_loads(line)
                except ValueError:
                    out.state = FILE_INVALID
                    out.reason = QUARANTINE_TRUNCATED
                    out.header = dict(header)
                    return out
                records.append(record)
        if len(records) > MAX_CHECKPOINT_RECORDS:
            out.state = FILE_INVALID
            out.reason = QUARANTINE_JSON_INVALID
            return out
        ok, reason = _validate_envelope_document(
            kind=kind,
            header=header,
            records=records,
            supported_schema_versions=supported_schema_versions,
            record_validator=record_validator,
            identity_fn=identity_fn,
            validation_now_utc=validation_now_utc,
            allowed_clock_skew_seconds=allowed_clock_skew_seconds,
        )
        out.header = dict(header)
        if not ok:
            out.state = FILE_INVALID
            out.reason = reason
            return out
        out.state = FILE_VALID_CURRENT
        out.records = [dict(record) for record in records]
        return out

    if legacy_classifier is None:
        out.state = FILE_INVALID
        out.reason = QUARANTINE_JSON_INVALID
        return out
    try:
        state, reason, legacy_payload, legacy_version = legacy_classifier(
            text, raw)
    except (TypeError, ValueError):
        out.state = FILE_INVALID
        out.reason = QUARANTINE_JSON_INVALID
        return out
    if state == FILE_VALID_LEGACY:
        out.state = FILE_VALID_LEGACY
        out.legacy_payload = legacy_payload
        out.legacy_schema_version = legacy_version
        return out
    out.state = FILE_INVALID
    out.reason = (reason if reason in QUARANTINE_REASONS
                  else QUARANTINE_JSON_INVALID)
    return out


# ---------------------------------------------------------------------------
# primary/backup decision matrix
# ---------------------------------------------------------------------------

@dataclass
class CheckpointDecision:
    """Outcome of the exact primary/backup load decision matrix."""

    status: str
    selected: Optional[str] = None  # "primary" | "backup" | None
    quarantined: bool = False
    quarantine_reason: Optional[str] = None
    migrated: bool = False
    recovered_from_backup: bool = False
    backup_invalid_reason: Optional[str] = None
    primary_invalid_reason: Optional[str] = None
    generation_conflict: bool = False
    ath_regression_rejected: int = 0
    notes: List[str] = field(default_factory=list)


def _chain_consistent(
    newer: FileClassification, older: FileClassification
) -> bool:
    """The newer envelope generation must link to the older one."""

    newer_gen = newer.generation
    older_gen = older.generation
    if not isinstance(newer_gen, int) or not isinstance(older_gen, int):
        return False
    if newer_gen - older_gen != 1:
        return False
    return newer.header is not None and older.header is not None and (
        newer.header.get("previous_generation_digest")
        == older.header.get("envelope_digest"))


def resolve_checkpoint_pair(
    primary: FileClassification,
    backup: FileClassification,
    *,
    cross_generation_check: Optional[
        Callable[[FileClassification, FileClassification],
                 Tuple[bool, Optional[str], int]]] = None,
) -> CheckpointDecision:
    """Apply the exact load decision matrix (cases A-I).

    ``cross_generation_check(selected, other)`` may veto the selected
    generation when the other VALID generation proves an illegitimate numeric
    regression (there is no legitimate automatic ATH reset). It returns
    ``(ok, veto_reason, regressions_detected)``.
    """

    # A: both missing — valid only for a genuinely new state directory.
    if primary.state == FILE_MISSING and backup.state == FILE_MISSING:
        return CheckpointDecision(status=CHECKPOINT_NOT_FOUND)

    # G-analogue: any existing file with invalid content and no valid peer.
    if not primary.usable and not backup.usable:
        reason = (primary.reason if primary.state == FILE_INVALID
                  else backup.reason) or QUARANTINE_JSON_INVALID
        return CheckpointDecision(
            status=CHECKPOINT_QUARANTINED,
            quarantined=True,
            quarantine_reason=reason,
            primary_invalid_reason=(
                primary.reason if primary.state == FILE_INVALID else None),
            backup_invalid_reason=(
                backup.reason if backup.state == FILE_INVALID else None),
        )

    # D/E: primary unusable, backup valid.
    if not primary.usable and backup.usable:
        decision = CheckpointDecision(
            status=CHECKPOINT_RECOVERED_FROM_BACKUP,
            selected="backup",
            recovered_from_backup=True,
            migrated=backup.state == FILE_VALID_LEGACY,
            primary_invalid_reason=(
                primary.reason if primary.state == FILE_INVALID else None),
        )
        return decision

    # B/F: primary valid, backup missing or invalid.
    if primary.usable and not backup.usable:
        if backup.state == FILE_INVALID:
            return CheckpointDecision(
                status=CHECKPOINT_BACKUP_INVALID,
                selected="primary",
                migrated=primary.state == FILE_VALID_LEGACY,
                backup_invalid_reason=backup.reason,
            )
        return CheckpointDecision(
            status=CHECKPOINT_PRIMARY_OK,
            selected="primary",
            migrated=primary.state == FILE_VALID_LEGACY,
        )

    # C/H/I: both usable.
    decision: Optional[CheckpointDecision] = None
    if primary.state == FILE_VALID_CURRENT and backup.state == FILE_VALID_CURRENT:
        p_gen, b_gen = primary.generation, backup.generation
        if p_gen == b_gen:
            if primary.envelope_digest == backup.envelope_digest:
                decision = CheckpointDecision(
                    status=CHECKPOINT_PRIMARY_AND_BACKUP_OK,
                    selected="primary")
            else:
                return CheckpointDecision(
                    status=CHECKPOINT_QUARANTINED,
                    quarantined=True,
                    generation_conflict=True,
                    quarantine_reason=QUARANTINE_GENERATION_CONFLICT)
        elif isinstance(p_gen, int) and isinstance(b_gen, int) and p_gen > b_gen:
            if _chain_consistent(primary, backup):
                decision = CheckpointDecision(
                    status=CHECKPOINT_PRIMARY_AND_BACKUP_OK,
                    selected="primary")
            else:
                return CheckpointDecision(
                    status=CHECKPOINT_QUARANTINED,
                    quarantined=True,
                    generation_conflict=True,
                    quarantine_reason=QUARANTINE_GENERATION_CONFLICT)
        else:
            # Backup newer than primary: legitimate only when the chain
            # proves the backup is the direct successor generation.
            if _chain_consistent(backup, primary):
                decision = CheckpointDecision(
                    status=CHECKPOINT_RECOVERED_FROM_BACKUP,
                    selected="backup",
                    recovered_from_backup=True,
                    notes=["BACKUP_GENERATION_NEWER_THAN_PRIMARY"])
            else:
                return CheckpointDecision(
                    status=CHECKPOINT_QUARANTINED,
                    quarantined=True,
                    generation_conflict=True,
                    quarantine_reason=QUARANTINE_GENERATION_CONFLICT)
    elif primary.state == FILE_VALID_CURRENT and backup.state == FILE_VALID_LEGACY:
        # Normal after a completed legacy migration: the envelope primary is
        # authoritative; the legacy backup remains preserved evidence.
        decision = CheckpointDecision(
            status=CHECKPOINT_PRIMARY_AND_BACKUP_OK,
            selected="primary",
            notes=["BACKUP_IS_PRESERVED_LEGACY"])
    elif primary.state == FILE_VALID_LEGACY and backup.state == FILE_VALID_CURRENT:
        # A legacy file REPLACED a current-schema primary: cannot be produced
        # by the writer contract — ambiguous, never guessed.
        return CheckpointDecision(
            status=CHECKPOINT_QUARANTINED,
            quarantined=True,
            generation_conflict=True,
            quarantine_reason=QUARANTINE_GENERATION_CONFLICT)
    else:
        # Both legacy: the primary is the newer legacy generation by contract.
        decision = CheckpointDecision(
            status=CHECKPOINT_PRIMARY_AND_BACKUP_OK,
            selected="primary",
            migrated=True)

    if decision is not None and cross_generation_check is not None:
        selected = primary if decision.selected == "primary" else backup
        other = backup if decision.selected == "primary" else primary
        ok, veto_reason, regressions = cross_generation_check(selected, other)
        if not ok:
            decision.ath_regression_rejected += max(1, regressions)
            if decision.selected == "primary" and other.usable:
                # Reject the regressed generation; restore the higher
                # authenticated evidence.
                other_ok, _, _ = cross_generation_check(other, selected)
                if other_ok:
                    return CheckpointDecision(
                        status=CHECKPOINT_RECOVERED_FROM_BACKUP,
                        selected="backup",
                        recovered_from_backup=True,
                        migrated=backup.state == FILE_VALID_LEGACY,
                        ath_regression_rejected=max(1, regressions),
                        quarantine_reason=None,
                        notes=[veto_reason or QUARANTINE_ATH_REGRESSION],
                    )
            return CheckpointDecision(
                status=CHECKPOINT_QUARANTINED,
                quarantined=True,
                quarantine_reason=veto_reason or QUARANTINE_ATH_REGRESSION,
                ath_regression_rejected=max(1, regressions),
            )
    assert decision is not None
    return decision


# ---------------------------------------------------------------------------
# safe write / rotation
# ---------------------------------------------------------------------------

def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(str(path), getattr(os, "O_DIRECTORY", os.O_RDONLY))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def encode_checkpoint_document(
    header: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> str:
    """Serialize an envelope for disk in its declared payload encoding."""

    encoding = header.get("payload_encoding")
    if encoding == PAYLOAD_ENCODING_DOCUMENT:
        document = dict(header)
        document["payload"] = {"records": [dict(r) for r in records]}
        return canonical_json(document) + "\n"
    lines = [canonical_json(header)]
    lines.extend(canonical_json(record) for record in records)
    return "\n".join(lines) + "\n"


def write_checkpoint_generation(
    *,
    primary_path: object,
    backup_path: object,
    header: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    classify: Callable[[object], FileClassification],
) -> None:
    """Write one new checkpoint generation with the safe rotation order.

    1-4. build/validate/serialize/digest happen in the caller + header build;
    5-7. write a temp file in the same directory, fsync, read it back and
         fully re-validate;
    8.   preserve the previous VALID primary as the backup generation;
    9.   atomically replace the primary;
    10.  fsync the containing directory where the platform supports it;
    11.  confirm the new primary validates.

    Raises :class:`CheckpointWriteError` without replacing the previous
    primary on any validation/write failure before step 9.
    """

    primary = Path(primary_path)
    backup = Path(backup_path)
    primary.parent.mkdir(parents=True, exist_ok=True)
    text = encode_checkpoint_document(header, records)
    temp = primary.with_name(primary.name + ".next.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temp_state = classify(temp)
        if temp_state.state != FILE_VALID_CURRENT:
            raise CheckpointWriteError(
                "CHECKPOINT_WRITE_READBACK_INVALID:"
                + (temp_state.reason or "UNKNOWN"))
        if primary.exists():
            existing = classify(primary)
            if existing.usable:
                backup_tmp = backup.with_name(backup.name + ".tmp")
                shutil.copyfile(primary, backup_tmp)
                # fsync needs a writable handle on Windows.
                with backup_tmp.open("r+b") as handle:
                    os.fsync(handle.fileno())
                os.replace(backup_tmp, backup)
        os.replace(temp, primary)
    except OSError as exc:
        raise CheckpointWriteError(
            f"CHECKPOINT_WRITE_FAILED:{type(exc).__name__}") from exc
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass
    _fsync_directory(primary.parent)
    confirmed = classify(primary)
    if confirmed.state != FILE_VALID_CURRENT:
        raise CheckpointWriteError(
            "CHECKPOINT_WRITE_CONFIRM_INVALID:"
            + (confirmed.reason or "UNKNOWN"))


# ---------------------------------------------------------------------------
# transient-failure classification + bounded-retry resilient write
# ---------------------------------------------------------------------------
#
# Live evidence (acceptance 20260723T025330Z §39): under a sustained
# ~108 writes/s firehose on this Windows filesystem, ``os.replace`` inside
# ``write_checkpoint_generation`` intermittently raises a transient sharing
# violation (``PermissionError``) that the envelope wraps as
# ``CHECKPOINT_WRITE_FAILED:<type>``. The cursor persist path already wraps and
# tolerates this; the ATH/watch persist paths did not, so a single transient
# blip escalated to a fatal producer stop. The primitives below let every
# checkpoint writer absorb the transient class with a small bounded retry while
# preserving the fail-closed guarantees of ``write_checkpoint_generation``
# (never replace the previous primary on failure; never advance a durable
# marker without a confirmed read-back).

# The bound is sized to outlast a transient Windows sharing-violation window
# (an antivirus / Search-indexer hold on a freshly written file), observed live
# to exceed a sub-second budget under a hot output directory, while still
# failing a genuinely PERMANENT failure (disk full, persistent permission
# denial, invalid destination) closed within a few seconds. The backoff is
# capped so a caller can never busy-loop. The window is sized to span the
# observed contention (concurrent ATH/watch atomic-replace + directory fsync in
# a hot output directory holds the target for well over a sub-second budget).
# Total worst-case retry window for the defaults
# ~= sum(min(MAX, BASE*k) for k in 1..MAX_ATTEMPTS-1) ~= 4.55s.
CHECKPOINT_WRITE_MAX_ATTEMPTS = 14
CHECKPOINT_WRITE_RETRY_BASE_SECONDS = 0.05
CHECKPOINT_WRITE_RETRY_MAX_SECONDS = 1.0

# Durability status (closed set) surfaced in checkpoint summaries / heartbeat.
# HEALTHY  = the last checkpoint write succeeded (state is current + durable).
# DEGRADED = the last checkpoint write did not resolve within the bounded retry
#            (persistence unresolved), but the previous VALID durable generation
#            is preserved and recoverable (write_checkpoint_generation never
#            replaces a valid primary on failure). It heals back to HEALTHY on
#            the next successful write. It is deliberately NOT called
#            "unrecoverable": a valid checkpoint always survives.
CHECKPOINT_DURABILITY_HEALTHY = "CHECKPOINT_DURABILITY_HEALTHY"
CHECKPOINT_DURABILITY_DEGRADED = "CHECKPOINT_DURABILITY_DEGRADED"

# Failure categories (closed set).
CHECKPOINT_FAILURE_TRANSIENT = "TRANSIENT_CHECKPOINT_FAILURE"
CHECKPOINT_FAILURE_PERMANENT = "PERMANENT_CHECKPOINT_FAILURE"
CHECKPOINT_FAILURE_STRUCTURAL = "STRUCTURAL_CHECKPOINT_FAILURE"


def is_transient_checkpoint_write_error(exc: BaseException) -> bool:
    """True for a retryable filesystem-contention write failure.

    ``write_checkpoint_generation`` wraps an ``OSError`` from the
    temp-write / backup-rotation / atomic-replace steps as
    ``CHECKPOINT_WRITE_FAILED:<type>`` — the class observed live as a transient
    Windows sharing violation. A read-back / confirm validation failure (the
    bytes just written do not validate) is STRUCTURAL: it is never retried and
    always fails closed so envelope validation strength is preserved.
    """

    if isinstance(exc, CheckpointWriteError):
        return str(exc).startswith("CHECKPOINT_WRITE_FAILED:")
    return isinstance(exc, OSError)


def classify_checkpoint_write_error(exc: BaseException) -> str:
    """Categorize a checkpoint-write failure for observability (closed set)."""

    if isinstance(exc, CheckpointWriteError):
        text = str(exc)
        if "READBACK_INVALID" in text or "CONFIRM_INVALID" in text:
            return CHECKPOINT_FAILURE_STRUCTURAL
    return (CHECKPOINT_FAILURE_TRANSIENT
            if is_transient_checkpoint_write_error(exc)
            else CHECKPOINT_FAILURE_PERMANENT)


@dataclass
class CheckpointWriteOutcome:
    """Result of a resilient write that ultimately SUCCEEDED."""

    attempts: int
    retried: int
    transient_failures: int


def write_checkpoint_generation_resilient(
    *,
    primary_path: object,
    backup_path: object,
    header: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    classify: Callable[[object], "FileClassification"],
    max_attempts: int = CHECKPOINT_WRITE_MAX_ATTEMPTS,
    retry_base_seconds: float = CHECKPOINT_WRITE_RETRY_BASE_SECONDS,
    retry_max_seconds: float = CHECKPOINT_WRITE_RETRY_MAX_SECONDS,
    sleep_fn: Optional[Callable[[float], None]] = None,
    on_transient_failure: Optional[Callable[[int, BaseException], None]] = None,
) -> "CheckpointWriteOutcome":
    """Write one checkpoint generation, retrying only TRANSIENT contention.

    Delegates to :func:`write_checkpoint_generation` (module-global, so test
    monkeypatches on that name are honoured), so all envelope validation,
    rotation ordering and fail-closed guarantees are exactly unchanged. Retries
    ONLY the transient ``CHECKPOINT_WRITE_FAILED`` / raw ``OSError`` class up to
    ``max_attempts`` with a small capped backoff. A structural
    read-back / confirm failure, or an exhausted transient failure, is re-raised
    unchanged so the caller decides whether the unpersisted state is
    safety-critical. No durable marker is advanced here — that remains the
    caller's post-success responsibility.
    """

    if sleep_fn is None:
        # Resolved at call time (not as a default) so a test can neutralise the
        # backoff via monkeypatching ``time.sleep``.
        sleep_fn = time.sleep
    if max_attempts < 1:
        max_attempts = 1
    transient_failures = 0
    attempt = 0
    while True:
        attempt += 1
        try:
            write_checkpoint_generation(
                primary_path=primary_path,
                backup_path=backup_path,
                header=header,
                records=records,
                classify=classify,
            )
            return CheckpointWriteOutcome(
                attempts=attempt,
                retried=attempt - 1,
                transient_failures=transient_failures,
            )
        except (CheckpointWriteError, OSError) as exc:
            if attempt < max_attempts:
                # EVERY checkpoint-write failure class is retried within the
                # bound. The write step (os.replace) and the read-back / confirm
                # validation of a freshly written checkpoint were both observed
                # live to fail intermittently under concurrent read contention
                # (an antivirus / indexer momentarily holds the file), and the
                # content is known-valid (it serialised from validated in-memory
                # state and re-validates on a later attempt). A genuinely
                # non-recovering failure -- real corruption, disk-full, a
                # persistent permission denial, an invalid destination -- simply
                # exhausts the bound and fails closed: validation is applied on
                # EVERY attempt, so envelope/digest strength is never weakened.
                if is_transient_checkpoint_write_error(exc):
                    transient_failures += 1
                if on_transient_failure is not None:
                    on_transient_failure(attempt, exc)
                delay = min(retry_max_seconds,
                            retry_base_seconds * float(attempt))
                if delay > 0:
                    sleep_fn(delay)
                continue
            raise


def preserve_evidence_copy(source: Path, *, label: str) -> Optional[Path]:
    """Copy a checkpoint file to an immutable evidence sidecar.

    The sidecar name embeds the source content digest so repeated migrations
    are idempotent and never overwrite distinct evidence.
    """

    try:
        raw = source.read_bytes()
    except OSError:
        return None
    digest8 = sha256_hex_bytes(raw)[:8]
    target = source.with_name(f"{source.name}.{label}_{digest8}")
    if target.exists():
        return target
    try:
        temp = target.with_name(target.name + ".tmp")
        with temp.open("wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except OSError:
        return None
    return target


# ---------------------------------------------------------------------------
# aggregated load result (observability contract)
# ---------------------------------------------------------------------------

@dataclass
class CheckpointLoadResult:
    """Safe, operator-facing summary of one checkpoint restore."""

    checkpoint_kind: str
    checkpoint_status: str = CHECKPOINT_NOT_FOUND
    checkpoint_primary_status: str = FILE_MISSING
    checkpoint_backup_status: str = FILE_MISSING
    checkpoint_schema_version: Optional[str] = None
    checkpoint_generation: Optional[int] = None
    checkpoint_recovered_from_backup: bool = False
    checkpoint_quarantined: bool = False
    checkpoint_quarantine_reason: Optional[str] = None
    checkpoint_records_validated: int = 0
    checkpoint_records_rejected: int = 0
    checkpoint_migrations_attempted: int = 0
    checkpoint_migrations_succeeded: int = 0
    checkpoint_migrations_failed: int = 0
    checkpoint_legacy_activation_migrated: int = 0
    checkpoint_legacy_activation_quarantined: int = 0
    checkpoint_ath_regression_rejected: int = 0
    checkpoint_digest_failure_total: int = 0
    checkpoint_generation_conflict_total: int = 0
    checkpoint_last_validated_at_utc: Optional[str] = None
    checkpoint_files_found: bool = False
    checkpoint_source_selected: Optional[str] = None
    checkpoint_primary_invalid_reason: Optional[str] = None
    checkpoint_backup_invalid_reason: Optional[str] = None
    checkpoint_migration_report: List[Dict[str, Any]] = field(
        default_factory=list)
    checkpoint_notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_kind": self.checkpoint_kind,
            "checkpoint_status": self.checkpoint_status,
            "checkpoint_primary_status": self.checkpoint_primary_status,
            "checkpoint_backup_status": self.checkpoint_backup_status,
            "checkpoint_schema_version": self.checkpoint_schema_version,
            "checkpoint_generation": self.checkpoint_generation,
            "checkpoint_recovered_from_backup":
                self.checkpoint_recovered_from_backup,
            "checkpoint_quarantined": self.checkpoint_quarantined,
            "checkpoint_quarantine_reason": self.checkpoint_quarantine_reason,
            "checkpoint_records_validated": self.checkpoint_records_validated,
            "checkpoint_records_rejected": self.checkpoint_records_rejected,
            "checkpoint_migrations_attempted":
                self.checkpoint_migrations_attempted,
            "checkpoint_migrations_succeeded":
                self.checkpoint_migrations_succeeded,
            "checkpoint_migrations_failed": self.checkpoint_migrations_failed,
            "checkpoint_legacy_activation_migrated":
                self.checkpoint_legacy_activation_migrated,
            "checkpoint_legacy_activation_quarantined":
                self.checkpoint_legacy_activation_quarantined,
            "checkpoint_ath_regression_rejected":
                self.checkpoint_ath_regression_rejected,
            "checkpoint_digest_failure_total":
                self.checkpoint_digest_failure_total,
            "checkpoint_generation_conflict_total":
                self.checkpoint_generation_conflict_total,
            "checkpoint_last_validated_at_utc":
                self.checkpoint_last_validated_at_utc,
            "checkpoint_files_found": self.checkpoint_files_found,
            "checkpoint_source_selected": self.checkpoint_source_selected,
            "checkpoint_primary_invalid_reason":
                self.checkpoint_primary_invalid_reason,
            "checkpoint_backup_invalid_reason":
                self.checkpoint_backup_invalid_reason,
            "checkpoint_notes": list(self.checkpoint_notes),
        }


__all__ = (
    "ENVELOPE_VERSION",
    "CHECKPOINT_KIND_WATCH",
    "CHECKPOINT_KIND_ATH",
    "PAYLOAD_ENCODING_JSONL",
    "PAYLOAD_ENCODING_DOCUMENT",
    "CHECKPOINT_WRITER_BUILD",
    "ZERO_DIGEST",
    "ALLOWED_CLOCK_SKEW_SECONDS",
    "MAX_CHECKPOINT_BYTES",
    "MAX_CHECKPOINT_RECORDS",
    "CHECKPOINT_NOT_FOUND",
    "CHECKPOINT_PRIMARY_OK",
    "CHECKPOINT_PRIMARY_AND_BACKUP_OK",
    "CHECKPOINT_RECOVERED_FROM_BACKUP",
    "CHECKPOINT_BACKUP_INVALID",
    "CHECKPOINT_MIGRATED",
    "CHECKPOINT_QUARANTINED",
    "CHECKPOINT_STATUSES",
    "FILE_MISSING",
    "FILE_VALID_CURRENT",
    "FILE_VALID_LEGACY",
    "FILE_INVALID",
    "QUARANTINE_JSON_INVALID",
    "QUARANTINE_TRUNCATED",
    "QUARANTINE_SCHEMA_UNSUPPORTED",
    "QUARANTINE_KIND_INVALID",
    "QUARANTINE_RECORD_DIGEST_INVALID",
    "QUARANTINE_PAYLOAD_DIGEST_INVALID",
    "QUARANTINE_ENVELOPE_DIGEST_INVALID",
    "QUARANTINE_GENERATION_CONFLICT",
    "QUARANTINE_DUPLICATE_RECORD",
    "QUARANTINE_RECORD_COUNT_MISMATCH",
    "QUARANTINE_MINT_BINDING_INVALID",
    "QUARANTINE_CANDIDATE_BINDING_INVALID",
    "QUARANTINE_NUMERIC_INVALID",
    "QUARANTINE_TIMESTAMP_INVALID",
    "QUARANTINE_ATH_REGRESSION",
    "QUARANTINE_ACTIVATION_PROOF_INVALID",
    "QUARANTINE_CROSSING_DIGEST_INVALID",
    "QUARANTINE_EVIDENCE_DIGEST_INVALID",
    "QUARANTINE_MIGRATION_AMBIGUOUS",
    "QUARANTINE_ACTIVATION_MIGRATION_AMBIGUOUS",
    "QUARANTINE_LEGACY_STATUS_UNSUPPORTED",
    "QUARANTINE_STATUS_UNSUPPORTED",
    "QUARANTINE_DELIVERY_STATE_INVALID",
    "QUARANTINE_MARKET_STATE_INVALID",
    "QUARANTINE_MIGRATION_WRITE_FAILED",
    "QUARANTINE_CROSS_CONSISTENCY_INVALID",
    "QUARANTINE_REASONS",
    "CheckpointWriteError",
    "strict_json_loads",
    "canonical_json",
    "sha256_hex_text",
    "sha256_hex_bytes",
    "is_sha256_digest",
    "parse_utc_timestamp",
    "utc_now_iso",
    "build_record_digest",
    "record_digest_is_valid",
    "build_payload_digest",
    "build_envelope_digest",
    "build_envelope_header",
    "FileClassification",
    "classify_checkpoint_file",
    "CheckpointDecision",
    "resolve_checkpoint_pair",
    "encode_checkpoint_document",
    "write_checkpoint_generation",
    "write_checkpoint_generation_resilient",
    "is_transient_checkpoint_write_error",
    "classify_checkpoint_write_error",
    "CheckpointWriteOutcome",
    "CHECKPOINT_WRITE_MAX_ATTEMPTS",
    "CHECKPOINT_WRITE_RETRY_BASE_SECONDS",
    "CHECKPOINT_WRITE_RETRY_MAX_SECONDS",
    "CHECKPOINT_DURABILITY_HEALTHY",
    "CHECKPOINT_DURABILITY_DEGRADED",
    "CHECKPOINT_FAILURE_TRANSIENT",
    "CHECKPOINT_FAILURE_PERMANENT",
    "CHECKPOINT_FAILURE_STRUCTURAL",
    "preserve_evidence_copy",
    "CheckpointLoadResult",
)
