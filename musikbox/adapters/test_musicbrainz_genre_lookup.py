import json
from unittest.mock import MagicMock, patch

from musikbox.adapters.musicbrainz_genre_lookup import MusicBrainzGenreLookup
from musikbox.domain.ports.genre_lookup import GenreLookup


def _make_search_response(recording_id: str) -> bytes:
    """Build a MusicBrainz recording search JSON response."""
    return json.dumps({"recordings": [{"id": recording_id, "score": 100}]}).encode()


def _make_tags_response(
    genres: list[dict[str, object]] | None = None,
    tags: list[dict[str, object]] | None = None,
) -> bytes:
    """Build a MusicBrainz recording lookup JSON response with genres/tags."""
    data: dict[str, object] = {"id": "abc-123"}
    if genres is not None:
        data["genres"] = genres
    if tags is not None:
        data["tags"] = tags
    return json.dumps(data).encode()


def _mock_response(body: bytes) -> MagicMock:
    """Create a mock urllib response context manager."""
    mock = MagicMock()
    mock.read.return_value = body
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def test_musicbrainz_lookup_implements_port() -> None:
    lookup = MusicBrainzGenreLookup()

    assert isinstance(lookup, GenreLookup)


@patch("musikbox.adapters.musicbrainz_genre_lookup.time.sleep")
@patch("musikbox.adapters.musicbrainz_genre_lookup.urllib.request.urlopen")
def test_musicbrainz_lookup_returns_genre_from_api(
    mock_urlopen: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    search_resp = _mock_response(_make_search_response("abc-123"))
    tags_resp = _mock_response(
        _make_tags_response(
            genres=[
                {"name": "electronic", "count": 8},
                {"name": "dance", "count": 5},
            ]
        )
    )
    mock_urlopen.side_effect = [search_resp, tags_resp]

    lookup = MusicBrainzGenreLookup()
    genre, confidence = lookup.lookup("Around the World", artist="Daft Punk")

    assert genre == "electronic"
    assert confidence == 1.0
    assert mock_urlopen.call_count == 2
    mock_sleep.assert_called_once()


@patch("musikbox.adapters.musicbrainz_genre_lookup.time.sleep")
@patch("musikbox.adapters.musicbrainz_genre_lookup.urllib.request.urlopen")
def test_musicbrainz_lookup_returns_unknown_on_api_error(
    mock_urlopen: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    mock_urlopen.side_effect = OSError("Connection refused")

    lookup = MusicBrainzGenreLookup()
    genre, confidence = lookup.lookup("Some Track", artist="Some Artist")

    assert genre == "Unknown"
    assert confidence == 0.0


@patch("musikbox.adapters.musicbrainz_genre_lookup.time.sleep")
@patch("musikbox.adapters.musicbrainz_genre_lookup.urllib.request.urlopen")
def test_musicbrainz_lookup_returns_unknown_when_no_results(
    mock_urlopen: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    empty_search = _mock_response(json.dumps({"recordings": []}).encode())
    mock_urlopen.return_value = empty_search

    lookup = MusicBrainzGenreLookup()
    genre, confidence = lookup.lookup("Nonexistent Track", artist="Nobody")

    assert genre == "Unknown"
    assert confidence == 0.0
