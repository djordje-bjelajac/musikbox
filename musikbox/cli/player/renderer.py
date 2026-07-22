import time

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from musikbox.domain.models import Track
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

from .render_state import RenderState
from .viewport import Viewport

_default_console = Console()

# Minimum seconds between paints -- the 4 Hz cap.
_FRAME_INTERVAL = 0.25

# Leading indent of a wrapped key-hint row.
_FOOTER_INDENT = 2

# Width of the pinned "  47  18:51  134  9A  " column block on a queue row.
# The panned title starts here, so these columns never scroll away and the
# row you are on stays identifiable however far right you have scrolled.
_QUEUE_PREFIX_WIDTH = 22

# Camelot wheel mapping from musical key to Camelot notation
_KEY_TO_CAMELOT: dict[str, tuple[int, str]] = {
    "G#m": (1, "A"),
    "Abm": (1, "A"),
    "D#m": (2, "A"),
    "Ebm": (2, "A"),
    "A#m": (3, "A"),
    "Bbm": (3, "A"),
    "Fm": (4, "A"),
    "Cm": (5, "A"),
    "Gm": (6, "A"),
    "Dm": (7, "A"),
    "Am": (8, "A"),
    "Em": (9, "A"),
    "Bm": (10, "A"),
    "F#m": (11, "A"),
    "Gbm": (11, "A"),
    "C#m": (12, "A"),
    "Dbm": (12, "A"),
    "B": (1, "B"),
    "F#": (2, "B"),
    "Gb": (2, "B"),
    "C#": (3, "B"),
    "Db": (3, "B"),
    "Ab": (4, "B"),
    "G#": (4, "B"),
    "Eb": (5, "B"),
    "D#": (5, "B"),
    "Bb": (6, "B"),
    "A#": (6, "B"),
    "F": (7, "B"),
    "C": (8, "B"),
    "G": (9, "B"),
    "D": (10, "B"),
    "A": (11, "B"),
    "E": (12, "B"),
}


def _to_camelot_str(key: str | None) -> str:
    if key is None:
        return "-"
    camelot = _KEY_TO_CAMELOT.get(key)
    if camelot is not None:
        return f"{camelot[0]}{camelot[1]}"
    return "-"


