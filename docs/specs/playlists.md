# Technical Specification: Playlists

## 1. Overview

Add named playlists to musikbox — manual curation, creation from library filters, YouTube playlist import, and interactive reordering/editing in player mode.

**Success criteria:** Users can create playlists from library filters, import YouTube playlists, reorder/remove tracks interactively, and play playlists.

## 2. Architecture

### Domain Model

```python
@dataclass
class Playlist:
    id: str                    # UUID
    name: str
    created_at: datetime
    updated_at: datetime

@dataclass
class PlaylistEntry:
    playlist_id: str
    track_id: str
    position: int              # 0-based ordering
```

### Storage

Two new SQLite tables (created via `musikbox db init`):

```sql
CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id TEXT NOT NULL,
    track_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, track_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(id)
);

CREATE INDEX IF NOT EXISTS idx_playlist_tracks_order
    ON playlist_tracks(playlist_id, position);
```

### New Port

```python
# domain/ports/playlist_repository.py
class PlaylistRepository(ABC):
    def create(self, playlist: Playlist) -> None: ...
    def get_by_id(self, playlist_id: str) -> Playlist: ...
    def get_by_name(self, name: str) -> Playlist | None: ...
    def list_all(self) -> list[Playlist]: ...
    def delete(self, playlist_id: str) -> None: ...
    def update(self, playlist: Playlist) -> None: ...
    def add_track(self, playlist_id: str, track_id: str, position: int) -> None: ...
    def remove_track(self, playlist_id: str, track_id: str) -> None: ...
    def get_tracks(self, playlist_id: str) -> list[Track]: ...
    def reorder(self, playlist_id: str, track_ids: list[str]) -> None: ...
```

### Service

```python
# services/playlist_service.py
class PlaylistService:
    def __init__(self, playlist_repo, track_repo, downloader, ...) -> None: ...

    def create_playlist(self, name: str) -> Playlist: ...
    def create_from_library(
        self, name: str, search_filter: SearchFilter, sort_fields: list[str]
    ) -> Playlist: ...
    def import_youtube_playlist(self, name: str, url: str, format: str) -> Playlist: ...
    def list_playlists(self) -> list[Playlist]: ...
    def get_playlist_tracks(self, name: str) -> list[Track]: ...
    def add_track(self, playlist_name: str, track_id: str) -> None: ...
    def remove_track(self, playlist_name: str, track_id: str) -> None: ...
    def move_track(self, playlist_name: str, track_id: str, new_position: int) -> None: ...
    def delete_playlist(self, name: str) -> None: ...
```

## 3. Technical Design

### CLI Commands

```bash
# Create empty playlist
musikbox playlist create "friday set"

# Create from library with filters and sorting
musikbox playlist create "techno 125" --from-library \
    --genre electronic --bpm-range 120-130 --key Am --sort-by key,bpm

# List all playlists
musikbox playlist list

# Show playlist contents
musikbox playlist show "friday set"

# Add/remove tracks
musikbox playlist add "friday set" <track-id>
musikbox playlist remove "friday set" <track-id>

# Delete playlist
musikbox playlist delete "friday set"

# Import from YouTube
musikbox playlist import-yt "disco mix" <youtube-playlist-url>

# Play a playlist
musikbox play --playlist "friday set"
```

### Create from Library

`--from-library` reuses the existing SearchFilter and sort logic:

1. Build SearchFilter from --genre, --key, --bpm-range, --bpm-min, --bpm-max, --query
2. Query TrackRepository.search(filter)
3. Sort using the same Camelot-aware \_sort_key logic from cli/library.py
4. Create playlist and add all matching tracks in sorted order
5. Skip duplicates (track already in playlist)

### YouTube Playlist Import

1. Use existing DownloadService.download_playlist() to download all tracks
2. As each track completes, add it to the new playlist
3. Auto-analyze if enabled
4. Skip tracks already in library (match by title+artist or file path)
5. Playlist name from CLI argument (not auto-detected from YouTube)

### Duplicate Prevention

- When adding a track to a playlist, check if track_id already exists in playlist_tracks
- When importing from YouTube, check if file already exists in library (get_by_file_path)
  - If found, add existing track to playlist instead of re-downloading

### Player Integration

`musikbox play --playlist "friday set"` loads the playlist tracks into the playback queue.

### Interactive Reordering in Player Mode

In the player queue browser (j/k navigation):

- Press `m` to grab the browsed track (enters move mode)
- Use `j`/`k` to move it up/down in the queue
- Press `Enter` to drop it at the new position
- Press `Esc`/`m` again to cancel the move
- Press `Backspace`/`Delete`/`x` to remove the browsed track from the playlist

Changes are persisted to the playlist immediately.

Visual: the grabbed track shows a different style (e.g., bold yellow) while being moved.

## 4. Non-Functional Requirements

- Playlist operations should be fast (SQLite indexed queries)
- YouTube playlist import can be slow (downloading) — show progress per track
- Reorder operations save immediately (no "save playlist" step)

## 5. Testing Strategy

- **PlaylistRepository:** in-memory SQLite tests — CRUD, ordering, duplicates
- **PlaylistService:** mock repository tests — create from filter, add/remove, reorder
- **CLI:** CliRunner tests — command registration, basic flag parsing
- **Player reorder:** tested via PlaybackService with FakePlayer

## 6. Risks & Mitigations

| Risk                            | Mitigation                             |
| ------------------------------- | -------------------------------------- |
| Large YouTube playlists timeout | Download sequentially, skip failures   |
| Reorder race with auto-advance  | Mark manual change (existing guard)    |
| Playlist name collisions        | UNIQUE constraint, clear error message |

## 7. Open Questions

- M3U export: deferred to later
- Smart playlists (auto-updating filters): deferred to later
- Harmonic auto-generation as separate feature: user chose sort-by key,bpm + manual curation instead
