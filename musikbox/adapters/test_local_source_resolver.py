from datetime import datetime
from pathlib import Path

from musikbox.adapters.local_source_resolver import LocalSourceResolver
from musikbox.domain.models import PlayableSource, Track, TrackId


def _make_track(file_path: Path, track_id: str = "track-1") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title="Test Song",
        artist="Test Artist",
        album=None,
        duration_seconds=180.0,
        file_path=file_path,
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


def test_resolve_returns_playable_source() -> None:
    resolver = LocalSourceResolver()
    track = _make_track(Path("/music/song.mp3"))

    source = resolver.resolve(track)

    assert isinstance(source, PlayableSource)


def test_resolve_uses_track_id_value() -> None:
    resolver = LocalSourceResolver()
    track = _make_track(Path("/music/song.mp3"), track_id="abc-123")

    source = resolver.resolve(track)

    assert source.track_id == "abc-123"


def test_resolve_locator_is_string_file_path() -> None:
    resolver = LocalSourceResolver()
    track = _make_track(Path("/music/song.flac"))

    source = resolver.resolve(track)

    assert source.locator == "/music/song.flac"
    assert isinstance(source.locator, str)


def test_resolve_marks_source_as_local() -> None:
    resolver = LocalSourceResolver()
    track = _make_track(Path("/music/song.mp3"))

    source = resolver.resolve(track)

    assert source.is_local is True
