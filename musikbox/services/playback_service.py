import time

from musikbox.domain.models import Track
from musikbox.domain.ports.player import Player

# Time window (seconds) after a manual track change during which
# auto-advance is suppressed. This prevents the end-file event from
# the interrupted track from triggering an immediate skip forward.
_TRACK_CHANGE_GUARD_SECONDS = 2.0


class PlaybackService:
    """Manages a queue of tracks and delegates playback to a Player port."""

    def __init__(self, player: Player) -> None:
        self._player = player
        self._queue: list[Track] = []
        self._index: int = 0
        self._is_active: bool = False
        self._last_manual_change: float = 0.0

    def load_queue(self, tracks: list[Track]) -> None:
        """Set the playback queue and reset to the beginning."""
        self._queue = list(tracks)
        self._index = 0

    def play(self) -> None:
        """Start playing the current track in the queue."""
        if not self._queue:
            return
        track = self._queue[self._index]
        self._player.play(track.file_path)
        self._is_active = True

    def pause_resume(self) -> None:
        """Toggle between pause and resume."""
        if self._player.is_paused():
            self._player.resume()
        else:
            self._player.pause()

    def next_track(self, auto: bool = False) -> Track | None:
        """Advance to the next track and play it. Returns None if at end.

        Args:
            auto: If True, this is an auto-advance from track end callback.
                  Suppressed if a manual track change happened recently.
        """
        if auto and self._in_guard_window():
            return self.current_track()
        if self._index + 1 >= len(self._queue):
            self.stop()
            return None
        self._mark_manual_change()
        self._index += 1
        track = self._queue[self._index]
        self._player.play(track.file_path)
        return track

    def previous_track(self) -> Track | None:
        """Go back to the previous track and play it.

        If already at the first track, restarts it from the beginning.
        """
        self._mark_manual_change()
        if self._index > 0:
            self._index -= 1
        track = self._queue[self._index]
        self._player.play(track.file_path)
        return track

    def _mark_manual_change(self) -> None:
        self._last_manual_change = time.monotonic()

    def _in_guard_window(self) -> bool:
        return (time.monotonic() - self._last_manual_change) < _TRACK_CHANGE_GUARD_SECONDS

    def stop(self) -> None:
        """Stop playback entirely."""
        self._player.stop()
        self._is_active = False

    def current_track(self) -> Track | None:
        """Return the current track, or None if queue is empty."""
        if not self._queue:
            return None
        return self._queue[self._index]

    @property
    def queue(self) -> list[Track]:
        return list(self._queue)

    @property
    def queue_index(self) -> int:
        return self._index

    @property
    def is_active(self) -> bool:
        return self._is_active

    def seek(self, seconds: float) -> None:
        """Seek relative to current position."""
        self._player.seek(seconds)

    def is_playing(self) -> bool:
        return self._player.is_playing()

    def is_paused(self) -> bool:
        return self._player.is_paused()

    def position(self) -> float:
        return self._player.position()

    def duration(self) -> float:
        return self._player.duration()
