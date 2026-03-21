from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from musikbox.cli.player.app import PlayerApp
from musikbox.domain.models import Track, TrackId
from musikbox.events.types import (
    MoveIndexChanged,
    Shutdown,
    TrackRemovedFromQueue,
)
from musikbox.services.playback_service import PlaybackService


def _make_track(title: str = "Test Track", index: int = 0) -> Track:
    return Track(
        id=TrackId(),
        title=title,
        artist="Test Artist",
        album=None,
        duration_seconds=180.0,
        file_path=Path(f"/tmp/test_{index}.mp3"),
        format="mp3",
        bpm=120.0,
        key="Am",
        genre="Electronic",
        mood=None,
        source_url=None,
        downloaded_at=datetime.now(UTC),
        analyzed_at=None,
        created_at=datetime.now(UTC),
    )


def _make_playback_service() -> PlaybackService:
    player = MagicMock()
    player.is_paused.return_value = False
    player.is_playing.return_value = True
    player.position.return_value = 0.0
    player.duration.return_value = 180.0
    return PlaybackService(player)


def _make_app_obj() -> MagicMock:
    app = MagicMock()
    app.playlist_service = None
    app.library_service._repository = MagicMock()
    return app


def test_player_app_creates_all_components() -> None:
    service = _make_playback_service()
    app = _make_app_obj()
    repository = MagicMock()

    player_app = PlayerApp(
        playback_service=service,
        repository=repository,
        app=app,
    )

    assert player_app.input is not None
    assert player_app.controls is not None
    assert player_app.renderer is not None
    assert player_app.editor is not None
    assert player_app.importer is not None
    assert player_app.browser is not None
    assert player_app.bus is not None


def test_player_app_subscribes_to_shutdown() -> None:
    service = _make_playback_service()
    app = _make_app_obj()
    repository = MagicMock()

    player_app = PlayerApp(
        playback_service=service,
        repository=repository,
        app=app,
    )

    assert not player_app._stopped
    player_app.bus.dispatch(Shutdown())
    assert player_app._stopped


def test_player_app_track_removed_adjusts_queue() -> None:
    service = _make_playback_service()
    tracks = [_make_track(f"Track {i}", i) for i in range(3)]
    service.load_queue(tracks)
    service._index = 2
    app = _make_app_obj()

    player_app = PlayerApp(
        playback_service=service,
        repository=MagicMock(),
        app=app,
    )

    # Remove track before current -- index should shift down
    player_app.bus.dispatch(TrackRemovedFromQueue(index=0))
    assert service._index == 1
    assert len(service._queue) == 2


def test_player_app_move_swaps_queue_entries() -> None:
    service = _make_playback_service()
    tracks = [_make_track(f"Track {i}", i) for i in range(3)]
    service.load_queue(tracks)
    service._index = 0
    app = _make_app_obj()

    player_app = PlayerApp(
        playback_service=service,
        repository=MagicMock(),
        app=app,
    )

    original_first = service._queue[0].title
    original_second = service._queue[1].title

    # Simulate move mode: set initial position, then move down
    player_app.bus.dispatch(MoveIndexChanged(index=0))
    player_app.bus.dispatch(MoveIndexChanged(index=1))

    # Tracks should be swapped
    assert service._queue[0].title == original_second
    assert service._queue[1].title == original_first


def test_player_app_sets_playlist_on_components() -> None:
    service = _make_playback_service()
    app = _make_app_obj()
    app.playlist_service = MagicMock()
    app.playlist_service._playlist_repo = MagicMock()

    player_app = PlayerApp(
        playback_service=service,
        repository=MagicMock(),
        app=app,
        playlist_name="My Playlist",
        playlist_service=app.playlist_service,
    )

    assert player_app.controls.has_playlist is True
    assert player_app.editor.playlist_name == "My Playlist"
    assert player_app.browser.playlist_name == "My Playlist"
    assert player_app.renderer._has_playlist is True
