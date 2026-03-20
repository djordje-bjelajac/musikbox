import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from click.testing import CliRunner

from musikbox.cli.main import cli
from musikbox.domain.models import AnalysisResult


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


def test_analyze_command_with_file(tmp_path: Path) -> None:
    wav_path = tmp_path / "test.wav"
    _create_test_wav(wav_path)

    mock_app = MagicMock()
    mock_app.analysis_service.analyze_file.return_value = _make_analysis_result()

    with patch("musikbox.cli.main.create_app", return_value=mock_app):
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", str(wav_path)])

    assert result.exit_code == 0
    mock_app.analysis_service.analyze_file.assert_called_once_with(wav_path)


def test_analyze_command_with_recursive_flag(tmp_path: Path) -> None:
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    _create_test_wav(sub_dir / "track.wav")

    mock_app = MagicMock()
    mock_app.analysis_service.analyze_directory.return_value = [_make_analysis_result()]

    with patch("musikbox.cli.main.create_app", return_value=mock_app):
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", str(tmp_path), "--recursive"])

    assert result.exit_code == 0
    mock_app.analysis_service.analyze_directory.assert_called_once_with(tmp_path, recursive=True)