def _format_duration(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


def _line(text: str, style: str = "") -> Text:
    """One panel row that is elided rather than wrapped when it is too long.

    Every logical line has to cost exactly one terminal row. A line that wraps
    costs two, the row budget under-counts by one, and the bottom border is
    pushed off the screen -- which is the whole reason the box looked open.
    """
    return Text(text, style=style, no_wrap=True, overflow="ellipsis")


def _queue_prefix(index: int, track: Track) -> str:
    """The pinned columns of a queue row, padded to a constant width.

    The duration is right-aligned to five cells so that a 18:51 does not shove
    the titles of its neighbours out of alignment.
    """
    bpm_str = f"{track.bpm:.0f}" if track.bpm else "---"
    length = _format_duration(track.duration_seconds) if track.duration_seconds else "--:--"
    prefix = f" {index + 1:>3}  {length:>5}  {bpm_str:>3} {_to_camelot_str(track.key):>3}  "
    return prefix.ljust(_QUEUE_PREFIX_WIDTH)


def _queue_title(track: Track) -> str:
    """The scrollable part of a queue row: everything that is not a fixed column."""
    artist_str = f" — {track.artist}" if track.artist else ""
    album_str = f" [{track.album}]" if track.album else ""
    return f"{track.title}{artist_str}{album_str}"


def _build_footer(queue_pos: str, parts: list[str], width: int) -> list[Text]:
    """Lay the key hints out over as many rows as they need.

    The hints are the one piece of chrome worth spending extra rows on -- an
    elided hint is a hint the user cannot act on -- so they wrap where every
    other line elides. Breaks fall between hints, never inside one, so a
    binding is never split across two rows.
    """
    head = f"  {queue_pos}"
    rows: list[list[str]] = []
    used = len(head) + 2
    current: list[str] = []
    for part in parts:
        # +2 for the double space that would join this part to the previous.
        cost = len(part) + (2 if current else 0)
        if current and used + cost > width:
            rows.append(current)
            current = []
            used = _FOOTER_INDENT
            cost = len(part)
        current.append(part)
        used += cost
    rows.append(current)

    lines = [
        Text.assemble(
            (head, "bold"),
            ("  ", ""),
            ("  ".join(rows[0]), "dim"),
            no_wrap=True,
            overflow="ellipsis",
        )
    ]
    indent = " " * _FOOTER_INDENT
    lines.extend(_line(indent + "  ".join(row), "dim") for row in rows[1:])
    return lines


def _frame(content: RenderableType, viewport: Viewport) -> Panel:
    """Wrap the body in the bordered frame, pinned to the full screen.

    The explicit height is what keeps the box closed on all four sides: Rich
    crops the body to fit rather than letting it push the bottom border past
    the last row of the terminal.
    """
    return Panel(content, title="Now Playing", expand=True, height=viewport.lines)


class Renderer:
    """Subscribes to events and rebuilds the Rich Live now-playing panel."""

    def __init__(
        self,
        bus: EventBus,
        playback_service: PlaybackService,
        playlist_repo: object | None = None,
        console: Console | None = None,
    ) -> None:
        self._bus = bus
        self._service = playback_service
        self._playlist_repo = playlist_repo
        self._console = console or _default_console
        self._live: Live | None = None
        self._browse_index: int | None = None
        self._move_index: int | None = None
        self._has_playlist: bool = False
        self._pan_offset: int = 0

        # Frame state: handlers mark dirty, only render_frame paints.
        self._dirty: bool = True
        self._last_state: RenderState | None = None
        self._last_paint_at: float = 0.0

        # Cached playlist membership (only refreshed on track change)
        self._cached_track_id: str | None = None
        self._cached_playlists: str = ""

        # Import status
        self._import_active = False
        self._import_name = ""
        self._import_count = 0
        self._import_last_track = ""
        self._import_done = False
        self._import_done_at = 0.0
        self._import_error: str | None = None

        # Register handlers
        bus.subscribe(Tick, self._on_tick)
        bus.subscribe(TrackStarted, self._on_track_started)
        bus.subscribe(BrowseIndexChanged, self._on_browse_changed)
        bus.subscribe(MoveIndexChanged, self._on_move_changed)
        bus.subscribe(PanRequested, self._on_pan_requested)
        bus.subscribe(ImportStarted, self._on_import_started)
        bus.subscribe(ImportTrackDownloaded, self._on_import_track)
        bus.subscribe(ImportCompleted, self._on_import_completed)
        bus.subscribe(ImportFailed, self._on_import_failed)
        bus.subscribe(UIRefreshRequested, self.mark_dirty)
        # Also subscribe to playback state changes
        bus.subscribe(PlaybackPaused, self.mark_dirty)
        bus.subscribe(PlaybackResumed, self.mark_dirty)
        bus.subscribe(QueueReordered, self.mark_dirty)
        bus.subscribe(TrackAddedToQueue, self.mark_dirty)
        bus.subscribe(TrackRemovedFromQueue, self.mark_dirty)

    def _create_live(self) -> None:
        """Build a fresh Live on the alternate screen.

        auto_refresh is off: Rich's own refresh thread and the main loop would
        otherwise paint at the same nominal rate with drifting phase, which is
        seen as flicker. render_frame is the only painter.
        """
        if not self._console.is_terminal:
            self._live = None
            return
        self._live = Live(
            self._build_panel(Viewport.from_console(self._console)),
            console=self._console,
            screen=True,
            auto_refresh=False,
            refresh_per_second=4,
            vertical_overflow="crop",
        )
        self._live.start()
        self._dirty = True
        self._last_state = None

    def start(self) -> None:
        """Create and start the Rich Live display."""
        self._create_live()

    def stop(self) -> None:
        """Stop the Rich Live display. Idempotent."""
        if self._live is not None:
            self._live.stop()
            self._live = None

    def suspend(self) -> None:
        """Leave the alternate screen so a modal can use the terminal."""
        self.stop()

    def pause(self) -> None:
        """Alias for suspend(), retained for the existing modal call sites."""
        self.suspend()

    def resume(self) -> None:
        """Resume after a modal with a fresh Live and a forced repaint.

        A stopped Live is never restarted in place -- that is not a supported
        Rich lifecycle.
        """
        self._create_live()

    def mark_dirty(self, event: object | None = None) -> None:
        """Flag that the panel needs repainting. Never paints."""
        self._dirty = True

    def _refresh(self, event: object | None = None) -> None:
        """Backward-compatible alias for mark_dirty."""
        self.mark_dirty(event)

    def _expire_transient_state(self) -> None:
        """Expire time-limited banners outside the panel builder."""
        if self._import_done and time.monotonic() - self._import_done_at > 10:
            self._import_done = False
            self._dirty = True

    def render_frame(self, now: float | None = None) -> bool:
        """Paint at most one frame. Returns whether a paint occurred."""
        if self._live is None or not self._live.is_started:
            return False

        self._expire_transient_state()

        if now is None:
            now = time.monotonic()
        if now - self._last_paint_at < _FRAME_INTERVAL:
            return False

        viewport = Viewport.from_console(self._console)
        state = RenderState.capture(self._service, self, viewport)
        if state == self._last_state and not self._dirty:
            return False

        self._live.update(self._build_panel(viewport), refresh=True)
        self._last_state = state
        self._dirty = False
        self._last_paint_at = now
        return True

    def _on_tick(self, event: Tick) -> None:
        self.mark_dirty()

    def _on_track_started(self, event: TrackStarted) -> None:
        self._browse_index = None
        self._move_index = None
        self.mark_dirty()

    def _on_browse_changed(self, event: BrowseIndexChanged) -> None:
        self._browse_index = event.index
        self.mark_dirty()

    def _on_move_changed(self, event: MoveIndexChanged) -> None:
        self._move_index = event.index
        self.mark_dirty()

    def _on_pan_requested(self, event: PanRequested) -> None:
        """Scroll the queue sideways, clamped so it cannot run off either end.

        Clamping on the way in rather than at paint time keeps the offset
        honest: holding l past the longest title would otherwise bank a debt
        of presses that h has to work off before anything moves.
        """
        limit = self._max_pan(Viewport.from_console(self._console))
        self._pan_offset = max(0, min(limit, self._pan_offset + event.delta))
        self.mark_dirty()

    def _on_import_started(self, event: ImportStarted) -> None:
        self._import_active = True
        self._import_name = event.playlist_name
        self._import_count = 0
        self._import_last_track = ""
        self._import_done = False
        self._import_error = None
        self.mark_dirty()

    def _on_import_track(self, event: ImportTrackDownloaded) -> None:
        self._import_count = event.count
        self._import_last_track = event.track.title
        self.mark_dirty()

    def _on_import_completed(self, event: ImportCompleted) -> None:
        self._import_active = False
        self._import_done = True
        self._import_done_at = time.monotonic()
        self._import_count = event.count
        self._import_name = event.playlist_name
        self._import_error = None
        self.mark_dirty()

    def _on_import_failed(self, event: ImportFailed) -> None:
        self._import_active = False
        self._import_done = True
        self._import_done_at = time.monotonic()
        self._import_error = event.error
        self.mark_dirty()

    def _build_panel(self, viewport: Viewport | None = None) -> Panel:
        """Build the Rich panel for the now-playing display.

        Pure in (service state, renderer state, viewport): it must not mutate
        renderer state, or a skipped frame would never expire the banners.
        """
        if viewport is None:
            viewport = Viewport.from_console(self._console)
        track = self._service.current_track()
        if track is None:
            return _frame(_line("No track loaded", "dim"), viewport)

        pos = self._service.position()
        dur = self._service.duration()
        progress_pct = (pos / dur * 100) if dur > 0 else 0

        status_icon = "\u23f8" if self._service.is_paused() else "\u25b6"

        header_lines: list[Text] = [
            _line(track.title, "bold"),
            _line(track.artist or "Unknown Artist", "dim"),
        ]
        if track.album:
            header_lines.append(_line(track.album, "dim italic"))

        meta_parts: list[str] = []
        if track.bpm:
            meta_parts.append(f"{track.bpm:.1f} BPM")
        if track.key:
            meta_parts.append(track.key)
        camelot = _to_camelot_str(track.key)
        if camelot != "-":
            meta_parts.append(camelot)
        if track.genre:
            meta_parts.append(track.genre)
        meta_line = _line("  ".join(meta_parts) if meta_parts else "", "cyan")

        queue_pos = f"[{self._service.queue_index + 1}/{len(self._service.queue)}]"
        if self._move_index is not None:
            parts = ["j/k: move", "Enter: drop", "Esc/m: cancel"]
        else:
            parts = ["space: pause", ",/.: seek", "j/k: browse", "h/l: pan"]
            if self._browse_index is not None:
                parts.append("Enter: jump")
            parts.extend(["/: search", "n/p: track", "e: edit", "^l: +playlist"])
            parts.extend(["s: sort", "a: add", "b: library", "i: import"])
            if self._has_playlist and self._browse_index is not None:
                parts.extend(["m: move", "x: remove"])
            parts.append("q: quit")

        bar_width = viewport.progress_bar_width()
        filled = int(bar_width * progress_pct / 100)
        empty = bar_width - filled
        if filled < bar_width:
            bar_str = "\u2501" * filled + "\u257a" + "\u2500" * max(0, empty - 1)
        else:
            bar_str = "\u2501" * bar_width

        progress_line = Text.assemble(
            (f" {status_icon}  ", "bold green"),
            (_format_duration(pos), ""),
            (" ", ""),
            (bar_str, "cyan"),
            (" ", ""),
            (_format_duration(dur), ""),
            no_wrap=True,
            overflow="ellipsis",
        )

        footer_lines = _build_footer(queue_pos, parts, viewport.panel_inner_width())

        # Show which playlists contain this track (cached, refreshed on track change)
        if self._playlist_repo and hasattr(self._playlist_repo, "get_playlists_for_track"):
            if self._cached_track_id != track.id.value:
                self._cached_track_id = track.id.value
                try:
                    pls = self._playlist_repo.get_playlists_for_track(track.id.value)
                    self._cached_playlists = ", ".join(pl.name for pl in pls) if pls else ""
                except Exception:
                    self._cached_playlists = ""
            if self._cached_playlists:
                header_lines.append(_line(f"\u266b {self._cached_playlists}", "dim magenta"))

        above: list[Text] = [
            *header_lines,
            _line(""),
            meta_line,
            _line(""),
            progress_line,
            _line(""),
            _line("\u2500" * viewport.panel_inner_width(), "dim"),
        ]

        below: list[Text] = [_line("")]

        # Show import status if active
        if self._import_active:
            status = (
                f"  \u2b07 Importing '{self._import_name}' \u2014 {self._import_count} downloaded"
            )
            if self._import_last_track:
                status += f" (latest: {self._import_last_track[:30]})"
            below.append(_line(status, "bold yellow"))
            below.append(_line(""))
        elif self._import_done:
            # Expiry lives in _expire_transient_state -- this branch only reads.
            if self._import_error:
                below.append(_line(f"  \u2717 Import failed: {self._import_error}", "bold red"))
            else:
                msg = (
                    f"  \u2713 Imported '{self._import_name}' \u2014 {self._import_count} track(s)"
                )
                below.append(_line(msg, "bold green"))
            below.append(_line(""))

        below.extend(footer_lines)

        # The queue absorbs whatever the chrome leaves over -- the two borders
        # included, so the bottom one always has a row left to land on.
        rows = viewport.queue_rows(len(above) + len(below) + 2)
        queue_lines = self._queue_lines(rows)
        # Pad a short queue out to its full allowance so the key hints rest on
        # the bottom border instead of floating in the middle of the panel.
        queue_lines.extend(_line("") for _ in range(rows - len(queue_lines)))
        content = Group(*above, *queue_lines, *below)
        return _frame(content, viewport)

    def _queue_lines(self, rows: int) -> list[Text]:
        """Render at most ``rows`` queue entries, scrolled to keep the focus centred."""
        queue = self._service.queue
        current_idx = self._service.queue_index

        focus = (
            self._move_index
            if self._move_index is not None
            else (self._browse_index if self._browse_index is not None else current_idx)
        )
        scroll_top = max(0, focus - rows // 2)
        scroll_top = min(scroll_top, max(0, len(queue) - rows))
        scroll_bottom = min(len(queue), scroll_top + rows)

        lines: list[Text] = []
        for i in range(scroll_top, scroll_bottom):
            label = _queue_prefix(i, queue[i]) + _queue_title(queue[i])[self._pan_offset :]
            lines.append(_line(label, self._queue_row_style(i, current_idx)))
        return lines

    def _max_pan(self, viewport: Viewport) -> int:
        """How far right the queue can scroll before the longest title runs out.

        Measured against the whole queue, not just the visible rows, so the
        pan range does not shift under the user as they browse up and down.
        """
        room = max(1, viewport.panel_inner_width() - _QUEUE_PREFIX_WIDTH)
        longest = max((len(_queue_title(t)) for t in self._service.queue), default=0)
        return max(0, longest - room)

    def _queue_row_style(self, index: int, current_idx: int) -> str:
        """Style for one queue row, most specific selection state first."""
        if index == self._move_index:
            return "bold yellow"
        if index == current_idx and index == self._browse_index:
            return "bold reverse green"
        if index == self._browse_index:
            return "bold reverse"
        if index == current_idx:
            return "bold green"
        return "dim"
