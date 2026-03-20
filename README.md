# musikbox

A CLI tool for downloading, analyzing, managing, and playing a local music library. Built for DJs and producers who need BPM, musical key, and genre metadata.

## Features

### Download

- Download audio from YouTube and YouTube Music (via yt-dlp)
- Download entire playlists
- Configurable output format (WAV, FLAC, MP3, etc.)
- Browser cookie support for bypassing bot detection
- Auto-analyze after download
- Auto-parse artist/title from YouTube filenames

### Audio Analysis

- **BPM detection** — accurate tempo estimation via librosa
- **Musical key detection** — Camelot and standard notation (e.g., `8A` / `Am`)
- **Genre lookup** — via MusicBrainz (artist-level fallback)
- **Metadata writing** — write BPM/key/genre into file ID3/Vorbis tags
- **LLM enrichment** — use Claude Haiku to extract artist, title, album, remix, year, genre, and sub-genre tags from messy YouTube titles

### Library Management

- SQLite-backed track catalog
- Search and filter by BPM, key, genre, artist, title
- Sort by Camelot key for harmonic mixing (compatible keys adjacent)
- Multi-column sort (e.g., `--sort-by key,bpm`)
- Named library folders with scan/rescan
- Batch import and analyze existing collections
- Fix metadata retroactively (`library fix-metadata`)
- Export library as CSV

### Playlists

- Create playlists manually or from library filters
- Import YouTube playlists (downloads + creates playlist)
- Interactive reorder/remove in player mode
- Play playlists directly

### Playback

- Terminal-based audio player (via mpv)
- Rich now-playing display with progress bar
- Interactive queue browser (j/k navigation)
- Keyboard controls: play/pause, seek, next/prev, search
- Inline track editing during playback
- Queue search with `/`

## Tech Stack

