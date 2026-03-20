from pathlib import Path

from musikbox.adapters.fake_downloader import FakeDownloader
from musikbox.domain.ports.downloader import Downloader


def test_fake_downloader_creates_file_in_output_dir(tmp_path: Path) -> None:
    downloader = FakeDownloader()
    result = downloader.download("https://example.com/song", tmp_path, "wav")
    assert result.exists()
    assert result.parent == tmp_path


def test_fake_downloader_returns_path_to_created_file(tmp_path: Path) -> None:
    downloader = FakeDownloader()
    result = downloader.download("https://example.com/song", tmp_path, "wav")
    assert result == tmp_path / "fake_download.wav"
    assert result.stat().st_size > 0


def test_fake_downloader_with_provided_file_copies_it(tmp_path: Path) -> None:
    source = tmp_path / "original.mp3"
    source.write_bytes(b"fake audio content")

    output_dir = tmp_path / "output"
    downloader = FakeDownloader(fake_file_path=source)
    result = downloader.download("https://example.com/song", output_dir, "mp3")

    assert result == output_dir / "original.mp3"
    assert result.read_bytes() == b"fake audio content"


def test_fake_downloader_implements_downloader_port() -> None:
    downloader = FakeDownloader()
    assert isinstance(downloader, Downloader)
