from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from musikbox.client.http_track_repository import HttpTrackRepository
from musikbox.client.transport import HttpTransport
from musikbox.domain.exceptions import RemoteServiceError, TrackNotFoundError
from musikbox.domain.models import SearchFilter, Track, TrackId
from musikbox.domain.ports.repository import TrackRepository

TrackDTO = dict[str, object]


def _track_dto() -> TrackDTO:
    return {
        "id": "track-1",
        "title": "Smoke",
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
        "stream_url": "http://testserver/tracks/track-1/stream",
    }


def _repo(handler: Callable[[httpx.Request], httpx.Response]) -> HttpTrackRepository:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    transport = HttpTransport("http://testserver", client=client)
    return HttpTrackRepository(transport)


def test_repository_isinstance_implements_track_repository_port() -> None:
    repo = _repo(lambda request: httpx.Response(404))
    assert isinstance(repo, TrackRepository)


def test_get_by_id_success_maps_all_scalar_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/tracks/track-1"
        return httpx.Response(200, json=_track_dto())

    repo = _repo(handler)
    track = repo.get_by_id(TrackId(value="track-1"))

    assert track.id.value == "track-1"
    assert track.title == "Smoke"
    assert track.artist == "A"
    assert track.album is None
    assert track.duration_seconds == 10.0
    assert track.format == "mp3"
    assert track.bpm == 128.0
    assert track.key == "Am"
    assert track.genre == "techno"
    assert track.mood is None
    assert track.source_url is None
    assert track.remix is None
    assert track.year is None
    assert track.tags is None


def test_get_by_id_success_maps_created_at_datetime() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_track_dto())

    repo = _repo(handler)
    track = repo.get_by_id(TrackId(value="track-1"))
    assert track.created_at == datetime(2025, 1, 1, 0, 0, 0)


def test_get_by_id_success_maps_null_optional_datetimes_to_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_track_dto())

    repo = _repo(handler)
    track = repo.get_by_id(TrackId(value="track-1"))
    assert track.downloaded_at is None
    assert track.analyzed_at is None
    assert track.enriched_at is None


def test_get_by_id_success_parses_present_optional_datetimes() -> None:
    dto = _track_dto()
    dto["downloaded_at"] = "2025-02-02T10:30:00"
    dto["analyzed_at"] = "2025-03-03T11:45:00"
    dto["enriched_at"] = "2025-04-04T12:00:00"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=dto)

    repo = _repo(handler)
    track = repo.get_by_id(TrackId(value="track-1"))
    assert track.downloaded_at == datetime(2025, 2, 2, 10, 30, 0)
    assert track.analyzed_at == datetime(2025, 3, 3, 11, 45, 0)
    assert track.enriched_at == datetime(2025, 4, 4, 12, 0, 0)


def test_get_by_id_success_derives_file_path_from_stream_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_track_dto())

    repo = _repo(handler)
    track = repo.get_by_id(TrackId(value="track-1"))
    assert track.file_path == Path("http://testserver/tracks/track-1/stream")


def test_get_by_id_when_missing_created_at_raises_remote_service_error() -> None:
    dto = _track_dto()
    del dto["created_at"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=dto)

    repo = _repo(handler)
    with pytest.raises(RemoteServiceError):
        repo.get_by_id(TrackId(value="track-1"))


def test_get_by_id_with_404_raises_track_not_found_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error_code": "TrackNotFoundError", "message": "nope"})

    repo = _repo(handler)
    with pytest.raises(TrackNotFoundError):
        repo.get_by_id(TrackId(value="missing"))


def test_get_by_id_with_500_raises_remote_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    repo = _repo(handler)
    with pytest.raises(RemoteServiceError):
        repo.get_by_id(TrackId(value="track-1"))


def test_list_all_sends_limit_and_offset_params() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tracks"
        captured["limit"] = request.url.params.get("limit")
        captured["offset"] = request.url.params.get("offset")
        return httpx.Response(200, json=[])

    repo = _repo(handler)
    repo.list_all(limit=25, offset=50)
    assert captured == {"limit": "25", "offset": "50"}


def test_list_all_maps_list_of_tracks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_track_dto(), _track_dto()])

    repo = _repo(handler)
    tracks = repo.list_all()
    assert len(tracks) == 2
    assert all(track.id.value == "track-1" for track in tracks)


def test_list_all_with_empty_result_returns_empty_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    repo = _repo(handler)
    assert repo.list_all() == []


def test_list_all_with_error_status_raises_remote_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    repo = _repo(handler)
    with pytest.raises(RemoteServiceError):
        repo.list_all()


def test_search_sends_only_non_none_filter_params() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tracks/search"
        for key in (
            "bpm_min",
            "bpm_max",
            "key",
            "genre",
            "mood",
            "artist",
            "album",
            "title",
            "query",
        ):
            captured[key] = request.url.params.get(key)
        return httpx.Response(200, json=[])

    repo = _repo(handler)
    repo.search(SearchFilter(bpm_min=120.0, genre="techno"))

    assert captured["bpm_min"] == "120.0"
    assert captured["genre"] == "techno"
    # Every None-valued filter field must be absent from the query string.
    assert captured["bpm_max"] is None
    assert captured["key"] is None
    assert captured["mood"] is None
    assert captured["artist"] is None
    assert captured["album"] is None
    assert captured["title"] is None
    assert captured["query"] is None


def test_search_with_no_filters_sends_no_params() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    repo = _repo(handler)
    repo.search(SearchFilter())
    assert captured == {}


def test_search_maps_list_of_tracks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_track_dto()])

    repo = _repo(handler)
    tracks = repo.search(SearchFilter(genre="techno"))
    assert len(tracks) == 1
    assert tracks[0].genre == "techno"


def test_search_with_error_status_raises_remote_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    repo = _repo(handler)
    with pytest.raises(RemoteServiceError):
        repo.search(SearchFilter(genre="techno"))


def test_save_raises_remote_service_error() -> None:
    repo = _repo(lambda request: httpx.Response(200))
    with pytest.raises(RemoteServiceError):
        repo.save(_build_track())


def test_delete_raises_remote_service_error() -> None:
    repo = _repo(lambda request: httpx.Response(200))
    with pytest.raises(RemoteServiceError):
        repo.delete(TrackId(value="track-1"))


def test_get_by_file_path_raises_remote_service_error() -> None:
    repo = _repo(lambda request: httpx.Response(200))
    with pytest.raises(RemoteServiceError):
        repo.get_by_file_path(Path("/music/x.mp3"))


def test_get_by_source_url_raises_remote_service_error() -> None:
    repo = _repo(lambda request: httpx.Response(200))
    with pytest.raises(RemoteServiceError):
        repo.get_by_source_url("http://example.com/track")


def _build_track() -> Track:
    return Track(
        id=TrackId(value="track-1"),
        title="Smoke",
        artist="A",
        album=None,
        duration_seconds=10.0,
        file_path=Path("/music/x.mp3"),
        format="mp3",
        bpm=128.0,
        key="Am",
        genre="techno",
        mood=None,
        source_url=None,
        downloaded_at=None,
        analyzed_at=None,
        created_at=datetime(2025, 1, 1),
    )
