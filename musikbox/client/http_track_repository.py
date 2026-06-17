from __future__ import annotations

from datetime import datetime
from pathlib import Path

from musikbox.client.transport import HttpTransport, ensure_ok
from musikbox.domain.exceptions import RemoteServiceError, TrackNotFoundError
from musikbox.domain.models import SearchFilter, Track, TrackId
from musikbox.domain.ports.repository import TrackRepository

_CLIENT_WRITE_MESSAGE = "write operations are not available in client mode"


def _str(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None


def _float(data: dict[str, object], key: str) -> float | None:
    value = data.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _int(data: dict[str, object], key: str) -> int | None:
    value = data.get(key)
    return int(value) if isinstance(value, int) else None


def _dt(data: dict[str, object], key: str) -> datetime | None:
    value = data.get(key)
    return datetime.fromisoformat(value) if isinstance(value, str) else None


def _track_from_json(data: dict[str, object]) -> Track:
    # file_path is a non-filesystem sentinel on the client; playback resolves
    # the stream URL by track id, never from this path.
    created_at = _dt(data, "created_at")
    if created_at is None:
        raise RemoteServiceError("malformed track payload: missing created_at")
    return Track(
        id=TrackId(value=str(data.get("id", ""))),
        title=_str(data, "title") or "",
        artist=_str(data, "artist"),
        album=_str(data, "album"),
        duration_seconds=_float(data, "duration_seconds") or 0.0,
        file_path=Path(_str(data, "stream_url") or ""),
        format=_str(data, "format") or "",
        bpm=_float(data, "bpm"),
        key=_str(data, "key"),
        genre=_str(data, "genre"),
        mood=_str(data, "mood"),
        source_url=_str(data, "source_url"),
        downloaded_at=_dt(data, "downloaded_at"),
        analyzed_at=_dt(data, "analyzed_at"),
        created_at=created_at,
        remix=_str(data, "remix"),
        year=_int(data, "year"),
        tags=_str(data, "tags"),
        enriched_at=_dt(data, "enriched_at"),
    )


class HttpTrackRepository(TrackRepository):
    """TrackRepository backed by a remote musikbox server (read-only)."""

    def __init__(self, transport: HttpTransport) -> None:
        self._http = transport

    def get_by_id(self, track_id: TrackId) -> Track:
        response = self._http.get(f"/tracks/{track_id.value}")
        if response.status_code == 404:
            raise TrackNotFoundError(track_id.value)
        ensure_ok(response)
        return _track_from_json(response.json())

    def search(self, filter: SearchFilter) -> list[Track]:
        params: dict[str, str | int | float | bool | None] = {
            "bpm_min": filter.bpm_min,
            "bpm_max": filter.bpm_max,
            "key": filter.key,
            "genre": filter.genre,
            "mood": filter.mood,
            "artist": filter.artist,
            "album": filter.album,
            "title": filter.title,
            "query": filter.query,
        }
        params = {k: v for k, v in params.items() if v is not None}
        response = ensure_ok(self._http.get("/tracks/search", params=params))
        return [_track_from_json(item) for item in response.json()]

    def list_all(self, limit: int = 50, offset: int = 0) -> list[Track]:
        response = ensure_ok(self._http.get("/tracks", params={"limit": limit, "offset": offset}))
        return [_track_from_json(item) for item in response.json()]

    def get_by_file_path(self, file_path: Path) -> Track | None:
        raise RemoteServiceError(_CLIENT_WRITE_MESSAGE)

    def get_by_source_url(self, source_url: str) -> Track | None:
        raise RemoteServiceError(_CLIENT_WRITE_MESSAGE)

    def save(self, track: Track) -> None:
        raise RemoteServiceError(_CLIENT_WRITE_MESSAGE)

    def delete(self, track_id: TrackId) -> None:
        raise RemoteServiceError(_CLIENT_WRITE_MESSAGE)
