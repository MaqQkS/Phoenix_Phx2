"""Watchdog observability state: atomic, authenticated, redaction-safe.

Three rules govern every byte this module writes.

1. ATOMIC.  A status file is written to a temporary sibling and then
   ``os.replace``-d, so a reader (operator, dashboard, another watchdog command)
   can never observe a half-written document.

2. AUTHENTICATED PRIMARY/BACKUP where the value must survive a restart.  The
   circuit state is the one piece of watchdog state whose loss would silently
   re-arm automatic restarts after an integrity failure, so it is written with a
   payload digest to both a primary and a backup file and is only accepted back
   if the digest verifies.

3. REDACTION-SAFE BY CONSTRUCTION.  Nothing here may carry a bot token, a chat
   id, a Bot API URL, a webhook, a provider endpoint, an API key, an environment
   value, a raw transaction signature, an outbound message body or a raw
   response body.  Absolute filesystem paths are also excluded: artifacts carry
   path CLASSIFICATIONS and digests instead, so a report can be shared without
   leaking an operator's directory layout.  ``scan_payload`` enforces this and
   ``write_json_atomic`` refuses to write a payload that fails it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

WATCHDOG_STATE_SCHEMA_V1 = "PHX2_WATCHDOG_STATE_V1"

# --------------------------------------------------------------------------- #
# redaction
# --------------------------------------------------------------------------- #

#: Key names that must never appear in a watchdog artifact, at any depth.
BANNED_KEY_FRAGMENTS = (
    "token", "secret", "password", "webhook", "chat_id", "chatid",
    "api_key", "apikey", "endpoint", "url", "signature", "body", "payload_text",
    "authorization", "bearer", "credential", "env_value",
)

#: Value patterns that prove an artifact leaked something it must not carry.
_TELEGRAM_BOT_TOKEN = re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b")
_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://")
_DISCORD_WEBHOOK = re.compile(r"(?i)discord(?:app)?\.com/api/webhooks")
_TELEGRAM_API = re.compile(r"(?i)api\.telegram\.org")
_BASE58_SIGNATURE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{80,}\b")
_TELEGRAM_HANDLE = re.compile(r"(?<![\w])@[A-Za-z][A-Za-z0-9_]{4,}")
_WINDOWS_PATH = re.compile(r"(?i)\b[a-z]:[\\/]")
_UNC_PATH = re.compile(r"\\\\[^\\]+\\")

_VALUE_RULES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("TELEGRAM_BOT_TOKEN", _TELEGRAM_BOT_TOKEN),
    ("TELEGRAM_API_URL", _TELEGRAM_API),
    ("DISCORD_WEBHOOK_URL", _DISCORD_WEBHOOK),
    ("ANY_URL", _URL),
    ("RAW_BASE58_SIGNATURE", _BASE58_SIGNATURE),
    ("TELEGRAM_HANDLE", _TELEGRAM_HANDLE),
    ("ABSOLUTE_WINDOWS_PATH", _WINDOWS_PATH),
    ("UNC_PATH", _UNC_PATH),
)

#: A deliberately unsafe probe string.  ``scan_payload`` must flag it; if it ever
#: stops doing so the scanner has been broken and the positive control fails.
REDACTION_POSITIVE_CONTROL = (
    "123456789:AAEEbbCCddEEffGGhhIIjjKKllMMnnOOppQQrr")


class RedactionViolation(ValueError):
    """A payload carried something a watchdog artifact may never contain."""

    def __init__(self, hits: List[str]) -> None:
        super().__init__("WATCHDOG_REDACTION_VIOLATION")
        self.hits = list(hits)


def scan_payload(payload: Any) -> List[str]:
    """Every redaction rule this payload violates, as closed-set labels.

    Labels name the RULE, never the offending value, so the scan result itself is
    safe to log.
    """

    hits: List[str] = []

    def _walk(node: Any, key_path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                key_text = str(key).lower()
                if any(fragment in key_text
                       for fragment in BANNED_KEY_FRAGMENTS):
                    # A boolean/int flag named e.g. ``telegram_token_configured``
                    # carries no secret; only a STRING value under a banned key
                    # is a leak.
                    if isinstance(value, str) and value.strip():
                        hits.append(f"BANNED_KEY:{key_text}")
                _walk(value, f"{key_path}.{key_text}" if key_path else key_text)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                _walk(item, key_path)
            return
        if isinstance(node, str):
            for label, pattern in _VALUE_RULES:
                if pattern.search(node):
                    hits.append(f"VALUE:{label}")
        return

    _walk(payload, "")
    seen: set = set()
    ordered: List[str] = []
    for hit in hits:
        if hit not in seen:
            seen.add(hit)
            ordered.append(hit)
    return ordered


def positive_control_ok() -> bool:
    """The scanner must flag a known-unsafe probe."""

    return bool(scan_payload({"probe": REDACTION_POSITIVE_CONTROL}))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def path_digest(path: object) -> str:
    """A stable, non-reversible identifier for a path.

    Lets two artifacts be compared for "same location" without either of them
    carrying the location.
    """

    try:
        normalized = os.path.normcase(
            os.path.normpath(os.path.abspath(str(path))))
    except (TypeError, ValueError):
        normalized = str(path)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def file_sha256(path: object) -> Optional[str]:
    try:
        data = Path(str(path)).read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def ledger_identity(path: object) -> Dict[str, Any]:
    """``sha256`` / ``bytes`` / ``lines`` for the canonical ledger, READ-ONLY.

    Opened in binary read mode only.  The watchdog never has a writable handle
    on this file; the producer is its sole writer.
    """

    result: Dict[str, Any] = {
        "sha256": None, "bytes": None, "lines": None,
        "parse_ok": False, "truncated_final_line": False,
    }
    try:
        data = Path(str(path)).read_bytes()
    except OSError:
        return result
    result["sha256"] = hashlib.sha256(data).hexdigest()
    result["bytes"] = len(data)
    if not data:
        result["lines"] = 0
        result["parse_ok"] = True
        return result
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    result["lines"] = len(lines)
    result["truncated_final_line"] = not text.endswith(("\n", "\r"))
    parse_ok = True
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            json.loads(stripped)
        except ValueError:
            parse_ok = False
            break
    result["parse_ok"] = parse_ok
    return result


def read_json(path: object) -> Tuple[bool, Any]:
    """``(parse_ok, document)``.  A missing file is ``(False, None)``.

    Decoded with ``utf-8-sig``, which reads plain UTF-8 unchanged but also
    tolerates a leading BOM.  This matters: Windows PowerShell 5.1's
    ``Out-File -Encoding utf8`` writes UTF-8 **with** a BOM, so the launcher's
    startup manifest begins ``EF BB BF`` and strict ``utf-8`` decoding leaves a
    ``\\ufeff`` that makes ``json.loads`` raise
    "Unexpected UTF-8 BOM (decode using utf-8-sig)".  That silently cost the
    watchdog the manifest -- and with it the producer's run directory, so the
    heartbeat could never be located.
    """

    try:
        text = Path(str(path)).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return False, None
    try:
        return True, json.loads(text)
    except ValueError:
        return False, None


# --------------------------------------------------------------------------- #
# atomic / authenticated writes
# --------------------------------------------------------------------------- #

def write_json_atomic(path: object, payload: Any, *,
                      allow_unsafe: bool = False) -> None:
    """Write ``payload`` atomically, refusing anything redaction-unsafe."""

    if not allow_unsafe:
        hits = scan_payload(payload)
        if hits:
            raise RedactionViolation(hits)
    target = Path(str(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(tmp), str(target))


def append_jsonl(path: object, record: Mapping[str, Any]) -> None:
    """Append one redaction-safe JSONL record."""

    hits = scan_payload(record)
    if hits:
        raise RedactionViolation(hits)
    target = Path(str(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, default=str)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _envelope(payload: Mapping[str, Any], *, kind: str,
              generation: int) -> Dict[str, Any]:
    body = json.dumps(payload, sort_keys=True, default=str)
    return {
        "envelope_version": WATCHDOG_STATE_SCHEMA_V1,
        "checkpoint_kind": str(kind),
        "generation": int(generation),
        "updated_at_utc": utc_now_iso(),
        "payload_digest": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "payload": json.loads(body),
    }


def write_authenticated(path: object, payload: Mapping[str, Any], *,
                        kind: str, generation: int) -> None:
    """Write primary AND backup with a verifying payload digest.

    The backup is written FIRST so a crash between the two writes always leaves
    at least one verifiable document, and the older of the two is never newer
    than the payload it claims to describe.
    """

    document = _envelope(payload, kind=kind, generation=generation)
    target = Path(str(path))
    write_json_atomic(target.with_name(target.name + ".bak"), document)
    write_json_atomic(target, document)


def read_authenticated(path: object, *, kind: str
                       ) -> Tuple[str, Optional[Dict[str, Any]], int]:
    """``(state, payload, generation)`` for an authenticated document.

    ``state`` is one of ``MISSING`` / ``VALID_PRIMARY`` / ``VALID_BACKUP`` /
    ``INVALID``.  A digest that does not verify is INVALID, never "close
    enough": the circuit breaker depends on this value being trustworthy.
    """

    target = Path(str(path))
    candidates = (("VALID_PRIMARY", target),
                  ("VALID_BACKUP", target.with_name(target.name + ".bak")))
    saw_file = False
    for label, candidate in candidates:
        parse_ok, document = read_json(candidate)
        if not parse_ok or not isinstance(document, dict):
            if candidate.exists():
                saw_file = True
            continue
        saw_file = True
        if document.get("envelope_version") != WATCHDOG_STATE_SCHEMA_V1:
            continue
        if str(document.get("checkpoint_kind")) != str(kind):
            continue
        payload = document.get("payload")
        if not isinstance(payload, dict):
            continue
        body = json.dumps(payload, sort_keys=True, default=str)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if digest != document.get("payload_digest"):
            continue
        try:
            generation = int(document.get("generation") or 0)
        except (TypeError, ValueError):
            generation = 0
        return label, dict(payload), generation
    return ("INVALID" if saw_file else "MISSING"), None, 0


# --------------------------------------------------------------------------- #
# circuit state
# --------------------------------------------------------------------------- #

CIRCUIT_KIND = "PHX2_WATCHDOG_CIRCUIT_STATE"

CIRCUIT_CLOSED = "CLOSED"
CIRCUIT_OPEN_STATUS = "OPEN"


@dataclass
class CircuitState:
    """Persisted restart budget and breaker position.

    ``integrity_locked`` is the difference between "this producer keeps
    crashing" and "the durable state is wrong".  Only the former may ever be
    cleared by the passage of time; the latter needs an explicit operator
    command, which is why it is a separate persisted flag rather than a reason
    string the loader could misread.
    """

    status: str = CIRCUIT_CLOSED
    opened_at_utc: Optional[str] = None
    open_reason: Optional[str] = None
    integrity_locked: bool = False
    restart_count_total: int = 0
    attempts_utc: List[str] = field(default_factory=list)
    last_restart_utc: Optional[str] = None
    last_failure_reason: Optional[str] = None
    generation: int = 0
    document_state: str = "MISSING"

    @property
    def is_open(self) -> bool:
        return self.status == CIRCUIT_OPEN_STATUS

    def to_payload(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "opened_at_utc": self.opened_at_utc,
            "open_reason": self.open_reason,
            "integrity_locked": bool(self.integrity_locked),
            "restart_count_total": int(self.restart_count_total),
            "attempts_utc": list(self.attempts_utc),
            "last_restart_utc": self.last_restart_utc,
            "last_failure_reason": self.last_failure_reason,
        }


def load_circuit_state(path: object) -> CircuitState:
    """Load the breaker, failing CLOSED-BUT-OPEN on an unreadable document.

    An INVALID document is treated as OPEN with an integrity lock: the watchdog
    cannot prove it is safe to restart, so it does not.
    """

    state_label, payload, generation = read_authenticated(path, kind=CIRCUIT_KIND)
    if state_label == "MISSING":
        return CircuitState(document_state=state_label)
    if state_label == "INVALID" or payload is None:
        return CircuitState(
            status=CIRCUIT_OPEN_STATUS,
            opened_at_utc=utc_now_iso(),
            open_reason="CIRCUIT_STATE_DOCUMENT_INVALID",
            integrity_locked=True,
            document_state="INVALID",
        )
    attempts = payload.get("attempts_utc")
    return CircuitState(
        status=str(payload.get("status") or CIRCUIT_CLOSED),
        opened_at_utc=payload.get("opened_at_utc"),
        open_reason=payload.get("open_reason"),
        integrity_locked=bool(payload.get("integrity_locked")),
        restart_count_total=int(payload.get("restart_count_total") or 0),
        attempts_utc=[str(item) for item in attempts] if isinstance(
            attempts, list) else [],
        last_restart_utc=payload.get("last_restart_utc"),
        last_failure_reason=payload.get("last_failure_reason"),
        generation=generation,
        document_state=state_label,
    )


def save_circuit_state(path: object, state: CircuitState) -> None:
    state.generation = int(state.generation) + 1
    write_authenticated(path, state.to_payload(), kind=CIRCUIT_KIND,
                        generation=state.generation)


def attempts_in_window(state: CircuitState, *, now_utc: str,
                       window_seconds: float) -> int:
    """Restart attempts inside the rolling window ending at ``now_utc``."""

    now = parse_utc(now_utc)
    if now is None:
        return len(state.attempts_utc)
    count = 0
    for stamp in state.attempts_utc:
        moment = parse_utc(stamp)
        if moment is None:
            continue
        if (now - moment).total_seconds() <= float(window_seconds):
            count += 1
    return count


def prune_attempts(state: CircuitState, *, now_utc: str,
                   window_seconds: float) -> None:
    now = parse_utc(now_utc)
    if now is None:
        return
    kept: List[str] = []
    for stamp in state.attempts_utc:
        moment = parse_utc(stamp)
        if moment is None:
            continue
        if (now - moment).total_seconds() <= float(window_seconds):
            kept.append(stamp)
    state.attempts_utc = kept


__all__ = (
    "WATCHDOG_STATE_SCHEMA_V1",
    "BANNED_KEY_FRAGMENTS",
    "REDACTION_POSITIVE_CONTROL",
    "RedactionViolation",
    "scan_payload",
    "positive_control_ok",
    "utc_now_iso",
    "parse_utc",
    "path_digest",
    "file_sha256",
    "ledger_identity",
    "read_json",
    "write_json_atomic",
    "append_jsonl",
    "write_authenticated",
    "read_authenticated",
    "CIRCUIT_KIND",
    "CIRCUIT_CLOSED",
    "CIRCUIT_OPEN_STATUS",
    "CircuitState",
    "load_circuit_state",
    "save_circuit_state",
    "attempts_in_window",
    "prune_attempts",
)
