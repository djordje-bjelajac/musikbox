from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from musikbox.domain.exceptions import MusikboxError, TrackNotFoundError
from musikbox.domain.models import SearchFilter, Track
from musikbox.services.library_service import LibraryService

console = Console()


@click.group()
def library() -> None:
    """Manage your music library."""


@library.command(name="list")
@click.option(
    "--sort-by",
    default="title",
    help="Sort by column(s), comma-separated (e.g. key,bpm).",
)
@click.option("--key", "key_filter", default=None, help="Filter by musical key.")
@click.option("--genre", default=None, help="Filter by genre.")
@click.option("--limit", default=50, help="Maximum number of tracks to show.")
@click.option("--offset", default=0, help="Number of tracks to skip.")
@click.pass_context
def list_tracks(
    ctx: click.Context,
    sort_by: str,
    key_filter: str | None,
    genre: str | None,
    limit: int,
    offset: int,
) -> None:
    """List tracks in the library."""
    try:
        service: LibraryService = ctx.obj.library_service

        if key_filter or genre:
            search_filter = SearchFilter(key=key_filter, genre=genre)
            tracks = service.search_tracks(search_filter)
        else:
            tracks = service.list_tracks(limit=limit, offset=offset)

        if sort_by:
            fields = [f.strip() for f in sort_by.split(",")]
            tracks = sorted(tracks, key=lambda t: tuple(_sort_key(t, f) for f in fields))

        if not tracks:
            console.print("[dim]No tracks found.[/dim]")
            return

        table = Table(title="Library")
        table.add_column("Title", style="bold")
        table.add_column("Artist")
        table.add_column("BPM", justify="right")
        table.add_column("Key")
        table.add_column("Camelot")
        table.add_column("Genre")

        for track in tracks:
            camelot = _to_camelot_str(track.key)
            table.add_row(
                track.title,
                track.artist or "-",
                f"{track.bpm:.1f}" if track.bpm else "-",
                track.key or "-",
                camelot,
                track.genre or "-",
            )

        console.print(table)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@library.command()
@click.argument("query", required=False)
@click.option("--bpm-min", type=float, default=None, help="Minimum BPM.")
@click.option("--bpm-max", type=float, default=None, help="Maximum BPM.")
@click.option("--bpm-range", default=None, help="BPM range as MIN-MAX (e.g. 120-130).")
@click.option("--key", "key_filter", default=None, help="Filter by musical key.")
@click.option(
    "--sort-by",
    default=None,
    help="Sort by column(s), comma-separated (e.g. key,bpm).",
)
@click.pass_context
def search(
    ctx: click.Context,
    query: str | None,
    bpm_min: float | None,
    bpm_max: float | None,
    bpm_range: str | None,
    key_filter: str | None,
    sort_by: str | None,
) -> None:
    """Search tracks by text, BPM range, or key."""
    try:
        if bpm_range:
            parts = bpm_range.split("-")
            if len(parts) == 2:
                bpm_min = float(parts[0])
                bpm_max = float(parts[1])

        search_filter = SearchFilter(
            query=query,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            key=key_filter,
        )

        service: LibraryService = ctx.obj.library_service
        tracks = service.search_tracks(search_filter)

        if sort_by:
            fields = [f.strip() for f in sort_by.split(",")]
            tracks = sorted(tracks, key=lambda t: tuple(_sort_key(t, f) for f in fields))

        if not tracks:
            console.print("[dim]No tracks found.[/dim]")
            return

        table = Table(title="Search Results")
        table.add_column("Title", style="bold")
        table.add_column("Artist")
        table.add_column("BPM", justify="right")
        table.add_column("Key")
        table.add_column("Camelot")
        table.add_column("Genre")

        for track in tracks:
            camelot = _to_camelot_str(track.key)
            table.add_row(
                track.title,
                track.artist or "-",
                f"{track.bpm:.1f}" if track.bpm else "-",
                track.key or "-",
                camelot,
                track.genre or "-",
            )

        console.print(table)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@library.command()
