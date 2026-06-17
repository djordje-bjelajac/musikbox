from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from musikbox.adapters.fake_player import FakePlayer
from musikbox.adapters.local_source_resolver import LocalSourceResolver
from musikbox.config.settings import load_config
from musikbox.domain.ports.player import Player
from musikbox.server.app import ServerServices, create_api
from musikbox.server.conftest import InMemoryTrackRepository, make_track
from musikbox.services.library_service import LibraryService


def _make_client(repo: InMemoryTrackRepository, player: Player | None) -> TestClient:
    services = ServerServices(
        config=load_config(),
        library_service=LibraryService(repo),
        repository=repo,
        player=player,
        source_resolver=LocalSourceResolver(),
    )
    return TestClient(create_api(services))


@pytest.fixture
def repo() -> InMemoryTrackRepository:
    return InMemoryTrackRepository()


@pytest.fixture
def player() -> FakePlayer:
    return FakePlayer()


@pytest.fixture
def client_with_player(repo: InMemoryTrackRepository, player: FakePlayer) -> TestClient:
    return _make_client(repo, player)


@pytest.fixture
def client_without_player(repo: InMemoryTrackRepository) -> TestClient:
    return _make_client(repo, None)


# --- With a FakePlayer ------------------------------------------------------


def test_play_returns_200_and_starts_player(
    client_with_player: TestClient,
    repo: InMemoryTrackRepository,
    player: FakePlayer,
) -> None:
    repo.save(make_track(track_id="t1", file_path=Path("/music/t1.mp3")))

    response = client_with_player.post("/player/play", json={"track_id": "t1"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert player.is_playing() is True


def test_play_unknown_track_returns_404(
    client_with_player: TestClient,
) -> None:
    response = client_with_player.post("/player/play", json={"track_id": "nope"})

    assert response.status_code == 404
    assert response.json()["error_code"] == "TrackNotFoundError"


def test_pause_returns_200_and_pauses_player(
    client_with_player: TestClient,
    repo: InMemoryTrackRepository,
    player: FakePlayer,
) -> None:
    repo.save(make_track(track_id="t1"))
    client_with_player.post("/player/play", json={"track_id": "t1"})

    response = client_with_player.post("/player/pause")

    assert response.status_code == 200
    assert player.is_paused() is True


def test_resume_returns_200_and_resumes_player(
    client_with_player: TestClient,
    repo: InMemoryTrackRepository,
    player: FakePlayer,
) -> None:
    repo.save(make_track(track_id="t1"))
    client_with_player.post("/player/play", json={"track_id": "t1"})
    client_with_player.post("/player/pause")

    response = client_with_player.post("/player/resume")

    assert response.status_code == 200
    assert player.is_paused() is False


def test_stop_returns_200_and_stops_player(
    client_with_player: TestClient,
    repo: InMemoryTrackRepository,
    player: FakePlayer,
) -> None:
    repo.save(make_track(track_id="t1"))
    client_with_player.post("/player/play", json={"track_id": "t1"})

    response = client_with_player.post("/player/stop")

    assert response.status_code == 200
    assert player.is_playing() is False


def test_seek_returns_200_and_moves_position(
    client_with_player: TestClient,
    repo: InMemoryTrackRepository,
    player: FakePlayer,
) -> None:
    repo.save(make_track(track_id="t1"))
    client_with_player.post("/player/play", json={"track_id": "t1"})

    response = client_with_player.post("/player/seek", json={"seconds": 30.0})

    assert response.status_code == 200
    assert player.position() == 30.0


def test_status_returns_player_state(
    client_with_player: TestClient,
    repo: InMemoryTrackRepository,
) -> None:
    repo.save(make_track(track_id="t1"))
    client_with_player.post("/player/play", json={"track_id": "t1"})

    response = client_with_player.get("/player/status")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "position": 0.0,
        "duration": 180.0,
        "is_playing": True,
        "is_paused": False,
    }


def test_status_reflects_paused_state(
    client_with_player: TestClient,
    repo: InMemoryTrackRepository,
) -> None:
    repo.save(make_track(track_id="t1"))
    client_with_player.post("/player/play", json={"track_id": "t1"})
    client_with_player.post("/player/pause")

    body = client_with_player.get("/player/status").json()

    assert body["is_playing"] is False
    assert body["is_paused"] is True


# --- Without a player (player=None) -----------------------------------------


def test_play_without_player_returns_503(
    client_without_player: TestClient,
) -> None:
    response = client_without_player.post("/player/play", json={"track_id": "t1"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "PlaybackUnavailableError"


def test_pause_without_player_returns_503(
    client_without_player: TestClient,
) -> None:
    response = client_without_player.post("/player/pause")

    assert response.status_code == 503
    assert response.json()["error_code"] == "PlaybackUnavailableError"


def test_resume_without_player_returns_503(
    client_without_player: TestClient,
) -> None:
    response = client_without_player.post("/player/resume")

    assert response.status_code == 503
    assert response.json()["error_code"] == "PlaybackUnavailableError"


def test_stop_without_player_returns_503(
    client_without_player: TestClient,
) -> None:
    response = client_without_player.post("/player/stop")

    assert response.status_code == 503
    assert response.json()["error_code"] == "PlaybackUnavailableError"


def test_seek_without_player_returns_503(
    client_without_player: TestClient,
) -> None:
    response = client_without_player.post("/player/seek", json={"seconds": 5.0})

    assert response.status_code == 503
    assert response.json()["error_code"] == "PlaybackUnavailableError"


def test_status_without_player_returns_503(
    client_without_player: TestClient,
) -> None:
    response = client_without_player.get("/player/status")

    assert response.status_code == 503
    assert response.json()["error_code"] == "PlaybackUnavailableError"
