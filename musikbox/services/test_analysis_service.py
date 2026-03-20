import struct
import wave
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from musikbox.domain.models import AnalysisResult, Track, TrackId
from musikbox.domain.ports.analyzer import Analyzer
from musikbox.domain.ports.metadata_writer import MetadataWriter
from musikbox.domain.ports.repository import TrackRepository
from musikbox.services.analysis_service import AnalysisService


def _create_test_wav(path: Path, duration: float = 0.1, sample_rate: int = 44100) -> None:
    num_samples = int(sample_rate * duration)
    samples = np.sin(2 * np.pi * 440 * np.linspace(0, duration, num_samples))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *[int(s * 32767) for s in samples]))


def _make_analysis_result() -> AnalysisResult:
    return AnalysisResult(
        bpm=128.0,
        key="Am",
        key_camelot="8A",
        genre="Techno",
        mood="Dark",
        confidence={"bpm": 0.95, "key": 0.9, "genre": 0.8, "mood": 0.7},
    )


def _make_track(track_id: str = "test-id") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title="Test Song",
        artist=None,
        album=None,
        duration_seconds=180.0,
        file_path=Path("/music/test.mp3"),
        format="mp3",
        bpm=None,
        key=None,
        genre=None,
        mood=None,
        source_url=None,
        downloaded_at=None,
        analyzed_at=None,
        created_at=datetime(2025, 1, 1),
    )


def _build_service(
    *,
    analyzer: Analyzer | None = None,
    repository: TrackRepository | None = None,
    metadata_writer: MetadataWriter | None = None,
    write_tags: bool = False,
    key_notation: str = "standard",
) -> tuple[AnalysisService, MagicMock, MagicMock, MagicMock]:
    mock_analyzer = analyzer or MagicMock(spec=Analyzer)
    mock_repo = repository or MagicMock(spec=TrackRepository)
    mock_writer = metadata_writer or MagicMock(spec=MetadataWriter)

    if isinstance(mock_analyzer, MagicMock):
        mock_analyzer.analyze.return_value = _make_analysis_result()

    service = AnalysisService(
        analyzer=mock_analyzer,
        repository=mock_repo,
        metadata_writer=mock_writer,
        write_tags=write_tags,
        key_notation=key_notation,
    )
    return service, mock_analyzer, mock_repo, mock_writer


def test_analyze_file_calls_analyzer() -> None:
    service, mock_analyzer, _, _ = _build_service()
    file_path = Path("/tmp/test.mp3")

    result = service.analyze_file(file_path)

    mock_analyzer.analyze.assert_called_once_with(file_path)
    assert result.bpm == 128.0
    assert result.key == "Am"


def test_analyze_file_writes_tags_when_enabled() -> None:
    service, _, _, mock_writer = _build_service(write_tags=True)
    file_path = Path("/tmp/test.mp3")

    result = service.analyze_file(file_path)

    mock_writer.write.assert_called_once_with(file_path, result)


def test_analyze_file_skips_tags_when_disabled() -> None:
    service, _, _, mock_writer = _build_service(write_tags=False)
    file_path = Path("/tmp/test.mp3")

    service.analyze_file(file_path)

    mock_writer.write.assert_not_called()


def test_analyze_file_updates_track_when_id_provided() -> None:
    track = _make_track("my-track-id")
    mock_repo = MagicMock(spec=TrackRepository)
    mock_repo.get_by_id.return_value = track

    service, _, _, _ = _build_service(repository=mock_repo)

    service.analyze_file(Path("/tmp/test.mp3"), track_id="my-track-id")

    mock_repo.get_by_id.assert_called_once()
    mock_repo.save.assert_called_once()
    saved_track = mock_repo.save.call_args[0][0]
    assert saved_track.bpm == 128.0
    assert saved_track.key == "Am"
    assert saved_track.genre == "Techno"
    assert saved_track.mood == "Dark"
    assert saved_track.analyzed_at is not None


def test_analyze_directory_finds_audio_files(tmp_path: Path) -> None:
    # Create audio files with various extensions
    for name in ["song1.mp3", "song2.flac", "song3.wav"]:
        _create_test_wav(tmp_path / name)

    # Create non-audio files that should be ignored
    (tmp_path / "notes.txt").write_text("not audio")
    (tmp_path / "image.jpg").write_bytes(b"not audio")

    service, mock_analyzer, _, _ = _build_service()

    results = service.analyze_directory(tmp_path)

    assert len(results) == 3
    assert mock_analyzer.analyze.call_count == 3
