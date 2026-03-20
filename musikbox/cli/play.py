import atexit
import select
import shutil
import sys
import termios
import threading
import time
import tty

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from musikbox.domain.exceptions import MusikboxError, TrackNotFoundError
from musikbox.domain.models import SearchFilter, Track
from musikbox.services.library_service import LibraryService
from musikbox.services.playback_service import PlaybackService

console = Console()

# Camelot mapping (duplicated from library.py to avoid coupling CLI modules)
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


def _sort_key(track: Track, field: str) -> tuple[int, str]:
    if field == "key":
        return _camelot_sort_key(track.key)
    value = getattr(track, field, None)
    if value is None:
        return (1, "")
    if isinstance(value, float):
        return (0, f"{value:020.4f}")
    return (0, str(value).lower())


def _camelot_sort_key(key: str | None) -> tuple[int, str]:
    if key is None:
        return (99, "Z")
    camelot = _KEY_TO_CAMELOT.get(key)
    if camelot is not None:
        return camelot
    if len(key) >= 2 and key[-1] in ("A", "B"):
        try:
            num = int(key[:-1])
            return (num, key[-1])
        except ValueError:
            pass
    return (99, "Z")


def _format_duration(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


def _resolve_tracks(
    ctx: click.Context,
    track_id: str | None,
    all_tracks: bool,
    key_filter: str | None,
    genre: str | None,
    bpm_range: str | None,
    bpm_min: float | None,
    bpm_max: float | None,
    query: str | None,
    sort_by: str | None,
) -> list[Track]:
    """Resolve which tracks to play based on CLI arguments."""
    service: LibraryService = ctx.obj.library_service

    if track_id:
        try:
            track = service.get_track(track_id)
            return [track]
        except TrackNotFoundError:
            console.print(f"[red]Track not found:[/red] {track_id}")
            raise SystemExit(1)

    if bpm_range:
        parts = bpm_range.split("-")
        if len(parts) == 2:
            bpm_min = float(parts[0])
            bpm_max = float(parts[1])

    has_filter = any([key_filter, genre, bpm_min, bpm_max, query])

    if all_tracks or has_filter:
        search_filter = SearchFilter(
            key=key_filter,
            genre=genre,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            query=query,
        )
        if all_tracks and not has_filter:
            tracks = service.list_tracks(limit=10000, offset=0)
        else:
            tracks = service.search_tracks(search_filter)
    else:
        console.print("[red]Specify a track ID, --all, or filter options.[/red]")
        raise SystemExit(1)

    if sort_by:
        fields = [f.strip() for f in sort_by.split(",")]
        tracks = sorted(tracks, key=lambda t: tuple(_sort_key(t, f) for f in fields))

    return tracks


def _display_queue_preview(tracks: list[Track]) -> bool:
    """Show the queue as a table and prompt to start. Returns True if user confirms."""
    table = Table(title="Playback Queue")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Title", style="bold")
    table.add_column("Artist")
    table.add_column("BPM", justify="right")
    table.add_column("Key")
    table.add_column("Camelot")

    for i, track in enumerate(tracks, 1):
        table.add_row(
            str(i),
            track.title,
            track.artist or "-",
            f"{track.bpm:.1f}" if track.bpm else "-",
            track.key or "-",
            _to_camelot_str(track.key),
        )

    console.print(table)

    total_duration = sum(t.duration_seconds for t in tracks)
    console.print(
        f"\n[bold]{len(tracks)}[/bold] track(s)  "
        f"[dim]{_format_duration(total_duration)} estimated[/dim]"
    )
    console.print("\nPress [bold]Enter[/bold] to play, [bold]q[/bold] to cancel")

    char = click.getchar()
    if char in ("q", "Q"):
        console.print("[dim]Cancelled.[/dim]")
        return False
    return True


def _build_now_playing_panel(service: PlaybackService) -> Panel:
    """Build the Rich panel for the now-playing display."""
    track = service.current_track()
    if track is None:
        return Panel("[dim]No track loaded[/dim]", title="Now Playing")

    pos = service.position()
    dur = service.duration()
    progress_pct = (pos / dur * 100) if dur > 0 else 0

    status_icon = "⏸" if service.is_paused() else "▶"

    title_line = Text(track.title, style="bold")
    artist_line = Text(track.artist or "Unknown Artist", style="dim")

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

    queue_pos = f"[{service.queue_index + 1}/{len(service.queue)}]"
    controls = "space: pause  ←/→: seek  n: next  p: prev  q: quit"

    from rich.console import Group

    # Dynamic bar width: terminal width minus panel borders and other text
    term_width = shutil.get_terminal_size().columns
    # Account for: panel borders (4), icon+spaces (4), two timestamps (12), spaces (3)
    bar_width = max(10, term_width - 23)
    filled = int(bar_width * progress_pct / 100)
    empty = bar_width - filled
    if filled < bar_width:
        bar_str = "━" * filled + "╺" + "─" * max(0, empty - 1)
    else:
        bar_str = "━" * bar_width

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

    content = Group(
        title_line,
        artist_line,
        Text(""),
        meta_line,
        Text(""),
        progress_line,
        Text(""),
        footer_line,
    )

    return Panel(content, title="Now Playing", expand=True)


def _read_key_raw(stop_event: threading.Event, key_queue: list[str]) -> None:
    """Background thread: read single characters from stdin in cbreak mode.

    Uses cbreak (not raw) so terminal output processing still works,
    allowing Rich Live to render correctly.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def restore_terminal() -> None:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    atexit.register(restore_terminal)

    try:
        tty.setcbreak(fd)
        buf = ""
        while not stop_event.is_set():
            ready, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not ready:
                # Flush any incomplete escape sequence
                for c in buf:
                    key_queue.append(c)
                buf = ""
                continue

            ch = sys.stdin.read(1)
            if not ch:
                continue

            buf += ch

            # Accumulate escape sequences
            if buf == "\x1b" or buf == "\x1b[":
                continue
            if buf == "\x1b[C":
                key_queue.append("RIGHT")
                buf = ""
                continue
            if buf == "\x1b[D":
                key_queue.append("LEFT")
                buf = ""
                continue
            if buf.startswith("\x1b"):
                # Unknown escape sequence, discard
                buf = ""
                continue

            # Regular character
            key_queue.append(buf)
            buf = ""
    finally:
        restore_terminal()


def _run_playback_loop(service: PlaybackService) -> None:
    """Main playback loop with Rich Live display and keyboard controls."""
    stop_event = threading.Event()
    key_queue: list[str] = []

    # Wire up auto-advance on track end
    def _on_track_end() -> None:
        result = service.next_track(auto=True)
        if result is None:
            stop_event.set()

    player = service._player
    if hasattr(player, "on_track_end"):
        player.on_track_end = _on_track_end

    input_thread = threading.Thread(
        target=_read_key_raw, args=(stop_event, key_queue), daemon=True
    )
    input_thread.start()

    try:
        with Live(
            _build_now_playing_panel(service),
            console=console,
            refresh_per_second=4,
            transient=True,
        ) as live:
            while not stop_event.is_set() and service.is_active:
                # Process key presses
                while key_queue:
                    ch = key_queue.pop(0)
                    if ch == " ":
                        service.pause_resume()
                    elif ch == "n":
                        result = service.next_track()
                        if result is None:
                            stop_event.set()
                    elif ch == "p":
                        service.previous_track()
                    elif ch in ("LEFT", ",", "<"):
                        service.seek(-10)
                    elif ch in ("RIGHT", ".", ">"):
                        service.seek(10)
                    elif ch in ("q", "\x03"):  # q or Ctrl+C
                        stop_event.set()

                live.update(_build_now_playing_panel(service))
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        service.stop()
        input_thread.join(timeout=1.0)


@click.command()
@click.argument("track_id", required=False)
@click.option("--all", "all_tracks", is_flag=True, help="Play entire library.")
@click.option("--key", "key_filter", default=None, help="Filter by musical key.")
@click.option("--genre", default=None, help="Filter by genre.")
@click.option("--bpm-range", default=None, help="BPM range as MIN-MAX (e.g. 120-130).")
@click.option("--bpm-min", type=float, default=None, help="Minimum BPM.")
@click.option("--bpm-max", type=float, default=None, help="Maximum BPM.")
@click.option("--sort-by", default=None, help="Sort by column(s), comma-separated (e.g. key,bpm).")
@click.option("--query", default=None, help="Free-text search across title/artist.")
@click.pass_context
def play(
    ctx: click.Context,
    track_id: str | None,
    all_tracks: bool,
    key_filter: str | None,
    genre: str | None,
    bpm_range: str | None,
    bpm_min: float | None,
    bpm_max: float | None,
    sort_by: str | None,
    query: str | None,
) -> None:
    """Play tracks from the library.

    Optionally provide a TRACK_ID to play a single track, or use filter options.
    """
    try:
        playback_service: PlaybackService | None = ctx.obj.playback_service
        if playback_service is None:
            console.print(
                "[red]Playback unavailable.[/red] "
                "Install mpv: brew install mpv && uv pip install 'musikbox[playback]'"
            )
            raise SystemExit(1)

        tracks = _resolve_tracks(
            ctx,
            track_id,
            all_tracks,
            key_filter,
            genre,
            bpm_range,
            bpm_min,
            bpm_max,
            query,
            sort_by,
        )

        if not tracks:
            console.print("[dim]No tracks found.[/dim]")
            return

        if not _display_queue_preview(tracks):
            return

        playback_service.load_queue(tracks)
        playback_service.play()
        _run_playback_loop(playback_service)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)
