import re
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from musikbox.config.settings import load_library_folders, save_library_folders
from musikbox.domain.exceptions import MusikboxError, TrackNotFoundError
from musikbox.domain.models import SearchFilter, Track
from musikbox.domain.ports.metadata_enricher import MetadataEnricher
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


@library.group()
def folders() -> None:
    """Manage library folders."""


@folders.command(name="add")
@click.argument("name")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def folders_add(ctx: click.Context, name: str, path: Path) -> None:
    """Add a named library folder. Usage: folders add NAME PATH"""
    config = ctx.obj.config
    libs = load_library_folders(config)
    libs[name] = path.resolve()
    save_library_folders(config, libs)
    console.print(f"[green]Added folder:[/green] {name} → {path.resolve()}")


@folders.command(name="remove")
@click.argument("name")
@click.pass_context
def folders_remove(ctx: click.Context, name: str) -> None:
    """Remove a named library folder."""
    config = ctx.obj.config
    libs = load_library_folders(config)
    if name not in libs:
        console.print(f"[red]Folder not found:[/red] {name}")
        raise SystemExit(1)
    del libs[name]
    save_library_folders(config, libs)
    console.print(f"[green]Removed folder:[/green] {name}")


@folders.command(name="list")
@click.pass_context
def folders_list(ctx: click.Context) -> None:
    """List all configured library folders."""
    config = ctx.obj.config
    libs = load_library_folders(config)
    if not libs:
        console.print("[dim]No library folders configured.[/dim]")
        return
    table = Table(title="Library Folders")
    table.add_column("Name", style="bold")
    table.add_column("Path")
    for name, path in sorted(libs.items()):
        table.add_row(name, str(path))
    console.print(table)


@folders.command(name="scan")
@click.argument("name", required=False)
@click.option("--recursive", "-r", is_flag=True, help="Scan recursively.")
@click.pass_context
def folders_scan(ctx: click.Context, name: str | None, recursive: bool) -> None:
    """Scan a library folder (or all) for new files and import them."""
    config = ctx.obj.config
    service: LibraryService = ctx.obj.library_service
    libs = load_library_folders(config)

    if not libs:
        console.print("[dim]No library folders configured.[/dim]")
        return

    if name:
        if name not in libs:
            console.print(f"[red]Folder not found:[/red] {name}")
            raise SystemExit(1)
        to_scan = {name: libs[name]}
    else:
        to_scan = libs

    total = 0
    for folder_name, path in to_scan.items():
        if not path.is_dir():
            console.print(f"[yellow]Skipping {folder_name}:[/] {path} not found")
            continue
        console.print(f"Scanning [bold]{folder_name}[/] ({path})...")
        try:
            tracks = service.import_directory(path, recursive=recursive)
            total += len(tracks)
            console.print(f"  Imported {len(tracks)} track(s)")
        except MusikboxError as e:
            console.print(f"  [red]Error:[/red] {e}")

    console.print(f"\n[bold green]Total: {total} track(s) imported.[/bold green]")


_JUNK_PATTERNS = re.compile(
    r"\s*[\(\[](official\s*(music\s*)?video|official\s*audio|"
    r"lyric\s*video|lyrics|visuali[sz]er|audio|hd|hq|"
    r"\d{4}\s*remaster(ed)?|\dk\s*remaster(ed)?|"
    r"remaster(ed)?|live|explicit|clean)[\)\]]",
    re.IGNORECASE,
)


def _parse_title(raw: str) -> tuple[str, str | None]:
    """Parse 'Artist - Title' and strip YouTube junk."""
    cleaned = _JUNK_PATTERNS.sub("", raw).strip()
    if " - " in cleaned:
        artist, title = cleaned.split(" - ", 1)
        return title.strip(), artist.strip()
    return cleaned, None


