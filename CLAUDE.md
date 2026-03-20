# CLAUDE.md

## Project Overview

musikbox — a Python CLI tool for downloading, analyzing, and managing a local music library. Built for DJs and producers who need BPM, musical key, and genre metadata.

## Tech Stack

- Python 3.12+, Click (CLI), Rich (terminal output), SQLite (storage)
- Essentia (audio analysis), yt-dlp (downloading), mutagen (metadata tagging)
- pytest (testing), mypy (type checking), ruff (linting + formatting)

## Architecture

Hexagonal architecture — domain core with ports and adapters.

- `domain/` — models, ports (ABCs), exceptions. **Zero imports from services/adapters/cli.**
- `services/` — orchestration layer. Depends only on domain ports, never on concrete adapters.
- `adapters/` — implementations of domain ports. Each adapter gets its dependencies via constructor injection.
- `cli/` — Click command groups. Thin layer that calls `bootstrap.create_app()` and uses returned services.
- `config/` — central configuration loading from `.env`. No business logic.
- `bootstrap.py` — single module that builds the object graph (creates adapters, injects into services).

**Dependency rule:** domain ← services ← adapters/cli. Never inward.

### Ports Structure

Ports live in separate files, one per interface:

```
domain/ports/
├── __init__.py
├── repository.py      # TrackRepository ABC
├── downloader.py      # Downloader ABC
├── analyzer.py        # Analyzer ABC
└── metadata_writer.py # MetadataWriter ABC
```

### Error Handling

- All domain exceptions live in `domain/exceptions.py`, inheriting from `MusikboxError`
- Adapters catch library-specific errors and raise domain exceptions (e.g., `yt_dlp.DownloadError` → `DownloadError`)
- Services propagate domain exceptions — no re-wrapping unless adding context
- CLI catches domain exceptions and renders user-friendly Rich output
- **No Result types** — use try/except for all error paths

### Wiring

- `bootstrap.py` creates all adapters and services — CLI commands never instantiate adapters directly
- Config is loaded once in bootstrap, individual values passed to adapters/services via constructor args

### Configuration

- Central `config/settings.py` loads all env variables from `~/.config/musikbox/.env` via `python-dotenv`
- Config is a set of dataclasses (`Config`, `DownloadConfig`, `AnalysisConfig`)
- Environment variables override `.env` values

### ID Generation

- `TrackId` is a value object that generates a UUID on construction
- Domain owns ID generation — callers never pass raw strings

### CLI Output

- Services return domain objects — no formatting in services
- CLI handles all Rich console output inline (no shared presentation layer)
- No `print()`, no `logging` module — Rich console only

### Database

- `musikbox db init` command for schema creation (not auto-create)
- SQLite with indexes on `bpm`, `key`, `genre`

### Search

- `SearchFilter` dataclass for all search/filter operations — no `**kwargs`

## Code Style

- All functions and methods have type hints (parameters and return types)
- No `Any` type — use `object`, generics, or proper union types
- Use `|` union syntax, not `Optional` or `Union`
- Dataclasses for domain models, not dicts
- All ports are ABCs with `@abstractmethod`
- Adapter constructors take dependencies via DI (no global state)
- Exceptions live in `domain/exceptions.py`
- Use `Path` objects, not strings, for file paths
- f-strings for string formatting
- Keep functions short and single-purpose

## Testing

**TDD — write tests first, then implement.**

**Co-located tests:** test files live next to the code they test, named `test_<module>.py`.

```
musikbox/
├── domain/
│   ├── models.py
│   ├── test_models.py
│   ├── ports/
│   │   ├── repository.py
│   │   └── ...
│   └── exceptions.py
├── adapters/
│   ├── sqlite_repository.py
│   ├── test_sqlite_repository.py
│   └── ...
├── services/
│   ├── download_service.py
│   ├── test_download_service.py
│   └── ...
```

- pytest with no test directory prefix — discover via `testpaths` in pyproject.toml
- Adapter tests use real implementations where feasible (e.g., in-memory SQLite)
- Service tests mock the ports (not the adapters)
- Use `pytest.fixture` over manual setup
- No `unittest.TestCase` — plain functions only
- Test names: `test_<what>_<condition>_<expected>` (e.g., `test_search_by_bpm_range_returns_matching_tracks`)
- Audio test fixtures generated via numpy (sine waves) — no committed binary files
- `FakeAnalyzer` and `FakeDownloader` implement ports for testing without external dependencies

## Naming Conventions

- Modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: single `_prefix`

## Commit Style

Conventional commits: `feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`

## Commands

```bash
# Run tests
pytest

# Type checking
mypy musikbox/

# Linting + formatting
ruff check musikbox/
ruff format musikbox/

# Install in dev mode
uv pip install -e ".[dev]"
```
