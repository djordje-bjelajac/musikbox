import csv
from datetime import datetime
from pathlib import Path

import mutagen

from musikbox.domain.exceptions import UnsupportedFormatError
from musikbox.domain.models import SearchFilter, Track, TrackId
from musikbox.domain.ports.repository import TrackRepository

_SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".wma"}


class LibraryService:
    """Orchestrates library operations using the TrackRepository port."""

    def __init__(self, repository: TrackRepository) -> None:
        self._repository = repository

    def list_tracks(self, limit: int = 50, offset: int = 0) -> list[Track]:
        return self._repository.list_all(limit=limit, offset=offset)

    def get_track(self, track_id: str) -> Track:
        return self._repository.get_by_id(TrackId(value=track_id))

    def get_track_by_file_path(self, file_path: Path) -> Track | None:
        return self._repository.get_by_file_path(file_path.resolve())

    def search_tracks(self, search_filter: SearchFilter) -> list[Track]:
        return self._repository.search(search_filter)

    def delete_track(self, track_id: str) -> None:
        self._repository.delete(TrackId(value=track_id))

    def import_file(self, file_path: Path) -> Track:
        file_path = file_path.resolve()

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in _SUPPORTED_EXTENSIONS:
            raise UnsupportedFormatError(f"Unsupported format: {suffix}")

        audio = mutagen.File(file_path)

        title = _extract_tag(audio, "title") or file_path.stem
        artist = _extract_tag(audio, "artist")
        album = _extract_tag(audio, "album")
        duration = audio.info.length if audio and audio.info else 0.0

        track = Track(
            id=TrackId(),
            title=title,
            artist=artist,
            album=album,
            duration_seconds=duration,
            file_path=file_path,
            format=suffix.lstrip("."),
            bpm=None,
            key=None,
            genre=_extract_tag(audio, "genre"),
            mood=None,
            source_url=None,
            downloaded_at=None,
            analyzed_at=None,
            created_at=datetime.now(),
        )

        self._repository.save(track)
        return track

    def import_directory(self, dir_path: Path, recursive: bool = False) -> list[Track]:
        dir_path = dir_path.resolve()

        if not dir_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {dir_path}")

        pattern = "**/*" if recursive else "*"
        imported: list[Track] = []

        for file_path in sorted(dir_path.glob(pattern)):
            if file_path.is_file() and file_path.suffix.lower() in _SUPPORTED_EXTENSIONS:
                track = self.import_file(file_path)
                imported.append(track)

        return imported

    def export_csv(self, output_path: Path) -> None:
        tracks = self._repository.list_all(limit=10_000, offset=0)

        fieldnames = [
            "id",
            "title",
            "artist",
            "album",
            "duration_seconds",
            "file_path",
            "format",
            "bpm",
            "key",
            "genre",
            "mood",
            "source_url",
            "downloaded_at",
            "analyzed_at",
            "created_at",
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for track in tracks:
                writer.writerow(
                    {
                        "id": track.id.value,
                        "title": track.title,
                        "artist": track.artist,
                        "album": track.album,
                        "duration_seconds": track.duration_seconds,
                        "file_path": str(track.file_path),
                        "format": track.format,
                        "bpm": track.bpm,
                        "key": track.key,
                        "genre": track.genre,
                        "mood": track.mood,
                        "source_url": track.source_url,
                        "downloaded_at": (
                            track.downloaded_at.isoformat() if track.downloaded_at else None
                        ),
                        "analyzed_at": (
                            track.analyzed_at.isoformat() if track.analyzed_at else None
                        ),
                        "created_at": track.created_at.isoformat(),
                    }
                )


def _extract_tag(audio: mutagen.FileType | None, tag_name: str) -> str | None:
    """Extract a tag value from a mutagen audio file, handling various tag formats."""
    if audio is None or audio.tags is None:
        return None

    # Try common tag key formats
    for key in [tag_name, tag_name.upper(), tag_name.capitalize()]:
        value = audio.tags.get(key)
        if value is not None:
            if isinstance(value, list):
                return str(value[0]) if value else None
            return str(value)

    # Try ID3-style keys (e.g., TIT2 for title, TPE1 for artist)
    _id3_map = {
        "title": "TIT2",
        "artist": "TPE1",
        "album": "TALB",
        "genre": "TCON",
    }
    id3_key = _id3_map.get(tag_name)
    if id3_key:
        value = audio.tags.get(id3_key)
        if value is not None:
            return str(value)

    return None