- **Python 3.12+**
- **[librosa](https://librosa.org/)** — audio analysis (BPM, key detection)
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — media downloading
- **[mutagen](https://mutagen.readthedocs.io/)** — audio metadata read/write
- **[Click](https://click.palletsprojects.com/)** — CLI framework
- **[Rich](https://rich.readthedocs.io/)** — terminal output and live display
- **[python-mpv](https://github.com/jaseg/python-mpv)** — audio playback (requires mpv)
- **[MusicBrainz API](https://musicbrainz.org/)** — genre lookup (no API key needed)
- **[Anthropic Claude Haiku](https://www.anthropic.com/)** — LLM metadata enrichment (optional)
- **SQLite** — library and playlist storage

## Installation

```bash
# Clone and install
git clone https://github.com/djordje-bjelajac/musikbox.git
cd musikbox
uv pip install -e ".[dev]"

# Optional: audio analysis
uv pip install -e ".[analysis]"

# Optional: playback (also install mpv: brew install mpv)
uv pip install -e ".[playback]"

# Optional: LLM enrichment
uv pip install -e ".[enrichment]"

# Initialize database
musikbox db init
```

## CLI Usage

```bash
# Download
musikbox download <url>
musikbox download <url> --format mp3 --no-analyze
musikbox download <url> --cookies-from-browser brave
musikbox download <url> --playlist --cookies-from-browser brave

# Analyze
musikbox analyze <file>
musikbox analyze <directory> --recursive
musikbox analyze --all                    # Analyze all unanalyzed library tracks

# Library management
musikbox library list
musikbox library list --sort-by key,bpm
musikbox library search "aphex twin"
musikbox library search --bpm-range 120-130 --key 8A --sort-by key,bpm
musikbox library inspect <track-id>
musikbox library import <file-or-directory> --recursive
musikbox library export output.csv
musikbox library fix-metadata             # Parse artist/title, look up genres
musikbox library enrich                   # LLM-powered metadata extraction

# Library folders
musikbox library folders add vinyl ~/Music/vinyl-rips
musikbox library folders add bandcamp ~/Music/bandcamp
musikbox library folders list
musikbox library folders scan --recursive
musikbox library folders scan vinyl

# Playlists
musikbox playlist create "friday set"
musikbox playlist create "techno" --from-library --genre electronic --bpm-range 120-130 --sort-by key,bpm
musikbox playlist import-yt "disco mix" <youtube-playlist-url> --cookies-from-browser brave
musikbox playlist list
musikbox playlist show "friday set"
musikbox playlist add "friday set" <track-id>
musikbox playlist remove "friday set" <track-id>
musikbox playlist delete "friday set"

# Playback
musikbox play --all --sort-by key,bpm
musikbox play --key Am --bpm-range 115-125
musikbox play --playlist "friday set"
musikbox play <track-id>

# Configuration
musikbox config show
musikbox config set MUSIKBOX_MUSIC_DIR=~/Music/musikbox
musikbox config set MUSIKBOX_DEFAULT_FORMAT=flac
musikbox config set MUSIKBOX_COOKIES_FROM_BROWSER=brave
```

## Playback Controls

| Key | Action |
|-----|--------|
| Space | Play/pause |
| `,` / `.` | Seek -10s / +10s |
| `j` / `k` | Browse queue up/down |
| Enter | Jump to browsed track |
| `n` / `p` | Next / previous track |
| `/` | Search queue |
| `e` | Edit track metadata |
| `m` | Grab track to reorder (playlist mode) |
| `x` | Remove track from playlist |
| `q` | Quit |

## Configuration

Config stored at `~/.config/musikbox/.env`:

```bash
MUSIKBOX_MUSIC_DIR=~/Music/musikbox
MUSIKBOX_DEFAULT_FORMAT=flac
MUSIKBOX_AUTO_ANALYZE=true
MUSIKBOX_WRITE_TAGS=true
MUSIKBOX_KEY_NOTATION=camelot
MUSIKBOX_AUDIO_QUALITY=best
MUSIKBOX_COOKIES_FROM_BROWSER=brave
ANTHROPIC_API_KEY=sk-...                  # Optional, for LLM enrichment
```

## Architecture

Hexagonal architecture — domain core with ports and adapters.

```
musikbox/
├── cli/                         # Click command groups
│   ├── main.py                  # CLI entrypoint
│   ├── download.py              # Download commands
│   ├── analyze.py               # Analyze commands
│   ├── library.py               # Library + folder management
│   ├── playlist.py              # Playlist commands
│   ├── play.py                  # Playback with Rich TUI
│   ├── db.py                    # Database init
│   └── config.py                # Config show/set
├── domain/
│   ├── models.py                # Track, Playlist, AnalysisResult, SearchFilter
│   ├── exceptions.py            # Domain exception hierarchy
│   └── ports/                   # Abstract interfaces
│       ├── repository.py        # TrackRepository
│       ├── playlist_repository.py
│       ├── downloader.py        # Downloader
│       ├── analyzer.py          # Analyzer
│       ├── metadata_writer.py   # MetadataWriter
│       ├── genre_lookup.py      # GenreLookup
│       ├── metadata_enricher.py # MetadataEnricher
│       └── player.py            # Player
├── services/
│   ├── download_service.py      # Download + analysis orchestration
│   ├── analysis_service.py      # Audio analysis pipeline
│   ├── library_service.py       # Library CRUD and search
│   ├── playlist_service.py      # Playlist management
│   └── playback_service.py      # Queue and playback control
├── adapters/
│   ├── sqlite_repository.py     # SQLite track storage
│   ├── sqlite_playlist_repository.py
│   ├── ytdlp_downloader.py      # yt-dlp downloading
│   ├── librosa_analyzer.py      # BPM/key detection
│   ├── musicbrainz_genre_lookup.py  # Genre from MusicBrainz
│   ├── metadata_writer.py       # Mutagen tag writing
│   ├── mpv_player.py            # mpv playback
│   ├── haiku_enricher.py        # Claude Haiku metadata extraction
│   ├── fake_analyzer.py         # Test doubles
│   ├── fake_downloader.py
│   ├── fake_player.py
│   └── fake_enricher.py
├── config/
│   └── settings.py              # .env config loading
└── bootstrap.py                 # Dependency wiring
```

## Development

```bash
# Run tests
uv run pytest

# Type checking
uv run mypy musikbox/

# Linting + formatting
uv run ruff check musikbox/
uv run ruff format musikbox/
```

## Roadmap

- [x] Download, analyze, library CRUD
- [x] Batch import/analyze existing music collections
- [x] Playlist management
- [x] Terminal playback with Rich TUI
- [x] MusicBrainz genre lookup
- [x] LLM metadata enrichment
- [ ] Duplicate detection (audio fingerprinting)
- [ ] M3U playlist export (Rekordbox, Traktor)
- [ ] Web UI (local)
- [ ] Ableton integration (export metadata, set markers)
- [ ] SoundCloud / Bandcamp support
