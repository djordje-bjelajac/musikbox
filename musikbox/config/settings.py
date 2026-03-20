import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class DownloadConfig:
    output_dir: Path
    default_format: str
    audio_quality: str
    cookies_from_browser: str | None


@dataclass
class AnalysisConfig:
    write_tags: bool
    key_notation: str
    model_dir: Path


@dataclass
class Config:
    music_dir: Path
    db_path: Path
    auto_analyze: bool
    download: DownloadConfig
    analysis: AnalysisConfig
    library_folders_path: Path = field(default_factory=lambda: Path.home())
    anthropic_api_key: str | None = None


def _env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes")


def load_config() -> Config:
    """Load configuration from ~/.config/musikbox/.env with environment variable overrides."""
    config_dir = Path.home() / ".config" / "musikbox"
    env_path = config_dir / ".env"

    load_dotenv(env_path)

    music_dir = Path(os.environ.get("MUSIKBOX_MUSIC_DIR", str(Path.home() / "Music" / "musikbox")))
    db_path = Path(os.environ.get("MUSIKBOX_DB_PATH", str(config_dir / "musikbox.db")))
    auto_analyze = _env_bool("MUSIKBOX_AUTO_ANALYZE", default=True)

    download = DownloadConfig(
        output_dir=music_dir,
        default_format=os.environ.get("MUSIKBOX_DEFAULT_FORMAT", "flac"),
        audio_quality=os.environ.get("MUSIKBOX_AUDIO_QUALITY", "best"),
        cookies_from_browser=os.environ.get("MUSIKBOX_COOKIES_FROM_BROWSER"),
    )

    analysis = AnalysisConfig(
        write_tags=_env_bool("MUSIKBOX_WRITE_TAGS", default=True),
        key_notation=os.environ.get("MUSIKBOX_KEY_NOTATION", "camelot"),
        model_dir=Path(os.environ.get("MUSIKBOX_MODEL_DIR", str(config_dir / "models"))),
    )

    library_folders_path = config_dir / "library_folders.json"

    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

    return Config(
        music_dir=music_dir,
        db_path=db_path,
        auto_analyze=auto_analyze,
        download=download,
        analysis=analysis,
        library_folders_path=library_folders_path,
        anthropic_api_key=anthropic_api_key,
    )


def load_library_folders(config: Config) -> dict[str, Path]:
    """Load named library folders from JSON file.

    Returns a dict of name -> path.
    """
    if not config.library_folders_path.exists():
        return {}
    try:
        data = json.loads(config.library_folders_path.read_text())
        return {k: Path(v) for k, v in data.items()}
    except (json.JSONDecodeError, TypeError):
        return {}


def save_library_folders(config: Config, folders: dict[str, Path]) -> None:
    """Save named library folders to JSON file."""
    config.library_folders_path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: str(v) for k, v in folders.items()}
    config.library_folders_path.write_text(json.dumps(data, indent=2))
