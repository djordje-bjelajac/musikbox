# Technical Specification: Event-Driven Player Architecture

## 1. Overview

Refactor the player mode from a monolithic 1400+ line file into an event-driven architecture with a queue-based event bus. All UI interaction, playback control, background tasks, and state management communicate through events.

**Goals:**

- Decouple input handling, playback logic, UI rendering, and background tasks
- Solve SQLite threading issues by processing all events on the main thread
- Make it easy to add new player features without touching existing code
- Design for future extension to the entire app

**Success criteria:** The player mode works identically to the current version but is built from small, focused components communicating via events.

## 2. Architecture

### Event Bus

Queue-based pub/sub. Events are posted to a `queue.Queue` from any thread. A single consumer loop on the main thread dispatches them to registered handlers.

```python
# events/bus.py

@dataclass
class EventBus:
    def subscribe(self, event_type: type, handler: Callable) -> None: ...
    def emit(self, event: object) -> None: ...
    def poll(self, timeout: float = 0.05) -> object | None: ...
    def dispatch(self, event: object) -> None: ...
```

- `emit()` is thread-safe — puts event on the queue from any thread
- `poll()` returns the next event or None (non-blocking with timeout)
- `dispatch()` calls all handlers registered for the event type
- Handlers run synchronously on the calling thread (main thread)

### Event Types

```python
# events/types.py

# Lifecycle
@dataclass
class Tick: ...

@dataclass
class Shutdown: ...

# Input
@dataclass
class KeyPressed:
    key: str

# Playback
@dataclass
class TrackStarted:
    track: Track
    index: int

@dataclass
class TrackEnded:
    index: int

@dataclass
class PlaybackPaused: ...

@dataclass
class PlaybackResumed: ...

@dataclass
class SeekRequested:
    seconds: float

# Queue
@dataclass
class QueueLoaded:
    tracks: list[Track]

@dataclass
class TrackAddedToQueue:
    track: Track

@dataclass
class TrackRemovedFromQueue:
    index: int

@dataclass
class QueueReordered: ...

@dataclass
class JumpToTrack:
    index: int

@dataclass
class NextTrackRequested:
    auto: bool = False

@dataclass
class PreviousTrackRequested: ...

# Browse / UI state
@dataclass
class BrowseIndexChanged:
    index: int | None

@dataclass
class MoveIndexChanged:
    index: int | None

@dataclass
class UIRefreshRequested: ...

# Edit mode
@dataclass
class EditTrackRequested:
    track: Track

@dataclass
class AddToPlaylistRequested:
    track: Track

@dataclass
class SearchQueueRequested: ...

@dataclass
class SortQueueRequested: ...

@dataclass
class BrowseLibraryRequested: ...

@dataclass
class AddTrackFromLibraryRequested: ...

# Background import
@dataclass
class ImportStarted:
    playlist_name: str

@dataclass
class ImportTrackDownloaded:
    track: Track
    count: int

@dataclass
class ImportCompleted:
    playlist_name: str
    count: int

@dataclass
class ImportFailed:
    error: str

@dataclass
class ImportTrackReady:
    """Track downloaded and ready to be saved to DB (main thread)."""
    track: Track
```

### Component Structure

```
musikbox/
├── events/
│   ├── __init__.py
│   ├── bus.py              # EventBus implementation
│   └── types.py            # All event dataclasses
├── cli/
│   ├── player/
│   │   ├── __init__.py
│   │   ├── app.py          # PlayerApp — main loop, wiring
│   │   ├── input.py        # Keyboard input → KeyPressed events
│   │   ├── controls.py     # KeyPressed → playback/queue commands
│   │   ├── renderer.py     # Events → Rich Live panel updates
│   │   ├── browser.py      # Library browser mode
│   │   ├── importer.py     # Background YouTube import
│   │   └── editor.py       # Track editing, playlist add, search
│   ├── play.py             # Thin CLI command entry point
```

### Component Responsibilities

**PlayerApp (`app.py`)**

- Creates EventBus
- Instantiates all components, each registers its own handlers
- Runs the main event loop
- Handles `Shutdown` event
- Emits `Tick` every ~250ms for progress bar updates

**InputHandler (`input.py`)**

- Background thread reading stdin in cbreak mode
- Emits `KeyPressed` events
- Can be paused/resumed (for edit mode, search mode)

**PlaybackControls (`controls.py`)**

- Subscribes to: `KeyPressed`, `TrackEnded`, `Tick`
- Manages: PlaybackService, browse_index, move_index state
- Emits: `TrackStarted`, `PlaybackPaused`, `PlaybackResumed`,
  `NextTrackRequested`, `BrowseIndexChanged`, `EditTrackRequested`,
  `SearchQueueRequested`, `SortQueueRequested`, etc.
