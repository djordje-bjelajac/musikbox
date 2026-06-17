# Client/Server Split with Selectable Playback Location

## Requirements

- Split the single-process musikbox application into a **library host (server)** and one or more **thin clients**, drawing the network boundary at the existing hexagonal ports so the domain core and orchestration services are reused unchanged.
- Centralize the **catalog, the audio files, and the heavy processing** on the server as the single source of truth and the single database writer.
- Let the user **choose, per listening session, where audio is rendered** — on the server's own audio output, or streamed to and rendered on the client device — without the controlling client needing the audio bytes (server output) or the server's filesystem (client output).
- Keep the client **lightweight**: runnable without the heavy/native dependencies (essentia, yt-dlp, anthropic).
- Preserve **backward compatibility**: the existing single-process ("local") mode must continue to work unchanged.

**Boundary for this slice:** browse/search the catalog from a client, plus full transport control in both output modes (server output and client output). Out of scope here: remote-triggered download/analyze/enrich (server already owns these; remote orchestration is a later phase), authentication, and a native/web client (the HTTP contract is designed to enable them later). LAN-only trust assumed.

## Entities

```mermaid
classDiagram
direction TB

class Track {
  +TrackId id
  +str title
  +str artist
  +float duration_seconds
  +Path file_path
  +str format
}

class PlayableSource {
  +str track_id
  +str locator
  +bool is_local
}

class TrackRepository {
  <<port>>
  +get_by_id(TrackId) Track
  +search(SearchFilter) list~Track~
  +list_all(limit, offset) list~Track~
}

class Player {
  <<port>>
  +play(PlayableSource) None
  +pause() None
  +resume() None
  +seek(seconds) None
  +position() float
  +duration() float
}

class TrackSourceResolver {
  <<port>>
  +resolve(Track) PlayableSource
}

class HttpTrackRepository {
  +base_url str
}

class RemotePlayer {
  +base_url str
}

class LocalSourceResolver
class RemoteStreamResolver {
  +base_url str
}

class TrackDTO {
  +str id
  +str title
  +str artist
  +float duration_seconds
  +str format
  +str stream_url
}

class PlayerStatusDTO {
  +float position
  +float duration
  +bool is_playing
  +bool is_paused
}

class ErrorResponse {
  +str error_code
  +str message
}

TrackRepository <|.. HttpTrackRepository : remote realization
Player <|.. RemotePlayer : remote realization
TrackSourceResolver <|.. LocalSourceResolver
TrackSourceResolver <|.. RemoteStreamResolver
TrackSourceResolver --> PlayableSource : produces
Player --> PlayableSource : consumes
Track --> TrackDTO : maps to (file_path hidden, stream_url added)
TrackDTO --> Track : reconstructs on client
RemoteStreamResolver --> PlayableSource : stream URL by track id
LocalSourceResolver --> PlayableSource : local path by track id
```

**Conservative-design notes (no unnecessary refactoring):**
- `Track`, `TrackId`, `SearchFilter`, `Playlist`, and all existing domain models are **unchanged**.
- The only domain additions are the `PlayableSource` value object and the `TrackSourceResolver` port.
- The only existing-contract change is generalizing `Player.play` from `Path` to `PlayableSource` (it must address a remote stream or a remote-controlled track, which a bare `Path` cannot express). All other `Player` methods are unchanged.
- DTOs (`TrackDTO`, `PlayerStatusDTO`, `ErrorResponse`) live only at the API boundary; they never leak into the domain. The client reconstructs domain `Track` objects from `TrackDTO` so `LibraryService` runs unmodified.

## Approach

