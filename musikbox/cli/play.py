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


class ImportStatus:
    """Shared state for background YouTube import."""

    def __init__(self) -> None:
        self.active = False
        self.playlist_name = ""
        self.downloaded = 0
        self.last_track = ""
        self.done = False
        self.done_at: float = 0.0
        self.error: str | None = None
        # Queue of tracks downloaded by background thread, to be
        # saved to DB by the main thread
        self.pending_tracks: list[Track] = []
        self.download_done = False
        self.album: str | None = None
        self.artist: str | None = None
        self.genre: str | None = None


# Global import status — accessed by panel builder and background thread
_import_status = ImportStatus()

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
            "  e: edit  s: sort  a: add  b: library  i: import  q: quit"
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

    parts: list[object] = [
        *header_lines,
        Text(""),
        meta_line,
        Text(""),
        progress_line,
        Text(""),
        Text("─" * (shutil.get_terminal_size().columns - 4), style="dim"),
        *queue_lines,
        Text(""),
    ]

    # Show import status if active
    if _import_status.active:
        status = (
            f"  ⬇ Importing '{_import_status.playlist_name}'"
            f" — {_import_status.downloaded} downloaded"
        )
        if _import_status.last_track:
            status += f" (latest: {_import_status.last_track[:30]})"
        parts.append(Text(status, style="bold yellow"))
        parts.append(Text(""))
    elif _import_status.done:
        # Auto-dismiss after 10 seconds
        if time.monotonic() - _import_status.done_at > 10:
            _import_status.done = False
        else:
            if _import_status.error:
                msg = f"  ✗ Import failed: {_import_status.error}"
                parts.append(Text(msg, style="bold red"))
            else:
                msg = (
                    f"  ✓ Imported '{_import_status.playlist_name}'"
                    f" — {_import_status.downloaded} track(s)"
                )
                parts.append(Text(msg, style="bold green"))
            parts.append(Text(""))

    parts.append(footer_line)

    content = Group(*parts)
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

    picked = _pick_track_interactive(results)
    if picked is None:
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    track = results[picked]

    # Add to queue
    service._queue.append(track)

    # Add to playlist if playing one
    if playlist_name and playlist_service:
        try:
            playlist_service.add_track(playlist_name, track.id.value)
        except Exception:
            pass

    artist_str = f" — {track.artist}" if track.artist else ""
    console.print(f"  [green]Added:[/] {track.title}{artist_str}\n")