@library.command(name="fix-metadata")
@click.pass_context
def fix_metadata(ctx: click.Context) -> None:
    """Fix artist/title/genre for library tracks.

    Parses 'Artist - Title' from track names and looks up genre
    from MusicBrainz for tracks missing it.
    """
    app = ctx.obj
    service: LibraryService = app.library_service
    genre_lookup = getattr(app, "genre_lookup", None)

    tracks = service.list_tracks(limit=10_000)
    if not tracks:
        console.print("[dim]No tracks in library.[/dim]")
        return

    fixed = 0
    for track in tracks:
        changed = False

        # Fix artist/title if artist is missing and title has " - "
        if not track.artist and " - " in track.title:
            new_title, new_artist = _parse_title(track.title)
            if new_artist:
                track.artist = new_artist
                track.title = new_title
                changed = True

        # Clean junk from title even if artist exists
        if not changed and _JUNK_PATTERNS.search(track.title):
            track.title = _JUNK_PATTERNS.sub("", track.title).strip()
            changed = True

        # Look up genre if missing
        if not track.genre or track.genre == "Unknown":
            if genre_lookup is not None:
                try:
                    genre, _ = genre_lookup.lookup(track.title, track.artist)
                    if genre != "Unknown":
                        track.genre = genre
                        changed = True
                except Exception:
                    pass

        if changed:
            service._repository.save(track)
            fixed += 1
            console.print(
                f"  [green]Fixed:[/] {track.artist or '-'} — {track.title} [{track.genre or '-'}]"
            )

    console.print(f"\n[bold green]Fixed {fixed} of {len(tracks)} track(s).[/bold green]")


@library.command()
@click.option("--force", is_flag=True, help="Re-enrich all tracks, not just unenriched ones.")
@click.pass_context
def enrich(ctx: click.Context, force: bool) -> None:
    """Enrich track metadata using LLM (requires ANTHROPIC_API_KEY)."""
    app = ctx.obj
    enricher = getattr(app, "enricher", None)

    if enricher is None:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY is not set. "
            "Add it to ~/.config/musikbox/.env to use enrichment."
        )
        raise SystemExit(1)

    if not isinstance(enricher, MetadataEnricher):
        console.print("[red]Error:[/red] Invalid enricher configuration.")
        raise SystemExit(1)

    service: LibraryService = app.library_service
    tracks = service.list_tracks(limit=10_000)
    unenriched = tracks if force else [t for t in tracks if t.enriched_at is None]

    if not unenriched:
        console.print("[dim]All tracks are already enriched. Use --force to re-enrich.[/dim]")
        return

    console.print(f"Enriching {len(unenriched)} track(s)...\n")

    enriched_count = 0
    for i, track in enumerate(unenriched, 1):
        try:
            # Prefer filename stem — it usually has the original YouTube title
            # with artist, remix info, etc. intact
            raw = track.file_path.stem if track.file_path.exists() else track.title
            result = enricher.enrich(raw, bpm=track.bpm, key=track.key)

            if result.artist is not None:
                track.artist = result.artist
            if result.title is not None:
                track.title = result.title
            if result.album is not None:
                track.album = result.album
            if result.remix is not None:
                track.remix = result.remix
            if result.year is not None:
                track.year = result.year
            if result.genre is not None:
                track.genre = result.genre
            if result.tags:
                track.tags = ", ".join(result.tags)

            track.enriched_at = datetime.now(UTC)
            service._repository.save(track)
            enriched_count += 1

            tag_str = track.tags or ""
            label = f"{track.artist or '-'} - {track.title}"
            if tag_str:
                label += f" [{tag_str}]"
            console.print(f"  [{i}/{len(unenriched)}] {label}")
        except Exception as e:
            console.print(f"  [{i}/{len(unenriched)}] [red]Error:[/red] {track.title} — {e}")

    console.print(
        f"\n[bold green]Enriched {enriched_count} of {len(unenriched)} track(s).[/bold green]"
    )


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
