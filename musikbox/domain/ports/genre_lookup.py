from abc import ABC, abstractmethod


class GenreLookup(ABC):
    """Port for looking up genre information by track title and artist."""

    @abstractmethod
    def lookup(self, title: str, artist: str | None = None) -> tuple[str, float]:
        """Look up genre for a track.

        Args:
            title: The track title.
            artist: Optional artist name for more accurate results.

        Returns:
            A tuple of (genre, confidence) where confidence is 0.0-1.0.
        """
        ...
