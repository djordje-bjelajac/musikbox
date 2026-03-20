from datetime import datetime
from pathlib import Path

import pytest

from musikbox.adapters.migrations import init_db
from musikbox.adapters.sqlite_repository import SqliteRepository
from musikbox.domain.exceptions import TrackNotFoundError
from musikbox.domain.models import SearchFilter, Track, TrackId


def _make_track(**overrides: object) -> Track:
    """Helper to build a Track with sensible defaults."""
    defaults: dict[str, object] = {
        "id": TrackId(value="test-id"),
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "duration_seconds": 180.0,
        "file_path": Path("/music/test.mp3"),
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


@pytest.fixture()
def repo(tmp_path: Path) -> SqliteRepository:
    """Initialize an in-memory-like SQLite DB and return a SqliteRepository."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return SqliteRepository(db_path)


def test_save_track_and_retrieve_by_id(repo: SqliteRepository) -> None:
    track = _make_track()
    repo.save(track)

    result = repo.get_by_id(TrackId(value="test-id"))

    assert result.id.value == track.id.value
    assert result.title == "Test Song"
    assert result.artist == "Test Artist"
    assert result.album == "Test Album"
    assert result.duration_seconds == 180.0
    assert result.file_path == Path("/music/test.mp3")
    assert result.format == "mp3"
    assert result.bpm == 128.0
    assert result.key == "Am"
    assert result.genre == "techno"
    assert result.mood == "energetic"
    assert result.source_url == "https://example.com/song"
    assert result.downloaded_at == datetime(2025, 6, 1, 12, 0, 0)
    assert result.analyzed_at == datetime(2025, 6, 1, 12, 5, 0)
    assert result.created_at == datetime(2025, 6, 1, 12, 0, 0)


def test_get_by_id_nonexistent_returns_none(repo: SqliteRepository) -> None:
    with pytest.raises(TrackNotFoundError):
        repo.get_by_id(TrackId(value="nonexistent-id"))


def test_save_track_upsert_overwrites(repo: SqliteRepository) -> None:
    track_v1 = _make_track(title="Original Title")
    repo.save(track_v1)

    track_v2 = _make_track(title="Updated Title")
    repo.save(track_v2)

    result = repo.get_by_id(TrackId(value="test-id"))
    assert result.title == "Updated Title"


def test_delete_track_removes_from_db(repo: SqliteRepository) -> None:
    track = _make_track()
    repo.save(track)

    repo.delete(TrackId(value="test-id"))

    with pytest.raises(TrackNotFoundError):
        repo.get_by_id(TrackId(value="test-id"))


def test_delete_track_nonexistent_raises(repo: SqliteRepository) -> None:
    with pytest.raises(TrackNotFoundError):
        repo.delete(TrackId(value="nonexistent-id"))


def test_list_all_returns_tracks_with_limit_offset(repo: SqliteRepository) -> None:
    for i in range(5):
        track = _make_track(
            id=TrackId(value=f"track-{i}"),
            title=f"Song {i}",
            file_path=Path(f"/music/song{i}.mp3"),
            created_at=datetime(2025, 1, 1, 0, i, 0),
        )
        repo.save(track)

    # list_all orders by created_at DESC
    all_tracks = repo.list_all(limit=50, offset=0)
    assert len(all_tracks) == 5

    limited = repo.list_all(limit=2, offset=0)
    assert len(limited) == 2

    offset = repo.list_all(limit=2, offset=2)
    assert len(offset) == 2

    # Verify no overlap between limit and offset pages
    limited_ids = {t.id.value for t in limited}
    offset_ids = {t.id.value for t in offset}
    assert limited_ids.isdisjoint(offset_ids)


def test_search_by_bpm_range(repo: SqliteRepository) -> None:
    repo.save(_make_track(id=TrackId(value="slow"), bpm=90.0, file_path=Path("/m/slow.mp3")))
    repo.save(_make_track(id=TrackId(value="mid"), bpm=128.0, file_path=Path("/m/mid.mp3")))
    repo.save(_make_track(id=TrackId(value="fast"), bpm=175.0, file_path=Path("/m/fast.mp3")))

    results = repo.search(SearchFilter(bpm_min=120.0, bpm_max=140.0))

    assert len(results) == 1
    assert results[0].id.value == "mid"


def test_search_by_key(repo: SqliteRepository) -> None:
    repo.save(_make_track(id=TrackId(value="am"), key="Am", file_path=Path("/m/am.mp3")))
    repo.save(_make_track(id=TrackId(value="cm"), key="Cm", file_path=Path("/m/cm.mp3")))

    results = repo.search(SearchFilter(key="Am"))

    assert len(results) == 1
    assert results[0].id.value == "am"


def test_search_by_genre(repo: SqliteRepository) -> None:
    repo.save(_make_track(id=TrackId(value="t1"), genre="techno", file_path=Path("/m/techno.mp3")))
    repo.save(_make_track(id=TrackId(value="t2"), genre="house", file_path=Path("/m/house.mp3")))

    results = repo.search(SearchFilter(genre="house"))

    assert len(results) == 1
    assert results[0].id.value == "t2"


def test_search_by_query_matches_title_and_artist(repo: SqliteRepository) -> None:
    repo.save(
        _make_track(
            id=TrackId(value="t1"),
            title="Windowlicker",
            artist="Aphex Twin",
            file_path=Path("/m/wl.mp3"),
        )
    )
    repo.save(
        _make_track(
            id=TrackId(value="t2"),
            title="Blue Monday",
            artist="New Order",
            file_path=Path("/m/bm.mp3"),
        )
    )

    by_title = repo.search(SearchFilter(query="Windowlicker"))
    assert len(by_title) == 1
    assert by_title[0].id.value == "t1"

    by_artist = repo.search(SearchFilter(query="Aphex"))
    assert len(by_artist) == 1
    assert by_artist[0].id.value == "t1"


def test_search_with_multiple_filters(repo: SqliteRepository) -> None:
    repo.save(
        _make_track(
            id=TrackId(value="t1"),
            bpm=128.0,
            genre="techno",
            key="Am",
            file_path=Path("/m/t1.mp3"),
        )
    )
    repo.save(
        _make_track(
            id=TrackId(value="t2"),
            bpm=128.0,
            genre="house",
            key="Am",
            file_path=Path("/m/t2.mp3"),
        )
    )
    repo.save(
        _make_track(
            id=TrackId(value="t3"),
            bpm=90.0,
            genre="techno",
            key="Am",
            file_path=Path("/m/t3.mp3"),
        )
    )

    results = repo.search(SearchFilter(bpm_min=120.0, bpm_max=140.0, genre="techno"))

    assert len(results) == 1
    assert results[0].id.value == "t1"
