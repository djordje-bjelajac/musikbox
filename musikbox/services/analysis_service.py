from datetime import UTC, datetime
from pathlib import Path

from musikbox.domain.models import AnalysisResult, TrackId
from musikbox.domain.ports.analyzer import Analyzer
from musikbox.domain.ports.genre_lookup import GenreLookup
from musikbox.domain.ports.metadata_writer import MetadataWriter
from musikbox.domain.ports.repository import TrackRepository

AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg"}


class AnalysisService:
    """Orchestrates audio analysis, metadata writing, and track updates."""

    def __init__(
        self,
        analyzer: Analyzer,
        repository: TrackRepository,
        metadata_writer: MetadataWriter,
        write_tags: bool,
        key_notation: str,
        genre_lookup: GenreLookup | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._repository = repository
        self._metadata_writer = metadata_writer
        self._write_tags = write_tags
        self._key_notation = key_notation
        self._genre_lookup = genre_lookup

    def analyze_file(self, file_path: Path, track_id: str | None = None) -> AnalysisResult:
        """Analyze a single audio file.

        Args:
            file_path: Path to the audio file.
            track_id: Optional track ID to update in the repository.

        Returns:
            The analysis result.
        """
        result = self._analyzer.analyze(file_path)

        if result.genre == "Unknown" and self._genre_lookup is not None and track_id is not None:
            track = self._repository.get_by_id(TrackId(value=track_id))
            if track.title:
                try:
                    genre, confidence = self._genre_lookup.lookup(track.title, track.artist)
                    result.genre = genre
                    result.confidence["genre"] = confidence
                except Exception:
                    pass

        if self._write_tags:
            self._metadata_writer.write(file_path, result)

        if track_id is not None:
            track = self._repository.get_by_id(TrackId(value=track_id))
            track.bpm = result.bpm
            track.key = result.key
            track.genre = result.genre
            track.mood = result.mood
            track.analyzed_at = datetime.now(UTC)
            self._repository.save(track)

        return result

    def analyze_directory(self, dir_path: Path, recursive: bool = False) -> list[AnalysisResult]:
        """Analyze all audio files in a directory.

        Args:
            dir_path: Path to the directory.
            recursive: Whether to search subdirectories.

        Returns:
            List of analysis results for each file.
        """
        results: list[AnalysisResult] = []

        if recursive:
            files = sorted(dir_path.rglob("*"))
        else:
            files = sorted(dir_path.iterdir())

        for file_path in files:
            if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTENSIONS:
                result = self.analyze_file(file_path)
                results.append(result)

        return results
