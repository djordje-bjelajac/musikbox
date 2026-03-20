from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from musikbox.domain.exceptions import AnalysisError, MusikboxError, UnsupportedFormatError
from musikbox.domain.models import AnalysisResult

console = Console()


def _print_result(file_path: Path, result: AnalysisResult) -> None:
    """Display a single analysis result as a Rich panel."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")

    table.add_row("BPM", f"{result.bpm:.1f}")
    table.add_row("Key", result.key)
    table.add_row("Camelot", result.key_camelot)
    table.add_row("Genre", result.genre)
    table.add_row("Mood", result.mood)

    for name, value in result.confidence.items():
        table.add_row(f"Confidence ({name})", f"{value:.0%}")

    console.print(Panel(table, title=str(file_path.name), expand=False))


@click.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--recursive", "-r", is_flag=True, help="Analyze directories recursively.")
@click.option("--no-tags", is_flag=True, default=False, help="Skip writing metadata tags.")
@click.pass_context
def analyze(ctx: click.Context, path: Path, recursive: bool, no_tags: bool) -> None:
    """Analyze audio files for BPM, key, genre, and mood.

    PATH can be a single audio file or a directory of audio files.
    """
    from musikbox.services.analysis_service import AnalysisService

    app = ctx.obj
    service: AnalysisService = app.analysis_service

    if no_tags:
        service._write_tags = False

    try:
        if path.is_dir():
            with console.status("Analyzing directory..."):
                results = service.analyze_directory(path, recursive=recursive)

            if not results:
                console.print("[dim]No audio files found.[/dim]")
                return

            for i, result in enumerate(results):
                audio_files = _collect_audio_files(path, recursive)
                if i < len(audio_files):
                    _print_result(audio_files[i], result)

            console.print(f"\n[green]Analyzed {len(results)} file(s).[/green]")
        else:
            track_id = _find_track_id(app, path)
            with console.status("Analyzing..."):
                result = service.analyze_file(path, track_id=track_id)
            _print_result(path, result)
            if track_id:
                console.print("[green]Library updated.[/green]")

    except AnalysisError as e:
        console.print(f"[bold red]Analysis failed:[/] {e}")
        raise SystemExit(1) from e
    except UnsupportedFormatError as e:
        console.print(f"[bold red]Unsupported format:[/] {e}")
        raise SystemExit(1) from e
    except MusikboxError as e:
        console.print(f"[bold red]Error:[/] {e}")
        raise SystemExit(1) from e


def _find_track_id(app: object, file_path: Path) -> str | None:
    """Look up a track by file path and return its ID if found."""
    try:
        track = app.library_service.get_track_by_file_path(file_path)
        if track is not None:
            return track.id.value
    except Exception:
        pass
    return None


def _collect_audio_files(dir_path: Path, recursive: bool) -> list[Path]:
    """Collect audio file paths from a directory, matching AnalysisService logic."""
    from musikbox.services.analysis_service import AUDIO_EXTENSIONS

    if recursive:
        files = sorted(dir_path.rglob("*"))
    else:
        files = sorted(dir_path.iterdir())

    return [f for f in files if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS]
