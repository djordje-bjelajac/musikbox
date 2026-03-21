# Technical Specification: LLM Track Enrichment

## 1. Overview

Use Claude Haiku to extract structured metadata from YouTube/filename titles. Improves track data quality by parsing artist, title, album, remix info, year, genre, and sub-genre tags from messy real-world titles.

**Success criteria:** `musikbox library enrich` processes all un-enriched tracks, calling Haiku once per track, and updates the library with clean structured metadata.

## 2. Architecture

### Domain Model Changes

Add fields to Track:

```python
@dataclass
class Track:
    # ... existing fields ...
    remix: str | None          # e.g., "Locussolus Edit"
    year: int | None           # e.g., 1987
    tags: str | None           # comma-separated sub-genre tags, e.g., "dark disco,balearic"
    enriched_at: datetime | None  # None = not yet enriched
```

### New Port

```python
# domain/ports/metadata_enricher.py
class MetadataEnricher(ABC):
    @abstractmethod
    def enrich(
        self,
        raw_title: str,
        bpm: float | None = None,
        key: str | None = None,
    ) -> EnrichmentResult: ...

@dataclass
class EnrichmentResult:
    artist: str | None
    title: str | None
    album: str | None
    remix: str | None
    year: int | None
    genre: str | None
    tags: list[str]        # sub-genre tags
```

### New Adapter

```python
# adapters/haiku_enricher.py
class HaikuEnricher(MetadataEnricher):
    """Calls Claude Haiku to extract metadata from track titles."""
```

### Fake Adapter

```python
# adapters/fake_enricher.py
class FakeEnricher(MetadataEnricher):
    """Returns hardcoded results for testing."""
```

## 3. Technical Design

### API Integration

- Use the `anthropic` Python SDK (`pip install anthropic`)
- Model: `claude-haiku-4-5-20251001`
- API key from `ANTHROPIC_API_KEY` in `~/.config/musikbox/.env`
- Single message per track, no conversation history

### Prompt

```
Extract music metadata from this track title. Return ONLY valid JSON.

Title: "{raw_title}"
{f"BPM: {bpm}" if bpm else ""}
{f"Key: {key}" if key else ""}

Return this exact JSON structure:
{
  "artist": "artist name or null",
  "title": "clean track title or null",
  "album": "album name or null",
  "remix": "remix/edit info or null (e.g. 'Locussolus Edit')",
  "year": year as integer or null,
  "genre": "primary genre or null",
  "tags": ["sub-genre", "tags", "as", "list"]
}

Rules:
- Split "Artist - Title" patterns
- Remove YouTube junk (Official Video, Remaster, HD, etc.)
- Genre should be specific (e.g., "acid house" not just "electronic")
- Tags are sub-genres, moods, or scene descriptors
- If you can't determine a field, use null
- BPM and key are provided as context to help identify genre
```

### Response Parsing

- Parse JSON from response
- Validate types (artist=str|None, year=int|None, tags=list[str])
- On parse failure, return empty EnrichmentResult (don't crash)

### Database Migration

Add columns to tracks table:

```sql
ALTER TABLE tracks ADD COLUMN remix TEXT;
ALTER TABLE tracks ADD COLUMN year INTEGER;
ALTER TABLE tracks ADD COLUMN tags TEXT;
ALTER TABLE tracks ADD COLUMN enriched_at TEXT;
```

Use `ALTER TABLE ... ADD COLUMN` with try/except to handle columns already existing (idempotent migration).

### CLI Command

```bash
musikbox library enrich
```

- Queries all tracks where `enriched_at IS NULL`
- Processes each track: call Haiku, update fields, set enriched_at
- Always overwrites existing values with LLM results
- Shows progress per track: `[1/60] DJ Harvey - Lovefinger [dark disco, balearic]`
- Skips tracks on API error, continues with next

### Config

Load `ANTHROPIC_API_KEY` from `.env`. If not set, show clear error message.

### Bootstrap

- If `ANTHROPIC_API_KEY` is set, create `HaikuEnricher`
- Otherwise, enricher is None
- Store on App dataclass

## 4. Non-Functional Requirements

- ~0.5-1s per track (Haiku latency)
- ~$0.01-0.02 per 60 tracks
- Graceful degradation: if API key missing or API errors, skip enrichment

## 5. Testing Strategy

- **HaikuEnricher:** manual testing only (requires API key)
- **FakeEnricher:** returns hardcoded EnrichmentResult
- **CLI:** test with FakeEnricher — verify tracks get updated
- **Prompt parsing:** unit test JSON extraction from mock responses

## 6. Risks & Mitigations

| Risk                         | Mitigation                                                   |
| ---------------------------- | ------------------------------------------------------------ |
| API key not configured       | Clear error message, command is opt-in                       |
| Haiku returns malformed JSON | Parse defensively, skip on failure                           |
| Rate limits                  | Haiku has generous limits, sequential calls are fine         |
| Hallucinated metadata        | LLM results are best-effort, user can edit via `e` in player |

## 7. Open Questions

- Should enrichment write tags to audio files (ID3)? Deferred — the metadata_writer already handles BPM/key/genre, can extend later.
- Should `library list` show sub-genre tags? Could add a `--tags` column. Defer to user request.