@click.argument("track_id")
@click.pass_context
def inspect(ctx: click.Context, track_id: str) -> None:
    """Show detailed information about a track."""
    try:
        service: LibraryService = ctx.obj.library_service
        track = service.get_track(track_id)

        panel_content = (
            f"[bold]Title:[/bold] {track.title}\n"
            f"[bold]Artist:[/bold] {track.artist or '-'}\n"
            f"[bold]Album:[/bold] {track.album or '-'}\n"
            f"[bold]Duration:[/bold] {_format_duration(track.duration_seconds)}\n"
            f"[bold]BPM:[/bold] {f'{track.bpm:.1f}' if track.bpm else '-'}\n"
            f"[bold]Key:[/bold] {track.key or '-'}\n"
            f"[bold]Genre:[/bold] {track.genre or '-'}\n"
            f"[bold]Mood:[/bold] {track.mood or '-'}\n"
            f"[bold]Format:[/bold] {track.format}\n"
            f"[bold]File:[/bold] {track.file_path}\n"
            f"[bold]Source:[/bold] {track.source_url or '-'}\n"
            f"[bold]Created:[/bold] {track.created_at.isoformat()}\n"
            f"[bold]Analyzed:[/bold] {track.analyzed_at.isoformat() if track.analyzed_at else '-'}"
        )

        console.print(Panel(panel_content, title=f"Track: {track.id.value}", expand=False))
    except TrackNotFoundError:
        console.print(f"[red]Track not found:[/red] {track_id}")
        raise SystemExit(1)
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@library.command(name="import")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--recursive", "-r", is_flag=True, help="Import directories recursively.")
@click.pass_context
def import_tracks(ctx: click.Context, path: Path, recursive: bool) -> None:
    """Import a file or directory into the library."""
    try:
        service: LibraryService = ctx.obj.library_service

        if path.is_dir():
            tracks = service.import_directory(path, recursive=recursive)
            console.print(f"[green]Imported {len(tracks)} track(s).[/green]")
            for track in tracks:
                console.print(f"  {track.title} - {track.artist or 'Unknown'}")
        else:
            track = service.import_file(path)
            console.print(f"[green]Imported:[/green] {track.title} - {track.artist or 'Unknown'}")
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@library.command()
@click.argument("output", type=click.Path(path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["csv"]), default="csv", help="Export format.")
@click.pass_context
def export(ctx: click.Context, output: Path, fmt: str) -> None:
    """Export the library to a file."""
    try:
        service: LibraryService = ctx.obj.library_service
        service.export_csv(output)
        console.print(f"[green]Library exported to:[/green] {output}")
    except MusikboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


def _sort_key(track: Track, field: str) -> tuple[int, str]:
    """Return a sort key for a track, handling None values.

    When sorting by key, uses Camelot wheel order so harmonically
    compatible keys are adjacent (e.g., 7A, 8A, 9A cluster together).
    """
    if field == "key":
        return _camelot_sort_key(track.key)

    value = getattr(track, field, None)
    if value is None:
        return (1, "")
    if isinstance(value, float):
        return (0, f"{value:020.4f}")
    return (0, str(value).lower())


# Standard notation → Camelot number and letter for sort ordering
# Sorted by Camelot number so compatible keys are adjacent
_KEY_TO_CAMELOT: dict[str, tuple[int, str]] = {
    # Minor keys (A)
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
    # Major keys (B)
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
    """Convert a musical key to Camelot notation string."""
    if key is None:
        return "-"
    camelot = _KEY_TO_CAMELOT.get(key)
    if camelot is not None:
        return f"{camelot[0]}{camelot[1]}"
    return "-"


def _camelot_sort_key(key: str | None) -> tuple[int, str]:
    """Convert a musical key to a Camelot-ordered sort key."""
    if key is None:
        return (99, "Z")
    camelot = _KEY_TO_CAMELOT.get(key)
    if camelot is not None:
        return camelot
    # Try parsing Camelot notation directly (e.g., "8A")
    if len(key) >= 2 and key[-1] in ("A", "B"):
        try:
            num = int(key[:-1])
            return (num, key[-1])
        except ValueError:
            pass
    return (99, "Z")


def _format_duration(seconds: float) -> str:
    """Format duration in seconds as MM:SS."""
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"
