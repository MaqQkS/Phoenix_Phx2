"""Indexes on dispatch_events.

Stage 12 query patterns include filtering by ``target`` (often a single sink
like ``discord_private_preview``) plus ``status`` and time bucketing on
``attempted_at``. The composite index ``idx_dispatch_events_target_status_time``
serves that pattern.
"""

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import apply_stage4_schema


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"dispatch_idx_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _phx2_connection() -> Iterator[sqlite3.Connection]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage4_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _index_names(connection: sqlite3.Connection) -> set:
    return {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='dispatch_events'"
        )
    }


def test_dispatch_events_target_status_time_index_exists():
    with _phx2_connection() as connection:
        names = _index_names(connection)
    assert "idx_dispatch_events_target_status_time" in names


def test_dispatch_events_target_status_time_index_columns_in_order():
    with _phx2_connection() as connection:
        rows = list(
            connection.execute(
                "PRAGMA index_info(idx_dispatch_events_target_status_time)"
            )
        )
    columns = [row["name"] for row in rows]
    assert columns == ["target", "status", "attempted_at"]
