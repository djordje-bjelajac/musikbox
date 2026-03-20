from datetime import datetime
from pathlib import Path

from musikbox.domain.models import AnalysisResult, SearchFilter, Track, TrackId

# --- TrackId ---


def test_track_id_generates_uuid_on_construction() -> None:
    track_id = TrackId()
    assert isinstance(track_id.value, str)
    assert len(track_id.value) == 36  # UUID format: 8-4-4-4-12


def test_track_id_two_instances_have_different_ids() -> None:
    id1 = TrackId()
    id2 = TrackId()
    assert id1.value != id2.value


def test_track_id_explicit_value_preserved() -> None:
    track_id = TrackId(value="my-custom-id")
    assert track_id.value == "my-custom-id"


# --- Track ---


def _make_track(**overrides: object) -> Track:
    """Helper to build a Track with sensible defaults."""
    defaults: dict[str, object] = {
        "id": TrackId(value="test-id"),
        "title": "Test Song",
        "artist": None,
        "album": None,
        "duration_seconds": 180.0,
        "file_path": Path("/music/test.mp3"),
        "format": "mp3",
        "bpm": None,
        "key": None,
        "genre": None,
        "mood": None,
        "source_url": None,
        "downloaded_at": None,
        "analyzed_at": None,
        "created_at": datetime(2025, 1, 1),
    }
    defaults.update(overrides)
    return Track(**defaults)  # type: ignore[arg-type]


def test_track_construction_all_fields() -> None:
    now = datetime.now()
    track = Track(
        id=TrackId(value="abc-123"),
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        duration_seconds=180.0,
        file_path=Path("/music/test.mp3"),
        format="mp3",
        bpm=128.0,
        key="Am",
        genre="techno",
        mood="energetic",
        source_url="https://example.com/song",
        downloaded_at=now,
        analyzed_at=now,
        created_at=now,
    )
    assert track.title == "Test Song"
    assert track.artist == "Test Artist"
    assert track.album == "Test Album"
    assert track.duration_seconds == 180.0
    assert track.bpm == 128.0
    assert track.key == "Am"
    assert track.genre == "techno"
    assert track.mood == "energetic"
    assert track.source_url == "https://example.com/song"
    assert track.id.value == "abc-123"


def test_track_file_path_is_path_object() -> None:
    track = _make_track(file_path=Path("/music/song.flac"))
    assert isinstance(track.file_path, Path)
    assert track.file_path == Path("/music/song.flac")


def test_track_optional_fields_accept_none() -> None:
    track = _make_track()
    assert track.artist is None
    assert track.album is None
    assert track.bpm is None
    assert track.key is None
    assert track.genre is None
    assert track.mood is None
    assert track.source_url is None
    assert track.downloaded_at is None
    assert track.analyzed_at is None


# --- AnalysisResult ---


def test_analysis_result_construction_all_fields() -> None:
    confidence = {"bpm": 0.95, "key": 0.88, "genre": 0.72}
    result = AnalysisResult(
        bpm=140.0,
        key="Cm",
        key_camelot="5A",
        genre="drum and bass",
        mood="dark",
        confidence=confidence,
    )
    assert result.bpm == 140.0
    assert result.key == "Cm"
    assert result.key_camelot == "5A"
    assert result.genre == "drum and bass"
    assert result.mood == "dark"
    assert result.confidence == {"bpm": 0.95, "key": 0.88, "genre": 0.72}


def test_analysis_result_confidence_is_dict() -> None:
    result = AnalysisResult(
        bpm=120.0,
        key="G",
        key_camelot="9B",
        genre="house",
        mood="uplifting",
        confidence={"bpm": 0.99},
    )
    assert isinstance(result.confidence, dict)


# --- SearchFilter ---


def test_search_filter_defaults_all_none() -> None:
    f = SearchFilter()
    assert f.bpm_min is None
    assert f.bpm_max is None
    assert f.key is None
    assert f.genre is None
    assert f.mood is None
    assert f.artist is None
    assert f.title is None
    assert f.query is None


def test_search_filter_set_bpm_range() -> None:
    f = SearchFilter(bpm_min=120.0, bpm_max=130.0)
    assert f.bpm_min == 120.0
    assert f.bpm_max == 130.0


def test_search_filter_set_individual_filters() -> None:
    f = SearchFilter(key="Am", genre="techno", mood="dark")
    assert f.key == "Am"
    assert f.genre == "techno"
    assert f.mood == "dark"
    assert f.bpm_min is None


def test_search_filter_set_query() -> None:
    f = SearchFilter(query="aphex twin")
    assert f.query == "aphex twin"
