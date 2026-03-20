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
from musikbox.services.playlist_service import PlaylistService

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
    artist: str | None,
    album: str | None,
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

    has_filter = any([artist, album, key_filter, genre, bpm_min, bpm_max, query])

    if all_tracks or has_filter:
        search_filter = SearchFilter(
            artist=artist,
            album=album,
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


def _display_queue_preview(tracks: list[Track], repository: object = None) -> int | None:
    """Interactive queue selector. Returns selected index, or None if cancelled."""
    selected = 0
    term_height = shutil.get_terminal_size().lines

    # How many rows we can show (reserve lines for header, footer, borders)
    max_visible = max(5, term_height - 8)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    total_duration = sum(t.duration_seconds for t in tracks)

    def build_table() -> Panel:
        table = Table(
            title=f"Playback Queue — {len(tracks)} tracks, {_format_duration(total_duration)}",
            expand=True,
        )
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("Title")
        table.add_column("Artist", width=15)
        table.add_column("BPM", justify="right", width=6)
        table.add_column("Key", width=4)
        table.add_column("Camelot", width=7)

        # Scroll window
        scroll_top = max(0, selected - max_visible // 2)
        scroll_top = min(scroll_top, max(0, len(tracks) - max_visible))
        scroll_bottom = min(len(tracks), scroll_top + max_visible)

        for i in range(scroll_top, scroll_bottom):
            track = tracks[i]
            style = "bold reverse" if i == selected else ""
            table.add_row(
                str(i + 1),
                track.title,
                track.artist or "-",
                f"{track.bpm:.1f}" if track.bpm else "-",
                track.key or "-",
                _to_camelot_str(track.key),
                style=style,
            )

        footer = Text.assemble(
            (" j/k: navigate  ", "dim"),
            ("/: search  ", "dim"),
            ("Enter: play  ", "bold"),
            ("e: edit  ", "dim"),
            ("q: cancel", "dim"),
        )

        from rich.console import Group

        return Panel(
            Group(table, Text(""), footer),
            expand=True,
        )

    try:
        tty.setcbreak(fd)
        with Live(build_table(), console=console, refresh_per_second=10) as live:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    continue

                ch = sys.stdin.read(1)
                if not ch:
                    continue

                if ch == "k":
                    selected = max(0, selected - 1)
                    live.update(build_table())
                elif ch == "j":
                    selected = min(len(tracks) - 1, selected + 1)
                    live.update(build_table())
                elif ch == "e" and repository is not None:
                    track = tracks[selected]
                    live.stop()
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    _edit_track(track, repository)
                    tty.setcbreak(fd)
                    live.start()
                    live.update(build_table())
                elif ch == "/":
                    live.stop()
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    match = _search_queue(tracks, selected + 1)
                    if match is not None:
                        selected = match
                    tty.setcbreak(fd)
                    live.start()
                    live.update(build_table())
                elif ch in ("\r", "\n"):
                    return selected
                elif ch in ("q", "Q", "\x03"):
                    return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _build_now_playing_panel(
    service: PlaybackService,
    browse_index: int | None = None,
    move_index: int | None = None,
    has_playlist: bool = False,
) -> Panel:
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

    queue_pos = f"[{service.queue_index + 1}/{len(service.queue)}]"
    if move_index is not None:
        controls = "j/k: move  Enter: drop  Esc/m: cancel"
    elif browse_index is not None:
        playlist_hint = "  m: move  x: remove" if has_playlist else ""
        controls = (
            f"j/k: browse  /: search  Enter: jump  e: edit  space: pause  q: quit{playlist_hint}"
        )
    else:
        controls = (
            "space: pause  ,/.: seek  j/k: browse  /: search  n/p: track"
            "  e: edit  s: sort  a: add  i: import  q: quit"
        )

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

    # Build mini queue list
    queue = service.queue
    current_idx = service.queue_index
    term_height = shutil.get_terminal_size().lines
    max_queue_rows = max(3, term_height - 14)

    # Determine scroll window centered on browse cursor or current track
    focus = (
        move_index
        if move_index is not None
        else (browse_index if browse_index is not None else current_idx)
    )
    scroll_top = max(0, focus - max_queue_rows // 2)
    scroll_top = min(scroll_top, max(0, len(queue) - max_queue_rows))
    scroll_bottom = min(len(queue), scroll_top + max_queue_rows)

    queue_lines: list[Text] = []
    for i in range(scroll_top, scroll_bottom):
        t = queue[i]
        bpm_str = f"{t.bpm:.0f}" if t.bpm else "---"
        cam = _to_camelot_str(t.key)
        artist_str = f" — {t.artist}" if t.artist else ""
        label = f" {i + 1:>3}  {bpm_str:>3} {cam:>3}  {t.title}{artist_str}"

        if move_index is not None and i == move_index:
            queue_lines.append(Text(label, style="bold yellow"))
        elif i == current_idx and i == browse_index:
            queue_lines.append(Text(label, style="bold reverse green"))
        elif i == browse_index:
            queue_lines.append(Text(label, style="bold reverse"))
        elif i == current_idx:
            queue_lines.append(Text(label, style="bold green"))
        else:
            queue_lines.append(Text(label, style="dim"))

    header_lines = [title_line, artist_line]
    if album_line:
        header_lines.append(album_line)

    content = Group(
        *header_lines,
        Text(""),
        meta_line,
        Text(""),
        progress_line,
        Text(""),
        Text("─" * (shutil.get_terminal_size().columns - 4), style="dim"),
        *queue_lines,
        Text(""),
        footer_line,
    )

    return Panel(content, title="Now Playing", expand=True)


def _read_key_raw(
    stop_event: threading.Event,
    key_queue: list[str],
    pause_event: threading.Event | None = None,
) -> None:
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
            if pause_event and pause_event.is_set():
                # Restore terminal while paused (edit mode)
                restore_terminal()
                while pause_event.is_set() and not stop_event.is_set():
                    time.sleep(0.1)
                # Re-enter cbreak mode
                if not stop_event.is_set():
                    tty.setcbreak(fd)
                continue

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


def _search_queue(queue: list[Track], start_from: int = 0) -> int | None:
    """Prompt for a search query and return the index of the first match."""
    query = input("  Search: ").strip().lower()
    if not query:
        return None

    # Search from start_from forward, wrapping around
    for offset in range(len(queue)):
        i = (start_from + offset) % len(queue)
        track = queue[i]
        haystack = f"{track.title} {track.artist or ''} {track.genre or ''}".lower()
        if query in haystack:
            return i

    console.print("  [dim]No match found.[/dim]")
    time.sleep(0.5)
    return None


def _sort_queue_interactive(
    service: PlaybackService,
    playlist_name: str | None,
    playlist_service: object | None,
) -> None:
    """Re-sort the queue by user-specified fields, keeping the current track playing."""
    console.print("\n[bold]Sort queue[/]\n")
    console.print("  Fields: title, artist, bpm, key, genre")
    sort_input = input("  Sort by (e.g. key,bpm): ").strip()
    if not sort_input:
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    fields = [f.strip() for f in sort_input.split(",")]

    current = service.current_track()
    queue = list(service._queue)
    sorted_queue = sorted(queue, key=lambda t: tuple(_sort_key(t, f) for f in fields))

    service._queue[:] = sorted_queue

    # Update index to follow the currently playing track
    if current:
        for i, t in enumerate(sorted_queue):
            if t.id.value == current.id.value:
                service._index = i
                break

    # Persist to playlist if applicable
    if playlist_name and playlist_service:
        try:
            track_ids = [t.id.value for t in sorted_queue]
            playlist_service.reorder_tracks(playlist_name, track_ids)
        except Exception:
            pass

    console.print(f"  [green]Sorted by {sort_input}.[/green]\n")


def _add_track_interactive(
    app: object,
    service: PlaybackService,
    playlist_name: str | None,
    playlist_service: object | None,
) -> None:
    """Search library and add a track to the current queue (and playlist)."""
    console.print("\n[bold]Add track from library[/]\n")

    query = input("  Search: ").strip()
    if not query:
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    from musikbox.domain.models import SearchFilter

    lib = app.library_service
    results = lib.search_tracks(SearchFilter(query=query))

    if not results:
        console.print("  [dim]No tracks found.[/dim]\n")
        return

    # Show up to 10 results
    for idx, t in enumerate(results[:10], 1):
        artist_str = f" — {t.artist}" if t.artist else ""
        bpm_str = f"{t.bpm:.0f}" if t.bpm else "---"
        cam = _to_camelot_str(t.key)
        console.print(f"  [bold]{idx:>2}[/]  {bpm_str:>3} {cam:>3}  {t.title}{artist_str}")

    console.print(f"\n  Pick 1-{min(len(results), 10)} (or Enter to cancel): ", end="")
    choice = input().strip()
    if not choice:
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    try:
        pick = int(choice) - 1
        if pick < 0 or pick >= min(len(results), 10):
            console.print("  [dim]Invalid choice.[/dim]\n")
            return
    except ValueError:
        console.print("  [dim]Invalid choice.[/dim]\n")
        return

    track = results[pick]

    # Add to queue
    service._queue.append(track)

    # Add to playlist if playing one
    if playlist_name and playlist_service:
        try:
            playlist_service.add_track(playlist_name, track.id.value)
        except Exception:
            pass  # Best effort

    artist_str = f" — {track.artist}" if track.artist else ""
    console.print(f"  [green]Added:[/] {track.title}{artist_str}\n")


def _import_yt_interactive(app: object) -> None:
    """Prompt user to import a YouTube playlist while in player mode."""
    console.print("\n[bold]Import YouTube playlist[/]\n")

    url = input("  YouTube URL: ").strip()
    if not url:
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    name = input("  Playlist name: ").strip()
    if not name:
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    artist_in = input("  Artist (Enter to skip): ").strip() or None
    album_in = input("  Album (Enter to skip): ").strip() or None
    genre_in = input("  Genre (Enter to skip): ").strip() or None

    console.print(f"\n  [dim]Importing '{name}'...[/dim]")

    try:
        pl_service = app.playlist_service
        pl, tracks = pl_service.import_youtube_playlist(
            name,
            url,
            album=album_in,
            artist=artist_in,
            genre=genre_in,
        )
        console.print(f"  [green]Imported '{pl.name}' — {len(tracks)} track(s).[/green]\n")
    except Exception as e:
        console.print(f"  [red]Import failed:[/red] {e}\n")


def _edit_track(track: Track, repository: object) -> None:
    """Prompt user to edit title, artist, genre of a track."""
    console.print("\n[bold]Edit track[/] (Enter to keep current, type new value to change)\n")

    new_title = input(f"  Title [{track.title}]: ").strip()
    if new_title:
        track.title = new_title

    new_artist = input(f"  Artist [{track.artist or ''}]: ").strip()
    if new_artist:
        track.artist = new_artist

    new_genre = input(f"  Genre [{track.genre or ''}]: ").strip()
    if new_genre:
        track.genre = new_genre

    repository.save(track)
    console.print("[green]Saved.[/green]\n")


def _run_playback_loop(
    service: PlaybackService,
    repository: object = None,
    playlist_name: str | None = None,
    playlist_service: PlaylistService | None = None,
    app: object = None,
) -> None:
    """Main playback loop with Rich Live display and keyboard controls."""
    stop_event = threading.Event()
    pause_input = threading.Event()
    key_queue: list[str] = []
    browse_index: int | None = None  # None = not browsing
    move_index: int | None = None  # None = not in move mode

    # Wire up auto-advance on track end
    def _on_track_end() -> None:
        nonlocal browse_index
        service._mark_manual_change()  # Prevent polling re-trigger
        result = service.next_track(auto=True)
        if result is None:
            stop_event.set()
        else:
            browse_index = None  # Reset browse on auto-advance

    player = service._player
    if hasattr(player, "on_track_end"):
        player.on_track_end = _on_track_end

    input_thread = threading.Thread(
        target=_read_key_raw, args=(stop_event, key_queue, pause_input), daemon=True
    )
    input_thread.start()

    def _persist_playlist_order() -> None:
        """Save the current queue order back to the playlist."""
        if playlist_name is None or playlist_service is None:
            return
        try:
            track_ids = [t.id.value for t in service._queue]
            playlist_service.reorder_tracks(playlist_name, track_ids)
        except Exception:
            pass  # Don't crash playback on persist failure

    def _remove_from_playlist(track_id: str) -> None:
        """Remove a track from the playlist."""
        if playlist_name is None or playlist_service is None:
            return
        try:
            playlist_service.remove_track(playlist_name, track_id)
        except Exception:
            pass  # Don't crash playback on persist failure

    try:
        with Live(
            _build_now_playing_panel(
                service, browse_index, move_index, has_playlist=playlist_name is not None
            ),
            console=console,
            refresh_per_second=4,
            transient=True,
        ) as live:
            while not stop_event.is_set() and service.is_active:
                while key_queue:
                    ch = key_queue.pop(0)
                    queue_len = len(service.queue)

                    # Move mode handling
                    if move_index is not None:
                        if ch == "j" and move_index < queue_len - 1:
                            # Swap track down in the internal queue
                            q = service._queue
                            q[move_index], q[move_index + 1] = q[move_index + 1], q[move_index]
                            # Adjust current playing index if affected
                            if service._index == move_index:
                                service._index = move_index + 1
                            elif service._index == move_index + 1:
                                service._index = move_index
                            move_index += 1
                        elif ch == "k" and move_index > 0:
                            q = service._queue
                            q[move_index], q[move_index - 1] = q[move_index - 1], q[move_index]
                            if service._index == move_index:
                                service._index = move_index - 1
                            elif service._index == move_index - 1:
                                service._index = move_index
                            move_index -= 1
                        elif ch in ("\r", "\n"):
                            # Drop: persist new order
                            browse_index = move_index
                            _persist_playlist_order()
                            move_index = None
                        elif ch in ("\x1b", "m"):
                            # Cancel move: we need to reload original order
                            # For simplicity, just exit move mode (order already changed in memory)
                            browse_index = move_index
                            move_index = None
                        continue

                    if ch == "j":
                        if browse_index is None:
                            browse_index = service.queue_index
                        browse_index = min(queue_len - 1, browse_index + 1)
                    elif ch == "k":
                        if browse_index is None:
                            browse_index = service.queue_index
                        browse_index = max(0, browse_index - 1)
                    elif ch in ("\r", "\n") and browse_index is not None:
                        # Jump to browsed track
                        service._index = browse_index
                        service._mark_manual_change()
                        service._player.play(service.queue[browse_index].file_path)
                        browse_index = None
                    elif ch == "m" and playlist_name and browse_index is not None:
                        # Enter move mode: grab the track at browse_index
                        move_index = browse_index
                    elif ch in ("x", "\x7f") and playlist_name and browse_index is not None:
                        # Remove track from playlist and queue
                        if queue_len <= 1:
                            continue  # Don't remove the last track
                        removed_track = service._queue[browse_index]
                        _remove_from_playlist(removed_track.id.value)
                        service._queue.pop(browse_index)
                        # Adjust current playing index
                        if browse_index < service._index:
                            service._index -= 1
                        elif browse_index == service._index:
                            # Currently playing track removed - play next
                            if service._index >= len(service._queue):
                                service._index = len(service._queue) - 1
                            service._mark_manual_change()
                            service._player.play(service._queue[service._index].file_path)
                        browse_index = min(browse_index, len(service._queue) - 1)
                    elif ch == " ":
                        service.pause_resume()
                    elif ch == "n":
                        result = service.next_track()
                        if result is None:
                            stop_event.set()
                        browse_index = None
                    elif ch == "p":
                        service.previous_track()
                        browse_index = None
                    elif ch in ("LEFT", ",", "<"):
                        service.seek(-10)
                    elif ch in ("RIGHT", ".", ">"):
                        service.seek(10)
                    elif ch == "/":
                        pause_input.set()
                        live.stop()
                        time.sleep(0.15)
                        start = (browse_index or service.queue_index) + 1
                        match = _search_queue(service.queue, start)
                        if match is not None:
                            browse_index = match
                        pause_input.clear()
                        time.sleep(0.15)
                        live.start()
                    elif ch == "e" and repository is not None:
                        # Edit browsed track, or current track if not browsing
                        if browse_index is not None:
                            track = service.queue[browse_index]
                        else:
                            track = service.current_track()
                        if track:
                            pause_input.set()
                            live.stop()
                            time.sleep(0.15)
                            _edit_track(track, repository)
                            pause_input.clear()
                            time.sleep(0.15)
                            live.start()
                    elif ch == "s":
                        pause_input.set()
                        live.stop()
                        time.sleep(0.15)
                        _sort_queue_interactive(service, playlist_name, playlist_service)
                        browse_index = None
                        pause_input.clear()
                        time.sleep(0.15)
                        live.start()
                    elif ch == "a" and app is not None:
                        pause_input.set()
                        live.stop()
                        time.sleep(0.15)
                        _add_track_interactive(app, service, playlist_name, playlist_service)
                        pause_input.clear()
                        time.sleep(0.15)
                        live.start()
                    elif ch == "i" and app is not None:
                        pause_input.set()
                        live.stop()
                        time.sleep(0.15)
                        _import_yt_interactive(app)
                        pause_input.clear()
                        time.sleep(0.15)
                        live.start()
                    elif ch in ("q", "\x03"):
                        stop_event.set()

                # Polling fallback: check if track finished but event didn't fire
                player = service._player
                if (
                    hasattr(player, "track_finished")
                    and player.track_finished
                    and not service._in_guard_window()
                ):
                    player._track_finished = False
                    service._mark_manual_change()  # Prevent re-trigger
                    result = service.next_track(auto=True)
                    if result is None:
                        stop_event.set()
                    else:
                        browse_index = None

                live.update(
                    _build_now_playing_panel(
                        service, browse_index, move_index, has_playlist=playlist_name is not None
                    )
                )
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
@click.option("--playlist", "playlist_name", default=None, help="Play a playlist by name.")
@click.option("--artist", default=None, help="Filter by artist name.")
@click.option("--album", default=None, help="Filter by album name.")
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
    playlist_name: str | None,
    artist: str | None,
    album: str | None,
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

        pl_service: PlaylistService | None = None
        if playlist_name:
            pl_service = ctx.obj.playlist_service
            tracks = pl_service.get_playlist_tracks(playlist_name)
        else:
            tracks = _resolve_tracks(
                ctx,
                track_id,
                all_tracks,
                artist,
                album,
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

        repository = ctx.obj.library_service._repository
        start_index = _display_queue_preview(tracks, repository)
        if start_index is None:
            return

        playback_service.load_queue(tracks)
        playback_service._index = start_index
        playback_service.play()
        _run_playback_loop(
            playback_service,
            repository,
            playlist_name=playlist_name,
            playlist_service=pl_service,
            app=ctx.obj,
        )
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)
