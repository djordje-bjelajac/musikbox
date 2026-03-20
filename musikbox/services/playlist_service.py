from datetime import UTC, datetime
from uuid import uuid4

from musikbox.domain.exceptions import PlaylistNotFoundError
from musikbox.domain.models import Playlist, Track
from musikbox.domain.ports.playlist_repository import PlaylistRepository
from musikbox.domain.ports.repository import TrackRepository
from musikbox.services.download_service import DownloadService


class PlaylistService:
    """Orchestrates playlist operations using repository ports."""

    def __init__(
        self,
        playlist_repository: PlaylistRepository,
        track_repository: TrackRepository,
        download_service: DownloadService,
    ) -> None:
        self._playlist_repo = playlist_repository
        self._track_repo = track_repository
        self._download_service = download_service

    def create_playlist(self, name: str) -> Playlist:
        """Create an empty playlist with the given name."""
        now = datetime.now(UTC)
        playlist = Playlist(
            id=str(uuid4()),
            name=name,
            created_at=now,
            updated_at=now,
        )
        self._playlist_repo.create(playlist)
        return playlist

    def create_from_tracks(self, name: str, tracks: list[Track]) -> Playlist:
        """Create a playlist pre-populated with the given tracks in order."""
        playlist = self.create_playlist(name)
        for position, track in enumerate(tracks):
            self._playlist_repo.add_track(playlist.id, track.id.value, position)
        return playlist

    def import_youtube_playlist(
        self,
        name: str,
        url: str,
        format: str | None = None,
        analyze: bool | None = None,
        album: str | None = None,
        artist: str | None = None,
        genre: str | None = None,
        on_track: object | None = None,
    ) -> tuple[Playlist, list[Track]]:
        """Import a YouTube playlist: download tracks and create a playlist.

        Returns the playlist and the list of tracks that were added.
        Skips duplicates by checking file path in the track repository.
        album/artist/genre overrides are applied to all downloaded tracks.
        """
        playlist = self.create_playlist(name)
        added_tracks: list[Track] = []
        position = 0

        for track in self._download_service.download_playlist(url, format=format, analyze=analyze):
            # Apply overrides
            if album:
                track.album = album
            if artist:
                track.artist = artist
            if genre:
                track.genre = genre
            if album or artist or genre:
                self._track_repo.save(track)

            # Check for duplicates by file path
            existing = self._track_repo.get_by_file_path(track.file_path)
            track_to_add = existing if existing is not None else track

            self._playlist_repo.add_track(playlist.id, track_to_add.id.value, position)
            added_tracks.append(track_to_add)
            position += 1

            if on_track is not None:
                try:
                    on_track(track_to_add)
                except Exception:
                    pass

        return playlist, added_tracks

    def list_playlists(self) -> list[Playlist]:
        """Return all playlists."""
        return self._playlist_repo.list_all()

    def get_playlist_tracks(self, name: str) -> list[Track]:
        """Get all tracks in a playlist by name, in order."""
        playlist = self._playlist_repo.get_by_name(name)
        if playlist is None:
            raise PlaylistNotFoundError(f"Playlist not found: {name}")
        return self._playlist_repo.get_tracks(playlist.id)

    def add_track(self, playlist_name: str, track_id: str) -> None:
        """Add a track to the end of a playlist."""
        playlist = self._playlist_repo.get_by_name(playlist_name)
        if playlist is None:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist_name}")

        existing_tracks = self._playlist_repo.get_tracks(playlist.id)
        position = len(existing_tracks)
        self._playlist_repo.add_track(playlist.id, track_id, position)

    def remove_track(self, playlist_name: str, track_id: str) -> None:
        """Remove a track from a playlist."""
        playlist = self._playlist_repo.get_by_name(playlist_name)
        if playlist is None:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist_name}")
        self._playlist_repo.remove_track(playlist.id, track_id)

    def reorder_tracks(self, playlist_name: str, track_ids_in_order: list[str]) -> None:
        """Reorder tracks in a playlist."""
        playlist = self._playlist_repo.get_by_name(playlist_name)
        if playlist is None:
            raise PlaylistNotFoundError(f"Playlist not found: {playlist_name}")
        self._playlist_repo.reorder(playlist.id, track_ids_in_order)

    def delete_playlist(self, name: str) -> None:
        """Delete a playlist by name."""
        playlist = self._playlist_repo.get_by_name(name)
        if playlist is None:
            raise PlaylistNotFoundError(f"Playlist not found: {name}")
        self._playlist_repo.delete(playlist.id)
