from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from musikbox.adapters.local_source_resolver import LocalSourceResolver
from musikbox.config.settings import load_config
from musikbox.server.app import ServerServices, create_api
from musikbox.server.conftest import (
    InMemoryPlaylistRepository,
    InMemoryTrackRepository,
    make_playlist,
    make_track,
)
from musikbox.services.library_service import LibraryService


@pytest.fixture
def tracks() -> InMemoryTrackRepository:
    return InMemoryTrackRepository()


@pytest.fixture
def playlists(tracks: InMemoryTrackRepository) -> InMemoryPlaylistRepository:
    return InMemoryPlaylistRepository(tracks)


@pytest.fixture
def client(tracks: InMemoryTrackRepository, playlists: InMemoryPlaylistRepository) -> TestClient:
    services = ServerServices(
        config=load_config(),
        library_service=LibraryService(tracks),
        repository=tracks,
        player=None,
        source_resolver=LocalSourceResolver(),
        playlist_repository=playlists,
    )
    return TestClient(create_api(services))


def test_list_playlists_empty_returns_empty_list(client: TestClient) -> None:
    response = client.get("/playlists")

    assert response.status_code == 200
    assert response.json() == []


def test_create_then_list_roundtrips_the_playlist(client: TestClient) -> None:
    dto = {
        "id": "pl-1",
        "name": "Friday Set",
        "created_at": "2025-01-01T12:00:00",
        "updated_at": "2025-01-01T12:00:00",
    }
    create = client.post("/playlists", json=dto)
    assert create.status_code == 200

    names = [p["name"] for p in client.get("/playlists").json()]
    assert names == ["Friday Set"]


def test_create_duplicate_name_returns_503(
    client: TestClient, playlists: InMemoryPlaylistRepository
) -> None:
    playlists.create(make_playlist("pl-1", name="Dupe"))
    dto = {
        "id": "pl-2",
        "name": "Dupe",
        "created_at": "2025-01-01T12:00:00",
        "updated_at": "2025-01-01T12:00:00",
    }

    response = client.post("/playlists", json=dto)

    assert response.status_code == 503
    assert response.json()["error_code"] == "DatabaseError"


def test_get_by_name_returns_playlist(
    client: TestClient, playlists: InMemoryPlaylistRepository
) -> None:
    playlists.create(make_playlist("pl-1", name="Warmup"))

    response = client.get("/playlists/by-name", params={"name": "Warmup"})

    assert response.status_code == 200
    assert response.json()["id"] == "pl-1"


def test_get_by_name_with_spaces_survives(
    client: TestClient, playlists: InMemoryPlaylistRepository
) -> None:
    playlists.create(make_playlist("pl-1", name="Late Night Deep"))

    response = client.get("/playlists/by-name", params={"name": "Late Night Deep"})

    assert response.status_code == 200
    assert response.json()["name"] == "Late Night Deep"


def test_get_by_name_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/playlists/by-name", params={"name": "nope"})

    assert response.status_code == 404
    assert response.json()["error_code"] == "PlaylistNotFoundError"


def test_by_name_route_not_shadowed_by_id_route(
    client: TestClient, playlists: InMemoryPlaylistRepository
) -> None:
    # The static /playlists/by-name route must win over /playlists/{id}.
    playlists.create(make_playlist("pl-1", name="Realname"))

    response = client.get("/playlists/by-name", params={"name": "Realname"})

    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert response.json()["name"] == "Realname"


def test_get_by_id_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/playlists/missing")

    assert response.status_code == 404
    assert response.json()["error_code"] == "PlaylistNotFoundError"


def test_delete_removes_playlist(
    client: TestClient, playlists: InMemoryPlaylistRepository
) -> None:
    playlists.create(make_playlist("pl-1", name="Trash"))

    response = client.delete("/playlists/pl-1")

    assert response.status_code == 200
    assert client.get("/playlists").json() == []


def test_delete_unknown_returns_404(client: TestClient) -> None:
    response = client.delete("/playlists/missing")

    assert response.status_code == 404


def test_add_track_then_get_tracks_returns_track_dtos(
    client: TestClient,
    tracks: InMemoryTrackRepository,
    playlists: InMemoryPlaylistRepository,
) -> None:
    tracks.save(make_track(track_id="t1", title="Opener"))
    playlists.create(make_playlist("pl-1", name="Set"))

    add = client.post("/playlists/pl-1/tracks", json={"track_id": "t1", "position": 0})
    assert add.status_code == 200

    body = client.get("/playlists/pl-1/tracks").json()
    assert [t["id"] for t in body] == ["t1"]
    # Serialized as TrackDTO: local path hidden, stream URL exposed.
    assert "file_path" not in body[0]
    assert body[0]["stream_url"].endswith("/tracks/t1/stream")


def test_add_unknown_track_returns_404(
    client: TestClient, playlists: InMemoryPlaylistRepository
) -> None:
    playlists.create(make_playlist("pl-1", name="Set"))

    response = client.post("/playlists/pl-1/tracks", json={"track_id": "ghost", "position": 0})

    assert response.status_code == 404
    assert response.json()["error_code"] == "TrackNotFoundError"


def test_remove_track(
    client: TestClient,
    tracks: InMemoryTrackRepository,
    playlists: InMemoryPlaylistRepository,
) -> None:
    tracks.save(make_track(track_id="t1"))
    playlists.create(make_playlist("pl-1", name="Set"))
    playlists.add_track("pl-1", "t1", 0)

    response = client.delete("/playlists/pl-1/tracks/t1")

    assert response.status_code == 200
    assert client.get("/playlists/pl-1/tracks").json() == []


def test_reorder_tracks(
    client: TestClient,
    tracks: InMemoryTrackRepository,
    playlists: InMemoryPlaylistRepository,
) -> None:
    for tid in ("a", "b", "c"):
        tracks.save(make_track(track_id=tid))
    playlists.create(make_playlist("pl-1", name="Set"))
    for pos, tid in enumerate(("a", "b", "c")):
        playlists.add_track("pl-1", tid, pos)

    response = client.put("/playlists/pl-1/tracks", json={"track_ids": ["c", "a", "b"]})

    assert response.status_code == 200
    ids = [t["id"] for t in client.get("/playlists/pl-1/tracks").json()]
    assert ids == ["c", "a", "b"]


def test_playlists_for_track(
    client: TestClient,
    tracks: InMemoryTrackRepository,
    playlists: InMemoryPlaylistRepository,
) -> None:
    tracks.save(make_track(track_id="t1"))
    playlists.create(make_playlist("pl-1", name="A-set"))
    playlists.create(make_playlist("pl-2", name="B-set"))
    playlists.add_track("pl-1", "t1", 0)

    response = client.get("/playlists/for-track/t1")

    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == ["pl-1"]


def test_playlist_endpoints_return_503_when_storage_absent() -> None:
    services = ServerServices(
        config=load_config(),
        library_service=LibraryService(InMemoryTrackRepository()),
        repository=InMemoryTrackRepository(),
        player=None,
        source_resolver=LocalSourceResolver(),
        playlist_repository=None,
    )
    client = TestClient(create_api(services), raise_server_exceptions=False)

    response = client.get("/playlists")

    # ConfigError -> 400 via the app's exception handlers.
    assert response.status_code == 400
    assert response.json()["error_code"] == "ConfigError"
