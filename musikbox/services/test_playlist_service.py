from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from musikbox.domain.exceptions import PlaylistNotFoundError
from musikbox.domain.models import Playlist, Track, TrackId
from musikbox.domain.ports.playlist_repository import PlaylistRepository
from musikbox.domain.ports.repository import TrackRepository
from musikbox.services.download_service import DownloadService
from musikbox.services.playlist_service import PlaylistService


def _make_track(track_id: str = "track-1", title: str = "Test Song") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title=title,
        artist="Test Artist",
        album=None,
        duration_seconds=180.0,
        file_path=Path(f"/music/{track_id}.mp3"),
        format="mp3",
        bpm=128.0,
        key="Am",
        genre="techno",
        mood="energetic",
        source_url=None,
        downloaded_at=None,
        analyzed_at=None,
        created_at=datetime(2025, 6, 1),
    )


def _make_playlist(playlist_id: str = "pl-1", name: str = "My Playlist") -> Playlist:
    now = datetime(2025, 6, 1, 12, 0, 0)
    return Playlist(id=playlist_id, name=name, created_at=now, updated_at=now)


def _make_service(
    playlist_repo: PlaylistRepository | None = None,
    track_repo: TrackRepository | None = None,
    download_service: DownloadService | None = None,
) -> PlaylistService:
    return PlaylistService(
        playlist_repository=playlist_repo or MagicMock(spec=PlaylistRepository),
        track_repository=track_repo or MagicMock(spec=TrackRepository),
        download_service=download_service or MagicMock(spec=DownloadService),
    )


def test_create_playlist_saves_to_repository() -> None:
    mock_repo = MagicMock(spec=PlaylistRepository)
    service = _make_service(playlist_repo=mock_repo)

    result = service.create_playlist("Friday Set")

    mock_repo.create.assert_called_once()
    saved = mock_repo.create.call_args[0][0]
    assert saved.name == "Friday Set"
    assert result.name == "Friday Set"
    assert result.id  # UUID was generated


def test_create_from_tracks_adds_all_tracks() -> None:
    mock_repo = MagicMock(spec=PlaylistRepository)
    service = _make_service(playlist_repo=mock_repo)

    tracks = [_make_track(f"t-{i}") for i in range(3)]
    result = service.create_from_tracks("My Mix", tracks)

    assert result.name == "My Mix"
    # create is called once for the playlist itself
    mock_repo.create.assert_called_once()
    # add_track is called for each track with correct positions
    assert mock_repo.add_track.call_count == 3
    for i in range(3):
        args = mock_repo.add_track.call_args_list[i]
        assert args == call(result.id, f"t-{i}", i)


def test_list_playlists_delegates_to_repository() -> None:
    mock_repo = MagicMock(spec=PlaylistRepository)
    playlists = [_make_playlist("pl-1", "A"), _make_playlist("pl-2", "B")]
    mock_repo.list_all.return_value = playlists
    service = _make_service(playlist_repo=mock_repo)

    result = service.list_playlists()

    mock_repo.list_all.assert_called_once()
    assert result == playlists


def test_get_playlist_tracks_by_name() -> None:
    mock_repo = MagicMock(spec=PlaylistRepository)
    playlist = _make_playlist()
    tracks = [_make_track("t-1"), _make_track("t-2")]
    mock_repo.get_by_name.return_value = playlist
    mock_repo.get_tracks.return_value = tracks
    service = _make_service(playlist_repo=mock_repo)

    result = service.get_playlist_tracks("My Playlist")

    mock_repo.get_by_name.assert_called_once_with("My Playlist")
    mock_repo.get_tracks.assert_called_once_with("pl-1")
    assert result == tracks


def test_get_playlist_tracks_not_found_raises() -> None:
    mock_repo = MagicMock(spec=PlaylistRepository)
    mock_repo.get_by_name.return_value = None
    service = _make_service(playlist_repo=mock_repo)

    with pytest.raises(PlaylistNotFoundError):
        service.get_playlist_tracks("Nonexistent")


def test_add_track_to_playlist() -> None:
    mock_repo = MagicMock(spec=PlaylistRepository)
    playlist = _make_playlist()
    mock_repo.get_by_name.return_value = playlist
    mock_repo.get_tracks.return_value = [_make_track("existing")]
    service = _make_service(playlist_repo=mock_repo)

    service.add_track("My Playlist", "new-track")

    # Position should be 1 (after the existing track at position 0)
    mock_repo.add_track.assert_called_once_with("pl-1", "new-track", 1)


def test_remove_track_from_playlist() -> None:
    mock_repo = MagicMock(spec=PlaylistRepository)
    playlist = _make_playlist()
    mock_repo.get_by_name.return_value = playlist
    service = _make_service(playlist_repo=mock_repo)

    service.remove_track("My Playlist", "track-1")

    mock_repo.remove_track.assert_called_once_with("pl-1", "track-1")


def test_delete_playlist() -> None:
    mock_repo = MagicMock(spec=PlaylistRepository)
    playlist = _make_playlist()
    mock_repo.get_by_name.return_value = playlist
    service = _make_service(playlist_repo=mock_repo)

    service.delete_playlist("My Playlist")

    mock_repo.delete.assert_called_once_with("pl-1")


def test_delete_playlist_not_found_raises() -> None:
    mock_repo = MagicMock(spec=PlaylistRepository)
    mock_repo.get_by_name.return_value = None
    service = _make_service(playlist_repo=mock_repo)

    with pytest.raises(PlaylistNotFoundError):
        service.delete_playlist("Nonexistent")
