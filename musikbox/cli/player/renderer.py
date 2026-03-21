import shutil
import time

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

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


class Renderer:
    """Subscribes to events and rebuilds the Rich Live now-playing panel."""

    def __init__(
        self,
        bus: EventBus,
        playback_service: PlaybackService,
        playlist_repo: object | None = None,
    ) -> None:
        self._bus = bus
        self._service = playback_service
        self._playlist_repo = playlist_repo
        self._live: Live | None = None
        self._browse_index: int | None = None
        self._move_index: int | None = None
        self._has_playlist: bool = False

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
        bus.subscribe(ImportStarted, self._on_import_started)
        bus.subscribe(ImportTrackDownloaded, self._on_import_track)
        bus.subscribe(ImportCompleted, self._on_import_completed)
        bus.subscribe(ImportFailed, self._on_import_failed)
        bus.subscribe(UIRefreshRequested, self._refresh)
        # Also subscribe to playback state changes
        bus.subscribe(PlaybackPaused, self._refresh)
        bus.subscribe(PlaybackResumed, self._refresh)
        bus.subscribe(QueueReordered, self._refresh)
        bus.subscribe(TrackAddedToQueue, self._refresh)
        bus.subscribe(TrackRemovedFromQueue, self._refresh)

    def start(self) -> None:
        """Create and start the Rich Live display."""
        self._live = Live(
            self._build_panel(),
            refresh_per_second=4,
            transient=True,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop the Rich Live display."""
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _refresh(self, event: object | None = None) -> None:
        """Rebuild and update the panel."""
        if self._live is not None:
            self._live.update(self._build_panel())

    def _on_tick(self, event: Tick) -> None:
        self._refresh()

    def _on_track_started(self, event: TrackStarted) -> None:
        self._browse_index = None
        self._move_index = None
        self._refresh()

    def _on_browse_changed(self, event: BrowseIndexChanged) -> None:
        self._browse_index = event.index
        self._refresh()

    def _on_move_changed(self, event: MoveIndexChanged) -> None:
        self._move_index = event.index
        self._refresh()

    def _on_import_started(self, event: ImportStarted) -> None:
        self._import_active = True
        self._import_name = event.playlist_name
        self._import_count = 0
        self._import_last_track = ""
        self._import_done = False
        self._import_error = None
        self._refresh()

    def _on_import_track(self, event: ImportTrackDownloaded) -> None:
        self._import_count = event.count
        self._import_last_track = event.track.title
        self._refresh()

    def _on_import_completed(self, event: ImportCompleted) -> None:
        self._import_active = False
        self._import_done = True
        self._import_done_at = time.monotonic()
        self._import_count = event.count
        self._import_name = event.playlist_name
        self._import_error = None
        self._refresh()

    def _on_import_failed(self, event: ImportFailed) -> None:
        self._import_active = False
        self._import_done = True
        self._import_done_at = time.monotonic()
        self._import_error = event.error
        self._refresh()

    def _build_panel(self) -> Panel:
        """Build the Rich panel for the now-playing display."""
        track = self._service.current_track()
        if track is None:
            return Panel("[dim]No track loaded[/dim]", title="Now Playing")

        pos = self._service.position()
        dur = self._service.duration()
        progress_pct = (pos / dur * 100) if dur > 0 else 0

        status_icon = "\u23f8" if self._service.is_paused() else "\u25b6"

        title_line = Text(track.title, style="bold")
        artist_line = Text(track.artist or "Unknown Artist", style="dim")
        album_line = Text(track.album, style="dim italic") if track.album else None

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
        meta_line = Text("  ".join(meta_parts) if meta_parts else "", style="cyan")

        queue_pos = f"[{self._service.queue_index + 1}/{len(self._service.queue)}]"
        if self._move_index is not None:
            controls = "j/k: move  Enter: drop  Esc/m: cancel"
        else:
            parts = ["space: pause", ",/.: seek", "j/k: browse"]
            if self._browse_index is not None:
                parts.append("Enter: jump")
            parts.extend(["/: search", "n/p: track", "e: edit", "l: +playlist"])
            parts.extend(["s: sort", "a: add", "b: library", "i: import"])
            if self._has_playlist and self._browse_index is not None:
                parts.extend(["m: move", "x: remove"])
            parts.append("q: quit")
            controls = "  ".join(parts)

        # Dynamic bar width: terminal width minus panel borders and other text
        term_width = shutil.get_terminal_size().columns
        # Account for: panel borders (4), icon+spaces (4), two timestamps (12), spaces (3)
        bar_width = max(10, term_width - 23)
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
        )

        footer_line = Text.assemble(
            (f"  {queue_pos}", "bold"),
            ("  ", ""),
            (controls, "dim"),
        )

        # Build mini queue list
        queue = self._service.queue
        current_idx = self._service.queue_index
        term_height = shutil.get_terminal_size().lines
        max_queue_rows = max(3, term_height - 14)

        # Determine scroll window centered on browse cursor or current track
        focus = (
            self._move_index
            if self._move_index is not None
            else (self._browse_index if self._browse_index is not None else current_idx)
        )
        scroll_top = max(0, focus - max_queue_rows // 2)
        scroll_top = min(scroll_top, max(0, len(queue) - max_queue_rows))
        scroll_bottom = min(len(queue), scroll_top + max_queue_rows)

        queue_lines: list[Text] = []
        for i in range(scroll_top, scroll_bottom):
            t = queue[i]
            bpm_str = f"{t.bpm:.0f}" if t.bpm else "---"
            cam = _to_camelot_str(t.key)
            artist_str = f" \u2014 {t.artist}" if t.artist else ""
            label = f" {i + 1:>3}  {bpm_str:>3} {cam:>3}  {t.title}{artist_str}"

            if self._move_index is not None and i == self._move_index:
                queue_lines.append(Text(label, style="bold yellow"))
            elif i == current_idx and i == self._browse_index:
                queue_lines.append(Text(label, style="bold reverse green"))
            elif i == self._browse_index:
                queue_lines.append(Text(label, style="bold reverse"))
            elif i == current_idx:
                queue_lines.append(Text(label, style="bold green"))
            else:
                queue_lines.append(Text(label, style="dim"))

        header_lines: list[Text] = [title_line, artist_line]
        if album_line:
            header_lines.append(album_line)

        # Show which playlists contain this track
        if self._playlist_repo and hasattr(self._playlist_repo, "get_playlists_for_track"):
            try:
                track_playlists = self._playlist_repo.get_playlists_for_track(track.id.value)
                if track_playlists:
                    names = ", ".join(pl.name for pl in track_playlists)
                    header_lines.append(Text(f"\u266b {names}", style="dim magenta"))
            except Exception:
                pass

        content_parts: list[object] = [
            *header_lines,
            Text(""),
            meta_line,
            Text(""),
            progress_line,
            Text(""),
            Text("\u2500" * (shutil.get_terminal_size().columns - 4), style="dim"),
            *queue_lines,
            Text(""),
        ]

        # Show import status if active
        if self._import_active:
            status = (
                f"  \u2b07 Importing '{self._import_name}' \u2014 {self._import_count} downloaded"
            )
            if self._import_last_track:
                status += f" (latest: {self._import_last_track[:30]})"
            content_parts.append(Text(status, style="bold yellow"))
            content_parts.append(Text(""))
        elif self._import_done:
            # Auto-dismiss after 10 seconds
            if time.monotonic() - self._import_done_at > 10:
                self._import_done = False
            else:
                if self._import_error:
                    msg = f"  \u2717 Import failed: {self._import_error}"
                    content_parts.append(Text(msg, style="bold red"))
                else:
                    msg = (
                        f"  \u2713 Imported '{self._import_name}'"
                        f" \u2014 {self._import_count} track(s)"
                    )
                    content_parts.append(Text(msg, style="bold green"))
                content_parts.append(Text(""))

        content_parts.append(footer_line)

        content = Group(*content_parts)
        return Panel(content, title="Now Playing", expand=True)
