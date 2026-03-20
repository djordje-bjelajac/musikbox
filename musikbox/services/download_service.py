from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import mutagen

from musikbox.domain.exceptions import DownloadError
from musikbox.domain.models import Track, TrackId
from musikbox.domain.ports.analyzer import Analyzer
from musikbox.domain.ports.downloader import Downloader
from musikbox.domain.ports.genre_lookup import GenreLookup
from musikbox.domain.ports.repository import TrackRepository


class DownloadService:
    """Orchestrates downloading, optional analysis, and persistence of tracks."""

    def __init__(
        self,
        downloader: Downloader,
        analyzer: Analyzer | None,
        repository: TrackRepository,
        music_dir: Path,
        default_format: str,
        auto_analyze: bool,
        genre_lookup: GenreLookup | None = None,
    ) -> None:
        self._downloader = downloader
        self._analyzer = analyzer
        self._repository = repository
        self._music_dir = music_dir
        self._default_format = default_format
        self._auto_analyze = auto_analyze
        self._genre_lookup = genre_lookup

    def download(
        self,
        url: str,
        format: str | None = None,
        analyze: bool | None = None,
    ) -> Track:
        fmt = format or self._default_format
        file_path = self._downloader.download(url, self._music_dir, fmt)

        title, artist, album, duration = _read_metadata(file_path)
        now = datetime.now(UTC)

        track = Track(
            id=TrackId(),
            title=title,
            artist=artist,
            album=album,
            duration_seconds=duration,
            file_path=file_path,
            format=fmt,
            bpm=None,
            key=None,
            genre=None,
            mood=None,
            source_url=url,
            downloaded_at=now,
            analyzed_at=None,
            created_at=now,
        )

        should_analyze = analyze if analyze is not None else self._auto_analyze
        if should_analyze and self._analyzer is not None:
            result = self._analyzer.analyze(file_path)
            track.bpm = result.bpm
            track.key = result.key
            track.genre = result.genre
            track.mood = result.mood
            track.analyzed_at = datetime.now(UTC)

        # Look up genre if still missing
        if not track.genre and self._genre_lookup is not None:
            try:
                genre, _ = self._genre_lookup.lookup(track.title, track.artist)
                if genre != "Unknown":
                    track.genre = genre
            except Exception:
                pass

        self._repository.save(track)
        return track

    def download_playlist(
        self,
        url: str,
        format: str | None = None,
        analyze: bool | None = None,
    ) -> Iterator[Track]:
        """Download all tracks in a playlist, yielding each Track as it completes."""
        fmt = format or self._default_format
        should_analyze = analyze if analyze is not None else self._auto_analyze

        for file_path, entry_url in self._downloader.download_playlist(url, self._music_dir, fmt):
            title, artist, album, duration = _read_metadata(file_path)
            now = datetime.now(UTC)

            track = Track(
                id=TrackId(),
                title=title,
                artist=artist,
                album=album,
                duration_seconds=duration,
                file_path=file_path,
                format=fmt,
                bpm=None,
                key=None,
                genre=None,
                mood=None,
                source_url=entry_url,
                downloaded_at=now,
                analyzed_at=None,
                created_at=now,
            )

            if should_analyze and self._analyzer is not None:
                try:
                    result = self._analyzer.analyze(file_path)
                    track.bpm = result.bpm
                    track.key = result.key
                    track.genre = result.genre
                    track.mood = result.mood
                    track.analyzed_at = datetime.now(UTC)
                except Exception:
                    pass  # Analysis failure shouldn't stop playlist download

            if not track.genre and self._genre_lookup is not None:
                try:
                    genre, _ = self._genre_lookup.lookup(track.title, track.artist)
                    if genre != "Unknown":
                        track.genre = genre
                except Exception:
                    pass

            self._repository.save(track)
            yield track


def _read_metadata(file_path: Path) -> tuple[str, str | None, str | None, float]:
    """Extract title, artist, album, and duration from an audio file using mutagen.

    If ID3 tags are missing, falls back to parsing "Artist - Title" from filename.
    """
    try:
        audio = mutagen.File(file_path)
    except Exception as e:
        raise DownloadError(f"Failed to read metadata from {file_path}: {e}") from e

    if audio is None:
        title, artist = _parse_filename(file_path.stem)
        return title, artist, None, 0.0

    duration = audio.info.length if audio.info else 0.0

    # mutagen stores tags differently per format; try common keys
    title = _first_tag(audio, "title", "TIT2")
    artist = _first_tag(audio, "artist", "TPE1")
    album = _first_tag(audio, "album", "TALB")

    # Fall back to filename parsing if tags are missing
    if not title or not artist:
        parsed_title, parsed_artist = _parse_filename(file_path.stem)
        if not title:
            title = parsed_title
        if not artist:
            artist = parsed_artist

    return title, artist, album, duration


def _parse_filename(stem: str) -> tuple[str, str | None]:
    """Parse 'Artist - Title' from a filename stem.

    Returns (title, artist). If no ' - ' separator found, returns
    (stem, None).
    """
    import re

    # Strip common YouTube junk
    junk = re.compile(
        r"\s*[\(\[](official\s*(music\s*)?video|official\s*audio|"
        r"lyric\s*video|lyrics|visuali[sz]er|audio|hd|hq|"
        r"\d{4}\s*remaster(ed)?|\dk\s*remaster(ed)?|"
        r"remaster(ed)?|live|explicit|clean)[\)\]]",
        re.IGNORECASE,
    )
    cleaned = junk.sub("", stem).strip()

    if " - " in cleaned:
        artist, title = cleaned.split(" - ", 1)
        return title.strip(), artist.strip()

    return cleaned, None


def _first_tag(audio: mutagen.FileType, *keys: str) -> str | None:
    """Return the first matching tag value as a string, or None."""
    for key in keys:
        value = audio.get(key)
        if value is not None:
            # mutagen may return lists; take the first element
            if isinstance(value, list):
                return str(value[0]) if value else None
            return str(value)
    return None
