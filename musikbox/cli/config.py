from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()

_ENV_PATH = Path.home() / ".config" / "musikbox" / ".env"

_KNOWN_KEYS = {
    "MUSIKBOX_MUSIC_DIR": "Directory for downloaded music",
    "MUSIKBOX_DB_PATH": "Path to SQLite database file",
    "MUSIKBOX_AUTO_ANALYZE": "Auto-analyze after download (true/false)",
    "MUSIKBOX_DEFAULT_FORMAT": "Default audio format (flac, mp3, wav)",
    "MUSIKBOX_AUDIO_QUALITY": "Audio quality for downloads",
    "MUSIKBOX_WRITE_TAGS": "Write metadata tags after analysis (true/false)",
    "MUSIKBOX_KEY_NOTATION": "Key notation style (camelot, standard, both)",
    "MUSIKBOX_MODEL_DIR": "Directory for Essentia models",
}


@click.group()
def config() -> None:
    """View and modify configuration."""


@config.command()
@click.pass_context
def show(ctx: click.Context) -> None:
    """Display current configuration."""
    cfg = ctx.obj.config

    table = Table(title="musikbox configuration")
    table.add_column("Setting", style="bold cyan")
    table.add_column("Value")

    table.add_row("music_dir", str(cfg.music_dir))
    table.add_row("db_path", str(cfg.db_path))
    table.add_row("auto_analyze", str(cfg.auto_analyze))
    table.add_row("download.output_dir", str(cfg.download.output_dir))
    table.add_row("download.default_format", cfg.download.default_format)
    table.add_row("download.audio_quality", cfg.download.audio_quality)
    table.add_row("analysis.write_tags", str(cfg.analysis.write_tags))
    table.add_row("analysis.key_notation", cfg.analysis.key_notation)
    table.add_row("analysis.model_dir", str(cfg.analysis.model_dir))

    console.print(table)

    env_status = "exists" if _ENV_PATH.exists() else "not found"
    console.print(f"\n[dim]Config file ({env_status}):[/dim] {_ENV_PATH}")


@config.command(name="set")
@click.argument("key_value")
def set_value(key_value: str) -> None:
    """Set a configuration value (KEY=VALUE).

    Writes to ~/.config/musikbox/.env. Changes take effect on next command.
    """
    if "=" not in key_value:
        console.print("[red]Invalid format.[/red] Use: musikbox config set KEY=VALUE")
        raise SystemExit(1)

    key, value = key_value.split("=", 1)
    key = key.strip().upper()

    if not key.startswith("MUSIKBOX_"):
        key = f"MUSIKBOX_{key}"

    if key not in _KNOWN_KEYS:
        known = ", ".join(sorted(_KNOWN_KEYS))
        console.print(f"[yellow]Warning:[/yellow] Unknown key '{key}'. Known keys: {known}")

    _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Read existing lines, update or append
    lines: list[str] = []
    found = False

    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text().splitlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                found = True
                break

    if not found:
        lines.append(f"{key}={value}")

    _ENV_PATH.write_text("\n".join(lines) + "\n")
    console.print(f"[green]Set[/green] {key}={value}")
