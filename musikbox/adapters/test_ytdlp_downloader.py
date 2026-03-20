from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from musikbox.adapters.ytdlp_downloader import YtdlpDownloader
from musikbox.domain.exceptions import DownloadError
from musikbox.domain.ports.downloader import Downloader


def test_ytdlp_downloader_implements_downloader_port() -> None:
    downloader = YtdlpDownloader()
    assert isinstance(downloader, Downloader)


@patch("musikbox.adapters.ytdlp_downloader.yt_dlp")
def test_download_calls_ytdlp_with_correct_options(mock_yt_dlp: MagicMock, tmp_path: Path) -> None:
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
    mock_ydl_instance.__exit__ = MagicMock(return_value=False)

    title = "My Song"
    mock_ydl_instance.extract_info.return_value = {"title": title}
    mock_yt_dlp.YoutubeDL.return_value = mock_ydl_instance

    # Create the expected output file so the downloader finds it
    expected_file = tmp_path / f"{title}.flac"
    expected_file.write_bytes(b"fake audio")

    downloader = YtdlpDownloader(audio_quality="320")
    result = downloader.download("https://example.com/song", tmp_path, "flac")

    mock_yt_dlp.YoutubeDL.assert_called_once()
    opts = mock_yt_dlp.YoutubeDL.call_args[0][0]
    assert opts["format"] == "bestaudio/best"
    assert opts["extract_audio"] is True
    assert opts["postprocessors"][0]["preferredcodec"] == "flac"
    assert opts["postprocessors"][0]["preferredquality"] == "320"
    assert opts["quiet"] is True

    mock_ydl_instance.extract_info.assert_called_once_with(
        "https://example.com/song", download=True
    )
    assert result == expected_file


@patch("musikbox.adapters.ytdlp_downloader.yt_dlp")
def test_download_raises_domain_error_on_ytdlp_failure(
    mock_yt_dlp: MagicMock, tmp_path: Path
) -> None:
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
    mock_ydl_instance.__exit__ = MagicMock(return_value=False)

    # Make yt_dlp.utils.DownloadError a real exception class for the raise
    mock_yt_dlp.utils.DownloadError = type("DownloadError", (Exception,), {})
    mock_ydl_instance.extract_info.side_effect = mock_yt_dlp.utils.DownloadError(
        "video unavailable"
    )
    mock_yt_dlp.YoutubeDL.return_value = mock_ydl_instance

    downloader = YtdlpDownloader()
    with pytest.raises(DownloadError, match="Failed to download"):
        downloader.download("https://example.com/bad", tmp_path, "mp3")
