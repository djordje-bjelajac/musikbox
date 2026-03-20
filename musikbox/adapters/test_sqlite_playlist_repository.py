from datetime import datetime
from pathlib import Path

import pytest

from musikbox.adapters.migrations import init_db
from musikbox.adapters.sqlite_playlist_repository import SqlitePlaylistRepository
from musikbox.adapters.sqlite_repository import SqliteRepository
from musikbox.domain.exceptions import DatabaseError
from musikbox.domain.models import Playlist, Track, TrackId


def _make_track(track_id: str = "track-1", **overrides: object) -> Track:
    """Helper to build a Track with sensible defaults."""
    defaults: dict[str, object] = {
        "id": TrackId(value=track_id),
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "duration_seconds": 180.0,
        "file_path": Path(f"/music/{track_id}.mp3"),
        "format": "mp3",
        "bpm": 128.0,
        "key": "Am",
        "genre": "techno",
        "mood": "energetic",
        "source_url": "https://example.com/song",
        "downloaded_at": datetime(2025, 6, 1, 12, 0, 0),
        "analyzed_at": datetime(2025, 6, 1, 12, 5, 0),
        "created_at": datetime(2025, 6, 1, 12, 0, 0),
    }
    defaults.update(overrides)
    return Track(**defaults)  # type: ignore[arg-type]


def _make_playlist(
    playlist_id: str = "pl-1",
    name: str = "My Playlist",
) -> Playlist:
    now = datetime(2025, 6, 1, 12, 0, 0)
    return Playlist(id=playlist_id, name=name, created_at=now, updated_at=now)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Initialize a SQLite DB with both tracks and playlists tables."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture()
def repo(db_path: Path) -> SqlitePlaylistRepository:
    return SqlitePlaylistRepository(db_path)


@pytest.fixture()
def track_repo(db_path: Path) -> SqliteRepository:
    return SqliteRepository(db_path)


def test_create_playlist_and_get_by_name(repo: SqlitePlaylistRepository) -> None:
    playlist = _make_playlist()
    repo.create(playlist)

    result = repo.get_by_name("My Playlist")

    assert result is not None
    assert result.id == "pl-1"
    assert result.name == "My Playlist"
    assert result.created_at == datetime(2025, 6, 1, 12, 0, 0)


def test_create_playlist_duplicate_name_raises(repo: SqlitePlaylistRepository) -> None:
    repo.create(_make_playlist(playlist_id="pl-1", name="Duplicate"))
    with pytest.raises(DatabaseError, match="already exists"):
        repo.create(_make_playlist(playlist_id="pl-2", name="Duplicate"))


def test_list_all_playlists(repo: SqlitePlaylistRepository) -> None:
    repo.create(_make_playlist(playlist_id="pl-1", name="Alpha"))
    repo.create(_make_playlist(playlist_id="pl-2", name="Beta"))
    repo.create(_make_playlist(playlist_id="pl-3", name="Charlie"))

    playlists = repo.list_all()

    assert len(playlists) == 3
    # list_all orders by name
    assert [p.name for p in playlists] == ["Alpha", "Beta", "Charlie"]


def test_delete_playlist(repo: SqlitePlaylistRepository) -> None:
    repo.create(_make_playlist())
    repo.delete("pl-1")

    result = repo.get_by_name("My Playlist")
    assert result is None


def test_add_track_to_playlist(
    repo: SqlitePlaylistRepository,
    track_repo: SqliteRepository,
) -> None:
    track = _make_track("track-1")
    track_repo.save(track)
    repo.create(_make_playlist())

    repo.add_track("pl-1", "track-1", 0)

    tracks = repo.get_tracks("pl-1")
    assert len(tracks) == 1
    assert tracks[0].id.value == "track-1"


def test_add_duplicate_track_skipped(
    repo: SqlitePlaylistRepository,
    track_repo: SqliteRepository,
) -> None:
    track = _make_track("track-1")
    track_repo.save(track)
    repo.create(_make_playlist())

    repo.add_track("pl-1", "track-1", 0)
    repo.add_track("pl-1", "track-1", 1)  # duplicate — should be silently skipped

    tracks = repo.get_tracks("pl-1")
    assert len(tracks) == 1


def test_remove_track_from_playlist(
    repo: SqlitePlaylistRepository,
    track_repo: SqliteRepository,
) -> None:
    track_repo.save(_make_track("track-1"))
    track_repo.save(_make_track("track-2"))
    repo.create(_make_playlist())
    repo.add_track("pl-1", "track-1", 0)
    repo.add_track("pl-1", "track-2", 1)

    repo.remove_track("pl-1", "track-1")

    tracks = repo.get_tracks("pl-1")
    assert len(tracks) == 1
    assert tracks[0].id.value == "track-2"


def test_get_tracks_returns_ordered_tracks(
    repo: SqlitePlaylistRepository,
    track_repo: SqliteRepository,
) -> None:
    for i in range(3):
        track_repo.save(_make_track(f"track-{i}", title=f"Song {i}"))
    repo.create(_make_playlist())
    # Add in reverse order with explicit positions
    repo.add_track("pl-1", "track-2", 0)
    repo.add_track("pl-1", "track-0", 1)
    repo.add_track("pl-1", "track-1", 2)

    tracks = repo.get_tracks("pl-1")

    assert [t.id.value for t in tracks] == ["track-2", "track-0", "track-1"]


def test_reorder_tracks(
    repo: SqlitePlaylistRepository,
    track_repo: SqliteRepository,
) -> None:
    for i in range(3):
        track_repo.save(_make_track(f"track-{i}"))
    repo.create(_make_playlist())
    repo.add_track("pl-1", "track-0", 0)
    repo.add_track("pl-1", "track-1", 1)
    repo.add_track("pl-1", "track-2", 2)

    # Reverse the order
    repo.reorder("pl-1", ["track-2", "track-1", "track-0"])

    tracks = repo.get_tracks("pl-1")
    assert [t.id.value for t in tracks] == ["track-2", "track-1", "track-0"]
