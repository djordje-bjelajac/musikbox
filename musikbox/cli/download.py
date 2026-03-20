import click
from rich.console import Console
from rich.table import Table

from musikbox.domain.exceptions import DownloadError, MusikboxError
from musikbox.domain.models import Track
from musikbox.services.download_service import DownloadService

console = Console()


def _format_duration(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


def _print_track_summary(track: Track) -> None:
    table = Table(title="Downloaded Track", show_header=False)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")

    table.add_row("Title", track.title)
    if track.artist:
        table.add_row("Artist", track.artist)
    if track.album:
        table.add_row("Album", track.album)
    table.add_row("Duration", _format_duration(track.duration_seconds))
    table.add_row("Format", track.format)
    table.add_row("File", str(track.file_path))

    if track.bpm is not None:
        table.add_row("BPM", f"{track.bpm:.1f}")
    if track.key is not None:
        table.add_row("Key", track.key)
    if track.genre is not None:
        table.add_row("Genre", track.genre)

    console.print(table)


@click.command()
@click.argument("url")
@click.option("--format", "-f", "fmt", default=None, help="Audio format (e.g. flac, mp3, wav).")
@click.option("--no-analyze", is_flag=True, default=False, help="Skip automatic audio analysis.")
@click.pass_context
def download(ctx: click.Context, url: str, fmt: str | None, no_analyze: bool) -> None:
    """Download a track from URL."""
    app = ctx.obj
    service: DownloadService = app.download_service

    analyze = False if no_analyze else None  # None lets the service use its default

    try:
        with console.status("Downloading..."):
            track = service.download(url, format=fmt, analyze=analyze)
    except DownloadError as e:
        console.print(f"[bold red]Download failed:[/] {e}")
        raise SystemExit(1) from e
    except MusikboxError as e:
        console.print(f"[bold red]Error:[/] {e}")
        raise SystemExit(1) from e

    _print_track_summary(track)
