from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from rich.panel import Panel

from musikbox.cli.player.renderer import Renderer, _to_camelot_str
from musikbox.domain.models import Track, TrackId
from musikbox.events.bus import EventBus
from musikbox.events.types import (
    BrowseIndexChanged,
    ImportCompleted,
    ImportFailed,
    ImportStarted,
    ImportTrackDownloaded,
    MoveIndexChanged,
    PlaybackPaused,
    PlaybackResumed,
    QueueReordered,
    Tick,
    TrackAddedToQueue,
    TrackRemovedFromQueue,
    TrackStarted,
    UIRefreshRequested,
)
from musikbox.services.playback_service import PlaybackService


def _make_track(
    title: str = "Test Track",
    artist: str | None = "Test Artist",
    album: str | None = "Test Album",
    bpm: float | None = 128.0,
    key: str | None = "Am",
    genre: str | None = "Techno",
) -> Track:
    return Track(
        id=TrackId(),
        title=title,
        artist=artist,
        album=album,
        duration_seconds=240.0,
        file_path=Path("/tmp/test.mp3"),
        format="mp3",
        bpm=bpm,
        key=key,
        genre=genre,
        mood=None,
        source_url=None,
        downloaded_at=None,
        analyzed_at=None,
        created_at=datetime.now(),
    )


def _make_service_with_track() -> PlaybackService:
    """Create a PlaybackService with a mock Player and a loaded track."""
    player = MagicMock()
    player.is_paused.return_value = False
    player.is_playing.return_value = True
    player.position.return_value = 60.0
    player.duration.return_value = 240.0
    service = PlaybackService(player)
    service.load_queue([_make_track()])
    return service


def test_renderer_subscribes_to_events() -> None:
    bus = EventBus()
    player = MagicMock()
    service = PlaybackService(player)

    Renderer(bus, service)

    expected_types = [
        Tick,
        TrackStarted,
        BrowseIndexChanged,
        MoveIndexChanged,
        ImportStarted,
        ImportTrackDownloaded,
        ImportCompleted,
        ImportFailed,
        UIRefreshRequested,
        PlaybackPaused,
        PlaybackResumed,
        QueueReordered,
        TrackAddedToQueue,
        TrackRemovedFromQueue,
    ]
    for event_type in expected_types:
        assert event_type in bus._handlers, f"Missing subscription for {event_type.__name__}"
        assert len(bus._handlers[event_type]) > 0


def test_build_panel_with_track() -> None:
    bus = EventBus()
    service = _make_service_with_track()

    renderer = Renderer(bus, service)
    panel = renderer._build_panel()

    assert isinstance(panel, Panel)
    assert panel.title is not None


def test_build_panel_no_track() -> None:
    bus = EventBus()
    player = MagicMock()
    service = PlaybackService(player)

    renderer = Renderer(bus, service)
    panel = renderer._build_panel()

    assert isinstance(panel, Panel)


def test_to_camelot_str_known_key() -> None:
    assert _to_camelot_str("Am") == "8A"
    assert _to_camelot_str("C") == "8B"
    assert _to_camelot_str("F#m") == "11A"


def test_to_camelot_str_none() -> None:
    assert _to_camelot_str(None) == "-"


def test_to_camelot_str_unknown() -> None:
    assert _to_camelot_str("Xm") == "-"


def test_browse_index_updates_on_event() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    renderer._on_browse_changed(BrowseIndexChanged(index=3))
    assert renderer._browse_index == 3

    renderer._on_browse_changed(BrowseIndexChanged(index=None))
    assert renderer._browse_index is None


def test_move_index_updates_on_event() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    renderer._on_move_changed(MoveIndexChanged(index=2))
    assert renderer._move_index == 2


def test_track_started_resets_browse_and_move() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    renderer._browse_index = 5
    renderer._move_index = 3
    renderer._on_track_started(TrackStarted(track=_make_track(), index=0))

    assert renderer._browse_index is None
    assert renderer._move_index is None


def test_import_started_sets_state() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    renderer._on_import_started(ImportStarted(playlist_name="My Playlist"))
    assert renderer._import_active is True
    assert renderer._import_name == "My Playlist"
    assert renderer._import_count == 0


def test_import_track_updates_count() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    track = _make_track(title="Downloaded Track")
    renderer._on_import_track(ImportTrackDownloaded(track=track, count=5))
    assert renderer._import_count == 5
    assert renderer._import_last_track == "Downloaded Track"


def test_import_completed_sets_done() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    renderer._import_active = True
    renderer._on_import_completed(ImportCompleted(playlist_name="PL", count=10))
    assert renderer._import_active is False
    assert renderer._import_done is True
    assert renderer._import_count == 10
    assert renderer._import_error is None


def test_import_failed_sets_error() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    renderer._import_active = True
    renderer._on_import_failed(ImportFailed(error="network error"))
    assert renderer._import_active is False
    assert renderer._import_done is True
    assert renderer._import_error == "network error"
