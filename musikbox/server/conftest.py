from __future__ import annotations

from datetime import datetime
from pathlib import Path

from musikbox.domain.exceptions import (
    DatabaseError,
    PlaylistNotFoundError,
    TrackNotFoundError,
)
from musikbox.domain.models import Playlist, SearchFilter, Track, TrackId
from musikbox.domain.ports.playlist_repository import PlaylistRepository
from musikbox.domain.ports.repository import TrackRepository


class InMemoryTrackRepository(TrackRepository):
    """Minimal in-memory TrackRepository for server tests.

    Implements every abstract method of
    ``musikbox.domain.ports.repository.TrackRepository`` so it can stand in
    for a real repository without touching SQLite.
    """

    def __init__(self) -> None:
        self._tracks: dict[str, Track] = {}

    def save(self, track: Track) -> None:
        self._tracks[track.id.value] = track

    def get_by_id(self, track_id: TrackId) -> Track:
        track = self._tracks.get(track_id.value)
        if track is None:
            raise TrackNotFoundError(f"Track not found: {track_id.value}")
        return track

    def get_by_file_path(self, file_path: Path) -> Track | None:
        for track in self._tracks.values():
            if track.file_path == file_path:
                return track
        return None

    def get_by_source_url(self, source_url: str) -> Track | None:
        for track in self._tracks.values():
            if track.source_url == source_url:
                return track
        return None

    def search(self, filter: SearchFilter) -> list[Track]:
        results: list[Track] = []
        for track in self._tracks.values():
            if not _matches(track, filter):
                continue
            results.append(track)
        return results

    def delete(self, track_id: TrackId) -> None:
        self._tracks.pop(track_id.value, None)

    def list_all(self, limit: int = 50, offset: int = 0) -> list[Track]:
        ordered = list(self._tracks.values())
        return ordered[offset : offset + limit]


def _matches(track: Track, filter: SearchFilter) -> bool:
    if filter.bpm_min is not None and (track.bpm is None or track.bpm < filter.bpm_min):
        return False
    if filter.bpm_max is not None and (track.bpm is None or track.bpm > filter.bpm_max):
        return False
    if filter.key is not None and track.key != filter.key:
        return False
    if filter.genre is not None and track.genre != filter.genre:
        return False
    if filter.mood is not None and track.mood != filter.mood:
        return False
    if filter.artist is not None and track.artist != filter.artist:
        return False
    if filter.album is not None and track.album != filter.album:
        return False
    if filter.title is not None and track.title != filter.title:
        return False
    if filter.query is not None and filter.query.lower() not in track.title.lower():
        return False
    return True


class InMemoryPlaylistRepository(PlaylistRepository):
    """Minimal in-memory PlaylistRepository for server tests.

    Shares a track store with an ``InMemoryTrackRepository`` so ``add_track``
    can enforce track existence and ``get_tracks`` can return real tracks,
    mirroring the SQLite adapter's foreign-key behaviour.
    """

    def __init__(self, tracks: InMemoryTrackRepository | None = None) -> None:
        self._playlists: dict[str, Playlist] = {}
        self._members: dict[str, list[str]] = {}
        self._tracks = tracks

    def create(self, playlist: Playlist) -> None:
        if any(p.name == playlist.name for p in self._playlists.values()):
            raise DatabaseError(f"Playlist with name '{playlist.name}' already exists")
        self._playlists[playlist.id] = playlist
        self._members.setdefault(playlist.id, [])

    def get_by_id(self, playlist_id: str) -> Playlist:
        playlist = self._playlists.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist_id}")
        return playlist

    def get_by_name(self, name: str) -> Playlist | None:
        for playlist in self._playlists.values():
            if playlist.name == name:
                return playlist
        return None

    def list_all(self) -> list[Playlist]:
        return sorted(self._playlists.values(), key=lambda p: p.name)

    def delete(self, playlist_id: str) -> None:
        if playlist_id not in self._playlists:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist_id}")
        del self._playlists[playlist_id]
        self._members.pop(playlist_id, None)

    def update(self, playlist: Playlist) -> None:
        if playlist.id not in self._playlists:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist.id}")
        self._playlists[playlist.id] = playlist

    def add_track(self, playlist_id: str, track_id: str, position: int) -> None:
        if self._tracks is not None:
            self._tracks.get_by_id(TrackId(value=track_id))  # raises if missing
        members = self._members.setdefault(playlist_id, [])
        if track_id not in members:
            members.insert(min(position, len(members)), track_id)

    def remove_track(self, playlist_id: str, track_id: str) -> None:
        members = self._members.get(playlist_id, [])
        if track_id not in members:
            raise TrackNotFoundError(f"Track {track_id} not in playlist {playlist_id}")
        members.remove(track_id)

    def get_tracks(self, playlist_id: str) -> list[Track]:
        tracks: list[Track] = []
        if self._tracks is None:
            return tracks
        for track_id in self._members.get(playlist_id, []):
            try:
                tracks.append(self._tracks.get_by_id(TrackId(value=track_id)))
            except TrackNotFoundError:
                continue
        return tracks

    def reorder(self, playlist_id: str, track_ids: list[str]) -> None:
        self._members[playlist_id] = list(track_ids)

    def get_playlists_for_track(self, track_id: str) -> list[Playlist]:
        matches = [
            self._playlists[pid]
            for pid, members in self._members.items()
            if track_id in members and pid in self._playlists
        ]
        return sorted(matches, key=lambda p: p.name)


def make_playlist(
    playlist_id: str = "pl-1",
    *,
    name: str = "Test Playlist",
) -> Playlist:
    """Build a Playlist with sensible defaults for server tests."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    return Playlist(id=playlist_id, name=name, created_at=now, updated_at=now)


def make_track(
    track_id: str = "track-1",
    *,
    file_path: Path | None = None,
    title: str = "Test Song",
    artist: str | None = "Test Artist",
    album: str | None = "Test Album",
    duration_seconds: float = 180.0,
    audio_format: str = "mp3",
    bpm: float | None = None,
    key: str | None = None,
    genre: str | None = None,
    mood: str | None = None,
    source_url: str | None = None,
    remix: str | None = None,
    year: int | None = None,
    tags: str | None = None,
) -> Track:
    """Build a Track with sensible defaults for server tests."""
    return Track(
        id=TrackId(value=track_id),
        title=title,
        artist=artist,
        album=album,
        duration_seconds=duration_seconds,
        file_path=file_path if file_path is not None else Path(f"/music/{track_id}.mp3"),
        format=audio_format,
        bpm=bpm,
        key=key,
        genre=genre,
        mood=mood,
        source_url=source_url,
        downloaded_at=None,
        analyzed_at=None,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        remix=remix,
        year=year,
        tags=tags,
    )
