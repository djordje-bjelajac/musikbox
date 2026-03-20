import csv
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from musikbox.domain.exceptions import TrackNotFoundError
from musikbox.domain.models import SearchFilter, Track, TrackId
from musikbox.domain.ports.repository import TrackRepository
from musikbox.services.library_service import LibraryService


def _make_track(**overrides: object) -> Track:
    """Helper to build a Track with sensible defaults."""
    defaults: dict[str, object] = {
        "id": TrackId(value="test-id"),
        "title": "Test Song",
        "artist": "Test Artist",
        "album": None,
        "duration_seconds": 180.0,
        "file_path": Path("/music/test.mp3"),
        "format": "mp3",
        "bpm": 128.0,
        "key": "Am",
        "genre": "techno",
        "mood": None,
        "source_url": None,
        "downloaded_at": None,
        "analyzed_at": None,
        "created_at": datetime(2025, 1, 1),
    }
    defaults.update(overrides)
    return Track(**defaults)  # type: ignore[arg-type]


@pytest.fixture()
def mock_repo() -> MagicMock:
    return MagicMock(spec=TrackRepository)


@pytest.fixture()
def service(mock_repo: MagicMock) -> LibraryService:
    return LibraryService(repository=mock_repo)


def test_list_tracks_delegates_to_repository(
    service: LibraryService, mock_repo: MagicMock
) -> None:
    tracks = [_make_track()]
    mock_repo.list_all.return_value = tracks

    result = service.list_tracks(limit=10, offset=5)

    mock_repo.list_all.assert_called_once_with(limit=10, offset=5)
    assert result == tracks


def test_get_track_returns_track(service: LibraryService, mock_repo: MagicMock) -> None:
    track = _make_track()
    mock_repo.get_by_id.return_value = track

    result = service.get_track("test-id")

    mock_repo.get_by_id.assert_called_once()
    call_arg = mock_repo.get_by_id.call_args[0][0]
    assert isinstance(call_arg, TrackId)
    assert call_arg.value == "test-id"
    assert result == track


def test_get_track_raises_not_found_when_missing(
    service: LibraryService, mock_repo: MagicMock
) -> None:
    mock_repo.get_by_id.side_effect = TrackNotFoundError("Track not found: missing-id")

    with pytest.raises(TrackNotFoundError):
        service.get_track("missing-id")


def test_search_tracks_passes_filter(service: LibraryService, mock_repo: MagicMock) -> None:
    tracks = [_make_track()]
    mock_repo.search.return_value = tracks
    search_filter = SearchFilter(bpm_min=120.0, genre="techno")

    result = service.search_tracks(search_filter)

    mock_repo.search.assert_called_once_with(search_filter)
    assert result == tracks


def test_delete_track_delegates_to_repository(
    service: LibraryService, mock_repo: MagicMock
) -> None:
    service.delete_track("test-id")

    mock_repo.delete.assert_called_once()
    call_arg = mock_repo.delete.call_args[0][0]
    assert isinstance(call_arg, TrackId)
    assert call_arg.value == "test-id"


def test_export_csv_writes_track_data(
    service: LibraryService, mock_repo: MagicMock, tmp_path: Path
) -> None:
    track = _make_track(
        id=TrackId(value="csv-id"),
        title="CSV Song",
        artist="CSV Artist",
        bpm=140.0,
        key="Cm",
        genre="house",
    )
    mock_repo.list_all.return_value = [track]

    output_path = tmp_path / "export.csv"
    service.export_csv(output_path)

    mock_repo.list_all.assert_called_once_with(limit=10_000, offset=0)

    with open(output_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "csv-id"
    assert row["title"] == "CSV Song"
    assert row["artist"] == "CSV Artist"
    assert row["bpm"] == "140.0"
    assert row["key"] == "Cm"
    assert row["genre"] == "house"
