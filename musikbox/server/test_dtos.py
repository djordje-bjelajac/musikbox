from __future__ import annotations

from datetime import datetime

from musikbox.server.conftest import make_track
from musikbox.server.dtos import (
    ErrorResponse,
    PlayCommand,
    PlayerStatusDTO,
    SeekCommand,
    TrackDTO,
)


def test_from_track_omits_file_path() -> None:
    track = make_track(track_id="abc")

    dto = TrackDTO.from_track(track, "http://testserver")

    assert "file_path" not in dto.model_dump()
    assert not hasattr(dto, "file_path")


def test_from_track_builds_stream_url_from_base_url() -> None:
    track = make_track(track_id="abc-123")

    dto = TrackDTO.from_track(track, "http://testserver")

    assert dto.stream_url == "http://testserver/tracks/abc-123/stream"


def test_from_track_strips_trailing_slash_in_stream_url() -> None:
    track = make_track(track_id="xyz")

    dto = TrackDTO.from_track(track, "http://testserver/")

    assert dto.stream_url == "http://testserver/tracks/xyz/stream"


def test_from_track_maps_scalar_fields() -> None:
    track = make_track(
        track_id="id-1",
        title="My Title",
        artist="My Artist",
        album="My Album",
        duration_seconds=200.5,
        audio_format="flac",
        bpm=128.0,
        key="8A",
        genre="House",
        mood="Energetic",
        source_url="https://example.com/x",
        remix="Club Mix",
        year=2024,
        tags="deep,house",
    )

    dto = TrackDTO.from_track(track, "http://testserver")

    assert dto.id == "id-1"
    assert dto.title == "My Title"
    assert dto.artist == "My Artist"
    assert dto.album == "My Album"
    assert dto.duration_seconds == 200.5
    assert dto.format == "flac"
    assert dto.bpm == 128.0
    assert dto.key == "8A"
    assert dto.genre == "House"
    assert dto.mood == "Energetic"
    assert dto.source_url == "https://example.com/x"
    assert dto.remix == "Club Mix"
    assert dto.year == 2024
    assert dto.tags == "deep,house"


def test_from_track_uses_track_id_value_as_id() -> None:
    track = make_track(track_id="uuid-value")

    dto = TrackDTO.from_track(track, "http://testserver")

    assert dto.id == "uuid-value"


def test_from_track_maps_timestamp_fields() -> None:
    track = make_track()

    dto = TrackDTO.from_track(track, "http://testserver")

    assert dto.created_at == datetime(2025, 1, 1, 12, 0, 0)
    assert dto.downloaded_at is None
    assert dto.analyzed_at is None
    assert dto.enriched_at is None


def test_from_track_preserves_nullable_fields_as_none() -> None:
    track = make_track(
        artist=None,
        album=None,
        bpm=None,
        key=None,
        genre=None,
        mood=None,
        source_url=None,
        remix=None,
        year=None,
        tags=None,
    )

    dto = TrackDTO.from_track(track, "http://testserver")

    assert dto.artist is None
    assert dto.album is None
    assert dto.bpm is None
    assert dto.key is None
    assert dto.genre is None
    assert dto.mood is None
    assert dto.source_url is None
    assert dto.remix is None
    assert dto.year is None
    assert dto.tags is None


def test_from_track_round_trips_through_model_dump() -> None:
    track = make_track(track_id="rt", bpm=120.0, genre="Techno")

    dto = TrackDTO.from_track(track, "http://testserver")
    rebuilt = TrackDTO(**dto.model_dump())

    assert rebuilt == dto
    assert rebuilt.stream_url == "http://testserver/tracks/rt/stream"


def test_player_status_dto_holds_state() -> None:
    status = PlayerStatusDTO(position=10.0, duration=180.0, is_playing=True, is_paused=False)

    assert status.position == 10.0
    assert status.duration == 180.0
    assert status.is_playing is True
    assert status.is_paused is False


def test_play_command_parses_track_id() -> None:
    cmd = PlayCommand(track_id="t-1")

    assert cmd.track_id == "t-1"


def test_seek_command_parses_seconds() -> None:
    cmd = SeekCommand(seconds=12.5)

    assert cmd.seconds == 12.5


def test_error_response_holds_code_and_message() -> None:
    err = ErrorResponse(error_code="TrackNotFoundError", message="missing")

    assert err.error_code == "TrackNotFoundError"
    assert err.message == "missing"
