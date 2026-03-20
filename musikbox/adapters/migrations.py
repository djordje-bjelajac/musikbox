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

_CREATE_PLAYLISTS_TABLE = """
CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_CREATE_PLAYLIST_TRACKS_TABLE = """
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id TEXT NOT NULL,
    track_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, track_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(id)
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tracks_bpm ON tracks(bpm);",
    "CREATE INDEX IF NOT EXISTS idx_tracks_key ON tracks(key);",
    "CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);",
    (
        "CREATE INDEX IF NOT EXISTS idx_playlist_tracks_order"
        " ON playlist_tracks(playlist_id, position);"
    ),
]


def _migrate_enrichment_columns(conn: sqlite3.Connection) -> None:
    """Add enrichment columns to tracks table (idempotent)."""
    for column_def in [
        "remix TEXT",
        "year INTEGER",
        "tags TEXT",
        "enriched_at TEXT",
    ]:
        try:
            conn.execute(f"ALTER TABLE tracks ADD COLUMN {column_def}")
        except sqlite3.OperationalError:
            pass  # Column already exists


def init_db(db_path: Path) -> None:
    """Initialize the database schema. Creates the tracks table and indexes."""
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(db_path))
        try:
            connection.execute(_CREATE_TRACKS_TABLE)
            connection.execute(_CREATE_PLAYLISTS_TABLE)
            connection.execute(_CREATE_PLAYLIST_TRACKS_TABLE)
            for index_sql in _CREATE_INDEXES:
                connection.execute(index_sql)
            _migrate_enrichment_columns(connection)
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to initialize database: {e}") from e
