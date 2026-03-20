import pytest

from musikbox.domain.models import Playlist, Track
from musikbox.domain.ports.playlist_repository import PlaylistRepository


def test_playlist_repository_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        PlaylistRepository()  # type: ignore[abstract]


def test_concrete_playlist_repository_can_be_instantiated() -> None:
    class FakePlaylistRepository(PlaylistRepository):
        def create(self, playlist: Playlist) -> None:
            pass

        def get_by_id(self, playlist_id: str) -> Playlist:
            raise NotImplementedError

        def get_by_name(self, name: str) -> Playlist | None:
            return None

        def list_all(self) -> list[Playlist]:
            return []

        def delete(self, playlist_id: str) -> None:
            pass

        def update(self, playlist: Playlist) -> None:
            pass

        def add_track(self, playlist_id: str, track_id: str, position: int) -> None:
            pass

        def remove_track(self, playlist_id: str, track_id: str) -> None:
            pass

        def get_tracks(self, playlist_id: str) -> list[Track]:
            return []

        def reorder(self, playlist_id: str, track_ids: list[str]) -> None:
            pass

        def get_playlists_for_track(self, track_id: str) -> list[Playlist]:
            return []

    repo = FakePlaylistRepository()
    assert isinstance(repo, PlaylistRepository)
