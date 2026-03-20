import json
from types import ModuleType

from musikbox.domain.models import EnrichmentResult
from musikbox.domain.ports.metadata_enricher import MetadataEnricher

try:
    import anthropic
except ImportError:
    anthropic: ModuleType = None  # type: ignore[no-redef]

_SYSTEM_PROMPT = """Extract music metadata from track titles. Return ONLY valid JSON."""

_USER_TEMPLATE = """Extract music metadata from this track title. Return ONLY valid JSON.

Title: "{raw_title}"
{bpm_line}{key_line}
Return this exact JSON structure:
{{
  "artist": "artist name or null",
  "title": "clean track title or null",
  "album": "album name or null",
  "remix": "remix/edit info or null (e.g. 'Locussolus Edit')",
  "year": year as integer or null,
  "genre": "primary genre or null",
  "tags": ["sub-genre", "tags", "as", "list"]
}}

Rules:
- Split "Artist - Title" patterns
- Remove YouTube junk (Official Video, Remaster, HD, etc.)
- Genre should be specific (e.g., "acid house" not just "electronic")
- Tags are sub-genres, moods, or scene descriptors
- If you can't determine a field, use null
- BPM and key are provided as context to help identify genre"""


class HaikuEnricher(MetadataEnricher):
    """Calls Claude Haiku to extract metadata from track titles."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def enrich(
        self,
        raw_title: str,
        bpm: float | None = None,
        key: str | None = None,
    ) -> EnrichmentResult:
        bpm_line = f"BPM: {bpm}\n" if bpm else ""
        key_line = f"Key: {key}\n" if key else ""

        user_message = _USER_TEMPLATE.format(
            raw_title=raw_title,
            bpm_line=bpm_line,
            key_line=key_line,
        )

        try:
            response = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            text = response.content[0].text  # type: ignore[union-attr]
            data = json.loads(text)

            return EnrichmentResult(
                artist=data.get("artist") if isinstance(data.get("artist"), str) else None,
                title=data.get("title") if isinstance(data.get("title"), str) else None,
                album=data.get("album") if isinstance(data.get("album"), str) else None,
                remix=data.get("remix") if isinstance(data.get("remix"), str) else None,
                year=data.get("year") if isinstance(data.get("year"), int) else None,
                genre=data.get("genre") if isinstance(data.get("genre"), str) else None,
                tags=data.get("tags") if isinstance(data.get("tags"), list) else [],
            )
        except Exception:
            return EnrichmentResult(
                artist=None,
                title=None,
                album=None,
                remix=None,
                year=None,
                genre=None,
                tags=[],
            )
