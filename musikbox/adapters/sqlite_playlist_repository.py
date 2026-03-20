import sqlite3
from datetime import datetime
from pathlib import Path

from musikbox.domain.exceptions import (
    DatabaseError,
    PlaylistNotFoundError,
    TrackNotFoundError,
)
from musikbox.domain.models import Playlist, Track, TrackId
from musikbox.domain.ports.playlist_repository import PlaylistRepository


class SqlitePlaylistRepository(PlaylistRepository):
    """SQLite implementation of the PlaylistRepository port."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(db_path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")

    def create(self, playlist: Playlist) -> None:
        sql = """
            INSERT INTO playlists (id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """
        try:
            self._connection.execute(
                sql,
                (
                    playlist.id,
                    playlist.name,
                    playlist.created_at.isoformat(),
                    playlist.updated_at.isoformat(),
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as e:
            raise DatabaseError(f"Playlist with name '{playlist.name}' already exists") from e
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to create playlist: {e}") from e

    def get_by_id(self, playlist_id: str) -> Playlist:
        try:
            cursor = self._connection.execute(
                "SELECT * FROM playlists WHERE id = ?",
                (playlist_id,),
            )
            row = cursor.fetchone()
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to fetch playlist: {e}") from e

        if row is None:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist_id}")

        return self._row_to_playlist(row)

    def get_by_name(self, name: str) -> Playlist | None:
        try:
            cursor = self._connection.execute(
                "SELECT * FROM playlists WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to fetch playlist: {e}") from e

        if row is None:
            return None

        return self._row_to_playlist(row)

    def list_all(self) -> list[Playlist]:
        try:
            cursor = self._connection.execute(
                "SELECT * FROM playlists ORDER BY name",
            )
            return [self._row_to_playlist(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to list playlists: {e}") from e

    def delete(self, playlist_id: str) -> None:
        try:
            cursor = self._connection.execute(
                "DELETE FROM playlists WHERE id = ?",
                (playlist_id,),
            )
            self._connection.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to delete playlist: {e}") from e

        if cursor.rowcount == 0:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist_id}")

    def update(self, playlist: Playlist) -> None:
        sql = """
            UPDATE playlists
            SET name = ?, updated_at = ?
            WHERE id = ?
        """
        try:
            cursor = self._connection.execute(
                sql,
                (
                    playlist.name,
                    playlist.updated_at.isoformat(),
                    playlist.id,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as e:
            raise DatabaseError(f"Playlist with name '{playlist.name}' already exists") from e
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to update playlist: {e}") from e

        if cursor.rowcount == 0:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist.id}")

    def add_track(self, playlist_id: str, track_id: str, position: int) -> None:
        try:
            # Check track exists
            cursor = self._connection.execute("SELECT id FROM tracks WHERE id = ?", (track_id,))
            if cursor.fetchone() is None:
                raise TrackNotFoundError(f"Track not found: {track_id}")

            # Skip if already in playlist
            cursor = self._connection.execute(
                "SELECT 1 FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, track_id),
            )
            if cursor.fetchone() is not None:
                return

            self._connection.execute(
                "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
                (playlist_id, track_id, position),
            )
            self._connection.commit()
        except (TrackNotFoundError, PlaylistNotFoundError):
            raise
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to add track to playlist: {e}") from e

    def remove_track(self, playlist_id: str, track_id: str) -> None:
        try:
            cursor = self._connection.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, track_id),
            )
            if cursor.rowcount == 0:
                raise TrackNotFoundError(f"Track {track_id} not in playlist {playlist_id}")

            # Re-compact positions
            cursor = self._connection.execute(
                "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
                (playlist_id,),
            )
            rows = cursor.fetchall()
            for i, row in enumerate(rows):
                self._connection.execute(
                    "UPDATE playlist_tracks SET position = ? "
                    "WHERE playlist_id = ? AND track_id = ?",
                    (i, playlist_id, row["track_id"]),
                )

            self._connection.commit()
        except (TrackNotFoundError, PlaylistNotFoundError):
            raise
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to remove track from playlist: {e}") from e

    def get_tracks(self, playlist_id: str) -> list[Track]:
        sql = """
            SELECT t.* FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
        """
        try:
            cursor = self._connection.execute(sql, (playlist_id,))
            return [self._row_to_track(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get playlist tracks: {e}") from e

    def reorder(self, playlist_id: str, track_ids: list[str]) -> None:
        try:
            self._connection.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            )
            for position, track_id in enumerate(track_ids):
                self._connection.execute(
                    "INSERT INTO playlist_tracks "
                    "(playlist_id, track_id, position) "
                    "VALUES (?, ?, ?)",
                    (playlist_id, track_id, position),
                )
            self._connection.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to reorder playlist: {e}") from e

    def get_playlists_for_track(self, track_id: str) -> list[Playlist]:
        try:
            cursor = self._connection.execute(
                "SELECT p.* FROM playlists p "
                "JOIN playlist_tracks pt ON p.id = pt.playlist_id "
                "WHERE pt.track_id = ? "
                "ORDER BY p.name",
                (track_id,),
            )
            return [self._row_to_playlist(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get playlists for track: {e}") from e

    def _row_to_playlist(self, row: sqlite3.Row) -> Playlist:
        return Playlist(
            id=row["id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

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