- Maps keys to actions:
  - Space → pause/resume
  - j/k → browse
  - n/p → next/prev
  - Enter → jump to track
  - etc.

**Renderer (`renderer.py`)**

- Subscribes to: `TrackStarted`, `PlaybackPaused`, `PlaybackResumed`,
  `BrowseIndexChanged`, `MoveIndexChanged`, `ImportStarted`,
  `ImportTrackDownloaded`, `ImportCompleted`, `Tick`, `UIRefreshRequested`
- Owns the Rich Live instance
- Rebuilds the now-playing panel on relevant events
- Progress bar updates on `Tick`

**LibraryBrowser (`browser.py`)**

- Activated by `BrowseLibraryRequested`
- Takes over input handling temporarily
- Emits `TrackAddedToQueue` when user selects a track

**Importer (`importer.py`)**

- Activated by import command (from `controls.py`)
- Runs yt-dlp download in background thread
- Emits `ImportTrackReady` (background thread → queue → main thread)
- Main thread handler saves to DB on `ImportTrackReady`
- Emits `ImportTrackDownloaded`, `ImportCompleted`, `ImportFailed`

**Editor (`editor.py`)**

- Handles `EditTrackRequested`, `AddToPlaylistRequested`
- Pauses input, restores terminal, prompts user
- Saves changes to DB
- Resumes input when done

## 3. Technical Design

### Main Event Loop

```python
class PlayerApp:
    def run(self, tracks: list[Track], start_index: int = 0):
        self.bus = EventBus()

        # Components register their own handlers
        self.input = InputHandler(self.bus)
        self.controls = PlaybackControls(self.bus, self.playback_service)
        self.renderer = Renderer(self.bus, self.playback_service)
        self.importer = Importer(self.bus, self.app)
        self.editor = Editor(self.bus, self.repository)

        self.bus.emit(QueueLoaded(tracks))
        self.bus.emit(JumpToTrack(start_index))

        last_tick = time.monotonic()
        while not self.stopped:
            event = self.bus.poll(timeout=0.05)
            if event:
                self.bus.dispatch(event)

            now = time.monotonic()
            if now - last_tick >= 0.25:
                self.bus.emit(Tick())
                last_tick = now

        self.cleanup()
```

### Thread Safety

- `EventBus.emit()` uses `queue.Queue.put()` — thread-safe
- All handlers run on the main thread via `dispatch()`
- Background threads (input, import) only call `bus.emit()`
- SQLite operations only happen in handlers (main thread)

### Pausing Input for Modal Dialogs

When edit/search/sort/import prompts need text input:

1. Component emits a "pause input" signal (e.g., sets a flag on InputHandler)
2. InputHandler stops reading and restores terminal
3. Component does its text I/O
4. Component resumes InputHandler
5. InputHandler re-enters cbreak mode

This is the same pattern as today, but formalized.

### Migration from Current play.py

Complete rewrite of `cli/play.py` and `cli/player/*`. The current
`play.py` Click command becomes a thin wrapper that:

1. Resolves tracks (same filter/sort logic)
2. Shows queue preview (can stay as-is or move to a component)
3. Creates PlayerApp and calls `app.run(tracks, start_index)`

All the inline key handling, panel building, import status tracking,
and state management moves into the respective components.

## 4. Non-Functional Requirements

- Event dispatch latency < 1ms (in-process queue)
- UI responsiveness identical to current implementation
- No new dependencies — uses stdlib `queue.Queue` and `dataclasses`

## 5. Testing Strategy

- **EventBus:** unit test emit/subscribe/dispatch, thread safety
- **Controls:** emit KeyPressed, verify correct events are emitted
- **Renderer:** emit state events, verify panel is rebuilt (mock Live)
- **Importer:** verify ImportTrackReady emitted from background, DB save on main thread
- **Integration:** wire bus + components, simulate key sequence, verify behavior

## 6. Risks & Mitigations

| Risk                                       | Mitigation                                  |
| ------------------------------------------ | ------------------------------------------- |
| Event ordering issues                      | Single queue, FIFO, single consumer         |
| Missed events during modal dialogs         | Input is paused, no events lost in queue    |
| Performance regression from event overhead | In-process queue is negligible              |
| Larger refactor than expected              | Complete rewrite, not incremental — cleaner |

## 7. Open Questions

- Should the queue preview selector also be event-driven, or stay as a separate function? Defer — it works fine standalone.
- Should non-player commands (download, analyze) emit events? Design for it but defer implementation.
- Should events carry enough data for handlers to be stateless, or is shared state OK? Start pragmatic — shared state in components is fine, events carry context where natural.
