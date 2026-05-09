"""Tests for PHX2 database connection boundaries."""

import sqlite3
import uuid
from pathlib import Path

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings, PHX2Settings
from PHX2.db.connection import get_phoenix1_readonly_connection, get_phx2_connection


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"phx2_dryrun_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


def test_default_db_paths_are_separate():
    settings = PHX2Settings()

    assert settings.phoenix1_db.path == "data/bot.db"
    assert settings.phx2_db.path == "data/phx2_dryrun.db"
    assert settings.phoenix1_db.path != settings.phx2_db.path


def test_phoenix1_readonly_connection_opens_when_bot_db_exists():
    settings = PHX2Settings()
    phoenix1_path = Path(settings.phoenix1_db.path)
    if not phoenix1_path.exists():
        pytest.skip("Phoenix1 data/bot.db is missing in this test environment")

    with get_phoenix1_readonly_connection(settings) as connection:
        row = connection.execute("PRAGMA database_list").fetchone()

    assert Path(row["file"]).resolve() == phoenix1_path.resolve()


def test_phoenix1_readonly_connection_rejects_writes():
    settings = PHX2Settings()
    phoenix1_path = Path(settings.phoenix1_db.path)
    if not phoenix1_path.exists():
        pytest.skip("Phoenix1 data/bot.db is missing in this test environment")

    with get_phoenix1_readonly_connection(settings) as connection:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE phx2_readonly_probe (id INTEGER)")


def test_phx2_connection_points_to_separate_dry_run_db():
    phx2_path = _temporary_phx2_db_path()
    settings = PHX2DryRunDbSettings(path=str(phx2_path))

    try:
        connection = get_phx2_connection(settings)
        try:
            row = connection.execute("PRAGMA database_list").fetchone()
            schema_count = connection.execute(
                "SELECT COUNT(*) AS count FROM sqlite_master"
            ).fetchone()["count"]
        finally:
            connection.close()

        assert Path(row["file"]).resolve() == phx2_path.resolve()
        assert phx2_path.resolve() != Path("data/bot.db").resolve()
        assert schema_count == 0
    finally:
        _cleanup_temporary_phx2_db(phx2_path)
