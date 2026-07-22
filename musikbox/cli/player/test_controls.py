from datetime import datetime
from pathlib import Path

from musikbox.adapters.fake_player import FakePlayer
from musikbox.adapters.local_source_resolver import LocalSourceResolver
from musikbox.cli.player.controls import _PAN_STEP, PlaybackControls
from musikbox.domain.models import Track, TrackId
from musikbox.events.bus import EventBus
from musikbox.events.types import (
    AddToPlaylistRequested,
    BrowseIndexChanged,
    KeyPressed,
    MoveIndexChanged,
    PanRequested,
    PlaybackPaused,
    PlaybackResumed,
    Shutdown,
    TrackEnded,
    TrackStarted,
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


def _make_service_and_bus(
    num_tracks: int = 3,
) -> tuple[EventBus, PlaybackService, PlaybackControls, list[Track]]:
    bus = EventBus()
    player = FakePlayer()
    service = PlaybackService(player, LocalSourceResolver())
    tracks = [_make_track(f"Track {i}", i) for i in range(num_tracks)]
    service.load_queue(tracks)
    service.play()
    controls = PlaybackControls(bus, service)
    return bus, service, controls, tracks


def _collect_events(bus: EventBus) -> list[object]:
    """Drain all events from the bus queue."""
    events: list[object] = []
    while True:
        event = bus.poll(timeout=0.01)
        if event is None:
            break
        events.append(event)
    return events


def test_space_toggles_pause() -> None:
    bus, service, controls, _ = _make_service_and_bus()

    # Press space to pause
    controls._on_key(KeyPressed(key=" "))
    events = _collect_events(bus)
    pause_events = [e for e in events if isinstance(e, PlaybackPaused)]
    assert len(pause_events) == 1
    assert service.is_paused()

    # Press space again to resume
    controls._on_key(KeyPressed(key=" "))
    events = _collect_events(bus)
    resume_events = [e for e in events if isinstance(e, PlaybackResumed)]
    assert len(resume_events) == 1
    assert not service.is_paused()


def test_j_k_changes_browse_index() -> None:
    bus, service, controls, _ = _make_service_and_bus()

    # Press j to start browsing (starts at current index, moves down)
    controls._on_key(KeyPressed(key="j"))
    assert controls.browse_index == 1
    events = _collect_events(bus)
    browse_events = [e for e in events if isinstance(e, BrowseIndexChanged)]
    assert len(browse_events) == 1
    assert browse_events[0].index == 1

    # Press j again
    controls._on_key(KeyPressed(key="j"))
    assert controls.browse_index == 2
    _ = _collect_events(bus)

    # Press k to go up
    controls._on_key(KeyPressed(key="k"))
    assert controls.browse_index == 1
    events = _collect_events(bus)
    browse_events = [e for e in events if isinstance(e, BrowseIndexChanged)]
    assert len(browse_events) == 1
    assert browse_events[0].index == 1


def test_j_does_not_exceed_queue_length() -> None:
    bus, service, controls, _ = _make_service_and_bus(num_tracks=2)

    controls._on_key(KeyPressed(key="j"))  # -> 1
    controls._on_key(KeyPressed(key="j"))  # -> still 1 (clamped)
    assert controls.browse_index == 1
    _ = _collect_events(bus)


def test_k_does_not_go_below_zero() -> None:
    bus, service, controls, _ = _make_service_and_bus()

    controls._on_key(KeyPressed(key="k"))  # starts at 0, goes to 0 (clamped)
    assert controls.browse_index == 0
    _ = _collect_events(bus)


def test_n_advances_to_next_track() -> None:
    bus, service, controls, tracks = _make_service_and_bus()

    controls._on_key(KeyPressed(key="n"))
    assert service.queue_index == 1
    events = _collect_events(bus)
    started_events = [e for e in events if isinstance(e, TrackStarted)]
    assert len(started_events) == 1
    assert started_events[0].index == 1


def test_n_at_end_emits_shutdown() -> None:
    bus, service, controls, _ = _make_service_and_bus(num_tracks=1)

    controls._on_key(KeyPressed(key="n"))
    events = _collect_events(bus)
    shutdown_events = [e for e in events if isinstance(e, Shutdown)]
    assert len(shutdown_events) == 1


def test_q_emits_shutdown() -> None:
    bus, service, controls, _ = _make_service_and_bus()

    controls._on_key(KeyPressed(key="q"))
    events = _collect_events(bus)
    shutdown_events = [e for e in events if isinstance(e, Shutdown)]
    assert len(shutdown_events) == 1


def test_ctrl_c_emits_shutdown() -> None:
    bus, service, controls, _ = _make_service_and_bus()

    controls._on_key(KeyPressed(key="\x03"))
    events = _collect_events(bus)
    shutdown_events = [e for e in events if isinstance(e, Shutdown)]
    assert len(shutdown_events) == 1


def test_track_ended_advances_to_next() -> None:
    bus, service, controls, tracks = _make_service_and_bus()

    controls._on_track_ended(TrackEnded(index=0))
    assert service.queue_index == 1
    events = _collect_events(bus)
    started_events = [e for e in events if isinstance(e, TrackStarted)]
    assert len(started_events) == 1
    assert started_events[0].track.title == "Track 1"


def test_track_ended_at_last_emits_shutdown() -> None:
    bus, service, controls, _ = _make_service_and_bus(num_tracks=1)

    controls._on_track_ended(TrackEnded(index=0))
    events = _collect_events(bus)
    shutdown_events = [e for e in events if isinstance(e, Shutdown)]
    assert len(shutdown_events) == 1


# --- h/l pan the queue sideways --------------------------------------------


def _pan_events(events: list[object]) -> list[PanRequested]:
    return [e for e in events if isinstance(e, PanRequested)]


def test_pan_step_is_positive() -> None:
    assert _PAN_STEP > 0


def test_h_emits_pan_left() -> None:
    bus, _, controls, _ = _make_service_and_bus()

    controls._on_key(KeyPressed(key="h"))

    pans = _pan_events(_collect_events(bus))
    assert len(pans) == 1
    assert pans[0].delta == -_PAN_STEP


def test_l_emits_pan_right() -> None:
    bus, _, controls, _ = _make_service_and_bus()

    controls._on_key(KeyPressed(key="l"))

    pans = _pan_events(_collect_events(bus))
    assert len(pans) == 1
    assert pans[0].delta == _PAN_STEP


def test_l_no_longer_adds_to_playlist() -> None:
    bus, _, controls, _ = _make_service_and_bus()

    controls._on_key(KeyPressed(key="l"))

    events = _collect_events(bus)
    assert not [e for e in events if isinstance(e, AddToPlaylistRequested)]


def test_ctrl_l_adds_to_playlist() -> None:
    bus, service, controls, tracks = _make_service_and_bus()

    controls._on_key(KeyPressed(key="\x0c"))

    events = _collect_events(bus)
    add_events = [e for e in events if isinstance(e, AddToPlaylistRequested)]
    assert len(add_events) == 1
    assert add_events[0].track == tracks[0]
    assert not _pan_events(events)


def test_ctrl_l_adds_the_browsed_track_when_browsing() -> None:
    bus, _, controls, tracks = _make_service_and_bus()

    controls._on_key(KeyPressed(key="j"))
    controls._on_key(KeyPressed(key="\x0c"))

    add_events = [e for e in _collect_events(bus) if isinstance(e, AddToPlaylistRequested)]
    assert len(add_events) == 1
    assert add_events[0].track == tracks[1]


def _enter_move_mode(bus: EventBus, controls: PlaybackControls) -> None:
    controls.has_playlist = True
    controls._on_key(KeyPressed(key="j"))
    controls._on_key(KeyPressed(key="m"))
    move_events = [e for e in _collect_events(bus) if isinstance(e, MoveIndexChanged)]
    assert move_events and move_events[-1].index is not None


def test_move_mode_swallows_h_and_l() -> None:
    bus, _, controls, _ = _make_service_and_bus()
    _enter_move_mode(bus, controls)

    controls._on_key(KeyPressed(key="h"))
    controls._on_key(KeyPressed(key="l"))

    events = _collect_events(bus)
    assert not _pan_events(events)
    assert controls.move_index is not None
