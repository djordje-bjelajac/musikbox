import sqlite3
from pathlib import Path

from musikbox.domain.exceptions import DatabaseError

_CREATE_TRACKS_TABLE = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT,
    album TEXT,
    duration_seconds REAL NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    format TEXT NOT NULL,
    bpm REAL,
    key TEXT,
    genre TEXT,
    mood TEXT,
    source_url TEXT,
    downloaded_at TEXT,
    analyzed_at TEXT,
    created_at TEXT NOT NULL
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tracks_bpm ON tracks(bpm);",
    "CREATE INDEX IF NOT EXISTS idx_tracks_key ON tracks(key);",
    "CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);",
]


def init_db(db_path: Path) -> None:
    """Initialize the database schema. Creates the tracks table and indexes."""
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(db_path))
        try:
            connection.execute(_CREATE_TRACKS_TABLE)
            for index_sql in _CREATE_INDEXES:
                connection.execute(index_sql)
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to initialize database: {e}") from e
