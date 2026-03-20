import json
from types import ModuleType

from musikbox.domain.models import EnrichmentResult
from musikbox.domain.ports.metadata_enricher import MetadataEnricher

try:
    import anthropic
except ImportError:
    anthropic: ModuleType = None  # type: ignore[no-redef]

_SYSTEM_PROMPT = """You are a music metadata expert. Your job is to identify tracks \
from YouTube/filename titles and return structured metadata.

Use the web_search tool to look up the track and verify artist, album, year, genre, \
and other details. Search for the track on music databases, Discogs, or review sites.

After researching, return your final answer as a JSON code block."""

_USER_TEMPLATE = """Identify this music track and return structured metadata.

Title: "{raw_title}"
{bpm_line}{key_line}
Search the web to verify the artist, album, year, and genre. Then return ONLY a JSON \
code block with this exact structure:

```json
{{
  "artist": "artist name or null",
  "title": "clean track title or null",
  "album": "album name or null",
  "remix": "remix/edit info or null (e.g. 'Locussolus Edit')",
  "year": year as integer or null,
  "genre": "primary genre or null",
  "tags": ["sub-genre", "tags", "as", "list"]
}}
```

Rules:
- Split "Artist - Title" patterns
- Remove YouTube junk (Official Video, Remaster, HD, etc.)
- Genre should be specific (e.g., "acid house" not just "electronic")
- Tags are sub-genres, moods, or scene descriptors
- If you can't determine a field even after searching, use null
- BPM and key are provided as context to help identify genre"""


class HaikuEnricher(MetadataEnricher):
    """Calls Claude Sonnet with web search to extract metadata from track titles."""

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
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": user_message}],
            )

            return _parse_response(response)
        except Exception:
            return _empty_result()


def _parse_response(response: object) -> EnrichmentResult:
    """Extract JSON from the response, handling web search tool use turns."""
    # The response may have multiple content blocks (tool_use, tool_result, text)
    # We need to find the final text block with JSON
    text = ""
    for block in response.content:  # type: ignore[attr-defined]
        if hasattr(block, "text"):
            text = block.text

    if not text:
        return _empty_result()

    # Try to extract JSON from a code block
    data = _extract_json(text)
    if data is None:
        return _empty_result()

    return EnrichmentResult(
        artist=data.get("artist") if isinstance(data.get("artist"), str) else None,
        title=data.get("title") if isinstance(data.get("title"), str) else None,
        album=data.get("album") if isinstance(data.get("album"), str) else None,
        remix=data.get("remix") if isinstance(data.get("remix"), str) else None,
        year=data.get("year") if isinstance(data.get("year"), int) else None,
        genre=data.get("genre") if isinstance(data.get("genre"), str) else None,
        tags=data.get("tags") if isinstance(data.get("tags"), list) else [],
    )


def _extract_json(text: str) -> dict[str, object] | None:
    """Extract JSON from text, trying code blocks first then raw JSON."""
    # Try ```json ... ``` block
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        try:
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Try ```...``` block
    if "```" in text:
        start = text.index("```") + 3
        # Skip optional language tag on first line
        newline = text.index("\n", start)
        start = newline + 1
        end = text.index("```", start)
        try:
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Try raw JSON
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # Try finding { ... } in the text
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start : brace_end + 1])
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _empty_result() -> EnrichmentResult:
    return EnrichmentResult(
        artist=None,
        title=None,
        album=None,
        remix=None,
        year=None,
        genre=None,
        tags=[],
    )
