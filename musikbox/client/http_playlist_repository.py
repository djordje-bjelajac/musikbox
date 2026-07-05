from __future__ import annotations

from datetime import datetime

from musikbox.client.http_track_repository import _track_from_json
from musikbox.client.transport import HttpTransport, ensure_ok
from musikbox.domain.exceptions import (
    PlaylistNotFoundError,
    RemoteServiceError,
    TrackNotFoundError,
)
from musikbox.domain.models import Playlist, Track
from musikbox.domain.ports.playlist_repository import PlaylistRepository


def _playlist_from_json(data: dict[str, object]) -> Playlist:
    created = data.get("created_at")
    updated = data.get("updated_at")
    if not isinstance(created, str) or not isinstance(updated, str):
        raise RemoteServiceError("malformed playlist payload: missing timestamps")
    return Playlist(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        created_at=datetime.fromisoformat(created),
        updated_at=datetime.fromisoformat(updated),
    )


def _playlist_to_json(playlist: Playlist) -> dict[str, object]:
    return {
        "id": playlist.id,
        "name": playlist.name,
        "created_at": playlist.created_at.isoformat(),
        "updated_at": playlist.updated_at.isoformat(),
    }


class HttpPlaylistRepository(PlaylistRepository):
    """PlaylistRepository backed by a remote musikbox server.

    Mirrors :class:`HttpTrackRepository`: each port method is one HTTP call
    against the server's ``/playlists`` router, translating status codes back
    into the domain exceptions the port contract promises.
    """

    def __init__(self, transport: HttpTransport) -> None:
        self._http = transport

    def create(self, playlist: Playlist) -> None:
        ensure_ok(self._http.post("/playlists", json=_playlist_to_json(playlist)))

    def get_by_id(self, playlist_id: str) -> Playlist:
        response = self._http.get(f"/playlists/{playlist_id}")
        if response.status_code == 404:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist_id}")
        return _playlist_from_json(ensure_ok(response).json())

    def get_by_name(self, name: str) -> Playlist | None:
        response = self._http.get("/playlists/by-name", params={"name": name})
        if response.status_code == 404:
            return None
        return _playlist_from_json(ensure_ok(response).json())

    def list_all(self) -> list[Playlist]:
        response = ensure_ok(self._http.get("/playlists"))
        return [_playlist_from_json(item) for item in response.json()]

    def delete(self, playlist_id: str) -> None:
        response = self._http.delete(f"/playlists/{playlist_id}")
        if response.status_code == 404:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist_id}")
        ensure_ok(response)

    def update(self, playlist: Playlist) -> None:
        response = self._http.put(f"/playlists/{playlist.id}", json=_playlist_to_json(playlist))
        if response.status_code == 404:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist.id}")
        ensure_ok(response)

    def add_track(self, playlist_id: str, track_id: str, position: int) -> None:
        response = self._http.post(
            f"/playlists/{playlist_id}/tracks",
            json={"track_id": track_id, "position": position},
        )
        if response.status_code == 404:
            raise TrackNotFoundError(f"Track not found: {track_id}")
        ensure_ok(response)

    def remove_track(self, playlist_id: str, track_id: str) -> None:
        response = self._http.delete(f"/playlists/{playlist_id}/tracks/{track_id}")
        if response.status_code == 404:
            raise TrackNotFoundError(f"Track {track_id} not in playlist {playlist_id}")
        ensure_ok(response)

    def get_tracks(self, playlist_id: str) -> list[Track]:
        response = ensure_ok(self._http.get(f"/playlists/{playlist_id}/tracks"))
        return [_track_from_json(item) for item in response.json()]

    def reorder(self, playlist_id: str, track_ids: list[str]) -> None:
        ensure_ok(
            self._http.put(f"/playlists/{playlist_id}/tracks", json={"track_ids": track_ids})
        )

    def get_playlists_for_track(self, track_id: str) -> list[Playlist]:
        response = ensure_ok(self._http.get(f"/playlists/for-track/{track_id}"))
        return [_playlist_from_json(item) for item in response.json()]
