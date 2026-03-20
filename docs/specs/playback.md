# Technical Specification: Playback

## 1. Overview

Add audio playback to musikbox via `mpv` (libmpv). Users can play tracks from their library with a Rich now-playing display and keyboard controls.

**Success criteria:** Play filtered/sorted library tracks with play/pause/skip controls and a live progress display in the terminal.

## 2. Architecture

### New Port

```python
# domain/ports/player.py
class Player(ABC):
    @abstractmethod
    def play(self, file_path: Path) -> None: ...

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def resume(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def is_playing(self) -> bool: ...

    @abstractmethod
    def is_paused(self) -> bool: ...

    @abstractmethod
    def position(self) -> float:
        """Current playback position in seconds."""
        ...

    @abstractmethod
    def duration(self) -> float:
        """Total duration of current track in seconds."""
        ...
```

### New Adapter

```python
# adapters/mpv_player.py
class MpvPlayer(Player):
    """Player implementation using python-mpv (libmpv)."""
```

### New Service

```python
# services/playback_service.py
class PlaybackService:
    """Manages a queue of tracks and delegates playback to Player port."""

    def __init__(self, player: Player) -> None: ...

    def load_queue(self, tracks: list[Track]) -> None: ...
    def play(self) -> None: ...
    def pause_resume(self) -> None: ...
    def next_track(self) -> Track | None: ...
    def previous_track(self) -> Track | None: ...
    def stop(self) -> None: ...
    def current_track(self) -> Track | None: ...
    def queue(self) -> list[Track]: ...
    def queue_index(self) -> int: ...
    def is_playing(self) -> bool: ...
    def is_paused(self) -> bool: ...
    def position(self) -> float: ...
    def duration(self) -> float: ...
```

### CLI

```python
# cli/play.py — Click command registered in main.py
```

## 3. Technical Design

### Dependencies

- `mpv` system package: `brew install mpv`
- `python-mpv` pip package: added to pyproject.toml optional deps

### Play Command

```
musikbox play [TRACK_ID]              # Play a single track
musikbox play --all                   # Play entire library
musikbox play --key 8A --sort-by bpm  # Play filtered/sorted subset
musikbox play --genre electronic      # Play by genre
musikbox play --bpm-range 120-130     # Play by BPM range
```

### Flow

1. Resolve tracks: by track ID, or by filters (reuse SearchFilter)
2. Sort if --sort-by provided
3. Display queue as Rich table, show track count and total duration
4. Wait for Enter to start (or `q` to cancel)
5. Enter playback loop with now-playing display and keyboard controls

### Now-Playing Display

Rich Live display that redraws in-place:

```
 Now Playing
┌──────────────────────────────────────────────┐
│  Track Title Here                            │
│  Artist Name                                 │
│  128.0 BPM  ·  Am  ·  8A  ·  Electronic     │
│                                              │
│  ▶  01:23 ━━━━━━━━━━━━━━━━━━━━━━━━━━ 04:56   │
│                                              │
│  [3/12]  space: pause  n: next  p: prev  q: quit │
└──────────────────────────────────────────────┘
```

### Keyboard Controls

| Key          | Action       |
|--------------|-------------|
| Space        | Play/Pause   |
| `n` / Right  | Next track   |
| `p` / Left   | Prev track   |
| `q`          | Quit         |

### Keyboard Input

Use `sys.stdin` in raw mode (tty.setraw + select/poll for non-blocking reads) on a background thread. Restore terminal on exit via try/finally + atexit.

### Track Advancement

When mpv fires its `end-file` event (track finished), auto-advance to next track in queue. If last track, stop and exit.

### Error Handling

- If mpv is not installed, raise a clear error: "mpv not found. Install with: brew install mpv"
- If a track file is missing, skip to next track with a warning
- Ctrl+C handled gracefully: stop playback, restore terminal, exit

## 4. Non-Functional Requirements

- Playback must not block the UI thread (mpv runs in its own thread)
- Terminal must be restored to normal state on any exit path
- Keyboard response time < 100ms

## 5. Testing Strategy

- **MpvPlayer:** manual testing (requires mpv + audio hardware)
- **FakePlayer:** implements Player port with state tracking, no audio
- **PlaybackService:** unit tests with FakePlayer — queue management, next/prev, pause/resume
- **CLI:** CliRunner tests with mocked service (verify filters, queue display)

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| mpv not installed | Clear error message with install instructions |
| Terminal left in raw mode on crash | atexit handler + try/finally to restore |
| python-mpv API changes | Pin version, thin adapter layer |

## 7. Open Questions

- Shuffle/loop: deferred to later
- Interactive queue editing: deferred to later
- Volume control: deferred to later
