import json
from unittest.mock import MagicMock, patch

from musikbox.adapters.lastfm_genre_lookup import LastfmGenreLookup
from musikbox.domain.ports.genre_lookup import GenreLookup


def _make_tags_response(tags: list[dict[str, object]]) -> bytes:
    """Build a Last.fm-style JSON response with toptags."""
    return json.dumps({"toptags": {"tag": tags}}).encode()


def test_lastfm_lookup_implements_port() -> None:
    lookup = LastfmGenreLookup(api_key="test-key")

    assert isinstance(lookup, GenreLookup)


@patch("musikbox.adapters.lastfm_genre_lookup.urllib.request.urlopen")
def test_lastfm_lookup_returns_genre_from_api(mock_urlopen: MagicMock) -> None:
    response_body = _make_tags_response(
        [
            {"name": "electronic", "count": 85},
            {"name": "dance", "count": 60},
        ]
    )
    mock_response = MagicMock()
    mock_response.read.return_value = response_body
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    lookup = LastfmGenreLookup(api_key="test-key")
    genre, confidence = lookup.lookup("Around the World", artist="Daft Punk")

    assert genre == "electronic"
    assert confidence == 0.85


@patch("musikbox.adapters.lastfm_genre_lookup.urllib.request.urlopen")
def test_lastfm_lookup_returns_unknown_on_api_error(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = OSError("Connection refused")

    lookup = LastfmGenreLookup(api_key="test-key")
    genre, confidence = lookup.lookup("Some Track", artist="Some Artist")

    assert genre == "Unknown"
    assert confidence == 0.0


@patch("musikbox.adapters.lastfm_genre_lookup.urllib.request.urlopen")
def test_lastfm_lookup_falls_back_to_artist_tags(mock_urlopen: MagicMock) -> None:
    # First call (track.getTopTags) returns empty tags
    empty_response = MagicMock()
    empty_response.read.return_value = json.dumps({"toptags": {"tag": []}}).encode()
    empty_response.__enter__ = MagicMock(return_value=empty_response)
    empty_response.__exit__ = MagicMock(return_value=False)

    # Second call (artist.getTopTags) returns results
    artist_response = MagicMock()
    artist_response.read.return_value = _make_tags_response(
        [
            {"name": "house", "count": 100},
        ]
    )
    artist_response.__enter__ = MagicMock(return_value=artist_response)
    artist_response.__exit__ = MagicMock(return_value=False)

    mock_urlopen.side_effect = [empty_response, artist_response]

    lookup = LastfmGenreLookup(api_key="test-key")
    genre, confidence = lookup.lookup("Unknown Track", artist="Disclosure")

    assert genre == "house"
    assert confidence == 1.0
    assert mock_urlopen.call_count == 2
