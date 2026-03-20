from pathlib import Path

import pytest

from musikbox.config.settings import Config, load_config


def test_load_config_returns_config_with_defaults(
    tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
) -> None:
    """load_config returns a Config with sensible defaults when no .env exists."""
    # Point config dir to a temp dir with no .env file
    monkeypatch.setenv("MUSIKBOX_CONFIG_DIR", str(tmp_path))
    # Clear any env vars that might interfere
    for var in [
        "MUSIKBOX_MUSIC_DIR",
        "MUSIKBOX_DB_PATH",
        "MUSIKBOX_AUTO_ANALYZE",
        "MUSIKBOX_OUTPUT_DIR",
        "MUSIKBOX_DEFAULT_FORMAT",
        "MUSIKBOX_AUDIO_QUALITY",
        "MUSIKBOX_WRITE_TAGS",
        "MUSIKBOX_KEY_NOTATION",
        "MUSIKBOX_MODEL_DIR",
    ]:
        monkeypatch.delenv(var, raising=False)

    config = load_config()

    assert isinstance(config, Config)
    assert isinstance(config.music_dir, Path)
    assert isinstance(config.db_path, Path)
    assert isinstance(config.download.output_dir, Path)
    assert isinstance(config.analysis.model_dir, Path)


def test_load_config_paths_are_path_objects(
    tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
) -> None:
    monkeypatch.setenv("MUSIKBOX_CONFIG_DIR", str(tmp_path))
    for var in [
        "MUSIKBOX_MUSIC_DIR",
        "MUSIKBOX_DB_PATH",
        "MUSIKBOX_OUTPUT_DIR",
        "MUSIKBOX_MODEL_DIR",
    ]:
        monkeypatch.delenv(var, raising=False)

    config = load_config()

    assert isinstance(config.music_dir, Path)
    assert isinstance(config.db_path, Path)
    assert isinstance(config.download.output_dir, Path)
    assert isinstance(config.analysis.model_dir, Path)


def test_load_config_env_vars_override_defaults(
    tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
) -> None:
    monkeypatch.setenv("MUSIKBOX_CONFIG_DIR", str(tmp_path))
    custom_music_dir = tmp_path / "my_music"
    monkeypatch.setenv("MUSIKBOX_MUSIC_DIR", str(custom_music_dir))

    config = load_config()

    assert config.music_dir == custom_music_dir


def test_load_config_download_config_has_defaults(
    tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
) -> None:
    monkeypatch.setenv("MUSIKBOX_CONFIG_DIR", str(tmp_path))
    for var in [
        "MUSIKBOX_MUSIC_DIR",
        "MUSIKBOX_DB_PATH",
        "MUSIKBOX_OUTPUT_DIR",
        "MUSIKBOX_DEFAULT_FORMAT",
        "MUSIKBOX_AUDIO_QUALITY",
    ]:
        monkeypatch.delenv(var, raising=False)

    config = load_config()

    assert isinstance(config.download.default_format, str)
    assert isinstance(config.download.audio_quality, str)


def test_load_config_analysis_config_has_defaults(
    tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
) -> None:
    monkeypatch.setenv("MUSIKBOX_CONFIG_DIR", str(tmp_path))
    for var in [
        "MUSIKBOX_MUSIC_DIR",
        "MUSIKBOX_DB_PATH",
        "MUSIKBOX_WRITE_TAGS",
        "MUSIKBOX_KEY_NOTATION",
        "MUSIKBOX_MODEL_DIR",
    ]:
        monkeypatch.delenv(var, raising=False)

    config = load_config()

    assert isinstance(config.analysis.write_tags, bool)
    assert isinstance(config.analysis.key_notation, str)