def _pick_track_interactive(tracks: list[Track]) -> int | None:
    """Interactive track picker with j/k navigation. Returns index or None."""
    selected = 0
    term_height = shutil.get_terminal_size().lines
    max_visible = max(5, term_height - 8)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def build_panel() -> Panel:
        table = Table(title=f"Search Results — {len(tracks)} tracks", expand=True)
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("Title")
        table.add_column("Artist", width=20)
        table.add_column("BPM", justify="right", width=6)
        table.add_column("Key", width=4)
        table.add_column("Camelot", width=7)

        scroll_top = max(0, selected - max_visible // 2)
        scroll_top = min(scroll_top, max(0, len(tracks) - max_visible))
        scroll_bottom = min(len(tracks), scroll_top + max_visible)

        for i in range(scroll_top, scroll_bottom):
            t = tracks[i]
            style = "bold reverse" if i == selected else ""
            table.add_row(
                str(i + 1),
                t.title,
                t.artist or "-",
                f"{t.bpm:.1f}" if t.bpm else "-",
                t.key or "-",
                _to_camelot_str(t.key),
                style=style,
            )

        footer = Text.assemble(
            (" j/k: navigate  ", "dim"),
            ("Enter: add  ", "bold"),
            ("q: cancel", "dim"),
        )

        from rich.console import Group

        return Panel(Group(table, Text(""), footer), expand=True)

    try:
        tty.setcbreak(fd)
        with Live(build_panel(), console=console, refresh_per_second=10) as live:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    continue
                ch = sys.stdin.read(1)
                if not ch:
                    continue
                if ch == "j":
                    selected = min(len(tracks) - 1, selected + 1)
                    live.update(build_panel())
                elif ch == "k":
                    selected = max(0, selected - 1)
                    live.update(build_panel())
                elif ch in ("\r", "\n"):
                    return selected
                elif ch in ("q", "Q", "\x03"):
                    return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _browse_library(
    app: object,
    service: PlaybackService,
    playlist_name: str | None,
    playlist_service: object | None,
) -> None:
    """Interactive library browser with expand/collapse tree navigation."""
    lib = app.library_service
    all_tracks = lib.list_tracks(limit=10_000)
    playlists = app.playlist_service.list_playlists() if app.playlist_service else []

    # Build tree nodes: each is (label, indent, type, data, expanded)
    # type: "category", "group", "track"
    class Node:
        def __init__(
            self,
            label: str,
            indent: int,
            kind: str,
            data: object = None,
            children_fn: object = None,
        ) -> None:
            self.label = label
            self.indent = indent
            self.kind = kind  # "category", "group", "track"
            self.data = data  # Track for "track" nodes
            self.expanded = False
            self.children_fn = children_fn  # callable -> list[Node]
            self.children: list[Node] = []

    # Group tracks by artist, album, genre
    from collections import defaultdict

    by_artist: dict[str, list[Track]] = defaultdict(list)
    by_genre: dict[str, list[Track]] = defaultdict(list)
    by_album: dict[str, list[Track]] = defaultdict(list)

    for t in all_tracks:
        by_artist[t.artist or "Unknown"].append(t)
        if t.genre and t.genre != "Unknown":
            by_genre[t.genre].append(t)
        if t.album:
            by_album[t.album].append(t)

    def make_track_nodes(tracks: list[Track], indent: int) -> list[Node]:
        nodes = []
        for t in tracks:
            artist_str = f" — {t.artist}" if t.artist else ""
            bpm_str = f"{t.bpm:.0f}" if t.bpm else "---"
            cam = _to_camelot_str(t.key)
            label = f"{bpm_str:>3} {cam:>3}  {t.title}{artist_str}"
            nodes.append(Node(label, indent, "track", data=t))
        return nodes

    def make_artist_children() -> list[Node]:
        nodes = []
        for name in sorted(by_artist.keys()):
            tracks = by_artist[name]
            n = Node(
                f"{name} ({len(tracks)})",
                1,
                "group",
            )
            # Group by album within artist
            albums: dict[str, list[Track]] = defaultdict(list)
            no_album: list[Track] = []
            for t in tracks:
                if t.album:
                    albums[t.album].append(t)
                else:
                    no_album.append(t)

            def make_artist_tracks(
                albums: dict[str, list[Track]], no_album: list[Track]
            ) -> list[Node]:
                result: list[Node] = []
                for alb_name in sorted(albums.keys()):
                    alb_node = Node(f"💿 {alb_name}", 2, "group")
                    alb_tracks = albums[alb_name]
                    alb_node.children_fn = lambda at=alb_tracks: make_track_nodes(at, 3)
                    result.append(alb_node)
                result.extend(make_track_nodes(no_album, 2))
                return result

            n.children_fn = lambda a=albums, na=no_album: make_artist_tracks(a, na)
            nodes.append(n)
        return nodes

    def make_genre_children() -> list[Node]:
        nodes = []
        for name in sorted(by_genre.keys()):
            tracks = by_genre[name]
            n = Node(f"{name} ({len(tracks)})", 1, "group")
            n.children_fn = lambda t=tracks: make_track_nodes(t, 2)
            nodes.append(n)
        return nodes

    def make_album_children() -> list[Node]:
        nodes = []
        for name in sorted(by_album.keys()):
            tracks = by_album[name]
            n = Node(f"{name} ({len(tracks)})", 1, "group")
            n.children_fn = lambda t=tracks: make_track_nodes(t, 2)
            nodes.append(n)
        return nodes

    def make_playlist_children() -> list[Node]:
        nodes = []
        for pl in playlists:
            n = Node(f"{pl.name}", 1, "group")
            pl_id = pl.id

            def make_pl_tracks(pid: str = pl_id) -> list[Node]:
                try:
                    tracks = app.playlist_service.get_playlist_tracks_by_id(pid)
                except Exception:
                    try:
                        tracks = app.playlist_service.get_playlist_tracks(pl.name)
                    except Exception:
                        tracks = []
                return make_track_nodes(tracks, 2)

            n.children_fn = make_pl_tracks
            nodes.append(n)
        return nodes

    # Root categories
    root_nodes = [
        Node("Artists", 0, "category"),
        Node("Albums", 0, "category"),
        Node("Genres", 0, "category"),
        Node("Playlists", 0, "category"),
    ]
    root_nodes[0].children_fn = make_artist_children
    root_nodes[1].children_fn = make_album_children
    root_nodes[2].children_fn = make_genre_children
    root_nodes[3].children_fn = make_playlist_children

    # Flatten visible nodes
    def flatten(nodes: list[Node]) -> list[Node]:
        result: list[Node] = []
        for n in nodes:
            result.append(n)
            if n.expanded and n.children:
                result.extend(flatten(n.children))
        return result

    selected = 0
    term_height = shutil.get_terminal_size().lines
    max_visible = max(5, term_height - 6)
    added_msg: str | None = None
    added_at: float = 0.0

    def build_panel() -> Panel:
        nonlocal added_msg
        visible = flatten(root_nodes)
        if not visible:
            return Panel("[dim]Empty library[/dim]", title="Library Browser")

        scroll_top = max(0, selected - max_visible // 2)
        scroll_top = min(scroll_top, max(0, len(visible) - max_visible))
        scroll_bottom = min(len(visible), scroll_top + max_visible)

        lines: list[Text] = []
        for i in range(scroll_top, scroll_bottom):
            node = visible[i]
            prefix = "  " * node.indent
            if node.kind == "track":
                icon = "  "
            elif node.expanded:
                icon = "▼ "
            else:
                icon = "▶ "

            label = f"{prefix}{icon}{node.label}"
            style = "bold reverse" if i == selected else ""
            if node.kind == "category":
                style = (style + " bold cyan").strip() if i == selected else "bold cyan"
            lines.append(Text(label, style=style))

        footer_parts = [
            (" j/k: navigate  ", "dim"),
            ("Enter: expand/add  ", "bold"),
            ("q: back", "dim"),
        ]

        footer = Text.assemble(*footer_parts)

        from rich.console import Group

        parts: list[object] = [*lines, Text("")]

        # Show added notification
        if added_msg and time.monotonic() - added_at < 3:
            parts.append(Text(f"  {added_msg}", style="bold green"))
            parts.append(Text(""))
        else:
            added_msg = None

        parts.append(footer)
        return Panel(Group(*parts), title="Library Browser", expand=True)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)
        with Live(build_panel(), console=console, refresh_per_second=10) as live:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    live.update(build_panel())
                    continue

                ch = sys.stdin.read(1)
                if not ch:
                    continue

                visible = flatten(root_nodes)
                if ch == "j":
                    selected = min(len(visible) - 1, selected + 1)
                elif ch == "k":
                    selected = max(0, selected - 1)
                elif ch in ("\r", "\n"):
                    if selected < len(visible):
                        node = visible[selected]
                        if node.kind == "track":
                            # Add track to queue
                            track = node.data
                            service._queue.append(track)
                            if playlist_name and playlist_service:
                                try:
                                    playlist_service.add_track(playlist_name, track.id.value)
                                except Exception:
                                    pass
                            added_msg = f"Added: {track.title}"
                            added_at = time.monotonic()
                        else:
                            # Toggle expand/collapse
                            if node.expanded:
                                node.expanded = False
                            else:
                                if not node.children and node.children_fn:
                                    node.children = node.children_fn()
                                node.expanded = True
                elif ch in ("q", "Q", "\x03"):
                    return

                live.update(build_panel())
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _import_yt_interactive(app: object) -> None:
    """Prompt for import details, then run download in background.

    Only the yt-dlp download runs in the background thread.
    Downloaded file paths are queued in _import_status.pending_tracks
    and processed (DB save) by the main thread via _process_import_queue.
    """
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

    if _import_status.active:
        console.print("  [yellow]An import is already in progress.[/yellow]\n")
        return

    _import_status.active = True
    _import_status.done = False
    _import_status.download_done = False
    _import_status.error = None
    _import_status.playlist_name = name
    _import_status.downloaded = 0
    _import_status.last_track = ""
    _import_status.pending_tracks = []
    _import_status.album = album_in
    _import_status.artist = artist_in
    _import_status.genre = genre_in

    def _bg_download() -> None:
        """Background: only download files, no DB access."""
        try:
            download_svc = app.playlist_service._download_service
            for track in download_svc.download_playlist(url):
                _import_status.pending_tracks.append(track)
                _import_status.downloaded += 1
                _import_status.last_track = track.title
        except Exception as e:
            _import_status.error = str(e)
        finally:
            _import_status.download_done = True

    thread = threading.Thread(target=_bg_download, daemon=True)
    thread.start()
    console.print("  [dim]Import started in background.[/dim]\n")


def _process_import_queue(app: object) -> None:
    """Called on main thread: save pending downloaded tracks to DB.

    Creates the playlist on first call, saves tracks, applies overrides.
    """
    if not _import_status.pending_tracks:
        if _import_status.download_done and _import_status.active:
            _import_status.active = False
            _import_status.done = True
            _import_status.done_at = time.monotonic()
        return

    pl_service = app.playlist_service

    # Create playlist on first track
    if not hasattr(_import_status, "_playlist_id") or _import_status._playlist_id is None:
        try:
            pl = pl_service.create_playlist(_import_status.playlist_name)
            _import_status._playlist_id = pl.id
            _import_status._position = 0
        except Exception as e:
            _import_status.error = str(e)
            _import_status.active = False
            _import_status.done = True
            _import_status.done_at = time.monotonic()
            _import_status.pending_tracks.clear()
            return

    # Process one track per call to keep main thread responsive
    track = _import_status.pending_tracks.pop(0)

    # Apply overrides
    if _import_status.album:
        track.album = _import_status.album
    if _import_status.artist:
        track.artist = _import_status.artist
    if _import_status.genre:
        track.genre = _import_status.genre

    try:
        track_repo = app.library_service._repository
        track_repo.save(track)

        existing = track_repo.get_by_file_path(track.file_path)
        track_to_add = existing if existing is not None else track

        playlist_repo = app.playlist_service._playlist_repo
        playlist_repo.add_track(
            _import_status._playlist_id,
            track_to_add.id.value,
            _import_status._position,
        )
        _import_status._position += 1
    except Exception:
        pass  # Best effort, continue with next track

    # Check if all done
    if not _import_status.pending_tracks and _import_status.download_done:
        _import_status.active = False
        _import_status.done = True
        _import_status.done_at = time.monotonic()
        _import_status._playlist_id = None


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
                    elif ch == "b" and app is not None:
                        pause_input.set()
                        live.stop()
                        time.sleep(0.15)
                        _browse_library(app, service, playlist_name, playlist_service)
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

                # Process background import queue on main thread (DB-safe)
                if _import_status.active or _import_status.pending_tracks:
                    _process_import_queue(app)

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
