from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import httpx
import pytest

from musikbox.client.http_playlist_repository import HttpPlaylistRepository
from musikbox.client.transport import HttpTransport
from musikbox.domain.exceptions import (
    PlaylistNotFoundError,
    RemoteServiceError,
    TrackNotFoundError,
)
from musikbox.domain.models import Playlist
from musikbox.domain.ports.playlist_repository import PlaylistRepository

PlaylistDTO = dict[str, object]


def _playlist_dto(playlist_id: str = "pl-1", name: str = "My Set") -> PlaylistDTO:
    return {
        "id": playlist_id,
        "name": name,
        "created_at": "2025-01-01T12:00:00",
        "updated_at": "2025-01-02T09:30:00",
    }


def _track_dto(track_id: str = "t1") -> dict[str, object]:
    return {
        "id": track_id,
        "title": "Opener",
        "artist": "A",
        "album": None,
        "duration_seconds": 10.0,
        "format": "mp3",
        "bpm": 128.0,
        "key": "Am",
        "genre": "techno",
        "mood": None,
        "source_url": None,
        "remix": None,
        "year": None,
        "tags": None,
        "created_at": "2025-01-01T00:00:00",
        "downloaded_at": None,
        "analyzed_at": None,
        "enriched_at": None,
        "stream_url": "http://testserver/tracks/t1/stream",
    }


def _repo(handler: Callable[[httpx.Request], httpx.Response]) -> HttpPlaylistRepository:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    transport = HttpTransport("http://testserver", client=client)
    return HttpPlaylistRepository(transport)


def _playlist(playlist_id: str = "pl-1", name: str = "My Set") -> Playlist:
    return Playlist(
        id=playlist_id,
        name=name,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        updated_at=datetime(2025, 1, 2, 9, 30, 0),
    )


def test_repository_isinstance_implements_playlist_repository_port() -> None:
    repo = _repo(lambda request: httpx.Response(404))
    assert isinstance(repo, PlaylistRepository)


def test_create_posts_playlist_body() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/playlists"
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(200, json=_playlist_dto())

    repo = _repo(handler)
    repo.create(_playlist())

    assert captured["id"] == "pl-1"
    assert captured["name"] == "My Set"
    assert captured["created_at"] == "2025-01-01T12:00:00"


def test_create_with_error_status_raises_remote_service_error() -> None:
    repo = _repo(lambda request: httpx.Response(503))
    with pytest.raises(RemoteServiceError):
        repo.create(_playlist())


def test_get_by_id_success_parses_playlist() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/playlists/pl-1"
        return httpx.Response(200, json=_playlist_dto())

    playlist = _repo(handler).get_by_id("pl-1")
    assert playlist.id == "pl-1"
    assert playlist.name == "My Set"
    assert playlist.created_at == datetime(2025, 1, 1, 12, 0, 0)
    assert playlist.updated_at == datetime(2025, 1, 2, 9, 30, 0)


def test_get_by_id_404_raises_playlist_not_found() -> None:
    repo = _repo(lambda request: httpx.Response(404))
    with pytest.raises(PlaylistNotFoundError):
        repo.get_by_id("missing")


def test_get_by_id_malformed_payload_raises_remote_service_error() -> None:
    dto = _playlist_dto()
    del dto["created_at"]
    repo = _repo(lambda request: httpx.Response(200, json=dto))
    with pytest.raises(RemoteServiceError):
        repo.get_by_id("pl-1")


def test_get_by_name_sends_name_query_and_parses() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/playlists/by-name"
        captured["name"] = request.url.params.get("name")
        return httpx.Response(200, json=_playlist_dto(name="Warmup"))

    playlist = _repo(handler).get_by_name("Warmup")
    assert captured["name"] == "Warmup"
    assert playlist is not None
    assert playlist.name == "Warmup"


def test_get_by_name_404_returns_none() -> None:
    repo = _repo(lambda request: httpx.Response(404))
    assert repo.get_by_name("nope") is None


def test_list_all_maps_playlists() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/playlists"
        return httpx.Response(200, json=[_playlist_dto("a", "A"), _playlist_dto("b", "B")])

    playlists = _repo(handler).list_all()
    assert [p.id for p in playlists] == ["a", "b"]


def test_list_all_error_raises_remote_service_error() -> None:
    repo = _repo(lambda request: httpx.Response(500))
    with pytest.raises(RemoteServiceError):
        repo.list_all()


def test_delete_sends_delete_and_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/playlists/pl-1"
        return httpx.Response(200, json={"status": "ok"})

    _repo(handler).delete("pl-1")


def test_delete_404_raises_playlist_not_found() -> None:
    repo = _repo(lambda request: httpx.Response(404))
    with pytest.raises(PlaylistNotFoundError):
        repo.delete("missing")


def test_update_puts_playlist_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/playlists/pl-1"
        return httpx.Response(200, json=_playlist_dto())

    _repo(handler).update(_playlist())


def test_update_404_raises_playlist_not_found() -> None:
    repo = _repo(lambda request: httpx.Response(404))
    with pytest.raises(PlaylistNotFoundError):
        repo.update(_playlist())


def test_add_track_posts_body() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/playlists/pl-1/tracks"
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok"})

    _repo(handler).add_track("pl-1", "t1", 3)
    assert captured == {"track_id": "t1", "position": 3}


def test_add_track_404_raises_track_not_found() -> None:
    repo = _repo(lambda request: httpx.Response(404))
    with pytest.raises(TrackNotFoundError):
        repo.add_track("pl-1", "ghost", 0)


def test_remove_track_sends_delete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/playlists/pl-1/tracks/t1"
        return httpx.Response(200, json={"status": "ok"})

    _repo(handler).remove_track("pl-1", "t1")


def test_remove_track_404_raises_track_not_found() -> None:
    repo = _repo(lambda request: httpx.Response(404))
    with pytest.raises(TrackNotFoundError):
        repo.remove_track("pl-1", "missing")


def test_get_tracks_maps_track_dtos() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/playlists/pl-1/tracks"
        return httpx.Response(200, json=[_track_dto("t1"), _track_dto("t2")])

    tracks = _repo(handler).get_tracks("pl-1")
    assert [t.id.value for t in tracks] == ["t1", "t2"]


def test_reorder_puts_track_ids() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/playlists/pl-1/tracks"
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok"})

    _repo(handler).reorder("pl-1", ["c", "a", "b"])
    assert captured == {"track_ids": ["c", "a", "b"]}


def test_get_playlists_for_track_maps_playlists() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/playlists/for-track/t1"
        return httpx.Response(200, json=[_playlist_dto("pl-1", "A")])

    playlists = _repo(handler).get_playlists_for_track("t1")
    assert [p.id for p in playlists] == ["pl-1"]
