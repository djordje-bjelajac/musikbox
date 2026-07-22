from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from rich.cells import cell_len
from rich.console import Console
from rich.panel import Panel

from musikbox.adapters.local_source_resolver import LocalSourceResolver
from musikbox.cli.player.renderer import Renderer, _to_camelot_str
from musikbox.cli.player.viewport import Viewport
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
    service = PlaybackService(player, LocalSourceResolver())
    service.load_queue([_make_track()])
    return service


def test_renderer_subscribes_to_events() -> None:
    bus = EventBus()
    player = MagicMock()
    service = PlaybackService(player, LocalSourceResolver())

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
    service = PlaybackService(player, LocalSourceResolver())

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


# --- Panel geometry: the border must always close --------------------------

_TERMINAL_SIZES: list[tuple[int, int]] = [(60, 14), (120, 40)]

# A title far wider than any terminal under test. The run of `x` is the wrap
# probe: if the line wrapped, a continuation row would also carry a run of `x`.
_OVERLONG_TITLE = "OVERLONG " + "x" * 400
_WRAP_PROBE = "x" * 10


def _make_service_with_queue(tracks: list[Track]) -> PlaybackService:
    """Create a PlaybackService with a mock Player and the given queue."""
    player = MagicMock()
    player.is_paused.return_value = False
    player.is_playing.return_value = True
    player.position.return_value = 60.0
    player.duration.return_value = 240.0
    service = PlaybackService(player, LocalSourceResolver())
    service.load_queue(tracks)
    return service


def _render_rows(renderer: Renderer, columns: int, lines: int) -> list[str]:
    """Render the panel at a fixed terminal size and return the plain rows."""
    console = Console(width=columns, height=lines, force_terminal=False)
    with console.capture() as capture:
        console.print(renderer._build_panel(Viewport(columns=columns, lines=lines)))
    rendered = capture.get()
    rows = rendered.split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    return rows


def _assert_complete_border(rows: list[str], columns: int, lines: int) -> None:
    """The panel occupies exactly `lines` rows and closes on all four sides."""
    assert len(rows) == lines, f"expected {lines} rows, got {len(rows)}"

    top = rows[0]
    assert "╭" in top and "╮" in top, f"top border missing: {top!r}"

    bottom = rows[-1]
    assert "╰" in bottom and "╯" in bottom, f"bottom border missing: {bottom!r}"

    for index, row in enumerate(rows):
        assert cell_len(row) <= columns, f"row {index} is {cell_len(row)} cells wide: {row!r}"

    for index, row in enumerate(rows[1:-1], start=1):
        assert row.startswith("│"), f"row {index} missing left border: {row!r}"
        assert row.rstrip().endswith("│"), f"row {index} missing right border: {row!r}"


def test_build_panel_sets_height_to_viewport_lines() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    panel = renderer._build_panel(Viewport(columns=120, lines=40))

    assert isinstance(panel, Panel)
    assert panel.height == 40


def test_build_panel_border_is_complete_at_every_terminal_size() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    for columns, lines in _TERMINAL_SIZES:
        rows = _render_rows(renderer, columns, lines)
        _assert_complete_border(rows, columns, lines)


def test_build_panel_with_overlong_queue_title_does_not_wrap() -> None:
    bus = EventBus()
    service = _make_service_with_queue(
        [_make_track(title="Short One"), _make_track(title=_OVERLONG_TITLE)]
    )
    renderer = Renderer(bus, service)
    # Browse to the overlong track so it stays inside the scroll window even
    # when the queue budget collapses to a single row on a short terminal.
    renderer._browse_index = 1

    for columns, lines in _TERMINAL_SIZES:
        rows = _render_rows(renderer, columns, lines)
        _assert_complete_border(rows, columns, lines)

        # The header shows the current track ("Short One"), so the only row
        # carrying the probe is the queue row -- exactly one, never wrapped.
        probe_rows = [row for row in rows if _WRAP_PROBE in row]
        assert len(probe_rows) == 1, (
            f"overlong title wrapped onto {len(probe_rows)} rows at {columns}x{lines}"
        )


def test_build_panel_with_overlong_current_track_title_does_not_wrap() -> None:
    bus = EventBus()
    service = _make_service_with_queue([_make_track(title=_OVERLONG_TITLE)])
    renderer = Renderer(bus, service)

    for columns, lines in _TERMINAL_SIZES:
        rows = _render_rows(renderer, columns, lines)
        _assert_complete_border(rows, columns, lines)

        # Once in the header, once in the single queue row -- never wrapped.
        probe_rows = [row for row in rows if _WRAP_PROBE in row]
        assert len(probe_rows) == 2, (
            f"overlong title wrapped onto {len(probe_rows)} rows at {columns}x{lines}"
        )


def test_build_panel_border_is_complete_with_large_queue() -> None:
    bus = EventBus()
    service = _make_service_with_queue(
        [_make_track(title=f"Track number {index}") for index in range(200)]
    )
    renderer = Renderer(bus, service)

    for columns, lines in _TERMINAL_SIZES:
        rows = _render_rows(renderer, columns, lines)
        _assert_complete_border(rows, columns, lines)


def test_build_panel_border_survives_import_banner_with_large_queue() -> None:
    bus = EventBus()
    service = _make_service_with_queue(
        [_make_track(title=f"Track number {index}") for index in range(200)]
        + [_make_track(title=_OVERLONG_TITLE)]
    )
    renderer = Renderer(bus, service)
    renderer._import_active = True
    renderer._import_name = "A Very Long Playlist Name That Runs Past The Terminal Edge" * 4
    renderer._import_count = 42
    renderer._import_last_track = _OVERLONG_TITLE

    for columns, lines in _TERMINAL_SIZES:
        rows = _render_rows(renderer, columns, lines)
        _assert_complete_border(rows, columns, lines)


def test_build_panel_border_is_complete_with_browse_and_move_cursors() -> None:
    bus = EventBus()
    service = _make_service_with_queue(
        [_make_track(title=f"Track number {index}") for index in range(200)]
    )
    renderer = Renderer(bus, service)

    for columns, lines in _TERMINAL_SIZES:
        renderer._browse_index = 150
        renderer._move_index = None
        _assert_complete_border(_render_rows(renderer, columns, lines), columns, lines)

        renderer._browse_index = 199
        renderer._move_index = 199
        _assert_complete_border(_render_rows(renderer, columns, lines), columns, lines)
