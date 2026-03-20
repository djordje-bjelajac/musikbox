import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class DownloadConfig:
    output_dir: Path
    default_format: str
    audio_quality: str


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
    lastfm_api_key: str | None


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
    )

    analysis = AnalysisConfig(
        write_tags=_env_bool("MUSIKBOX_WRITE_TAGS", default=True),
        key_notation=os.environ.get("MUSIKBOX_KEY_NOTATION", "camelot"),
        model_dir=Path(os.environ.get("MUSIKBOX_MODEL_DIR", str(config_dir / "models"))),
    )

    lastfm_api_key = os.environ.get("MUSIKBOX_LASTFM_API_KEY")

    return Config(
        music_dir=music_dir,
        db_path=db_path,
        auto_analyze=auto_analyze,
        download=download,
        analysis=analysis,
        lastfm_api_key=lastfm_api_key,
    )
