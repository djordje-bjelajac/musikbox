from abc import ABC, abstractmethod

from musikbox.domain.models import SearchFilter, Track, TrackId


class TrackRepository(ABC):
    @abstractmethod
    def save(self, track: Track) -> None: ...

    @abstractmethod
    def get_by_id(self, track_id: TrackId) -> Track: ...

    @abstractmethod
    def search(self, filter: SearchFilter) -> list[Track]: ...

    @abstractmethod
    def delete(self, track_id: TrackId) -> None: ...

    @abstractmethod
    def list_all(self, limit: int = 50, offset: int = 0) -> list[Track]: ...
