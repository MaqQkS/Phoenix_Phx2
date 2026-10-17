"""Process identity, locks, and the adoption proof.

Two Windows facts shape everything here.

* The repository venv ``python.exe`` is a **re-exec launcher stub**: every
  logical producer therefore appears in the process table as a shim -> real PAIR
  with an identical command line.  Counting matching images would report two
  producers where there is one, so :func:`logical_producer_pids` counts only
  matching processes whose PARENT is not itself a matching process.  This was
  measured during the Step-6 ceremony and is the reason a naive count is wrong.

* Command lines carry the arm-gate confirm token.  A command line is therefore
  used for MATCHING in memory only and is never returned in a payload, never
  logged and never written to an artifact.  ``state.scan_payload`` is the
  backstop: a command line also contains absolute paths, which it rejects.

The watchdog owns the WATCHDOG lock and nothing else.  The producer's state-dir
runtime lock is read here, and removed only in the one narrow case Phase 4
allows: a proven-dead owner, no matching producer process anywhere, and no
Yellowstone owner.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PHX2.free_tier_producer.phx1_parity_policy import normalize_alert_policy
from PHX2.watchdog.state import parse_utc, path_digest, utc_now_iso

#: The tracked module every canonical producer runs.
PRODUCER_MODULE = "PHX2.free_tier_producer.free_tier_session"

#: Image names a canonical producer / launcher wrapper may present as.
PRODUCER_IMAGE_NAMES = ("python.exe",)
LAUNCHER_IMAGE_NAMES = ("powershell.exe", "pwsh.exe")

WATCHDOG_LOCK_SCHEMA_V1 = "PHX2_WATCHDOG_LOCK_V1"

# --------------------------------------------------------------------------- #
# closed-set adoption refusals
# --------------------------------------------------------------------------- #

ADOPT_OK = "ADOPTED"
ADOPT_NO_LOCK = "NO_PRODUCER_RUNTIME_LOCK"
ADOPT_LOCK_MALFORMED = "PRODUCER_RUNTIME_LOCK_MALFORMED"
ADOPT_OWNER_DEAD = "PRODUCER_RUNTIME_LOCK_OWNER_DEAD"
ADOPT_PID_NOT_IN_TABLE = "PRODUCER_PID_NOT_IN_PROCESS_TABLE"
ADOPT_START_TIME_MISMATCH = "PRODUCER_START_TIME_MISMATCH"
ADOPT_IMAGE_MISMATCH = "PRODUCER_IMAGE_MISMATCH"
ADOPT_EXECUTABLE_MISMATCH = "PRODUCER_EXECUTABLE_NOT_REPO_VENV"
ADOPT_MODULE_MISMATCH = "PRODUCER_MODULE_MISMATCH"
ADOPT_HEAD_MISMATCH = "PRODUCER_EXPECTED_HEAD_MISMATCH"
ADOPT_STATE_PATH_MISMATCH = "PRODUCER_CURSOR_STATE_DIR_MISMATCH"
ADOPT_LEDGER_PATH_MISMATCH = "PRODUCER_LEDGER_PATH_MISMATCH"
ADOPT_TELEGRAM_MISMATCH = "PRODUCER_TELEGRAM_ONLY_MISMATCH"
ADOPT_DISCORD_PRESENT = "PRODUCER_DISCORD_ARM_PRESENT"
ADOPT_SHADOW_MISSING = "PRODUCER_STRUCTURAL_SHADOW_MISSING"
ADOPT_ALERT_POLICY_MISMATCH = "PRODUCER_ALERT_POLICY_MISMATCH"
ADOPT_DUPLICATE = "MULTIPLE_LOGICAL_PRODUCERS"
ADOPT_OWNER_COUNT = "YELLOWSTONE_OWNER_COUNT_NOT_ONE"
ADOPT_AMBIGUOUS = "AMBIGUOUS_PRODUCER_OWNERSHIP"

ADOPTION_REFUSAL_REASONS = (
    ADOPT_NO_LOCK, ADOPT_LOCK_MALFORMED, ADOPT_OWNER_DEAD,
    ADOPT_PID_NOT_IN_TABLE, ADOPT_START_TIME_MISMATCH, ADOPT_IMAGE_MISMATCH,
    ADOPT_EXECUTABLE_MISMATCH, ADOPT_MODULE_MISMATCH, ADOPT_HEAD_MISMATCH,
    ADOPT_STATE_PATH_MISMATCH, ADOPT_LEDGER_PATH_MISMATCH,
    ADOPT_TELEGRAM_MISMATCH, ADOPT_DISCORD_PRESENT, ADOPT_SHADOW_MISSING,
    ADOPT_ALERT_POLICY_MISMATCH,
    ADOPT_DUPLICATE, ADOPT_OWNER_COUNT, ADOPT_AMBIGUOUS,
)


@dataclass(frozen=True)
class ProcessRecord:
    """One process, as the watchdog needs to see it."""

    pid: int
    parent_pid: int
    name: str
    executable: Optional[str] = None
    command_line: Optional[str] = None
    create_time_utc: Optional[str] = None

    @property
    def image_name(self) -> str:
        return str(self.name or "").lower()


ProcessTable = Sequence[ProcessRecord]
ProcessTableFn = Callable[[], ProcessTable]


_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_VM_READ = 0x0010
_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_COMMAND_LINE_INFORMATION = 60
_MAX_PROCESS_PATH_CHARS = 32768
_MAX_COMMAND_LINE_BYTES = 1024 * 1024
_WINDOWS_EPOCH_TICKS = 116444736000000000


def _filetime_utc(high: int, low: int) -> Optional[str]:
    ticks = (int(high) << 32) | int(low)
    if ticks < _WINDOWS_EPOCH_TICKS:
        return None
    seconds = (ticks - _WINDOWS_EPOCH_TICKS) / 10_000_000.0
    try:
        stamp = datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _windows_process_table() -> List[ProcessRecord]:
    """Enumerate Windows processes through in-process Win32/NT APIs.

    This function is deliberately shell-free.  The former implementation
    launched ``powershell.exe Get-CimInstance Win32_Process`` on every watchdog
    cycle, which created the operator-visible recurring console and could return
    an empty table when CIM access failed.  Toolhelp supplies identity/parent
    data, while query-only process handles supply executable, creation time and
    command line.  Inaccessible system processes remain useful partial records;
    PHX2's same-user watchdog and producer are fully queryable.
    """

    try:
        import ctypes
        from ctypes import wintypes
    except Exception:                                  # pragma: no cover
        return []

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = (
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        )

    class FILETIME(ctypes.Structure):
        _fields_ = (
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        )

    class UNICODE_STRING(ctypes.Structure):
        _fields_ = (
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", wintypes.LPWSTR),
        )

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    except (AttributeError, OSError):                  # pragma: no cover
        return []

    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (
        wintypes.DWORD, wintypes.DWORD)
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32FirstW.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD))
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME))
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    ntdll.NtQueryInformationProcess.restype = wintypes.LONG
    ntdll.NtQueryInformationProcess.argtypes = (
        wintypes.HANDLE, wintypes.ULONG, wintypes.LPVOID, wintypes.ULONG,
        ctypes.POINTER(wintypes.ULONG))

    def _open(pid: int):
        handle = kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if handle:
            return handle
        return kernel32.OpenProcess(
            _PROCESS_QUERY_INFORMATION | _PROCESS_VM_READ, False, int(pid))

    def _image(handle) -> Optional[str]:
        size = wintypes.DWORD(_MAX_PROCESS_PATH_CHARS)
        buffer = ctypes.create_unicode_buffer(int(size.value))
        if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)):
            return None
        return str(buffer[:int(size.value)]) or None

    def _created(handle) -> Optional[str]:
        created = FILETIME()
        exited = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if not kernel32.GetProcessTimes(
                handle, ctypes.byref(created), ctypes.byref(exited),
                ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return _filetime_utc(
            created.dwHighDateTime, created.dwLowDateTime)

    def _command_line(handle) -> Optional[str]:
        required = wintypes.ULONG(0)
        ntdll.NtQueryInformationProcess(
            handle, _PROCESS_COMMAND_LINE_INFORMATION, None, 0,
            ctypes.byref(required))
        byte_count = int(required.value)
        if byte_count <= ctypes.sizeof(UNICODE_STRING) \
                or byte_count > _MAX_COMMAND_LINE_BYTES:
            return None
        buffer = ctypes.create_string_buffer(byte_count)
        status = int(ntdll.NtQueryInformationProcess(
            handle, _PROCESS_COMMAND_LINE_INFORMATION, buffer, byte_count,
            ctypes.byref(required)))
        if status < 0:
            return None
        descriptor = UNICODE_STRING.from_buffer(buffer)
        length = int(descriptor.Length)
        if not descriptor.Buffer or length <= 0 or length % 2:
            return None
        try:
            return ctypes.wstring_at(descriptor.Buffer, length // 2)
        except (ValueError, OSError):
            return None

    invalid_handle = ctypes.c_void_p(-1).value
    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snapshot or int(snapshot) == int(invalid_handle):
        return []

    records: List[ProcessRecord] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        available = bool(kernel32.Process32FirstW(
            snapshot, ctypes.byref(entry)))
        while available:
            pid = int(entry.th32ProcessID)
            executable: Optional[str] = None
            command_line: Optional[str] = None
            create_time_utc: Optional[str] = None
            handle = _open(pid) if pid > 0 else None
            if handle:
                try:
                    executable = _image(handle)
                    create_time_utc = _created(handle)
                    command_line = _command_line(handle)
                finally:
                    kernel32.CloseHandle(handle)
            if pid > 0:
                records.append(ProcessRecord(
                    pid=pid,
                    parent_pid=int(entry.th32ParentProcessID),
                    name=str(entry.szExeFile or ""),
                    executable=executable,
                    command_line=command_line,
                    create_time_utc=create_time_utc,
                ))
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            available = bool(kernel32.Process32NextW(
                snapshot, ctypes.byref(entry)))
    finally:
        kernel32.CloseHandle(snapshot)
    return records


def default_process_table(*, timeout_seconds: float = 45.0) -> List[ProcessRecord]:
    """Return a shell-free process snapshot for recurring watchdog observation."""

    del timeout_seconds  # retained for backward-compatible callers
    if os.name != "nt":                                 # pragma: no cover
        return []
    return _windows_process_table()


#: Additional Win32 constants for the liveness probe below.
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_ERROR_ACCESS_DENIED = 5
_ERROR_INVALID_PARAMETER = 87


def _pid_alive_windows(pid: int) -> Optional[bool]:
    """Non-destructive Win32 liveness probe, or ``None`` if unavailable.

    WHY THIS EXISTS -- and why ``os.kill(pid, 0)`` must never be used here.
    On Windows, CPython's ``os.kill`` has no "probe" mode: for any signal other
    than ``CTRL_C_EVENT`` / ``CTRL_BREAK_EVENT`` it calls
    ``OpenProcess(PROCESS_ALL_ACCESS, ...)`` followed by
    ``TerminateProcess(handle, sig)``.  ``os.kill(pid, 0)`` therefore TERMINATES
    the target with exit code 0 instead of reporting on it.  A watchdog that
    probed the live producer that way once per cycle would kill the very process
    it exists to keep alive, so liveness is answered here with
    ``WaitForSingleObject(handle, 0)``, which is read-only and -- unlike
    ``GetExitCodeProcess`` -- has no ``STILL_ACTIVE``/exit-code-259 ambiguity.
    """

    try:
        import ctypes
        from ctypes import wintypes
    except Exception:                                  # pragma: no cover
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):                  # pragma: no cover
        return None

    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                     wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    access = _PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE
    handle = kernel32.OpenProcess(access, False, int(pid))
    if not handle:
        error = ctypes.get_last_error()
        if error == _ERROR_ACCESS_DENIED:
            # The process exists; this session simply may not open it.
            return True
        if error == _ERROR_INVALID_PARAMETER:
            return False
        # Fall back to the SYNCHRONIZE-less query right before giving up.
        handle = kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        status = kernel32.WaitForSingleObject(handle, 0)
    finally:
        kernel32.CloseHandle(handle)
    if status == _WAIT_TIMEOUT:
        return True
    if status == _WAIT_OBJECT_0:
        return False
    return None


def pid_alive(pid: object) -> bool:
    """Is this PID a live process?  READ-ONLY on every platform.

    Deliberately NOT a mirror of ``StateDirRuntimeLock._pid_alive``: that helper
    uses ``os.kill(pid, 0)``, which on Windows terminates the target rather than
    probing it (see :func:`_pid_alive_windows`).  The watchdog must be able to
    ask "is the producer still running?" thousands of times without affecting it.
    """

    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        verdict = _pid_alive_windows(int(pid))
        if verdict is not None:
            return verdict
        return False
    try:
        os.kill(int(pid), 0)                      # POSIX: genuinely a probe
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _same_path(left: object, right: object) -> bool:
    if left is None or right is None:
        return False
    try:
        return (Path(str(left)).expanduser().resolve()
                == Path(str(right)).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        return False


def _command_names_path(command_line: object, flag: str,
                        expected: object) -> Optional[bool]:
    """Does ``--flag <value>`` in this command line name ``expected``?

    ``None`` means the flag is absent.  Quoting is handled by comparing resolved
    paths, so ``"C:\\a\\b"`` and ``C:\\a\\b`` agree.
    """

    tokens = _tokenize(command_line)
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            return _same_path(tokens[index + 1], expected)
    return None


def _command_flag_value(command_line: object, flag: str) -> Optional[str]:
    tokens = _tokenize(command_line)
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            return tokens[index + 1]
    return None


def _tokenize(command_line: object) -> List[str]:
    """Split a Windows command line into tokens, honouring double quotes."""

    text = str(command_line or "")
    tokens: List[str] = []
    current: List[str] = []
    in_quotes = False
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
            continue
        if char.isspace() and not in_quotes:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _count_flag(command_line: object, flag: str) -> int:
    return sum(1 for token in _tokenize(command_line) if token == flag)


def acceptable_producer_executables(repo_python: object) -> List[str]:
    """Every executable path a canonical producer may legitimately present.

    The repository venv ``python.exe`` is a **re-exec launcher stub**: one logical
    producer appears as a shim -> real PAIR, and the REAL half -- the one that
    calls ``os.getpid()`` and therefore OWNS the state-dir runtime lock -- reports
    the BASE interpreter as its ``ExecutablePath``, not the venv shim.  Measured
    live on 2026-07-26:

        pid 49628  <repo>\\.venv\\Scripts\\python.exe        (shim, logical root)
        pid 40588  C:\\Program Files\\Python312\\python.exe   (real, lock holder)

    Comparing the lock holder against the venv path alone therefore refuses a
    perfectly valid producer.  The base interpreter is read from the venv's own
    ``pyvenv.cfg``, so this stays an exact allow-list of two known binaries rather
    than being weakened to "any python.exe".
    """

    accepted: List[str] = []

    def _add(candidate: object) -> None:
        if not candidate:
            return
        try:
            resolved = Path(str(candidate)).expanduser().resolve()
        except (OSError, ValueError, RuntimeError):
            return
        text = str(resolved)
        if text not in accepted:
            accepted.append(text)

    _add(repo_python)
    try:
        venv_root = Path(str(repo_python)).resolve().parent.parent
        config_path = venv_root / "pyvenv.cfg"
        for line in config_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().lower()
            value = value.strip()
            if key == "executable":
                _add(value)
            elif key == "home":
                _add(Path(value) / "python.exe")
    except OSError:
        pass
    return accepted


def matches_producer_module(record: ProcessRecord) -> bool:
    """Is this process an instance of the tracked producer module?"""

    if record.image_name not in PRODUCER_IMAGE_NAMES:
        return False
    tokens = _tokenize(record.command_line)
    return PRODUCER_MODULE in tokens


def logical_producer_pids(table: ProcessTable) -> List[int]:
    """PIDs of DISTINCT logical producers (shim/real pairs collapsed).

    A matching process whose parent is also a matching process is the re-exec
    half of one logical producer and is not counted again.
    """

    matching = {record.pid: record for record in table
                if matches_producer_module(record)}
    roots: List[int] = []
    for pid, record in matching.items():
        if record.parent_pid in matching:
            continue
        roots.append(pid)
    return sorted(roots)


def producer_process_pids(table: ProcessTable) -> List[int]:
    """Every matching PID, shims included (used for exit confirmation)."""

    return sorted(record.pid for record in table
                  if matches_producer_module(record))


def descendants_of(table: ProcessTable, pid: int) -> List[int]:
    """Every transitive child PID of ``pid`` present in ``table``."""

    children: Dict[int, List[int]] = {}
    for record in table:
        children.setdefault(record.parent_pid, []).append(record.pid)
    found: List[int] = []
    stack = list(children.get(int(pid), []))
    seen: set = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        found.append(current)
        stack.extend(children.get(current, []))
    return sorted(found)


# --------------------------------------------------------------------------- #
# producer runtime lock (producer-owned; read here, removed only when proven)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProducerLockView:
    """A read-only view of the producer's state-dir runtime lock."""

    present: bool
    holder_pid: Optional[int]
    acquired_at_utc: Optional[str]
    malformed: bool


