# Technical Specification: musikbox

## 1. Overview

A CLI tool for downloading, analyzing, and managing a local music library. Built for DJs and producers who need BPM, musical key, and genre metadata.

**Success criteria:** MVP delivers download, analyze, and library CRUD via CLI with accurate BPM/key detection and persistent SQLite-backed catalog.

## 2. Architecture

Hexagonal architecture — domain core with ports and adapters.

### Dependency Direction

```
cli/ → bootstrap.py → services/ → domain/ports/
                       adapters/ → domain/ports/
```

Domain has zero imports from services, adapters, or CLI. Services depend only on port interfaces. Adapters implement port interfaces.

### Domain Model

```python
# domain/models.py

@dataclass
class TrackId:
    """Value object — generates UUID on construction."""
    value: str = field(default_factory=lambda: str(uuid4()))

@dataclass
class Track:
    id: TrackId
    title: str
    artist: str | None
    album: str | None
    duration_seconds: float
    file_path: Path
    format: str
    bpm: float | None
    key: str | None
    genre: str | None
    mood: str | None
    source_url: str | None
    downloaded_at: datetime | None
    analyzed_at: datetime | None
    created_at: datetime

@dataclass
class AnalysisResult:
    bpm: float
    key: str
    key_camelot: str
    genre: str
    mood: str
    confidence: dict[str, float]

@dataclass
class SearchFilter:
    bpm_min: float | None = None
    bpm_max: float | None = None
    key: str | None = None
    genre: str | None = None
    mood: str | None = None
    artist: str | None = None
    title: str | None = None
    query: str | None = None  # free-text search across title/artist
```

### Ports (Separate Files)

```
domain/ports/
├── __init__.py
├── repository.py      # TrackRepository ABC
├── downloader.py      # Downloader ABC
├── analyzer.py        # Analyzer ABC
└── metadata_writer.py # MetadataWriter ABC
```

Each port is an ABC with `@abstractmethod`. All methods use domain types — no adapter-specific types leak through.

### Domain Exceptions

```python
# domain/exceptions.py

class MusikboxError(Exception): ...
class TrackNotFoundError(MusikboxError): ...
class DownloadError(MusikboxError): ...
class AnalysisError(MusikboxError): ...
class UnsupportedFormatError(MusikboxError): ...
class ConfigError(MusikboxError): ...
class DatabaseError(MusikboxError): ...
class MetadataWriteError(MusikboxError): ...
```

Adapters catch adapter-specific exceptions and raise domain exceptions. Services and CLI never see adapter internals.

## 3. Technical Design

### Bootstrap / Wiring

```python
# bootstrap.py — single module that builds the object graph

def create_app() -> App:
    config = load_config()
    repository = SqliteRepository(config.db_path)
    downloader = YtdlpDownloader(config.download)
    analyzer = EssentiaAnalyzer(config.analysis)  # or FakeAnalyzer
    metadata_writer = MutagenMetadataWriter()

    return App(
        download_service=DownloadService(downloader, analyzer, repository, config),
        analysis_service=AnalysisService(analyzer, repository, metadata_writer, config),
        library_service=LibraryService(repository),
    )
```

CLI commands call `create_app()` and use the returned services.

### Configuration

```python
# config/settings.py — central config, loads from .env

@dataclass
class DownloadConfig:
    output_dir: Path
    default_format: str
    audio_quality: str

@dataclass
class AnalysisConfig:
    write_tags: bool
    key_notation: str  # "camelot" | "standard" | "both"
    model_dir: Path

@dataclass
class Config:
    music_dir: Path
    db_path: Path
    auto_analyze: bool
    download: DownloadConfig
    analysis: AnalysisConfig
```

- Loads from `~/.config/musikbox/.env` using `python-dotenv`
- Environment variables override `.env` values
- All paths resolve to absolute `Path` objects

### SQLite Schema Management

Separate migration command: `musikbox db init`

```sql
CREATE TABLE tracks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT,
    album TEXT,
    duration_seconds REAL NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    format TEXT NOT NULL,
    bpm REAL,
    key TEXT,
    genre TEXT,
    mood TEXT,
    source_url TEXT,
    downloaded_at TEXT,
    analyzed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_tracks_bpm ON tracks(bpm);
CREATE INDEX idx_tracks_key ON tracks(key);
CREATE INDEX idx_tracks_genre ON tracks(genre);
```

### Error Handling

- All error paths use try/except with domain exceptions
- Adapters catch library-specific errors and raise domain exceptions:
  ```python
  # In ytdlp_downloader.py
  try:
      ydl.download([url])
  except yt_dlp.DownloadError as e:
      raise DownloadError(f"Failed to download {url}: {e}") from e
  ```
- Services propagate domain exceptions — no catching and re-wrapping at service layer unless adding context
- CLI catches domain exceptions and renders user-friendly Rich output

### CLI Output

- Services return domain objects
- CLI commands handle all Rich formatting inline (no shared presentation layer for now)
- Rich console for all user-facing output (no `print()`, no `logging` module)

## 4. Non-Functional Requirements

- **Performance:** Analysis of a single track should complete in under 30 seconds
- **Storage:** SQLite is sufficient — single-user, local-only tool
- **Compatibility:** Python 3.12+, macOS and Linux

## 5. Testing Strategy

**TDD — tests first, then implementation.**

**Co-located:** `test_<module>.py` lives next to the module it tests.

| Layer    | What to test                         | Mocking strategy                          |
|----------|--------------------------------------|-------------------------------------------|
| Domain   | Model construction, value objects, SearchFilter validation | No mocks                              |
| Services | Orchestration logic, error propagation | Mock ports (not adapters)               |
| Adapters | Real behavior against real backends  | In-memory SQLite; `FakeAnalyzer` for Essentia; numpy-generated audio fixtures |
| CLI      | Command wiring, output formatting    | Mock services                             |

### Audio Test Fixtures

- Generated via numpy (sine waves) in pytest fixtures
- No committed binary files
- Fixtures create temporary WAV/FLAC files per test session

### Fake Adapters

- `FakeAnalyzer` implements `Analyzer` port with hardcoded results — used by Agent 1/2 work and integration tests
- `FakeDownloader` implements `Downloader` port for testing download service without network

## 6. Operations

- **Installation:** `uv pip install -e ".[dev]"`
- **DB init:** `musikbox db init` before first use
- **Config:** `~/.config/musikbox/.env`

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Essentia installation is complex (C++ deps) | FakeAnalyzer allows development/testing without Essentia; document install steps |
| yt-dlp breaks on upstream changes | Pin version; adapter isolates breakage from domain |
| Large music libraries slow SQLite queries | Indexes on bpm, key, genre; pagination via limit/offset |

## 8. Open Questions & Decisions

- **Essentia model selection:** Which pre-trained models for genre/mood? Defer to implementation of Agent 3.
- **Config format:** Spec uses `.env` for simplicity. The README mentions `config.toml` — `.env` is the source of truth per interview decision.
- **Playlist generation / Camelot wheel:** Roadmap item, not MVP scope.
