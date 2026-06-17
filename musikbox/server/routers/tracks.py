from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request

from musikbox.domain.models import SearchFilter
from musikbox.server.dtos import TrackDTO

if TYPE_CHECKING:
    from musikbox.server.app import ServerServices


def create_tracks_router(services: ServerServices) -> APIRouter:
    router = APIRouter()

    def _base_url(request: Request) -> str:
        return str(request.base_url).rstrip("/")

    @router.get("/tracks")
    def list_tracks(request: Request, limit: int = 50, offset: int = 0) -> list[TrackDTO]:
        base = _base_url(request)
        tracks = services.library_service.list_tracks(limit=limit, offset=offset)
        return [TrackDTO.from_track(track, base) for track in tracks]

    # Declared before /tracks/{track_id} so "search" is not captured as an id.
    @router.get("/tracks/search")
    def search_tracks(
        request: Request,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        key: str | None = None,
        genre: str | None = None,
        mood: str | None = None,
        artist: str | None = None,
        album: str | None = None,
        title: str | None = None,
        query: str | None = None,
    ) -> list[TrackDTO]:
        search_filter = SearchFilter(
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            key=key,
            genre=genre,
            mood=mood,
            artist=artist,
            album=album,
            title=title,
            query=query,
        )
        base = _base_url(request)
        tracks = services.library_service.search_tracks(search_filter)
        return [TrackDTO.from_track(track, base) for track in tracks]

    @router.get("/tracks/{track_id}")
    def get_track(track_id: str, request: Request) -> TrackDTO:
        track = services.library_service.get_track(track_id)
        return TrackDTO.from_track(track, _base_url(request))

    return router
