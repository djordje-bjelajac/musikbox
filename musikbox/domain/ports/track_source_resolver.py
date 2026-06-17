from abc import ABC, abstractmethod

from musikbox.domain.models import PlayableSource, Track


class TrackSourceResolver(ABC):
    """Port that converts a Track into a PlayableSource for the current mode."""

    @abstractmethod
    def resolve(self, track: Track) -> PlayableSource:
        """Return the playable source (local path or stream URL) for a track."""
        ...
