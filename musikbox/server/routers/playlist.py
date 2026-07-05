from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request

from musikbox.domain.exceptions import ConfigError, PlaylistNotFoundError
from musikbox.domain.ports.playlist_repository import PlaylistRepository
from musikbox.server.dtos import (
    AddTrackToPlaylistCommand,
    PlaylistDTO,
    ReorderPlaylistCommand,
    TrackDTO,
)

if TYPE_CHECKING:
    from musikbox.server.app import ServerServices

_OK = {"status": "ok"}


def create_playlist_router(services: ServerServices) -> APIRouter:
    router = APIRouter(prefix="/playlists")

    def _repo() -> PlaylistRepository:
        if services.playlist_repository is None:
            raise ConfigError("playlist storage is not available on this server")
        return services.playlist_repository

    def _base_url(request: Request) -> str:
        return str(request.base_url).rstrip("/")

    @router.get("")
    def list_playlists() -> list[PlaylistDTO]:
        return [PlaylistDTO.from_playlist(p) for p in _repo().list_all()]

    @router.post("")
    def create_playlist(dto: PlaylistDTO) -> PlaylistDTO:
        _repo().create(dto.to_playlist())
        return dto

    # Static segments declared before "/{playlist_id}" so they are not
    # captured as an id (mirrors the tracks router's search-before-id order).
    # ``name`` is a query param, not a path segment, so names with spaces or
    # slashes survive intact.
    @router.get("/by-name")
    def get_by_name(name: str) -> PlaylistDTO:
        playlist = _repo().get_by_name(name)
        if playlist is None:
            raise PlaylistNotFoundError(f"Playlist not found: {name}")
        return PlaylistDTO.from_playlist(playlist)

    @router.get("/for-track/{track_id}")
    def playlists_for_track(track_id: str) -> list[PlaylistDTO]:
        return [PlaylistDTO.from_playlist(p) for p in _repo().get_playlists_for_track(track_id)]

    @router.get("/{playlist_id}")
    def get_by_id(playlist_id: str) -> PlaylistDTO:
        return PlaylistDTO.from_playlist(_repo().get_by_id(playlist_id))

    @router.put("/{playlist_id}")
    def update_playlist(playlist_id: str, dto: PlaylistDTO) -> PlaylistDTO:
        _repo().update(dto.to_playlist())
        return dto

    @router.delete("/{playlist_id}")
    def delete_playlist(playlist_id: str) -> dict[str, str]:
        _repo().delete(playlist_id)
        return _OK

    @router.get("/{playlist_id}/tracks")
    def get_tracks(playlist_id: str, request: Request) -> list[TrackDTO]:
        base = _base_url(request)
        return [TrackDTO.from_track(t, base) for t in _repo().get_tracks(playlist_id)]

    @router.post("/{playlist_id}/tracks")
    def add_track(playlist_id: str, cmd: AddTrackToPlaylistCommand) -> dict[str, str]:
        _repo().add_track(playlist_id, cmd.track_id, cmd.position)
        return _OK

    @router.put("/{playlist_id}/tracks")
    def reorder_tracks(playlist_id: str, cmd: ReorderPlaylistCommand) -> dict[str, str]:
        _repo().reorder(playlist_id, cmd.track_ids)
        return _OK

    @router.delete("/{playlist_id}/tracks/{track_id}")
    def remove_track(playlist_id: str, track_id: str) -> dict[str, str]:
        _repo().remove_track(playlist_id, track_id)
        return _OK

    return router
