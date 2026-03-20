from datetime import datetime
from pathlib import Path

import pytest

from musikbox.adapters.fake_player import FakePlayer
from musikbox.domain.models import Track, TrackId
from musikbox.services.playback_service import PlaybackService


def _make_track(tmp_path: Path, name: str = "song.mp3", **overrides: object) -> Track:
    """Build a Track with sensible defaults and a real temp file."""
    file_path = tmp_path / name
    file_path.touch()
    defaults: dict[str, object] = {
        "id": TrackId(),
        "title": name.removesuffix(".mp3"),
        "artist": "Test Artist",
        "album": None,
        "duration_seconds": 180.0,
        "file_path": file_path,
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
def player() -> FakePlayer:
    return FakePlayer()


@pytest.fixture()
def service(player: FakePlayer) -> PlaybackService:
    return PlaybackService(player=player)


@pytest.fixture()
def three_tracks(tmp_path: Path) -> list[Track]:
    return [
        _make_track(tmp_path, "track1.mp3", title="Track 1"),
        _make_track(tmp_path, "track2.mp3", title="Track 2"),
        _make_track(tmp_path, "track3.mp3", title="Track 3"),
    ]


def test_load_queue_sets_tracks(service: PlaybackService, three_tracks: list[Track]) -> None:
    service.load_queue(three_tracks)

    assert service.queue == three_tracks
    assert service.queue_index == 0


def test_play_starts_first_track(
    service: PlaybackService, player: FakePlayer, three_tracks: list[Track]
) -> None:
    service.load_queue(three_tracks)
    service.play()

    assert player.is_playing() is True
    assert service.is_playing() is True
    assert service.current_track() == three_tracks[0]


def test_next_track_advances_queue(service: PlaybackService, three_tracks: list[Track]) -> None:
    service.load_queue(three_tracks)
    service.play()

    result = service.next_track()

    assert result == three_tracks[1]
    assert service.queue_index == 1
    assert service.current_track() == three_tracks[1]


def test_next_track_at_end_returns_none(
    service: PlaybackService, player: FakePlayer, three_tracks: list[Track]
) -> None:
    service.load_queue(three_tracks)
    service.play()

    service.next_track()  # -> track 2
    service.next_track()  # -> track 3
    result = service.next_track()  # -> end

    assert result is None
    assert player.is_playing() is False


def test_previous_track_goes_back(service: PlaybackService, three_tracks: list[Track]) -> None:
    service.load_queue(three_tracks)
    service.play()
    service.next_track()  # -> track 2

    result = service.previous_track()

    assert result == three_tracks[0]
    assert service.queue_index == 0


def test_previous_track_at_start_stays(
    service: PlaybackService, three_tracks: list[Track]
) -> None:
    service.load_queue(three_tracks)
    service.play()

    result = service.previous_track()

    # At start, previous_track restarts the current track
    assert result == three_tracks[0]
    assert service.queue_index == 0


def test_pause_resume_toggles(
    service: PlaybackService, player: FakePlayer, three_tracks: list[Track]
) -> None:
    service.load_queue(three_tracks)
    service.play()

    service.pause_resume()
    assert service.is_paused() is True
    assert service.is_playing() is False

    service.pause_resume()
    assert service.is_paused() is False
    assert service.is_playing() is True


def test_stop_clears_playback(
    service: PlaybackService, player: FakePlayer, three_tracks: list[Track]
) -> None:
    service.load_queue(three_tracks)
    service.play()

    service.stop()

    assert player.is_playing() is False
    assert service.is_active is False


def test_current_track_returns_active_track(
    service: PlaybackService, three_tracks: list[Track]
) -> None:
    assert service.current_track() is None

    service.load_queue(three_tracks)
    assert service.current_track() == three_tracks[0]

    service.next_track()
    assert service.current_track() == three_tracks[1]


def test_queue_index_tracks_position(service: PlaybackService, three_tracks: list[Track]) -> None:
    service.load_queue(three_tracks)
    assert service.queue_index == 0

    service.play()
    service.next_track()
    assert service.queue_index == 1

    service.next_track()
    assert service.queue_index == 2
