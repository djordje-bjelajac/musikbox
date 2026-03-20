import json
import urllib.parse
import urllib.request

from musikbox.domain.ports.genre_lookup import GenreLookup

_BASE_URL = "http://ws.audioscrobbler.com/2.0/"
_UNKNOWN_GENRE = ("Unknown", 0.0)


class LastfmGenreLookup(GenreLookup):
    """Genre lookup using the Last.fm API.

    Queries track.getTopTags first, falling back to artist.getTopTags
    if no tags are found. Returns the top tag as the genre with a
    normalized confidence score.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def lookup(self, title: str, artist: str | None = None) -> tuple[str, float]:
        """Look up genre via Last.fm. Never raises on failure."""
        if artist:
            result = self._track_tags(title, artist)
            if result is not None:
                return result

            result = self._artist_tags(artist)
            if result is not None:
                return result

        return _UNKNOWN_GENRE

    def _track_tags(self, title: str, artist: str) -> tuple[str, float] | None:
        params = {
            "method": "track.gettoptags",
            "artist": artist,
            "track": title,
            "api_key": self._api_key,
            "format": "json",
        }
        data = self._request(params)
        if data is None:
            return None
        return _extract_top_tag(data, "toptags")

    def _artist_tags(self, artist: str) -> tuple[str, float] | None:
        params = {
            "method": "artist.gettoptags",
            "artist": artist,
            "api_key": self._api_key,
            "format": "json",
        }
        data = self._request(params)
        if data is None:
            return None
        return _extract_top_tag(data, "toptags")

    def _request(self, params: dict[str, str]) -> dict[str, object] | None:
        url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return json.loads(response.read().decode())  # type: ignore[no-any-return]
        except Exception:
            return None


def _extract_top_tag(data: dict[str, object], key: str) -> tuple[str, float] | None:
    """Extract the top tag name and normalized confidence from a Last.fm response."""
    try:
        toptags = data.get(key)
        if not isinstance(toptags, dict):
            return None

        tags = toptags.get("tag")
        if not isinstance(tags, list) or len(tags) == 0:
            return None

        top = tags[0]
        if not isinstance(top, dict):
            return None

        name = top.get("name")
        if not isinstance(name, str) or not name.strip():
            return None

        count = int(top.get("count", 0))
        # Last.fm tag counts go up to 100; normalize to 0.0-1.0
        confidence = min(1.0, max(0.0, count / 100.0))

        return name.strip(), confidence
    except (ValueError, TypeError, KeyError):
        return None
