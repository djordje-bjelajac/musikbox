from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from musikbox.adapters.local_source_resolver import LocalSourceResolver
from musikbox.config.settings import load_config
from musikbox.server.app import ServerServices, create_api
from musikbox.server.conftest import InMemoryTrackRepository, make_track
from musikbox.services.library_service import LibraryService

_AUDIO_BYTES = bytes(range(256)) * 4  # 1024 deterministic bytes


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


def _save_audio_track(
    repo: InMemoryTrackRepository,
    tmp_path: Path,
    *,
    track_id: str = "audio",
    audio_format: str = "mp3",
    data: bytes = _AUDIO_BYTES,
) -> Path:
    audio_path = tmp_path / f"{track_id}.{audio_format}"
    audio_path.write_bytes(data)
    repo.save(make_track(track_id=track_id, file_path=audio_path, audio_format=audio_format))
    return audio_path


def test_full_stream_returns_200_with_full_bytes(
    client: TestClient, repo: InMemoryTrackRepository, tmp_path: Path
) -> None:
    _save_audio_track(repo, tmp_path)

    response = client.get("/tracks/audio/stream")

    assert response.status_code == 200
    assert response.content == _AUDIO_BYTES


def test_full_stream_advertises_accept_ranges(
    client: TestClient, repo: InMemoryTrackRepository, tmp_path: Path
) -> None:
    _save_audio_track(repo, tmp_path)

    response = client.get("/tracks/audio/stream")

    assert response.headers["accept-ranges"] == "bytes"


def test_range_request_returns_206_partial_content(
    client: TestClient, repo: InMemoryTrackRepository, tmp_path: Path
) -> None:
    _save_audio_track(repo, tmp_path)

    response = client.get("/tracks/audio/stream", headers={"Range": "bytes=0-9"})

    assert response.status_code == 206
    assert len(response.content) == 10
    assert response.content == _AUDIO_BYTES[0:10]


def test_range_request_mid_file_returns_correct_slice(
    client: TestClient, repo: InMemoryTrackRepository, tmp_path: Path
) -> None:
    _save_audio_track(repo, tmp_path)

    response = client.get("/tracks/audio/stream", headers={"Range": "bytes=100-149"})

    assert response.status_code == 206
    assert len(response.content) == 50
    assert response.content == _AUDIO_BYTES[100:150]


def test_range_request_includes_content_range_header(
    client: TestClient, repo: InMemoryTrackRepository, tmp_path: Path
) -> None:
    _save_audio_track(repo, tmp_path)

    response = client.get("/tracks/audio/stream", headers={"Range": "bytes=0-9"})

    assert response.headers["content-range"] == f"bytes 0-9/{len(_AUDIO_BYTES)}"


def test_stream_unknown_id_returns_404(client: TestClient) -> None:
    response = client.get("/tracks/missing/stream")

    assert response.status_code == 404
    assert response.json()["error_code"] == "TrackNotFoundError"


def test_stream_missing_file_returns_404(
    client: TestClient, repo: InMemoryTrackRepository
) -> None:
    repo.save(make_track(track_id="ghost", file_path=Path("/no/such/file.mp3")))

    response = client.get("/tracks/ghost/stream")

    assert response.status_code == 404
    assert response.json()["error_code"] == "TrackNotFoundError"


def test_stream_mp3_uses_audio_mpeg_content_type(
    client: TestClient, repo: InMemoryTrackRepository, tmp_path: Path
) -> None:
    _save_audio_track(repo, tmp_path, track_id="song", audio_format="mp3")

    response = client.get("/tracks/song/stream")

    assert response.headers["content-type"] == "audio/mpeg"


def test_stream_flac_uses_audio_flac_content_type(
    client: TestClient, repo: InMemoryTrackRepository, tmp_path: Path
) -> None:
    _save_audio_track(repo, tmp_path, track_id="lossless", audio_format="flac")

    response = client.get("/tracks/lossless/stream")

    assert response.headers["content-type"] == "audio/flac"


def test_stream_unknown_format_uses_octet_stream_content_type(
    client: TestClient, repo: InMemoryTrackRepository, tmp_path: Path
) -> None:
    _save_audio_track(repo, tmp_path, track_id="weird", audio_format="xyz")

    response = client.get("/tracks/weird/stream")

    assert response.headers["content-type"] == "application/octet-stream"
