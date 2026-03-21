import select
import shutil
import sys
import termios
import time
import tty

import click
from rich.console import Console, Group
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


def _search_queue(queue: list[Track], start_from: int = 0) -> int | None:
    """Prompt for a search query and return the index of the first match."""
    query = input("  Search: ").strip().lower()
    if not query:
        return None

    for offset in range(len(queue)):
        i = (start_from + offset) % len(queue)
        track = queue[i]
        haystack = f"{track.title} {track.artist or ''} {track.genre or ''}".lower()
        if query in haystack:
            return i

    console.print("  [dim]No match found.[/dim]")
    time.sleep(0.5)
    return None


def _display_queue_preview(tracks: list[Track], repository: object = None) -> int | None:
    """Interactive queue selector. Returns selected index, or None if cancelled."""
    selected = 0
    term_height = shutil.get_terminal_size().lines

    max_visible = max(5, term_height - 8)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    total_duration = sum(t.duration_seconds for t in tracks)

    def build_table() -> Panel:
        table = Table(
            title=(
                f"Playback Queue \u2014 {len(tracks)} tracks, {_format_duration(total_duration)}"
            ),
            expand=True,
        )
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("Title")
        table.add_column("Artist", width=15)
        table.add_column("BPM", justify="right", width=6)
        table.add_column("Key", width=4)
        table.add_column("Camelot", width=7)

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

        from musikbox.cli.player.app import PlayerApp

        player_app = PlayerApp(
            playback_service=playback_service,
            repository=repository,
            app=ctx.obj,
            playlist_name=playlist_name,
            playlist_service=pl_service,
        )
        player_app.run(tracks, start_index)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)
