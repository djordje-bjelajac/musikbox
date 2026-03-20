"""Full-stack integration tests using real adapters with test doubles for I/O."""

import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from musikbox.adapters.fake_analyzer import FakeAnalyzer
from musikbox.adapters.fake_downloader import FakeDownloader
from musikbox.adapters.metadata_writer import MutagenMetadataWriter
from musikbox.adapters.migrations import init_db
from musikbox.adapters.sqlite_repository import SqliteRepository
from musikbox.domain.models import SearchFilter
from musikbox.services.analysis_service import AnalysisService
from musikbox.services.download_service import DownloadService
from musikbox.services.library_service import LibraryService


def _create_test_wav(path: Path, duration: float = 0.1, sample_rate: int = 44100) -> None:
    """Generate a minimal WAV file with a 440 Hz sine wave."""
    num_samples = int(sample_rate * duration)
    samples = np.sin(2 * np.pi * 440 * np.linspace(0, duration, num_samples))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *[int(s * 32767) for s in samples]))


@pytest.fixture()
def repo(tmp_path: Path) -> SqliteRepository:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return SqliteRepository(db_path)


def test_download_and_analyze_full_flow(repo: SqliteRepository, tmp_path: Path) -> None:
    """Download a track with auto_analyze=True and verify it is saved with analysis data."""
    music_dir = tmp_path / "music"
    downloader = FakeDownloader()
    analyzer = FakeAnalyzer(bpm=140.0, key="Cm", genre="Techno", mood="Dark")

    service = DownloadService(
        downloader=downloader,
        analyzer=analyzer,
        repository=repo,
        music_dir=music_dir,
        default_format="wav",
        auto_analyze=True,
    )

    track = service.download("https://example.com/track")

    assert track.file_path.exists()
    assert track.bpm == 140.0
    assert track.key == "Cm"
    assert track.genre == "Techno"
    assert track.mood == "Dark"
    assert track.analyzed_at is not None
    assert track.source_url == "https://example.com/track"

    # Verify persistence through the repository
    saved = repo.get_by_id(track.id)
    assert saved.title == track.title
    assert saved.bpm == 140.0
    assert saved.key == "Cm"


def test_import_and_search_flow(repo: SqliteRepository, tmp_path: Path) -> None:
    """Import a real WAV file and verify search by various filters returns it."""
    wav_path = tmp_path / "sine_wave.wav"
    _create_test_wav(wav_path)

    library = LibraryService(repo)

    track = library.import_file(wav_path)
    assert track.title == "sine_wave"
    assert track.format == "wav"

    # Search by title
    results = library.search_tracks(SearchFilter(title="sine"))
    assert len(results) == 1
    assert results[0].id.value == track.id.value

    # Search by query (matches title or artist)
    results = library.search_tracks(SearchFilter(query="sine_wave"))
    assert len(results) == 1

    # Verify list_tracks includes the imported track
    all_tracks = library.list_tracks()
    assert len(all_tracks) == 1
    assert all_tracks[0].id.value == track.id.value


def test_analyze_and_write_tags_flow(tmp_path: Path) -> None:
    """Analyze a real WAV file with write_tags=True and verify the result."""
    wav_path = tmp_path / "test_analyze.wav"
    _create_test_wav(wav_path)

    analyzer = FakeAnalyzer(bpm=125.0, key="Fm", key_camelot="4A", genre="House", mood="Groovy")
    writer = MutagenMetadataWriter()

    # Repository not needed for file-only analysis (no track_id passed)
    db_path = tmp_path / "analysis.db"
    init_db(db_path)
    repo = SqliteRepository(db_path)

    service = AnalysisService(
        analyzer=analyzer,
        repository=repo,
        metadata_writer=writer,
        write_tags=True,
        key_notation="camelot",
    )

    result = service.analyze_file(wav_path)

    assert result.bpm == 125.0
    assert result.key == "Fm"
    assert result.genre == "House"
    assert result.mood == "Groovy"
    assert result.key_camelot == "4A"
    assert result.confidence["bpm"] == 0.9
