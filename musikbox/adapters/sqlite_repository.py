import sqlite3
from datetime import datetime
from pathlib import Path

from musikbox.domain.exceptions import DatabaseError, TrackNotFoundError
from musikbox.domain.models import SearchFilter, Track, TrackId
from musikbox.domain.ports.repository import TrackRepository


class SqliteRepository(TrackRepository):
    """SQLite implementation of the TrackRepository port."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(db_path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")

    def save(self, track: Track) -> None:
        sql = """
            INSERT OR REPLACE INTO tracks
            (id, title, artist, album, duration_seconds, file_path, format,
             bpm, key, genre, mood, source_url, downloaded_at, analyzed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            self._connection.execute(
                sql,
                (
                    track.id.value,
                    track.title,
                    track.artist,
                    track.album,
                    track.duration_seconds,
                    str(track.file_path),
                    track.format,
                    track.bpm,
                    track.key,
                    track.genre,
                    track.mood,
                    track.source_url,
                    track.downloaded_at.isoformat() if track.downloaded_at else None,
                    track.analyzed_at.isoformat() if track.analyzed_at else None,
                    track.created_at.isoformat(),
                ),
            )
            self._connection.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to save track: {e}") from e

    def get_by_id(self, track_id: TrackId) -> Track:
        try:
            cursor = self._connection.execute(
                "SELECT * FROM tracks WHERE id = ?", (track_id.value,)
            )
            row = cursor.fetchone()
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to fetch track: {e}") from e

        if row is None:
            raise TrackNotFoundError(f"Track not found: {track_id.value}")

        return self._row_to_track(row)

    def search(self, filter: SearchFilter) -> list[Track]:
        clauses: list[str] = []
        params: list[str | float] = []

        if filter.bpm_min is not None:
            clauses.append("bpm >= ?")
            params.append(filter.bpm_min)
        if filter.bpm_max is not None:
            clauses.append("bpm <= ?")
            params.append(filter.bpm_max)
        if filter.key is not None:
            clauses.append("key = ?")
            params.append(filter.key)
        if filter.genre is not None:
            clauses.append("genre = ?")
            params.append(filter.genre)
        if filter.mood is not None:
            clauses.append("mood = ?")
            params.append(filter.mood)
        if filter.artist is not None:
            clauses.append("artist LIKE ?")
            params.append(f"%{filter.artist}%")
        if filter.title is not None:
            clauses.append("title LIKE ?")
            params.append(f"%{filter.title}%")
        if filter.query is not None:
            clauses.append("(title LIKE ? OR artist LIKE ?)")
            params.append(f"%{filter.query}%")
            params.append(f"%{filter.query}%")

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM tracks{where}"

        try:
            cursor = self._connection.execute(sql, params)
            return [self._row_to_track(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to search tracks: {e}") from e

    def delete(self, track_id: TrackId) -> None:
        try:
            cursor = self._connection.execute("DELETE FROM tracks WHERE id = ?", (track_id.value,))
            self._connection.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to delete track: {e}") from e

        if cursor.rowcount == 0:
            raise TrackNotFoundError(f"Track not found: {track_id.value}")

    def list_all(self, limit: int = 50, offset: int = 0) -> list[Track]:
        try:
            cursor = self._connection.execute(
                "SELECT * FROM tracks ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            return [self._row_to_track(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to list tracks: {e}") from e

    def _row_to_track(self, row: sqlite3.Row) -> Track:
        return Track(
            id=TrackId(value=row["id"]),
            title=row["title"],
            artist=row["artist"],
            album=row["album"],
            duration_seconds=row["duration_seconds"],
            file_path=Path(row["file_path"]),
            format=row["format"],
            bpm=row["bpm"],
            key=row["key"],
            genre=row["genre"],
            mood=row["mood"],
            source_url=row["source_url"],
            downloaded_at=(
                datetime.fromisoformat(row["downloaded_at"]) if row["downloaded_at"] else None
            ),
            analyzed_at=(
                datetime.fromisoformat(row["analyzed_at"]) if row["analyzed_at"] else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
