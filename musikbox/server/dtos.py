from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from musikbox.domain.models import Track


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
