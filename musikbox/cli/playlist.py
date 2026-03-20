import click
from rich.console import Console
from rich.table import Table

from musikbox.domain.exceptions import MusikboxError, PlaylistNotFoundError
from musikbox.domain.models import SearchFilter, Track
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


def _sort_key(track: Track, field: str) -> tuple[int, str]:
    if field == "key":
        return _camelot_sort_key(track.key)
    value = getattr(track, field, None)
    if value is None:
        return (1, "")
    if isinstance(value, float):
        return (0, f"{value:020.4f}")
    return (0, str(value).lower())


@click.group()
def playlist() -> None:
    """Manage playlists."""


@playlist.command()
@click.argument("name")
@click.option("--from-library", is_flag=True, help="Create from library tracks matching filters.")
@click.option("--genre", default=None, help="Filter by genre.")
@click.option("--key", "key_filter", default=None, help="Filter by musical key.")
@click.option("--bpm-range", default=None, help="BPM range as MIN-MAX (e.g. 120-130).")
@click.option("--bpm-min", type=float, default=None, help="Minimum BPM.")
@click.option("--bpm-max", type=float, default=None, help="Maximum BPM.")
@click.option("--query", default=None, help="Free-text search across title/artist.")
@click.option("--sort-by", default=None, help="Sort by column(s), comma-separated (e.g. key,bpm).")
@click.pass_context
def create(
    ctx: click.Context,
    name: str,
    from_library: bool,
    genre: str | None,
    key_filter: str | None,
    bpm_range: str | None,
    bpm_min: float | None,
    bpm_max: float | None,
    query: str | None,
    sort_by: str | None,
) -> None:
    """Create a new playlist."""
    try:
        service: PlaylistService = ctx.obj.playlist_service

        if from_library:
            if bpm_range:
                parts = bpm_range.split("-")
                if len(parts) == 2:
                    bpm_min = float(parts[0])
                    bpm_max = float(parts[1])

            search_filter = SearchFilter(
                genre=genre,
                key=key_filter,
                bpm_min=bpm_min,
                bpm_max=bpm_max,
                query=query,
            )

            from musikbox.services.library_service import LibraryService

            library_service: LibraryService = ctx.obj.library_service
            tracks = library_service.search_tracks(search_filter)

            if sort_by:
                fields = [f.strip() for f in sort_by.split(",")]
                tracks = sorted(tracks, key=lambda t: tuple(_sort_key(t, f) for f in fields))

            if not tracks:
                console.print("[dim]No matching tracks found.[/dim]")
                return

            pl = service.create_from_tracks(name, tracks)
            console.print(f"[green]Created playlist:[/green] {pl.name} ({len(tracks)} tracks)")
        else:
            pl = service.create_playlist(name)
            console.print(f"[green]Created playlist:[/green] {pl.name}")
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@playlist.command(name="list")
@click.pass_context
def list_playlists(ctx: click.Context) -> None:
    """List all playlists."""
    try:
        service: PlaylistService = ctx.obj.playlist_service
        playlists = service.list_playlists()

        if not playlists:
            console.print("[dim]No playlists found.[/dim]")
            return

        table = Table(title="Playlists")
        table.add_column("Name", style="bold")
        table.add_column("Tracks", justify="right")
        table.add_column("Created")

        for pl in playlists:
            tracks = service.get_playlist_tracks(pl.name)
            table.add_row(
                pl.name,
                str(len(tracks)),
                pl.created_at.strftime("%Y-%m-%d %H:%M"),
            )

        console.print(table)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@playlist.command()
@click.argument("name")
@click.pass_context
def show(ctx: click.Context, name: str) -> None:
    """Show tracks in a playlist."""
    try:
        service: PlaylistService = ctx.obj.playlist_service
        tracks = service.get_playlist_tracks(name)

        if not tracks:
            console.print(f"[dim]Playlist '{name}' is empty.[/dim]")
            return

        table = Table(title=f"Playlist: {name}")
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
    except PlaylistNotFoundError:
        console.print(f"[red]Playlist not found:[/red] {name}")
        raise SystemExit(1)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@playlist.command()
@click.argument("name")
@click.argument("track_id")
@click.pass_context
def add(ctx: click.Context, name: str, track_id: str) -> None:
    """Add a track to a playlist."""
    try:
        service: PlaylistService = ctx.obj.playlist_service
        service.add_track(name, track_id)
        console.print(f"[green]Added track to:[/green] {name}")
    except PlaylistNotFoundError:
        console.print(f"[red]Playlist not found:[/red] {name}")
        raise SystemExit(1)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@playlist.command()
@click.argument("name")
@click.argument("track_id")
@click.pass_context
def remove(ctx: click.Context, name: str, track_id: str) -> None:
    """Remove a track from a playlist."""
    try:
        service: PlaylistService = ctx.obj.playlist_service
        service.remove_track(name, track_id)
        console.print(f"[green]Removed track from:[/green] {name}")
    except PlaylistNotFoundError:
        console.print(f"[red]Playlist not found:[/red] {name}")
        raise SystemExit(1)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@playlist.command()
@click.argument("name")
@click.pass_context
def delete(ctx: click.Context, name: str) -> None:
    """Delete a playlist."""
    try:
        service: PlaylistService = ctx.obj.playlist_service
        service.delete_playlist(name)
        console.print(f"[green]Deleted playlist:[/green] {name}")
    except PlaylistNotFoundError:
        console.print(f"[red]Playlist not found:[/red] {name}")
        raise SystemExit(1)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@playlist.command(name="import-yt")
@click.argument("name")
@click.argument("url")
@click.option("--format", "-f", "fmt", default=None, help="Audio format (e.g. mp3, flac).")
@click.option("--no-analyze", is_flag=True, default=False, help="Skip audio analysis.")
@click.option("--album", default=None, help="Set album name for all tracks.")
@click.option("--artist", default=None, help="Set artist name for all tracks.")
@click.option("--genre", default=None, help="Set genre for all tracks.")
@click.option(
    "--cookies-from-browser",
    default=None,
    help="Browser to extract cookies from.",
)
@click.pass_context
def import_yt(
    ctx: click.Context,
    name: str,
    url: str,
    fmt: str | None,
    no_analyze: bool,
    album: str | None,
    artist: str | None,
    genre: str | None,
    cookies_from_browser: str | None,
) -> None:
    """Import a YouTube playlist.

    Use --album, --artist, --genre to set metadata for all tracks.
    """
    try:
        service: PlaylistService = ctx.obj.playlist_service

        if cookies_from_browser:
            download_svc = service._download_service
            download_svc._downloader._cookies_from_browser = cookies_from_browser

        analyze = False if no_analyze else None

        console.print(f"[bold]Importing YouTube playlist into '{name}'...[/bold]")
        pl, tracks = service.import_youtube_playlist(
            name,
            url,
            format=fmt,
            analyze=analyze,
            album=album,
            artist=artist,
            genre=genre,
        )

        for i, track in enumerate(tracks, 1):
            artist_str = f" — {track.artist}" if track.artist else ""
            console.print(f"[green][{i}][/] {track.title}{artist_str}")

        console.print(
            f"\n[bold green]Created playlist '{pl.name}' with {len(tracks)} track(s).[/bold green]"
        )
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)
