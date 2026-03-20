import json
import re
import time
import urllib.parse
import urllib.request

from musikbox.domain.ports.genre_lookup import GenreLookup

_RECORDING_SEARCH_URL = "https://musicbrainz.org/ws/2/recording/"
_RECORDING_LOOKUP_URL = "https://musicbrainz.org/ws/2/recording/{recording_id}"
_ARTIST_SEARCH_URL = "https://musicbrainz.org/ws/2/artist/"
_ARTIST_LOOKUP_URL = "https://musicbrainz.org/ws/2/artist/{artist_id}"
_USER_AGENT = "musikbox/0.1.0 (https://github.com/djordje-bjelajac/musikbox)"
_UNKNOWN_GENRE = ("Unknown", 0.0)
_RATE_LIMIT_SECONDS = 1.1


class MusicBrainzGenreLookup(GenreLookup):
    """Genre lookup using the MusicBrainz API.

    Searches for a recording by title and artist, then fetches tags/genres
    for the matched recording. Returns the top tag by count with a
    normalized confidence score. No API key required -- only a User-Agent header.
    """

    def lookup(self, title: str, artist: str | None = None) -> tuple[str, float]:
        """Look up genre via MusicBrainz. Never raises on failure.

        Tries recording-level tags first, falls back to artist-level genres.
        """
        try:
            # Try recording tags first
            recording_id = self._search_recording(title, artist)
            if recording_id is not None:
                time.sleep(_RATE_LIMIT_SECONDS)
                result = self._fetch_recording_tags(recording_id)
                if result != _UNKNOWN_GENRE:
                    return result

            # Fall back to artist genres
            if artist is not None:
                time.sleep(_RATE_LIMIT_SECONDS)
                return self._lookup_artist_genre(artist)

            # Try extracting artist from title
            _, parsed_artist = _clean_title(title)
            if parsed_artist:
                time.sleep(_RATE_LIMIT_SECONDS)
                return self._lookup_artist_genre(parsed_artist)

            return _UNKNOWN_GENRE
        except Exception:
            return _UNKNOWN_GENRE

    def _search_recording(self, title: str, artist: str | None) -> str | None:
        """Search for a recording and return its MusicBrainz ID."""
        clean_title, parsed_artist = _clean_title(title)
        if artist is None and parsed_artist:
            artist = parsed_artist

        query = f"recording:{clean_title}"
        if artist:
            query += f" AND artist:{artist}"

        params = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": "1"})
        url = f"{_RECORDING_SEARCH_URL}?{params}"

        data = self._request(url)
        if data is None:
            return None

        recordings = data.get("recordings")
        if not isinstance(recordings, list) or len(recordings) == 0:
            return None

        first = recordings[0]
        if not isinstance(first, dict):
            return None

        recording_id = first.get("id")
        if not isinstance(recording_id, str):
            return None

        return recording_id

    def _fetch_recording_tags(self, recording_id: str) -> tuple[str, float]:
        """Fetch tags/genres for a recording and return the top one."""
        params = urllib.parse.urlencode({"inc": "genres+tags", "fmt": "json"})
        url = f"{_RECORDING_LOOKUP_URL.format(recording_id=recording_id)}?{params}"

        data = self._request(url)
        if data is None:
            return _UNKNOWN_GENRE

        return _extract_top_tag(data)

    def _lookup_artist_genre(self, artist: str) -> tuple[str, float]:
        """Search for an artist and return their top genre."""
        params = urllib.parse.urlencode(
            {"query": f'artist:"{artist}"', "fmt": "json", "limit": "1"}
        )
        url = f"{_ARTIST_SEARCH_URL}?{params}"

        data = self._request(url)
        if data is None:
            return _UNKNOWN_GENRE

        artists = data.get("artists")
        if not isinstance(artists, list) or len(artists) == 0:
            return _UNKNOWN_GENRE

        artist_id = artists[0].get("id")
        if not isinstance(artist_id, str):
            return _UNKNOWN_GENRE

        time.sleep(_RATE_LIMIT_SECONDS)

        params = urllib.parse.urlencode({"inc": "genres+tags", "fmt": "json"})
        url = f"{_ARTIST_LOOKUP_URL.format(artist_id=artist_id)}?{params}"

        data = self._request(url)
        if data is None:
            return _UNKNOWN_GENRE

        return _extract_top_tag(data)

    def _request(self, url: str) -> dict[str, object] | None:
        """Make an HTTP request with the required User-Agent header."""
        req = urllib.request.Request(url)
        req.add_header("User-Agent", _USER_AGENT)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode())  # type: ignore[no-any-return]
        except Exception:
            return None


def _extract_top_tag(data: dict[str, object]) -> tuple[str, float]:
    """Extract the top tag/genre from a MusicBrainz recording response.

    Tries 'genres' first (official MusicBrainz genres), then 'tags'
    (user-submitted folksonomy tags). Returns the highest-count entry
    with a normalized confidence score.
    """
    for key in ("genres", "tags"):
        items = data.get(key)
        if not isinstance(items, list) or len(items) == 0:
            continue

        best = max(items, key=lambda t: t.get("count", 0) if isinstance(t, dict) else 0)
        if not isinstance(best, dict):
            continue

        name = best.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        count = int(best.get("count", 0))
        max_count = max(count, 1)
        # Find the maximum count across all items to normalize
        for item in items:
            if isinstance(item, dict):
                item_count = int(item.get("count", 0))
                if item_count > max_count:
                    max_count = item_count

        confidence = min(1.0, max(0.0, count / max_count))
        return name.strip(), confidence

    return _UNKNOWN_GENRE


# Patterns to strip from YouTube-style titles
_JUNK_PATTERNS = re.compile(
    r"\s*[\(\[](official\s*(music\s*)?video|"
    r"official\s*audio|"
    r"lyric\s*video|"
    r"lyrics|"
    r"visuali[sz]er|"
    r"audio|"
    r"hd|hq|"
    r"\d{4}\s*remaster(ed)?|"
    r"\dk\s*remaster(ed)?|"
    r"remaster(ed)?|"
    r"live|"
    r"explicit|"
    r"clean)[\)\]]",
    re.IGNORECASE,
)


def _clean_title(raw_title: str) -> tuple[str, str | None]:
    """Clean a YouTube-style title and optionally extract artist.

    Handles patterns like "Artist - Title (Official Video) (4K Remaster)".
    Returns (cleaned_title, artist_or_none).
    """
    title = _JUNK_PATTERNS.sub("", raw_title).strip()

    # Try to split "Artist - Title"
    artist: str | None = None
    if " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()

    return title, artist
