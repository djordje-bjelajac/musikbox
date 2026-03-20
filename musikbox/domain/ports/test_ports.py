from pathlib import Path

import pytest

from musikbox.domain.models import AnalysisResult, SearchFilter, Track, TrackId
from musikbox.domain.ports.analyzer import Analyzer
from musikbox.domain.ports.downloader import Downloader
from musikbox.domain.ports.metadata_writer import MetadataWriter
from musikbox.domain.ports.repository import TrackRepository


def test_track_repository_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        TrackRepository()  # type: ignore[abstract]


def test_downloader_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        Downloader()  # type: ignore[abstract]


def test_analyzer_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        Analyzer()  # type: ignore[abstract]


def test_metadata_writer_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        MetadataWriter()  # type: ignore[abstract]


def test_concrete_repository_can_be_instantiated() -> None:
    class FakeRepository(TrackRepository):
        async def save(self, track: Track) -> None:
            pass

        async def get_by_id(self, track_id: TrackId) -> Track | None:
            return None

        async def delete(self, track_id: TrackId) -> None:
            pass

        async def search(self, filter: SearchFilter) -> list[Track]:
            return []

        async def get_by_file_path(self, file_path: Path) -> Track | None:
            return None

        async def list_all(self) -> list[Track]:
            return []

    repo = FakeRepository()
    assert isinstance(repo, TrackRepository)


def test_concrete_downloader_can_be_instantiated() -> None:
    class FakeDownloader(Downloader):
        def download(self, url: str, output_dir: Path, format: str) -> Path:
            return output_dir / "fake.mp3"

        def download_playlist(self, url: str, output_dir: Path, format: str):  # type: ignore[override]
            yield output_dir / "fake.mp3", "https://example.com/track"

    dl = FakeDownloader()
    assert isinstance(dl, Downloader)


def test_concrete_analyzer_can_be_instantiated() -> None:
    class FakeAnalyzer(Analyzer):
        async def analyze(self, file_path: Path) -> AnalysisResult:
            return AnalysisResult(
                bpm=120.0,
                key="Am",
                key_camelot="8A",
                genre="house",
                mood="chill",
                confidence={"bpm": 1.0},
            )

    analyzer = FakeAnalyzer()
    assert isinstance(analyzer, Analyzer)


def test_concrete_metadata_writer_can_be_instantiated() -> None:
    class FakeMetadataWriter(MetadataWriter):
        async def write(self, file_path: Path, analysis: AnalysisResult) -> None:
            pass

    writer = FakeMetadataWriter()
    assert isinstance(writer, MetadataWriter)
