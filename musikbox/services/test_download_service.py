import struct
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from musikbox.domain.exceptions import DownloadError
from musikbox.domain.models import AnalysisResult
from musikbox.domain.ports.analyzer import Analyzer
from musikbox.domain.ports.downloader import Downloader
from musikbox.domain.ports.repository import TrackRepository
from musikbox.services.download_service import DownloadService


def _write_wav(path: Path) -> None:
    """Write a minimal valid WAV file (1 second of silence)."""
    sample_rate = 44100
    num_samples = sample_rate
    data_size = num_samples * 2  # 16-bit mono
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack("<H", 1))  # PCM
        f.write(struct.pack("<H", 1))  # mono
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", sample_rate * 2))
        f.write(struct.pack("<H", 2))
        f.write(struct.pack("<H", 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)


def _make_service(
    downloader: Downloader,
    repository: TrackRepository,
    analyzer: Analyzer | None = None,
    music_dir: Path = Path("/tmp/music"),
    auto_analyze: bool = False,
) -> DownloadService:
    return DownloadService(
        downloader=downloader,
        analyzer=analyzer,
        repository=repository,
        music_dir=music_dir,
        default_format="wav",
        auto_analyze=auto_analyze,
    )


def test_download_calls_downloader_and_saves_track(tmp_path: Path) -> None:
    wav_file = tmp_path / "song.wav"
    _write_wav(wav_file)

    mock_downloader = MagicMock(spec=Downloader)
    mock_downloader.download.return_value = wav_file

    mock_repo = MagicMock(spec=TrackRepository)

    service = _make_service(mock_downloader, mock_repo, music_dir=tmp_path)
    track = service.download("https://example.com/song")

    mock_downloader.download.assert_called_once_with("https://example.com/song", tmp_path, "wav")
    mock_repo.save.assert_called_once()
    saved_track = mock_repo.save.call_args[0][0]
    assert saved_track.title == "song"
    assert saved_track.source_url == "https://example.com/song"
    assert saved_track.file_path == wav_file
    assert track is saved_track


def test_download_with_auto_analyze_calls_analyzer(tmp_path: Path) -> None:
    wav_file = tmp_path / "song.wav"
    _write_wav(wav_file)

    mock_downloader = MagicMock(spec=Downloader)
    mock_downloader.download.return_value = wav_file

    mock_analyzer = MagicMock(spec=Analyzer)
    mock_analyzer.analyze.return_value = AnalysisResult(
        bpm=128.0,
        key="Am",
        key_camelot="8A",
        genre="Techno",
        mood="Energetic",
        confidence={"bpm": 0.9},
    )

    mock_repo = MagicMock(spec=TrackRepository)

    service = _make_service(
        mock_downloader, mock_repo, analyzer=mock_analyzer, music_dir=tmp_path, auto_analyze=True
    )
    track = service.download("https://example.com/song")

    mock_analyzer.analyze.assert_called_once_with(wav_file)
    assert track.bpm == 128.0
    assert track.key == "Am"
    assert track.genre == "Techno"
    assert track.mood == "Energetic"
    assert track.analyzed_at is not None


def test_download_with_no_analyze_skips_analysis(tmp_path: Path) -> None:
    wav_file = tmp_path / "song.wav"
    _write_wav(wav_file)

    mock_downloader = MagicMock(spec=Downloader)
    mock_downloader.download.return_value = wav_file

    mock_analyzer = MagicMock(spec=Analyzer)
    mock_repo = MagicMock(spec=TrackRepository)

    service = _make_service(
        mock_downloader, mock_repo, analyzer=mock_analyzer, music_dir=tmp_path, auto_analyze=True
    )
    track = service.download("https://example.com/song", analyze=False)

    mock_analyzer.analyze.assert_not_called()
    assert track.bpm is None
    assert track.analyzed_at is None


def test_download_raises_download_error_on_failure(tmp_path: Path) -> None:
    mock_downloader = MagicMock(spec=Downloader)
    mock_downloader.download.side_effect = DownloadError("network error")

    mock_repo = MagicMock(spec=TrackRepository)

    service = _make_service(mock_downloader, mock_repo, music_dir=tmp_path)
    with pytest.raises(DownloadError, match="network error"):
        service.download("https://example.com/bad")
