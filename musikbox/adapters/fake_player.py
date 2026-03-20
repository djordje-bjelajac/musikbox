from pathlib import Path

from musikbox.domain.ports.player import Player


class FakePlayer(Player):
    """In-memory Player implementation for testing."""

    def __init__(self) -> None:
        self._playing: bool = False
        self._paused: bool = False
        self._position: float = 0.0
        self._duration: float = 0.0
        self._file_path: Path | None = None

    def play(self, file_path: Path) -> None:
        self._file_path = file_path
        self._playing = True
        self._paused = False
        self._position = 0.0
        self._duration = 180.0

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def seek(self, seconds: float) -> None:
        self._position = max(0.0, min(self._duration, self._position + seconds))

    def stop(self) -> None:
        self._playing = False
        self._paused = False
        self._position = 0.0

    def is_playing(self) -> bool:
        return self._playing and not self._paused

    def is_paused(self) -> bool:
        return self._paused

    def position(self) -> float:
        return self._position

    def duration(self) -> float:
        return self._duration
