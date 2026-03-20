import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from musikbox.adapters.metadata_writer import MutagenMetadataWriter
from musikbox.domain.exceptions import UnsupportedFormatError
from musikbox.domain.models import AnalysisResult
from musikbox.domain.ports.metadata_writer import MetadataWriter


def _create_test_wav(path: Path, duration: float = 0.1, sample_rate: int = 44100) -> None:
    """Generate a minimal WAV file with a 440 Hz sine wave."""
    num_samples = int(sample_rate * duration)
    samples = np.sin(2 * np.pi * 440 * np.linspace(0, duration, num_samples))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *[int(s * 32767) for s in samples]))


def _make_analysis() -> AnalysisResult:
    return AnalysisResult(
        bpm=128.0,
        key="Am",
        key_camelot="8A",
        genre="Techno",
        mood="Dark",
        confidence={"bpm": 0.95, "key": 0.9, "genre": 0.8, "mood": 0.7},
    )


def test_write_tags_to_wav_file(tmp_path: Path) -> None:
    wav_path = tmp_path / "test.wav"
    _create_test_wav(wav_path)
    analysis = _make_analysis()
    writer = MutagenMetadataWriter()

    # Should not raise - WAV writing may silently skip but must not error
    writer.write(wav_path, analysis)


def test_write_unsupported_format_raises_error(tmp_path: Path) -> None:
    unsupported_file = tmp_path / "test.aac"
    unsupported_file.write_text("fake audio data")
    analysis = _make_analysis()
    writer = MutagenMetadataWriter()

    with pytest.raises(UnsupportedFormatError, match="Unsupported format: .aac"):
        writer.write(unsupported_file, analysis)


def test_metadata_writer_implements_port() -> None:
    writer = MutagenMetadataWriter()
    assert isinstance(writer, MetadataWriter)