1. **Architecture & boundary placement:**
   - Place the network seam **at the ports**, not through the services. The server *exposes* the existing services over HTTP; the client *realizes* `TrackRepository` and `Player` remotely. `LibraryService` and `PlaybackService` are reused on the client unchanged (the latter gains one injected dependency).
   - Three deployment modes selected by config: `local` (today's single process — default, unchanged behavior), `server` (runs the HTTP API), `client` (CLI/TUI wired to a remote server).
   - Model "where audio plays" as the **swap of the `Player` realization** on the client: `MpvPlayer` (renders locally from a stream URL) for client output, `RemotePlayer` (forwards transport commands to the server) for server output. `PlaybackService` owns the queue in both modes and is agnostic to the choice.

2. **Technical implementation:**
   - **Transport:** FastAPI + uvicorn on the server; `httpx` on the client. REST/JSON for catalog and control; a ranged streaming response for media (enables client-side seeking).
   - **Source resolution:** introduce `TrackSourceResolver` so `PlaybackService` converts each `Track` to a `PlayableSource` before calling `Player.play`. `LocalSourceResolver` yields the local file path (server / local mode); `RemoteStreamResolver` yields `{base_url}/tracks/{id}/stream` (client-output mode). `RemotePlayer` uses `PlayableSource.track_id` to tell the server which track to render (server-output mode).
   - **Error mapping (FastAPI analogue of a GlobalExceptionHandler):** central FastAPI exception handlers translate `MusikboxError` subtypes to HTTP status + `ErrorResponse`. The client's `HttpTrackRepository`/`RemotePlayer` translate non-2xx responses back into the same domain exceptions, preserving the existing CLI error-rendering paths.
   - **Performance/security:** stream addressed strictly by track id (no filesystem path in the API → no path traversal); `Range` requests for seek; reuse mpv's existing cache/buffer tuning for network playback; server is the single SQLite writer with WAL enabled.

3. **Business logic:**
   - Catalog reads flow client → `HttpTrackRepository` → server `LibraryService` → repository.
   - Client-output playback: `PlaybackService` (client) resolves track → stream URL → local `MpvPlayer`.
   - Server-output playback: `PlaybackService` (client) resolves track → `RemotePlayer` → server `/player/*` → server `MpvPlayer` + `LocalSourceResolver`.
   - Validation/error handling: unknown track id → `TrackNotFoundError` (404); unreachable/unexpected server response → new `RemoteServiceError` (rendered by CLI). Queue logic, auto-advance guard, and pause/resume semantics are unchanged.

## Structure

### Inheritance Relationships
1. `TrackRepository` port defines catalog persistence/query operations.
2. `HttpTrackRepository` implements `TrackRepository` over HTTP.
3. `Player` port defines transport control; `play` now accepts a `PlayableSource`.
4. `MpvPlayer` implements `Player` (renders a `PlayableSource.locator`, local path or URL).
5. `RemotePlayer` implements `Player` (forwards commands to the server by `PlayableSource.track_id`).
6. `TrackSourceResolver` port defines `resolve(Track) -> PlayableSource`.
7. `LocalSourceResolver` and `RemoteStreamResolver` implement `TrackSourceResolver`.
8. `RemoteServiceError` extends `MusikboxError`.

### Dependencies
1. Server `FastAPI app` injects `LibraryService`, the server-side `PlaybackService`, and `Config` via a server bootstrap.
2. Server `PlaybackService` depends on `MpvPlayer` + `LocalSourceResolver`.
3. Client `PlaybackService` depends on (`MpvPlayer` + `RemoteStreamResolver`) for client output, or (`RemotePlayer` + a track-id-only resolver) for server output.
4. Client `LibraryService` depends on `HttpTrackRepository`.
5. `HttpTrackRepository` and `RemotePlayer` depend on a shared `httpx.Client` wrapper.
6. CLI/TUI inject the services produced by the client bootstrap (unchanged call sites).

### Layered Architecture
1. **Domain layer:** add `PlayableSource` model and `TrackSourceResolver` port; generalize `Player.play`. Zero imports from outer layers (unchanged rule).
2. **Service layer:** `LibraryService` unchanged; `PlaybackService` gains a `TrackSourceResolver` dependency. No new services.
3. **Adapter layer:** add `HttpTrackRepository`, `RemotePlayer`, `LocalSourceResolver`, `RemoteStreamResolver`; generalize `MpvPlayer.play` and `FakePlayer`.
4. **API layer (new, server only):** FastAPI app, routers (`tracks`, `stream`, `player`), DTOs, exception handlers. Depends inward on services only.
5. **CLI layer:** `main` chooses bootstrap by mode; `play` command gains an output-target selector.
6. **Bootstrap/config:** split into `create_app` (local — unchanged signature/default), `bootstrap_server`, `bootstrap_client`; config gains mode/server-url/output-target/host/port.
7. **Exception-handling layer:** FastAPI exception handlers map domain exceptions → `ErrorResponse`; client adapters map HTTP errors → domain exceptions.

## Operations

### Create Domain Model - PlayableSource
1. Responsibility: Represent a location a `Player` can render, decoupled from local filesystem assumptions.
2. Attributes:
   - `track_id`: str — identity of the track to play.
   - `locator`: str — local file path (local mode) or stream URL (client-output mode); may be empty for server-output control.
   - `is_local`: bool — True if `locator` is a local filesystem path.
3. Definition: `@dataclass` in `musikbox/domain/models.py`; immutable value object; no behavior.
4. Constraints: No imports from services/adapters; `track_id` always populated.

### Create Domain Port - TrackSourceResolver
1. File: `musikbox/domain/ports/track_source_resolver.py`.
2. Interface Definition: ABC with `@abstractmethod resolve(self, track: Track) -> PlayableSource`.
3. Responsibility: Convert a `Track` into a `PlayableSource` appropriate to the runtime mode.
4. Constraints: Pure port; type-hinted; exported from `domain/ports/__init__.py`.

### Update Domain Port - Player
1. Change `play(self, file_path: Path) -> None` → `play(self, source: PlayableSource) -> None`.
2. Leave `pause/resume/stop/seek/position/duration/is_playing/is_paused` unchanged.
3. Constraints: Update the port docstring; this is the only signature change in the slice.

### Update Adapter - MpvPlayer
1. Change `play(self, source: PlayableSource) -> None` to call `self._mpv.play(source.locator)`.
2. Logic:
   - Reset `self._track_finished = False` (unchanged).
   - `self._mpv.play(source.locator)` — works for both local paths and `http(s)://` URLs (libmpv handles network streams).
3. Keep `set_media_title`, end-file callback, buffer/cache settings unchanged (network buffering reuses existing tuning).
4. Constraints: No new behavior beyond accepting a URL locator.

### Update Test Adapter - FakePlayer
1. Update `play` to accept `PlayableSource`; record `source` (track_id/locator) instead of a `Path` for assertions.
2. Constraints: Keep it dependency-free; update co-located `test_fake_player.py`.

### Create Adapter - LocalSourceResolver
1. File: `musikbox/adapters/local_source_resolver.py`.
2. Method: `resolve(track) -> PlayableSource`
   - Logic: return `PlayableSource(track_id=track.id.value, locator=str(track.file_path), is_local=True)`.
3. Usage: server and local modes.

### Create Adapter - RemoteStreamResolver
1. File: `musikbox/adapters/remote_stream_resolver.py`.
2. Attributes: `base_url: str`.
3. Method: `resolve(track) -> PlayableSource`
   - Logic: return `PlayableSource(track_id=track.id.value, locator=f"{self._base_url}/tracks/{track.id.value}/stream", is_local=False)`.
4. Usage: client-output mode (paired with `MpvPlayer`).

### Update Service - PlaybackService
1. Constructor: `__init__(self, player: Player, source_resolver: TrackSourceResolver)`.
2. Core change: in `play`, `next_track`, `previous_track`, replace `self._player.play(track.file_path)` with `self._player.play(self._source_resolver.resolve(track))`.
3. Logic: Queue management, auto-advance guard window, and pause/resume semantics remain identical.
4. Constraints: No other behavior change; update `test_playback_service.py` to inject a resolver.

### Create Adapter - HttpTrackRepository (implements TrackRepository)
1. File: `musikbox/client/http_track_repository.py`.
2. Attributes: `base_url: str`, shared `httpx.Client`.
3. Core Methods:
   - `get_by_id(track_id) -> Track`
     - Input: `TrackId`. Calls `GET /tracks/{id}`.
     - On 200: map `TrackDTO` → `Track` (reconstruct, set `file_path` to the stream URL placeholder or a sentinel; clients must not use it for local IO).
     - On 404: raise `TrackNotFoundError`. On other non-2xx: raise `RemoteServiceError`.
   - `search(filter) -> list[Track]`: `GET /tracks/search` with `SearchFilter` fields as query params; map list of DTOs.
   - `list_all(limit, offset) -> list[Track]`: `GET /tracks?limit=&offset=`; map list.
   - `get_by_file_path`, `get_by_source_url`, `save`, `delete`: implement against corresponding endpoints **or** raise `RemoteServiceError("unsupported in client mode")` for write paths not in this slice (browse-and-play scope). Document which are stubbed.
4. Constraints: Translate transport errors to domain exceptions; never expose `httpx` types upward.

### Create Adapter - RemotePlayer (implements Player)
1. File: `musikbox/client/remote_player.py`.
2. Attributes: `base_url: str`, shared `httpx.Client`.
3. Methods:
   - `play(source) -> None`: `POST /player/play` with `{ "track_id": source.track_id }`.
   - `pause/resume/stop`: `POST /player/pause` `/resume` `/stop`.
   - `seek(seconds) -> None`: `POST /player/seek` with `{ "seconds": seconds }`.
   - `position/duration/is_playing/is_paused`: `GET /player/status`, read the field from `PlayerStatusDTO` (poll-based; acceptable for the TUI Tick loop).
4. Constraints: Map non-2xx to `RemoteServiceError`; tolerate transient status polling failures by returning last-known/zero values rather than raising in hot paths.

### Create API DTOs
1. File: `musikbox/server/dtos.py` (pydantic models).
2. `TrackDTO`: mirror public `Track` fields; **omit `file_path`**, add `stream_url`. Provide `from_track(track, base_url) -> TrackDTO`.
3. `PlayerStatusDTO`: `position, duration, is_playing, is_paused`.
4. `PlayCommand`: `{ track_id: str }`; `SeekCommand`: `{ seconds: float }`.
5. `ErrorResponse`: `{ error_code: str, message: str }`.

### Create API Routers
1. File: `musikbox/server/routers/tracks.py`
   - `GET /tracks?limit&offset` → `LibraryService.list_tracks` → `[TrackDTO]`.
   - `GET /tracks/{id}` → `LibraryService.get_track` → `TrackDTO`.
   - `GET /tracks/search` (query params per `SearchFilter`) → `LibraryService.search_tracks` → `[TrackDTO]`.
2. File: `musikbox/server/routers/stream.py`
   - `GET /tracks/{id}/stream` → resolve track → stream the file with **`Range` support** and correct content-type; 404 if missing.
3. File: `musikbox/server/routers/player.py`
   - `POST /player/play` (`PlayCommand`): resolve track via `LocalSourceResolver`, call server `PlaybackService`/`MpvPlayer`.
   - `POST /player/pause|resume|stop`, `POST /player/seek` (`SeekCommand`).
   - `GET /player/status` → `PlayerStatusDTO`.
4. Constraints: Routers depend only on injected services; no business logic in routers.

### Create Server App & Exception Handlers
1. File: `musikbox/server/app.py` — `create_api(app_services) -> FastAPI`; mount routers; register exception handlers.
2. Exception handlers (FastAPI analogue of GlobalExceptionHandler):
   - `TrackNotFoundError`/`PlaylistNotFoundError` → 404 + `ErrorResponse`.
   - `UnsupportedFormatError` → 415; `ConfigError` → 400; `DatabaseError` → 503; `MusikboxError` (fallback) → 500.
   - Each returns `ErrorResponse(error_code=<ExceptionClassName>, message=str(exc))` — never expose stack traces or internal paths.
3. Constraints: Handlers registered centrally; consistent response shape.

### Create Business Exception - RemoteServiceError
1. Inheritance: `class RemoteServiceError(MusikboxError)` in `musikbox/domain/exceptions.py`.
2. Usage: raised by client adapters when the server is unreachable or returns an unmapped non-2xx response.
3. Constraints: Carries a human-readable message; rendered by the CLI like other domain exceptions.

### Update Config & Bootstrap
1. `Config`: add `mode: str` (`local|server|client`, default `local`), `server_url: str | None`, `output_target: str` (`server|client`, default `client`), `server_host: str`, `server_port: int`.
2. `load_config`: read `MUSIKBOX_MODE`, `MUSIKBOX_SERVER_URL`, `MUSIKBOX_OUTPUT_TARGET`, `MUSIKBOX_SERVER_HOST` (default `0.0.0.0`), `MUSIKBOX_SERVER_PORT` (default `8765`).
3. `bootstrap_server() -> <services bundle>`: build repository (WAL), `LibraryService`, server `PlaybackService` (`MpvPlayer` + `LocalSourceResolver`); pass to `create_api`.
4. `bootstrap_client() -> App`: build `HttpTrackRepository`, `LibraryService` over it; build `PlaybackService` with `MpvPlayer + RemoteStreamResolver` (client output) or `RemotePlayer + track-id resolver` (server output) per `output_target`.
5. `create_app()` (local): unchanged behavior — wire `LocalSourceResolver` into `PlaybackService`; default path preserved.

### Update CLI Entry Points
1. `musikbox/cli/main.py`: select bootstrap by `config.mode` (`local` → `create_app`, `client` → `bootstrap_client`).
2. New console script `musikbox-server` (in `pyproject.toml`) → runs uvicorn against `bootstrap_server`.
3. `musikbox/cli/play.py`: add `--output [server|client]` (default from config) to choose the playback location at launch; wire the corresponding `Player`/resolver.

## Norms

1. **Type hints:** every function/method fully annotated; **no `Any`**; use `|` unions; `Path` for filesystem paths; DTO/network strings stay strings.
2. **Domain purity:** `domain/` imports nothing from services/adapters/api; new `PlayableSource`/`TrackSourceResolver` follow this.
3. **Dependency injection:** all adapters receive dependencies (base URLs, `httpx.Client`, resolvers) via constructors; no global state; wiring only in bootstrap modules.
4. **Ports as ABCs:** new ports use `@abstractmethod`; one interface per file under `domain/ports/`.
5. **DTO boundary:** pydantic models only under `musikbox/server/`; map to/from domain models explicitly; **never** serialize `file_path`.
6. **Exception handling:** reuse `domain/exceptions.py`; add only `RemoteServiceError`. Server maps domain → `ErrorResponse`; client maps HTTP status → domain exceptions. No `print`/`logging` — Rich console in CLI only; the API returns structured `ErrorResponse`.
7. **No Result types:** try/except throughout (per project convention).
8. **Testing (TDD, co-located `test_<module>.py`):**
   - Service tests mock ports (inject fake resolver/player/repository).
   - `HttpTrackRepository`/`RemotePlayer`: test against a stubbed `httpx` transport (e.g. `httpx.MockTransport`) — no live server.
   - API routers: test with FastAPI `TestClient` over `bootstrap_server` wired with fakes (`FakePlayer`, in-memory SQLite).
   - Streaming: assert `Range` requests return 206 with correct partial bytes.
   - Audio fixtures generated via numpy; no committed binaries.
9. **Formatting/typing:** `ruff check` + `ruff format` + `mypy --strict` clean before commit; conventional commits (`feat:`, `refactor:`, `test:`); run lint/format before each commit; commit in small increments.
10. **Dependencies:** add `[server]` extra (`fastapi`, `uvicorn[standard]`) and `[client]` extra (`httpx`); pydantic comes via FastAPI. Client install must not require essentia/yt-dlp/anthropic.

## Safeguards

1. **Functional constraints:** `local` mode behavior is byte-for-byte preserved (default mode; existing tests pass unchanged except the mechanical `Player.play`/`PlaybackService` constructor updates). Both output modes must support play/pause/resume/stop/next/previous/seek and report position/duration.
2. **Performance constraints:** streaming endpoint must honor HTTP `Range` (206 Partial Content) so client-side seek works without full-file download; status polling for `RemotePlayer` must be lightweight enough for the TUI Tick cadence; reuse existing mpv buffer settings for network playback.
3. **Security constraints:** media is addressed by track id only — no filesystem path accepted from clients (prevents path traversal); `ErrorResponse` must not leak stack traces, absolute paths, or internal identifiers; LAN-only assumption documented; the contract must leave room for an access-token gate before any non-LAN exposure (no design choice that precludes it).
4. **Integration constraints:** `LibraryService` is reused **unmodified**; the only service change is `PlaybackService`'s added `TrackSourceResolver` dependency; the only port change is `Player.play`. No other existing public signatures change.
5. **Business-rule constraints:** server is the single SQLite writer; WAL enabled for concurrent client reads; `Track.file_path` is never interpreted on the client; write operations (download/analyze/enrich) are not exposed to clients in this slice (stubbed adapter methods raise `RemoteServiceError`).
6. **Exception-handling constraints:** all domain exceptions crossing the API map to `ErrorResponse` with a stable `error_code`; client adapters re-raise the matching domain exception so existing CLI rendering is unchanged; unmapped/transport failures surface as `RemoteServiceError`.
7. **Technical constraints:** domain layer remains import-clean; pydantic/httpx/fastapi confined to api/client packages; no `Any`; `mypy --strict` clean.
8. **Data constraints:** `TrackDTO` excludes `file_path` and includes a resolvable `stream_url`; search query params map exactly to `SearchFilter` fields; pagination params (`limit`, `offset`) validated as non-negative.
9. **API constraints:** REST resource paths as specified (`/tracks`, `/tracks/{id}`, `/tracks/search`, `/tracks/{id}/stream`, `/player/*`); JSON request/response except the binary stream; consistent `ErrorResponse` envelope on errors; OpenAPI auto-generated by FastAPI for future web/mobile clients.
