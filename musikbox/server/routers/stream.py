from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import FileResponse

from musikbox.domain.exceptions import TrackNotFoundError

if TYPE_CHECKING:
    from musikbox.server.app import ServerServices

# Map known audio formats to MIME types for correct client playback.
_MEDIA_TYPES: dict[str, str] = {
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "wma": "audio/x-ms-wma",
}


def create_stream_router(services: ServerServices) -> APIRouter:
    router = APIRouter()

    @router.get("/tracks/{track_id}/stream")
    def stream_track(track_id: str) -> FileResponse:
        # Raises TrackNotFoundError (-> 404) if the id is unknown.
        track = services.library_service.get_track(track_id)
        if not track.file_path.exists():
            raise TrackNotFoundError(f"Audio file missing for track: {track_id}")
        media_type = _MEDIA_TYPES.get(track.format.lower(), "application/octet-stream")
        # FileResponse honors the Range header (206 Partial Content) for seeking.
        return FileResponse(track.file_path, media_type=media_type)

    return router
