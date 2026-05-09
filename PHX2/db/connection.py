"""SQLite connection boundaries for PHX2.

Stage 2 only defines safe connection helpers. It does not create schemas, call
Phoenix1 initialization code, or import Phoenix1 database modules.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence, Union
from urllib.parse import quote

from PHX2.config.settings import PHX2DryRunDbSettings, PHX2Settings, Phoenix1ReadOnlyDbSettings


ReadablePhoenix1Settings = Union[PHX2Settings, Phoenix1ReadOnlyDbSettings]
WritablePHX2Settings = Union[PHX2Settings, PHX2DryRunDbSettings]


class PHX2Connection:
    """Wrapper around sqlite3.Connection that owns explicit transaction state.

    Repositories on the same wrapper share one transaction, which lets services
    compose atomic cross-repository writes via `with conn.transaction(): ...`.
    """

    def __init__(self, raw: sqlite3.Connection) -> None:
        self._raw = raw
        self._in_transaction: bool = False

    @property
    def in_transaction(self) -> bool:
        """True iff inside an explicit transaction() block on this wrapper.

        Shadows sqlite3.Connection.in_transaction (which reflects autocommit
        dirty state). Repositories check THIS flag to skip per-write commits.
        """
        return self._in_transaction

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group writes across repositories into one atomic SQLite transaction.

        Commits on clean exit, rolls back on any exception. Nested calls raise
        RuntimeError.
        """
        if self._in_transaction:
            raise RuntimeError("nested transactions not supported")
        self._in_transaction = True
        try:
            yield
        except BaseException:
            self._raw.rollback()
            raise
        else:
            self._raw.commit()
        finally:
            self._in_transaction = False

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self._raw.execute(sql, params)

    def executescript(self, sql: str) -> sqlite3.Cursor:
        return self._raw.executescript(sql)

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


def _resolve_database_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _sqlite_readonly_uri(path: str) -> str:
    resolved = _resolve_database_path(path)
    quoted = quote(resolved.as_posix(), safe="/:")
    return f"file:{quoted}?mode=ro"


def _phoenix1_path(settings: ReadablePhoenix1Settings) -> str:
    if isinstance(settings, PHX2Settings):
        return settings.phoenix1_db.path
    return settings.path


def _phx2_path(settings: WritablePHX2Settings) -> str:
    if isinstance(settings, PHX2Settings):
        return settings.phx2_db.path
    return settings.path


def get_phoenix1_readonly_connection(
    settings: ReadablePhoenix1Settings,
) -> sqlite3.Connection:
    """Open Phoenix1 SQLite database in read-only URI mode."""

    connection = sqlite3.connect(_sqlite_readonly_uri(_phoenix1_path(settings)), uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def get_phx2_connection(settings: WritablePHX2Settings) -> PHX2Connection:
    """Open the separate PHX2 dry-run SQLite database.

    This helper creates no tables and performs no migrations.
    """

    path = _resolve_database_path(_phx2_path(settings))
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    return PHX2Connection(raw)
