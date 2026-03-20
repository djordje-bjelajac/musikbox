from abc import ABC, abstractmethod

from musikbox.domain.models import Playlist, Track


class PlaylistRepository(ABC):
    @abstractmethod
    def create(self, playlist: Playlist) -> None: ...

    @abstractmethod
    def get_by_id(self, playlist_id: str) -> Playlist: ...

    @abstractmethod
    def get_by_name(self, name: str) -> Playlist | None: ...

    @abstractmethod
    def list_all(self) -> list[Playlist]: ...

    @abstractmethod
    def delete(self, playlist_id: str) -> None: ...

    @abstractmethod
    def update(self, playlist: Playlist) -> None: ...

    @abstractmethod
    def add_track(self, playlist_id: str, track_id: str, position: int) -> None: ...

    @abstractmethod
    def remove_track(self, playlist_id: str, track_id: str) -> None: ...

    @abstractmethod
    def get_tracks(self, playlist_id: str) -> list[Track]: ...

    @abstractmethod
    def reorder(self, playlist_id: str, track_ids: list[str]) -> None: ...

    @abstractmethod
    def get_playlists_for_track(self, track_id: str) -> list[Playlist]: ...
