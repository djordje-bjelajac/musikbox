import sqlite3
from pathlib import Path

from musikbox.adapters.migrations import init_db


def test_init_db_creates_tracks_table(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'")
    tables = cursor.fetchall()
    conn.close()

    assert len(tables) == 1
    assert tables[0][0] == "tracks"


def test_init_db_creates_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_tracks_%'"
    )
    indexes = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "idx_tracks_bpm" in indexes
    assert "idx_tracks_key" in indexes
    assert "idx_tracks_genre" in indexes


def test_init_db_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"

    init_db(db_path)
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'")
    tables = cursor.fetchall()
    conn.close()

    assert len(tables) == 1