def read_producer_lock(path: object) -> ProducerLockView:
    """Parse ``<pid>|<iso-utc>`` exactly as the producer writes it."""

    try:
        text = Path(str(path)).read_text(encoding="utf-8").strip()
    except OSError:
        return ProducerLockView(False, None, None, False)
    if not text:
        return ProducerLockView(True, None, None, True)
    parts = text.split("|", 1)
    try:
        pid = int(parts[0])
    except (ValueError, IndexError):
        return ProducerLockView(True, None, None, True)
    if pid <= 0:
        return ProducerLockView(True, None, None, True)
    stamp = parts[1].strip() if len(parts) > 1 else None
    return ProducerLockView(True, pid, stamp, False)


@dataclass
class StaleLockVerdict:
    """May the producer runtime lock be removed, and on what proof?"""

    removable: bool
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)


def evaluate_stale_producer_lock(
    *, lock: ProducerLockView, table: ProcessTable,
    yellowstone_owner_count: Optional[int],
) -> StaleLockVerdict:
    """A stale lock is removable only on THREE independent proofs.

    Owner PID dead, no matching producer process anywhere in the table, and no
    Yellowstone owner reported.  An unknown owner count is NOT proof of zero, so
    it refuses.
    """

    evidence: Dict[str, Any] = {
        "lock_present": bool(lock.present),
        "holder_pid": lock.holder_pid,
        "holder_alive": None,
        "matching_producer_pids": producer_process_pids(table),
        "yellowstone_owner_count": yellowstone_owner_count,
    }
    if not lock.present:
        return StaleLockVerdict(False, "NO_LOCK_PRESENT", evidence)
    if lock.malformed or lock.holder_pid is None:
        # A malformed lock names no owner that could be proven dead.
        return StaleLockVerdict(False, ADOPT_LOCK_MALFORMED, evidence)
    holder_alive = pid_alive(int(lock.holder_pid))
    evidence["holder_alive"] = holder_alive
    if holder_alive:
        return StaleLockVerdict(False, "LOCK_OWNER_ALIVE", evidence)
    if evidence["matching_producer_pids"]:
        return StaleLockVerdict(
            False, "MATCHING_PRODUCER_PROCESS_STILL_PRESENT", evidence)
    if yellowstone_owner_count is None:
        return StaleLockVerdict(
            False, "YELLOWSTONE_OWNER_COUNT_UNKNOWN", evidence)
    if int(yellowstone_owner_count) != 0:
        return StaleLockVerdict(False, "YELLOWSTONE_OWNER_PRESENT", evidence)
    return StaleLockVerdict(True, "STALE_LOCK_OWNER_PROVEN_DEAD", evidence)


