from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from musikbox.cli.download import download
from musikbox.domain.models import Track, TrackId


def _make_track(**overrides: object) -> Track:
    defaults: dict[str, object] = {
        "id": TrackId(value="test-id"),
        "title": "Test Song",
        "artist": None,
        "album": None,
        "duration_seconds": 180.0,
        "file_path": Path("/music/test.wav"),
        "format": "wav",
        "bpm": None,
        "key": None,
        "genre": None,
        "mood": None,
        "source_url": "https://example.com/song",
        "downloaded_at": datetime(2025, 1, 1),
        "analyzed_at": None,
        "created_at": datetime(2025, 1, 1),
    }
    defaults.update(overrides)
    return Track(**defaults)  # type: ignore[arg-type]


def test_download_command_requires_url() -> None:
    runner = CliRunner()
    result = runner.invoke(download, [])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


@patch("musikbox.cli.download.console")
def test_download_command_accepts_format_option(mock_console: MagicMock) -> None:
    mock_service = MagicMock()
    mock_service.download.return_value = _make_track(format="flac")

    mock_app = MagicMock()
    mock_app.download_service = mock_service

    runner = CliRunner()
    result = runner.invoke(
        download,
        ["https://example.com/song", "--format", "flac"],
        obj=mock_app,
    )

    assert result.exit_code == 0
    mock_service.download.assert_called_once_with(
        "https://example.com/song", format="flac", analyze=None
    )
