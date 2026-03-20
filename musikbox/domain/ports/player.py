from abc import ABC, abstractmethod
from pathlib import Path


class Player(ABC):
    """Port for audio playback."""

    @abstractmethod
    def play(self, file_path: Path) -> None:
        """Start playing the given audio file."""
        ...

    @abstractmethod
    def pause(self) -> None:
        """Pause the current playback."""
        ...

    @abstractmethod
    def resume(self) -> None:
        """Resume paused playback."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop playback entirely."""
        ...

    @abstractmethod
    def is_playing(self) -> bool:
        """Return True if audio is actively playing (not paused)."""
        ...

    @abstractmethod
    def is_paused(self) -> bool:
        """Return True if playback is paused."""
        ...

    @abstractmethod
    def seek(self, seconds: float) -> None:
        """Seek relative to current position (positive = forward, negative = back)."""
        ...

    @abstractmethod
    def position(self) -> float:
        """Current playback position in seconds."""
        ...

    @abstractmethod
    def duration(self) -> float:
        """Total duration of current track in seconds."""
        ...
