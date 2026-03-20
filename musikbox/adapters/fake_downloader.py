import shutil
import struct
from collections.abc import Iterator
from pathlib import Path

from musikbox.domain.ports.downloader import Downloader


class FakeDownloader(Downloader):
    """Downloader that produces files locally without network access.

    If ``fake_file_path`` is given, that file is copied into *output_dir*.
    Otherwise a minimal WAV file (1 second of silence) is created.
    """

    def __init__(self, fake_file_path: Path | None = None) -> None:
        self._fake_file_path = fake_file_path

    def download(self, url: str, output_dir: Path, format: str) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)

        if self._fake_file_path is not None:
            dest = output_dir / self._fake_file_path.name
            shutil.copy2(self._fake_file_path, dest)
            return dest

        dest = output_dir / f"fake_download.{format}"
        _write_minimal_wav(dest)
        return dest

    def download_playlist(self, url: str, output_dir: Path, format: str) -> Iterator[Path]:
        for i in range(3):
            dest = output_dir / f"fake_track_{i}.{format}"
            _write_minimal_wav(dest)
            yield dest


def _write_minimal_wav(path: Path) -> None:
    """Write a minimal 1-second mono 16-bit 44100 Hz silent WAV file using struct."""
    sample_rate = 44100
    num_channels = 1
    bits_per_sample = 16
    num_samples = sample_rate  # 1 second
    bytes_per_sample = bits_per_sample // 8
    data_size = num_samples * num_channels * bytes_per_sample
    fmt_chunk_size = 16

    with open(path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        # fmt sub-chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", fmt_chunk_size))
        f.write(struct.pack("<H", 1))  # PCM
        f.write(struct.pack("<H", num_channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", sample_rate * num_channels * bytes_per_sample))
        f.write(struct.pack("<H", num_channels * bytes_per_sample))
        f.write(struct.pack("<H", bits_per_sample))
        # data sub-chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)
