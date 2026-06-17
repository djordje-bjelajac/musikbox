from datetime import datetime
from pathlib import Path

from musikbox.adapters.remote_stream_resolver import RemoteStreamResolver
from musikbox.domain.models import PlayableSource, Track, TrackId


def _make_track(track_id: str = "track-1") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title="Test Song",
        artist="Test Artist",
        album=None,
        duration_seconds=180.0,
        file_path=Path("/music/song.mp3"),
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
    resolver = RemoteStreamResolver(base_url="https://server.local")
    track = _make_track()

    source = resolver.resolve(track)

    assert isinstance(source, PlayableSource)


def test_resolve_uses_track_id_value() -> None:
    resolver = RemoteStreamResolver(base_url="https://server.local")
    track = _make_track(track_id="abc-123")

    source = resolver.resolve(track)

    assert source.track_id == "abc-123"


def test_resolve_builds_stream_url() -> None:
    resolver = RemoteStreamResolver(base_url="https://server.local")
    track = _make_track(track_id="abc-123")

    source = resolver.resolve(track)

    assert source.locator == "https://server.local/tracks/abc-123/stream"


def test_resolve_strips_trailing_slash_from_base_url() -> None:
    resolver = RemoteStreamResolver(base_url="https://server.local/")
    track = _make_track(track_id="abc-123")

    source = resolver.resolve(track)

    assert source.locator == "https://server.local/tracks/abc-123/stream"


def test_resolve_marks_source_as_not_local() -> None:
    resolver = RemoteStreamResolver(base_url="https://server.local")
    track = _make_track()

    source = resolver.resolve(track)

    assert source.is_local is False
