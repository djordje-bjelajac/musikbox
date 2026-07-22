from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from rich.cells import cell_len
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from musikbox.adapters.local_source_resolver import LocalSourceResolver
from musikbox.cli.player.renderer import (
    _FOOTER_INDENT,
    _QUEUE_PREFIX_WIDTH,
    Renderer,
    _build_footer,
    _queue_prefix,
    _queue_title,
    _to_camelot_str,
)
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
    PanRequested,
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
    duration_seconds: float = 240.0,
) -> Track:
    return Track(
        id=TrackId(),
        title=title,
        artist=artist,
        album=album,
        duration_seconds=duration_seconds,
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
        PanRequested,
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

# Sizes tall enough to leave the queue at least one row. 60x14 is deliberately
# not among them: there the wrapped key hints eat the entire queue budget, and
# a queue-row probe would have nothing to find.
_ROOMY_SIZES: list[tuple[int, int]] = [(60, 20), (120, 40)]

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

    for columns, lines in _ROOMY_SIZES:
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

    for columns, lines in _ROOMY_SIZES:
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


# --- Key-hint footer: wraps between hints rather than eliding them ----------

# The live hint set from `_build_panel`, as it stands outside move mode.
_HINT_PARTS: list[str] = [
    "space: pause",
    ",/.: seek",
    "j/k: browse",
    "h/l: pan",
    "/: search",
    "n/p: track",
    "e: edit",
    "^l: +playlist",
    "s: sort",
    "a: add",
    "b: library",
    "i: import",
    "q: quit",
]

# Hints from opposite ends of the set: on one row when the footer fits, on
# different rows the moment it has to wrap.
_FOOTER_MARKERS: tuple[str, str] = ("space: pause", "q: quit")


def _render_text_rows(text: Text, width: int) -> list[str]:
    """Render one footer Text at `width` and return the plain rows it occupies."""
    console = Console(width=width, force_terminal=False)
    with console.capture() as capture:
        console.print(text)
    rows = capture.get().split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    return rows


def test_build_footer_fits_on_one_row_when_width_is_ample() -> None:
    rows = _build_footer("[1/1]", _HINT_PARTS, 400)

    assert len(rows) == 1
    assert rows[0].plain.startswith(f"  [1/1]{' ' * 2}")
    for part in _HINT_PARTS:
        assert part in rows[0].plain


def test_build_footer_narrow_width_wraps_without_splitting_any_hint() -> None:
    rows = _build_footer("[1/200]", _HINT_PARTS, 56)

    assert len(rows) > 1, "narrow footer should span more than one row"

    joined = "".join(row.plain for row in rows)
    for part in _HINT_PARTS:
        assert part in joined, f"hint {part!r} was split across rows"


def test_build_footer_rows_never_exceed_the_given_width() -> None:
    for width in (24, 40, 56, 80, 120):
        rows = _build_footer("[7/200]", _HINT_PARTS, width)
        for index, row in enumerate(rows):
            rendered = _render_text_rows(row, width)
            assert len(rendered) == 1, f"footer row {index} wrapped at width {width}"
            assert cell_len(rendered[0]) <= width, (
                f"footer row {index} is {cell_len(rendered[0])} cells wide at width {width}"
            )


def test_build_footer_continuation_rows_start_with_the_indent() -> None:
    rows = _build_footer("[1/200]", _HINT_PARTS, 56)

    assert len(rows) > 1
    indent = " " * _FOOTER_INDENT
    for row in rows[1:]:
        assert row.plain.startswith(indent)
        assert not row.plain.startswith(indent + " "), "continuation row over-indented"


def test_build_footer_hint_longer_than_the_width_still_yields_a_row() -> None:
    monster = "z" * 200

    rows = _build_footer("[1/1]", [monster], 20)

    assert len(rows) == 1
    assert monster in rows[0].plain
    assert cell_len(_render_text_rows(rows[0], 20)[0]) <= 20


def test_build_footer_with_several_oversized_hints_gives_each_its_own_row() -> None:
    parts = ["z" * 200, "y" * 200, "x" * 200]

    rows = _build_footer("[1/1]", parts, 20)

    assert len(rows) == len(parts)
    for part, row in zip(parts, rows, strict=True):
        assert part in row.plain


def _footer_row_indices(rows: list[str]) -> list[int]:
    """Indices of the rendered panel rows that carry a key hint."""
    return [i for i, row in enumerate(rows) if any(m in row for m in _FOOTER_MARKERS)]


def test_build_panel_footer_wraps_onto_several_rows_on_a_narrow_terminal() -> None:
    bus = EventBus()
    service = _make_service_with_track()
    renderer = Renderer(bus, service)

    rows = _render_rows(renderer, 60, 20)

    _assert_complete_border(rows, 60, 20)
    assert len(_footer_row_indices(rows)) > 1, (
        "expected the key hints to span more than one row at 60 columns"
    )


def test_build_panel_footer_is_not_cropped_off_the_bottom() -> None:
    bus = EventBus()
    service = _make_service_with_queue(
        [_make_track(title=f"Track number {index}") for index in range(200)]
    )
    renderer = Renderer(bus, service)

    rows = _render_rows(renderer, 60, 20)

    _assert_complete_border(rows, 60, 20)
    # The last hint is the last thing in the panel body, so if it survives the
    # crop the whole footer did.
    assert "q: quit" in rows[-2], f"last content row is not a hint row: {rows[-2]!r}"


def test_build_panel_gives_the_hints_the_last_rows_on_a_short_terminal() -> None:
    """When the chrome outgrows the terminal the hints win, not a stray queue row."""
    bus = EventBus()
    service = _make_service_with_queue(
        [_make_track(title=f"Track number {index}") for index in range(200)]
    )
    renderer = Renderer(bus, service)

    rows = _render_rows(renderer, 60, 14)

    _assert_complete_border(rows, 60, 14)
    assert not [row for row in rows if "Track number" in row and "8A" in row], (
        "a queue row squeezed in ahead of the key hints"
    )
    assert _footer_row_indices(rows), "the key hints were cropped away entirely"


# --- Sideways panning of the queue -----------------------------------------

# A title long enough to run past the panned window at 60 columns, with a
# distinct head and tail so the visible slice pins down the offset exactly.
_PAN_HEAD = "HEADHEAD"
_PAN_TAIL = "TAILTAIL"
_PANNED_TITLE = _PAN_HEAD + "m" * 40 + _PAN_TAIL

_PAN_COLUMNS = 60
_PAN_LINES = 20


def _make_pan_setup() -> tuple[EventBus, Renderer, list[Track]]:
    """A short current track plus a long-titled queue entry, at 60x20.

    The current track's title is short on purpose: the header echoes it, so a
    long one would put the pan probes on a row that never scrolls.
    """
    tracks = [
        _make_track(title="Current", artist=None, album=None),
        _make_track(title=_PANNED_TITLE, artist=None, album=None),
    ]
    bus = EventBus()
    service = _make_service_with_queue(tracks)
    console = Console(width=_PAN_COLUMNS, height=_PAN_LINES, force_terminal=False)
    renderer = Renderer(bus, service, console=console)
    return bus, renderer, tracks


def _pan(bus: EventBus, delta: int) -> None:
    """Round-trip a pan through the bus so the renderer's clamp is exercised."""
    bus.emit(PanRequested(delta=delta))
    event = bus.poll(timeout=0.05)
    assert event is not None, "PanRequested never reached the bus"
    bus.dispatch(event)


def _pan_rows(renderer: Renderer) -> list[str]:
    return _render_rows(renderer, _PAN_COLUMNS, _PAN_LINES)


def test_queue_title_is_the_scrollable_part_of_the_row() -> None:
    track = _make_track(title="Title", artist="Artist", album="Album")

    assert _queue_title(track) == "Title — Artist [Album]"
    assert _queue_title(_make_track(title="Bare", artist=None, album=None)) == "Bare"


def test_queue_prefix_right_aligns_duration_in_a_fixed_width_block() -> None:
    short = _queue_prefix(46, _make_track(duration_seconds=240.0))
    long = _queue_prefix(46, _make_track(duration_seconds=1131.0))

    assert len(short) == _QUEUE_PREFIX_WIDTH
    assert len(long) == _QUEUE_PREFIX_WIDTH
    assert " 4:00" in short
    assert "18:51" in long
    # The bpm column starts at the same offset either way -- that is the whole
    # point of right-aligning the duration.
    assert short.index("128") == long.index("128")


def test_pan_offset_starts_at_zero() -> None:
    _, renderer, _ = _make_pan_setup()

    assert renderer._pan_offset == 0


def test_panning_right_hides_the_head_and_reveals_the_tail_of_a_title() -> None:
    bus, renderer, _ = _make_pan_setup()

    before = _pan_rows(renderer)
    assert any(_PAN_HEAD in row for row in before)
    assert not any(_PAN_TAIL in row for row in before)

    # Well past the end -- the clamp is what stops it at the last column.
    for _ in range(10):
        _pan(bus, 8)

    after = _pan_rows(renderer)
    assert not any(_PAN_HEAD in row for row in after), "panning right did not hide the head"
    assert any(_PAN_TAIL in row for row in after), "panning right did not reveal the tail"


def test_pinned_prefix_columns_stay_put_at_every_pan_offset() -> None:
    bus, renderer, tracks = _make_pan_setup()
    prefix = _queue_prefix(1, tracks[1])

    positions: set[int] = set()
    for _ in range(5):
        rows = _pan_rows(renderer)
        carrying = [row for row in rows if prefix in row]
        assert len(carrying) == 1, f"expected one row with the pinned columns, got {len(carrying)}"
        positions.add(carrying[0].index(prefix))
        _pan(bus, 8)

    assert len(positions) == 1, f"pinned columns moved between offsets: {sorted(positions)}"


def test_panning_left_past_zero_clamps_to_zero() -> None:
    bus, renderer, _ = _make_pan_setup()

    for _ in range(5):
        _pan(bus, -8)

    assert renderer._pan_offset == 0
    assert any(_PAN_HEAD in row for row in _pan_rows(renderer))


def test_panning_right_saturates_so_one_step_back_moves_the_view() -> None:
    bus, renderer, _ = _make_pan_setup()
    limit = renderer._max_pan(Viewport(columns=_PAN_COLUMNS, lines=_PAN_LINES))
    assert limit > 8, "the probe title is too short to test saturation"

    for _ in range(20):
        _pan(bus, 8)
    assert renderer._pan_offset == limit, "pan right did not clamp at the last column"

    saturated = _pan_rows(renderer)
    _pan(bus, -8)

    assert renderer._pan_offset == limit - 8, "pan left banked a debt of ignored presses"
    assert _pan_rows(renderer) != saturated, "one step back after saturating did not repaint"


def test_panned_rows_never_wrap_and_the_border_stays_closed() -> None:
    bus, renderer, _ = _make_pan_setup()

    for _ in range(6):
        rows = _pan_rows(renderer)
        _assert_complete_border(rows, _PAN_COLUMNS, _PAN_LINES)
        # A wrapped queue row would put the tail marker on a second row.
        assert len([row for row in rows if _PAN_TAIL in row]) <= 1
        _pan(bus, 8)


def test_panning_a_large_queue_keeps_the_border_closed_at_every_size() -> None:
    tracks = [_make_track(title=f"{_PANNED_TITLE} {index}") for index in range(200)]
    for columns, lines in _TERMINAL_SIZES:
        bus = EventBus()
        service = _make_service_with_queue(tracks)
        console = Console(width=columns, height=lines, force_terminal=False)
        renderer = Renderer(bus, service, console=console)

        for _ in range(8):
            _pan(bus, 8)
            _assert_complete_border(_render_rows(renderer, columns, lines), columns, lines)
