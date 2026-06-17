from __future__ import annotations

import pytest
from fastapi import FastAPI
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
def services(repo: InMemoryTrackRepository) -> ServerServices:
    return ServerServices(
        config=load_config(),
        library_service=LibraryService(repo),
        repository=repo,
        player=None,
        source_resolver=LocalSourceResolver(),
    )


@pytest.fixture
def client(services: ServerServices) -> TestClient:
    return TestClient(create_api(services))


def test_create_api_returns_fastapi_app(services: ServerServices) -> None:
    api = create_api(services)

    assert isinstance(api, FastAPI)


def test_create_api_includes_track_routes(client: TestClient) -> None:
    # Routers are wired in: each known path resolves rather than 404-ing on
    # an unknown route (a genuinely unknown path returns FastAPI's 404 detail).
    assert client.get("/tracks").status_code == 200
    assert client.get("/player/status").status_code == 503  # player is None
    assert client.get("/totally-unknown-path").status_code == 404


def test_track_not_found_returns_404(client: TestClient) -> None:
    response = client.get("/tracks/does-not-exist")

    assert response.status_code == 404


def test_track_not_found_uses_error_code_envelope(client: TestClient) -> None:
    response = client.get("/tracks/does-not-exist")

    body = response.json()
    assert body["error_code"] == "TrackNotFoundError"
    assert "does-not-exist" in body["message"]


def test_error_response_envelope_shape(client: TestClient) -> None:
    response = client.get("/tracks/missing")

    body = response.json()
    assert set(body.keys()) == {"error_code", "message"}


def test_known_track_returns_200(client: TestClient, repo: InMemoryTrackRepository) -> None:
    repo.save(make_track(track_id="known"))

    response = client.get("/tracks/known")

    assert response.status_code == 200
    assert response.json()["id"] == "known"
