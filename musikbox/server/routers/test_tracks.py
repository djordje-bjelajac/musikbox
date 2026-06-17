from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from musikbox.adapters.local_source_resolver import LocalSourceResolver
from musikbox.config.settings import load_config
from musikbox.server.app import ServerServices, create_api
from musikbox.server.conftest import InMemoryTrackRepository, make_track
from musikbox.services.library_service import LibraryService


@pytest.fixture
def repo() -> InMemoryTrackRepository:
    return InMemoryTrackRepository()


@pytest.fixture
def client(repo: InMemoryTrackRepository) -> TestClient:
    services = ServerServices(
        config=load_config(),
        library_service=LibraryService(repo),
        repository=repo,
        player=None,
        source_resolver=LocalSourceResolver(),
    )
    return TestClient(create_api(services))


def test_list_tracks_empty_returns_empty_list(client: TestClient) -> None:
    response = client.get("/tracks")

    assert response.status_code == 200
    assert response.json() == []


def test_list_tracks_returns_all_tracks(client: TestClient, repo: InMemoryTrackRepository) -> None:
    repo.save(make_track(track_id="a"))
    repo.save(make_track(track_id="b"))

    response = client.get("/tracks")

    ids = [track["id"] for track in response.json()]
    assert ids == ["a", "b"]


def test_list_tracks_honors_limit(client: TestClient, repo: InMemoryTrackRepository) -> None:
    repo.save(make_track(track_id="a"))
    repo.save(make_track(track_id="b"))
    repo.save(make_track(track_id="c"))

    response = client.get("/tracks", params={"limit": 2})

    ids = [track["id"] for track in response.json()]
    assert ids == ["a", "b"]


def test_list_tracks_honors_offset(client: TestClient, repo: InMemoryTrackRepository) -> None:
    repo.save(make_track(track_id="a"))
    repo.save(make_track(track_id="b"))
    repo.save(make_track(track_id="c"))

    response = client.get("/tracks", params={"offset": 1})

    ids = [track["id"] for track in response.json()]
    assert ids == ["b", "c"]


def test_list_tracks_omits_file_path_and_includes_stream_url(
    client: TestClient, repo: InMemoryTrackRepository
) -> None:
    repo.save(make_track(track_id="a"))

    payload = client.get("/tracks").json()[0]

    assert "file_path" not in payload
    assert payload["stream_url"].endswith("/tracks/a/stream")


def test_get_track_by_id_returns_track(client: TestClient, repo: InMemoryTrackRepository) -> None:
    repo.save(make_track(track_id="abc", title="Found Me"))

    response = client.get("/tracks/abc")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "abc"
    assert body["title"] == "Found Me"


def test_get_track_unknown_id_returns_404(client: TestClient) -> None:
    response = client.get("/tracks/nope")

    assert response.status_code == 404
    assert response.json()["error_code"] == "TrackNotFoundError"


def test_get_track_omits_file_path_and_includes_stream_url(
    client: TestClient, repo: InMemoryTrackRepository
) -> None:
    repo.save(make_track(track_id="abc"))

    payload = client.get("/tracks/abc").json()

    assert "file_path" not in payload
    assert payload["stream_url"].endswith("/tracks/abc/stream")


def test_search_by_genre_returns_matching_tracks(
    client: TestClient, repo: InMemoryTrackRepository
) -> None:
    repo.save(make_track(track_id="house", genre="House"))
    repo.save(make_track(track_id="techno", genre="Techno"))

    response = client.get("/tracks/search", params={"genre": "House"})

    ids = [track["id"] for track in response.json()]
    assert ids == ["house"]


def test_search_by_bpm_range_returns_matching_tracks(
    client: TestClient, repo: InMemoryTrackRepository
) -> None:
    repo.save(make_track(track_id="slow", bpm=90.0))
    repo.save(make_track(track_id="mid", bpm=125.0))
    repo.save(make_track(track_id="fast", bpm=160.0))

    response = client.get("/tracks/search", params={"bpm_min": 120, "bpm_max": 130})

    ids = [track["id"] for track in response.json()]
    assert ids == ["mid"]


def test_search_results_omit_file_path(client: TestClient, repo: InMemoryTrackRepository) -> None:
    repo.save(make_track(track_id="house", genre="House"))

    payload = client.get("/tracks/search", params={"genre": "House"}).json()[0]

    assert "file_path" not in payload
    assert payload["stream_url"].endswith("/tracks/house/stream")


def test_search_route_not_shadowed_by_track_id_route(
    client: TestClient, repo: InMemoryTrackRepository
) -> None:
    # No track with id "search" exists; the /tracks/search route must win.
    repo.save(make_track(track_id="house", genre="House"))

    response = client.get("/tracks/search", params={"genre": "House"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert [track["id"] for track in body] == ["house"]


def test_search_with_no_filters_returns_all_tracks(
    client: TestClient, repo: InMemoryTrackRepository
) -> None:
    repo.save(make_track(track_id="a"))
    repo.save(make_track(track_id="b"))

    response = client.get("/tracks/search")

    ids = sorted(track["id"] for track in response.json())
    assert ids == ["a", "b"]
