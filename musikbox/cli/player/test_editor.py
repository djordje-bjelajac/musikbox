from datetime import datetime
from pathlib import Path

from musikbox.adapters.fake_player import FakePlayer
from musikbox.cli.player.editor import Editor
from musikbox.cli.player.input import InputHandler
from musikbox.domain.models import Track, TrackId
from musikbox.events.bus import EventBus
from musikbox.events.types import (
    AddToPlaylistRequested,
    AddTrackFromLibraryRequested,
    EditTrackRequested,
    SearchQueueRequested,
    SortQueueRequested,
)
from musikbox.services.playback_service import PlaybackService


def _make_track(title: str = "Test Track", index: int = 0) -> Track:
    return Track(
        id=TrackId(),
        title=title,
        artist="Test Artist",
        album="Test Album",
        duration_seconds=180.0,
        file_path=Path(f"/tmp/track_{index}.mp3"),
        format="mp3",
        bpm=120.0,
        key="Am",
        genre="Electronic",
        mood="Energetic",
        source_url=None,
        downloaded_at=None,
        analyzed_at=None,
        created_at=datetime(2025, 1, 1),
    )


def _make_editor() -> tuple[EventBus, Editor]:
    bus = EventBus()
    input_handler = InputHandler(bus)
    player = FakePlayer()
    service = PlaybackService(player)
    tracks = [_make_track(f"Track {i}", i) for i in range(3)]
    service.load_queue(tracks)
    service.play()

    class FakeRepo:
        def save(self, track: Track) -> None:
            pass

    class FakeApp:
        library_service = None
        playlist_service = None

    editor = Editor(bus, input_handler, service, FakeRepo(), FakeApp())
    return bus, editor


def test_editor_subscribes_to_events() -> None:
    """Editor registers handlers for all expected event types."""
    bus, _editor = _make_editor()

    expected_events = [
        EditTrackRequested,
        AddToPlaylistRequested,
        SearchQueueRequested,
        SortQueueRequested,
        AddTrackFromLibraryRequested,
    ]

    for event_type in expected_events:
        handlers = bus._handlers.get(event_type, [])
        assert len(handlers) > 0, f"No handler registered for {event_type.__name__}"
