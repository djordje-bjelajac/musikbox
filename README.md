# musikbox

A CLI tool for downloading, analyzing, and managing a local music library. Built for DJs and producers who need BPM, musical key, and genre metadata that DAWs like Ableton don't provide out of the box.

## Features

### Download

- Download audio from YouTube (and other yt-dlp supported platforms)
- Configurable output format (WAV, FLAC, MP3, etc.)
- Auto-analyze after download

### Audio Analysis

- **BPM detection** — accurate tempo estimation
- **Musical key detection** — Camelot and standard notation (e.g., `8A` / `Am`)
- **Genre/mood tagging** — classification via Essentia's pre-trained models

### Library Management

- SQLite-backed track catalog
- Search and filter by BPM, key, genre, mood, artist, title
- Embedded metadata — write analysis results into file ID3/Vorbis tags
- List, inspect, and export library contents

## Tech Stack

- **Python 3.12+**
- **[Essentia](https://essentia.upf.edu/)** — audio analysis (BPM, key, genre, mood)
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — media downloading
- **[mutagen](https://mutagen.readthedocs.io/)** — audio metadata read/write
- **[Click](https://click.palletsprojects.com/)** — CLI framework
- **[Rich](https://rich.readthedocs.io/)** — terminal output formatting
- **SQLite** — library catalog storage

## Architecture

Hexagonal architecture — domain core with ports and adapters.

```
musikbox/
├── cli/                    # Click command groups
│   ├── __init__.py
│   ├── main.py             # CLI entrypoint
│   ├── download.py         # download commands
│   ├── analyze.py          # analyze commands
│   └── library.py          # library commands
├── domain/
│   ├── __init__.py
│   ├── models.py           # Track, AnalysisResult, KeyNotation
│   └── ports.py            # Abstract interfaces (TrackRepository, Downloader, Analyzer)
├── services/
│   ├── __init__.py
│   ├── download_service.py # Orchestrates download + optional analysis
│   ├── analysis_service.py # Orchestrates audio analysis pipeline
│   └── library_service.py  # Library CRUD and search
├── adapters/
│   ├── __init__.py
│   ├── sqlite_repository.py  # TrackRepository implementation
│   ├── ytdlp_downloader.py   # Downloader implementation
│   ├── essentia_analyzer.py  # Analyzer implementation
│   └── metadata_writer.py    # Mutagen-based tag writer
├── config/
│   ├── __init__.py
│   └── settings.py          # Config loading (paths, defaults)
└── __init__.py
```

### Domain Models

```python
@dataclass
class Track:
    id: str                     # UUID
    title: str
    artist: str | None
    album: str | None
    duration_seconds: float
    file_path: Path
    format: str                 # wav, flac, mp3, etc.
    bpm: float | None
    key: str | None             # e.g., "Am" or "8A"
    genre: str | None
    mood: str | None
    source_url: str | None
    downloaded_at: datetime | None
    analyzed_at: datetime | None
    created_at: datetime

@dataclass
class AnalysisResult:
    bpm: float
    key: str                    # Standard notation (e.g., "Am")
    key_camelot: str            # Camelot notation (e.g., "8A")
    genre: str
    mood: str
    confidence: dict[str, float]  # Per-field confidence scores
```

### Ports (Interfaces)

```python
class TrackRepository(ABC):
    def save(self, track: Track) -> None: ...
    def get_by_id(self, track_id: str) -> Track | None: ...
    def search(self, **filters) -> list[Track]: ...
    def delete(self, track_id: str) -> None: ...
    def list_all(self, limit: int = 50, offset: int = 0) -> list[Track]: ...

class Downloader(ABC):
    def download(self, url: str, output_dir: Path, format: str = "flac") -> Path: ...

class Analyzer(ABC):
    def analyze(self, file_path: Path) -> AnalysisResult: ...
```

## CLI Usage

```bash
# Download and auto-analyze
musikbox download <url>
musikbox download <url> --format mp3 --no-analyze

# Analyze existing files
musikbox analyze <file>
musikbox analyze <directory> --recursive

# Library management
musikbox library list
musikbox library list --sort-by bpm --key Am
musikbox library search "aphex twin"
musikbox library search --bpm-range 120-130 --key 8A
musikbox library inspect <track-id>
musikbox library import <file-or-directory>    # Import existing files into library
musikbox library export --format csv           # Export catalog as CSV

# Configuration
musikbox config show
musikbox config set music_dir ~/Music/musikbox
musikbox config set default_format flac
```

## Configuration

Config stored at `~/.config/musikbox/config.toml`:

```toml
[general]
music_dir = "~/Music/musikbox"
default_format = "flac"
auto_analyze = true

[analysis]
write_tags = true          # Write BPM/key/genre into file metadata
key_notation = "camelot"   # "camelot" | "standard" | "both"

[download]
audio_quality = "best"
```

## Installation

```bash
# Clone and install in editable mode
git clone <repo-url>
cd musikbox
pip install -e ".[dev]"

# Or with uv
uv pip install -e ".[dev]"
```

## Development

```bash
# Run tests
pytest

# Type checking
mypy musikbox/

# Linting
ruff check musikbox/
ruff format musikbox/
```

## Roadmap

- [ ] MVP: download, analyze, library CRUD
- [ ] Batch import/analyze existing music collection
- [ ] Duplicate detection (audio fingerprinting)
- [ ] Playlist generation (harmonic mixing suggestions based on Camelot wheel)
- [ ] Web UI (local)
- [ ] Ableton integration (export metadata, set markers)
- [ ] SoundCloud / Bandcamp support
