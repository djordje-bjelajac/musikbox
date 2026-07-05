from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from musikbox.domain.models import Playlist, Track


class TrackDTO(BaseModel):
    """Network representation of a Track. Omits the server-local file path."""

    id: str
    title: str
    artist: str | None
    album: str | None
    duration_seconds: float
    format: str
    bpm: float | None
    key: str | None
    genre: str | None
    mood: str | None
    source_url: str | None
    remix: str | None
    year: int | None
    tags: str | None
    created_at: datetime
    downloaded_at: datetime | None
    analyzed_at: datetime | None
    enriched_at: datetime | None
    stream_url: str

    @classmethod
    def from_track(cls, track: Track, base_url: str) -> TrackDTO:
        track_id = track.id.value
        return cls(
            id=track_id,
            title=track.title,
            artist=track.artist,
            album=track.album,
            duration_seconds=track.duration_seconds,
            format=track.format,
            bpm=track.bpm,
            key=track.key,
            genre=track.genre,
            mood=track.mood,
            source_url=track.source_url,
            remix=track.remix,
            year=track.year,
            tags=track.tags,
            created_at=track.created_at,
            downloaded_at=track.downloaded_at,
            analyzed_at=track.analyzed_at,
            enriched_at=track.enriched_at,
            stream_url=f"{base_url.rstrip('/')}/tracks/{track_id}/stream",
        )


class PlaylistDTO(BaseModel):
    """Network representation of a Playlist.

    Carries the full identity (id + timestamps) so the domain service keeps
    owning id/timestamp generation on the client, exactly as in local mode —
    the HTTP layer is a transport for the repository, not a second factory.
    """

    id: str
    name: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_playlist(cls, playlist: Playlist) -> PlaylistDTO:
        return cls(
            id=playlist.id,
            name=playlist.name,
            created_at=playlist.created_at,
            updated_at=playlist.updated_at,
        )

    def to_playlist(self) -> Playlist:
        return Playlist(
            id=self.id,
            name=self.name,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class AddTrackToPlaylistCommand(BaseModel):
    track_id: str
    position: int


class ReorderPlaylistCommand(BaseModel):
    track_ids: list[str]


class PlayerStatusDTO(BaseModel):
    position: float
    duration: float
    is_playing: bool
    is_paused: bool


class PlayCommand(BaseModel):
    track_id: str


class SeekCommand(BaseModel):
    seconds: float


class ErrorResponse(BaseModel):
    error_code: str
    message: str