def remove_stale_producer_lock(path: object, *,
                               verdict: StaleLockVerdict) -> bool:
    """Delete the ONE exact stale lock file, only on a removable verdict."""

    if not verdict.removable:
        return False
    try:
        Path(str(path)).unlink()
    except OSError:
        return False
    return True


# --------------------------------------------------------------------------- #
# watchdog lock
# --------------------------------------------------------------------------- #

ALREADY_RUNNING = "ALREADY_RUNNING"
LOCK_ACQUIRED = "LOCK_ACQUIRED"
LOCK_RECLAIMED_STALE = "LOCK_RECLAIMED_STALE"
LOCK_UNWRITABLE = "LOCK_UNWRITABLE"
LOCK_AMBIGUOUS = "LOCK_AMBIGUOUS"


@dataclass
class WatchdogLockResult:
    outcome: str
    holder_pid: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def acquired(self) -> bool:
        return self.outcome in (LOCK_ACQUIRED, LOCK_RECLAIMED_STALE)


class WatchdogLock:
    """Single-instance lock for the watchdog itself.

    Contents are an authenticated, redaction-safe descriptor: pid, process start
    identity, repository HEAD, launcher sha256, startup UTC, a non-secret random
    instance nonce and a schema version.  The nonce lets two watchdogs that race
    on creation detect that the file they can read is not the one they wrote.
    """

    def __init__(self, path: object) -> None:
        self._path = Path(str(path))
        self._nonce: Optional[str] = None
        self._acquired = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def nonce(self) -> Optional[str]:
        return self._nonce

    def read(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return False, None
        try:
            document = json.loads(text)
        except ValueError:
            return True, None
        return True, document if isinstance(document, dict) else None

    def holder_pid(self) -> Optional[int]:
        present, document = self.read()
        if not present or not isinstance(document, dict):
            return None
        try:
            pid = int(document.get("watchdog_pid") or 0)
        except (TypeError, ValueError):
            return None
        return pid if pid > 0 else None

    def held_by_live_other_watchdog(self, *, table: ProcessTable) -> bool:
        pid = self.holder_pid()
        if pid is None or pid == os.getpid():
            return False
        if not pid_alive(pid):
            return False
        # Liveness alone is not ownership: the PID may have been recycled by an
        # unrelated program. Require the live process to still look like a
        # Python watchdog when the table can tell us.
        for record in table:
            if record.pid == pid:
                return record.image_name in PRODUCER_IMAGE_NAMES
        return True

    def acquire(self, *, repo_head: str, launcher_sha256: Optional[str],
                nonce: str, table: ProcessTable,
                now_utc: Optional[str] = None) -> WatchdogLockResult:
        present, document = self.read()
        if present:
            if document is None:
                return WatchdogLockResult(
                    LOCK_AMBIGUOUS, None,
                    {"reason": "WATCHDOG_LOCK_MALFORMED"})
            holder = self.holder_pid()
            if holder is not None and holder != os.getpid() and pid_alive(holder):
                return WatchdogLockResult(
                    ALREADY_RUNNING, holder,
                    {"reason": "ANOTHER_WATCHDOG_HOLDS_THE_LOCK"})
            try:
                self._path.unlink()
            except OSError:
                return WatchdogLockResult(
                    LOCK_UNWRITABLE, holder,
                    {"reason": "STALE_WATCHDOG_LOCK_UNREMOVABLE"})
            reclaimed = True
        else:
            reclaimed = False

        payload = {
            "schema_version": WATCHDOG_LOCK_SCHEMA_V1,
            "watchdog_pid": int(os.getpid()),
            "watchdog_started_at_utc": str(now_utc or utc_now_iso()),
            "repo_head": str(repo_head or "").lower(),
            "launcher_sha256": launcher_sha256,
            "instance_nonce": str(nonce),
            "lock_path_digest": path_digest(self._path),
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handle = os.open(
                str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return WatchdogLockResult(
                ALREADY_RUNNING, self.holder_pid(),
                {"reason": "WATCHDOG_LOCK_CREATED_CONCURRENTLY"})
        try:
            os.write(handle, json.dumps(
                payload, indent=2, sort_keys=True).encode("utf-8"))
        finally:
            os.close(handle)
        # Read back: if another watchdog won the race, the nonce differs.
        _, verify = self.read()
        if not isinstance(verify, dict) \
                or verify.get("instance_nonce") != str(nonce):
            return WatchdogLockResult(
                ALREADY_RUNNING, self.holder_pid(),
                {"reason": "WATCHDOG_LOCK_NONCE_MISMATCH"})
        self._nonce = str(nonce)
        self._acquired = True
        return WatchdogLockResult(
            LOCK_RECLAIMED_STALE if reclaimed else LOCK_ACQUIRED,
            int(os.getpid()), {"reason": "OK"})

    def release(self) -> bool:
        if not self._acquired:
            return False
        _, document = self.read()
        if isinstance(document, dict) \
                and document.get("instance_nonce") != self._nonce:
            # Never remove a lock this instance does not own.
            self._acquired = False
            return False
        try:
            self._path.unlink()
        except OSError:
            return False
        self._acquired = False
        return True


def new_instance_nonce() -> str:
    """A non-secret random instance identifier."""

    return hashlib.sha256(os.urandom(32)).hexdigest()[:24]


# --------------------------------------------------------------------------- #
# adoption
# --------------------------------------------------------------------------- #

@dataclass
class AdoptionVerdict:
    adoptable: bool
    reasons: List[str] = field(default_factory=list)
    producer_pid: Optional[int] = None
    checks: Dict[str, Any] = field(default_factory=dict)


def evaluate_producer_adoption(
    *,
    table: ProcessTable,
    lock: ProducerLockView,
    repo_python: object,
    expected_head: str,
    cursor_state_dir: object,
    ledger_path: object,
    recorded_start_utc: Optional[str] = None,
    heartbeat: Optional[Mapping[str, Any]] = None,
    yellowstone_owner_count: Optional[int] = None,
    expected_alert_policy: Optional[str] = None,
) -> AdoptionVerdict:
    """Prove -- or refuse -- that a running process is THE canonical producer.

    Every violation is listed, so one evaluation tells the operator everything.
    Ambiguity is always a refusal: the watchdog would rather monitor nothing than
    adopt a process it cannot identify, and it never starts a second producer
    while an unidentified candidate is alive.
    """

    reasons: List[str] = []
    checks: Dict[str, Any] = {}

    logical = logical_producer_pids(table)
    checks["logical_producer_count"] = len(logical)
    if len(logical) > 1:
        reasons.append(ADOPT_DUPLICATE)

    if not lock.present:
        reasons.append(ADOPT_NO_LOCK)
        return AdoptionVerdict(False, reasons, None, checks)
    if lock.malformed or lock.holder_pid is None:
        reasons.append(ADOPT_LOCK_MALFORMED)
        return AdoptionVerdict(False, reasons, None, checks)

    pid = int(lock.holder_pid)
    checks["lock_holder_pid"] = pid
    if not pid_alive(pid):
        reasons.append(ADOPT_OWNER_DEAD)
        return AdoptionVerdict(False, reasons, None, checks)

    record = next((item for item in table if item.pid == pid), None)
    if record is None:
        reasons.append(ADOPT_PID_NOT_IN_TABLE)
        return AdoptionVerdict(False, reasons, pid, checks)

    checks["image_name"] = record.image_name
    if record.image_name not in PRODUCER_IMAGE_NAMES:
        reasons.append(ADOPT_IMAGE_MISMATCH)
    accepted_executables = acceptable_producer_executables(repo_python)
    checks["executable_accepted"] = any(
        _same_path(record.executable, candidate)
        for candidate in accepted_executables)
    if not checks["executable_accepted"]:
        reasons.append(ADOPT_EXECUTABLE_MISMATCH)
    if not matches_producer_module(record):
        reasons.append(ADOPT_MODULE_MISMATCH)

    if recorded_start_utc is not None:
        observed = parse_utc(record.create_time_utc)
        recorded = parse_utc(recorded_start_utc)
        matched = (observed is not None and recorded is not None
                   and abs((observed - recorded).total_seconds()) <= 2.0)
        checks["start_time_match"] = matched
        if not matched:
            reasons.append(ADOPT_START_TIME_MISMATCH)

    head_value = _command_flag_value(record.command_line, "--expected-head")
    checks["expected_head_match"] = bool(
        head_value and str(head_value).strip().lower()
        == str(expected_head).strip().lower())
    if not checks["expected_head_match"]:
        reasons.append(ADOPT_HEAD_MISMATCH)

    if _command_names_path(
            record.command_line, "--cursor-state-dir", cursor_state_dir) is not True:
        reasons.append(ADOPT_STATE_PATH_MISMATCH)
    if _command_names_path(
            record.command_line, "--ledger-path", ledger_path) is not True:
        reasons.append(ADOPT_LEDGER_PATH_MISMATCH)

    telegram_flags = _count_flag(record.command_line, "--enable-telegram")
    discord_flags = _count_flag(record.command_line, "--enable-private-discord")
    checks["telegram_flag_count"] = telegram_flags
    checks["discord_flag_count"] = discord_flags
    if telegram_flags != 1:
        reasons.append(ADOPT_TELEGRAM_MISMATCH)
    if discord_flags != 0:
        reasons.append(ADOPT_DISCORD_PRESENT)

    policy = _command_flag_value(record.command_line, "--phx1-structural-policy")
    checks["structural_policy"] = str(policy or "").lower() or None
    if str(policy or "").strip().lower() != "shadow":
        reasons.append(ADOPT_SHADOW_MISSING)

    # Adoption is where an already-running process is taken under management,
    # so it is the boundary at which a producer running a different alert
    # policy than the deployment expects must be refused rather than inherited.
    # The expectation is supplied by the caller (the watchdog derives it from
    # the launcher it would itself run); when no expectation is stated, an
    # UNPARSEABLE policy is still refused -- absence is tolerated, corruption
    # never is.
    alert_flag_count = _count_flag(record.command_line, "--alert-policy")
    alert_value = _command_flag_value(record.command_line, "--alert-policy")
    checks["alert_policy_flag_count"] = alert_flag_count
    observed_alert_policy: Optional[str] = None
    if alert_flag_count == 1:
        try:
            observed_alert_policy = normalize_alert_policy(
                str(alert_value or "").strip())
        except ValueError:
            observed_alert_policy = None
    checks["alert_policy"] = observed_alert_policy
    if expected_alert_policy is not None:
        try:
            wanted = normalize_alert_policy(expected_alert_policy)
        except ValueError:
            wanted = None
        checks["expected_alert_policy"] = wanted
        if alert_flag_count != 1 or observed_alert_policy is None \
                or wanted is None or observed_alert_policy != wanted:
            reasons.append(ADOPT_ALERT_POLICY_MISMATCH)
    elif alert_flag_count and observed_alert_policy is None:
        reasons.append(ADOPT_ALERT_POLICY_MISMATCH)

    if heartbeat is not None:
        telegram_enabled = bool(heartbeat.get("telegram_enabled"))
        discord_enabled = bool(heartbeat.get("discord_enabled"))
        checks["heartbeat_telegram_enabled"] = telegram_enabled
        checks["heartbeat_discord_enabled"] = discord_enabled
        if not telegram_enabled:
            reasons.append(ADOPT_TELEGRAM_MISMATCH)
        if discord_enabled:
            reasons.append(ADOPT_DISCORD_PRESENT)

    if yellowstone_owner_count is not None:
        checks["yellowstone_owner_count"] = int(yellowstone_owner_count)
        if int(yellowstone_owner_count) > 1:
            reasons.append(ADOPT_OWNER_COUNT)

    ordered: List[str] = []
    seen: set = set()
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            ordered.append(reason)
    return AdoptionVerdict(not ordered, ordered, pid, checks)


def redacted_process_summary(table: ProcessTable) -> Dict[str, Any]:
    """A redaction-safe topology summary: counts and PIDs only, no command text."""

    logical = logical_producer_pids(table)
    return {
        "logical_producer_count": len(logical),
        "logical_producer_pids": logical,
        "matching_process_count": len(producer_process_pids(table)),
        "table_size": len(list(table)),
    }


__all__ = (
    "PRODUCER_MODULE", "PRODUCER_IMAGE_NAMES", "LAUNCHER_IMAGE_NAMES",
    "WATCHDOG_LOCK_SCHEMA_V1",
    "ADOPT_OK", "ADOPTION_REFUSAL_REASONS",
    "ADOPT_NO_LOCK", "ADOPT_LOCK_MALFORMED", "ADOPT_OWNER_DEAD",
    "ADOPT_PID_NOT_IN_TABLE", "ADOPT_START_TIME_MISMATCH",
    "ADOPT_IMAGE_MISMATCH", "ADOPT_EXECUTABLE_MISMATCH",
    "ADOPT_MODULE_MISMATCH", "ADOPT_HEAD_MISMATCH",
    "ADOPT_STATE_PATH_MISMATCH", "ADOPT_LEDGER_PATH_MISMATCH",
    "ADOPT_TELEGRAM_MISMATCH", "ADOPT_DISCORD_PRESENT", "ADOPT_SHADOW_MISSING",
    "ADOPT_ALERT_POLICY_MISMATCH",
    "ADOPT_DUPLICATE", "ADOPT_OWNER_COUNT", "ADOPT_AMBIGUOUS",
    "ALREADY_RUNNING", "LOCK_ACQUIRED", "LOCK_RECLAIMED_STALE",
    "LOCK_UNWRITABLE", "LOCK_AMBIGUOUS",
    "ProcessRecord", "ProcessTable", "ProcessTableFn",
    "default_process_table", "pid_alive", "acceptable_producer_executables",
    "matches_producer_module", "logical_producer_pids", "producer_process_pids",
    "descendants_of",
    "ProducerLockView", "read_producer_lock", "StaleLockVerdict",
    "evaluate_stale_producer_lock", "remove_stale_producer_lock",
    "WatchdogLock", "WatchdogLockResult", "new_instance_nonce",
    "AdoptionVerdict", "evaluate_producer_adoption",
    "redacted_process_summary",
)
