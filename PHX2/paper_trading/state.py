"""Local paper state boundaries and single-owner process lease."""
from __future__ import annotations

import json
import os
from pathlib import Path


def transaction(method):
    """Public engine mutations commit together, including nested operations."""
    def wrapped(self, *args, **kwargs):
        owner = not self._batch_active
        if owner:
            self.begin_batch()
        try:
            result = method(self, *args, **kwargs)
            if owner:
                self.commit_batch()
            return result
        except BaseException:
            if owner:
                self.rollback_batch()
            raise
    return wrapped


def json_copy(value):
    return json.loads(json.dumps(value, allow_nan=False))


def tuples(value):
    return tuple(tuples(item) for item in value) if isinstance(value, list) else value


class PaperRunLease:
    """OS-owned exclusive lock, automatically released even after a crash.

    The tiny lease file remains in the run directory. Its existence alone is
    not ownership: the OS byte lock is authoritative and is never unlinked.
    """
    def __init__(self, run_dir):
        self.path = Path(run_dir) / ".paper_owner.lock"
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            if handle.seek(0, 2) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError("PAPER_RUN_ALREADY_OWNED") from exc
        self.handle = handle
        return self

    def __exit__(self, *args):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
