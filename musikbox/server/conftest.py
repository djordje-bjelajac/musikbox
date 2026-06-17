from __future__ import annotations

from datetime import datetime
from pathlib import Path

from musikbox.domain.exceptions import TrackNotFoundError
from musikbox.domain.models import SearchFilter, Track, TrackId
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
