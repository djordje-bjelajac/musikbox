import threading
import time

from rich.console import Console

from musikbox.domain.models import Track
from musikbox.events.bus import EventBus
from musikbox.events.types import (
    ImportCompleted,
    ImportFailed,
    ImportStarted,
    ImportTrackDownloaded,
    ImportTrackReady,
    UIRefreshRequested,
)

from .input import InputHandler

console = Console()


class Importer:
    """Background YouTube import -- downloads in background thread, DB saves on main thread."""

    def __init__(
        self,
        bus: EventBus,
        input_handler: InputHandler,
        app: object,
    ) -> None:
        self._bus = bus
        self._input_handler = input_handler
        self._app = app
        self._active = False
        self._playlist_name = ""
        self._downloaded = 0
        self._last_track = ""
        self._done = False
        self._done_at: float = 0.0
        self._error: str | None = None
        self._download_done = False
        self._album: str | None = None
        self._artist: str | None = None
        self._genre: str | None = None
        self._playlist_id: str | None = None
        self._position: int = 0

        bus.subscribe(ImportTrackReady, self._on_import_track_ready)

    @property
    def active(self) -> bool:
        return self._active

    @property
    def playlist_name(self) -> str:
        return self._playlist_name

    @property
    def downloaded(self) -> int:
        return self._downloaded

    @property
    def last_track(self) -> str:
        return self._last_track

    @property
    def done(self) -> bool:
        return self._done

    @done.setter
    def done(self, value: bool) -> None:
        self._done = value

    @property
    def done_at(self) -> float:
        return self._done_at

    @property
    def error(self) -> str | None:
        return self._error

    def start_import(self, renderer: object = None) -> None:
        """Prompt for import details, then run download in background."""
        self._input_handler.pause()
        if renderer and hasattr(renderer, "pause"):
            renderer.pause()
        time.sleep(0.15)
        try:
            self._prompt_and_start()
        finally:
            self._input_handler.resume()
            if renderer and hasattr(renderer, "resume"):
                renderer.resume()
            time.sleep(0.15)
            self._bus.emit(UIRefreshRequested())

    def _prompt_and_start(self) -> None:
        console.print("\n[bold]Import YouTube playlist[/]\n")

        url = input("  YouTube URL: ").strip()
        if not url:
            console.print("  [dim]Cancelled.[/dim]\n")
            return

        name = input("  Playlist name: ").strip()
        if not name:
            console.print("  [dim]Cancelled.[/dim]\n")
            return

        artist_in = input("  Artist (Enter to skip): ").strip() or None
        album_in = input("  Album (Enter to skip): ").strip() or None
        genre_in = input("  Genre (Enter to skip): ").strip() or None

        if self._active:
            console.print("  [yellow]An import is already in progress.[/yellow]\n")
            return

        self._active = True
        self._done = False
        self._download_done = False
        self._error = None
        self._playlist_name = name
        self._downloaded = 0
        self._last_track = ""
        self._album = album_in
        self._artist = artist_in
        self._genre = genre_in
        self._playlist_id = None
        self._position = 0

        self._bus.emit(ImportStarted(playlist_name=name))

        thread = threading.Thread(target=self._bg_download, args=(url,), daemon=True)
        thread.start()
        console.print("  [dim]Import started in background.[/dim]\n")

    def _bg_download(self, url: str) -> None:
        """Background: only download files via yt-dlp, no DB access."""
        try:
            from musikbox.domain.models import TrackId
            from musikbox.services.download_service import _read_metadata

            download_svc = self._app.playlist_service._download_service
            downloader = download_svc._downloader
            music_dir = download_svc._music_dir
            fmt = download_svc._default_format

            for file_path, entry_url in downloader.download_playlist(url, music_dir, fmt):
                from datetime import UTC, datetime

                title, artist, album, duration = _read_metadata(file_path)
                now = datetime.now(UTC)
                track = Track(
                    id=TrackId(),
                    title=title,
                    artist=artist,
                    album=album,
                    duration_seconds=duration,
                    file_path=file_path,
                    format=fmt,
                    bpm=None,
                    key=None,
                    genre=None,
                    mood=None,
                    source_url=entry_url,
                    downloaded_at=now,
                    analyzed_at=None,
                    created_at=now,
                )
                self._bus.emit(ImportTrackReady(track=track))
        except Exception as e:
            self._error = str(e)
            self._bus.emit(ImportFailed(error=str(e)))
        finally:
            self._download_done = True

    def _on_import_track_ready(self, event: ImportTrackReady) -> None:
        """Main thread: save downloaded track to DB and add to playlist."""
        track = event.track

        # Apply overrides
        if self._album:
            track.album = self._album
        if self._artist:
            track.artist = self._artist
        if self._genre:
            track.genre = self._genre

        pl_service = self._app.playlist_service

        # Create playlist on first track
        if self._playlist_id is None:
            try:
                pl = pl_service.create_playlist(self._playlist_name)
                self._playlist_id = pl.id
                self._position = 0
            except Exception as e:
                self._error = str(e)
                self._active = False
                self._done = True
                self._done_at = time.monotonic()
                return

        try:
            track_repo = self._app.library_service._repository
            track_repo.save(track)

            existing = track_repo.get_by_file_path(track.file_path)
            track_to_add = existing if existing is not None else track

            playlist_repo = self._app.playlist_service._playlist_repo
            playlist_repo.add_track(
                self._playlist_id,
                track_to_add.id.value,
                self._position,
            )
            self._position += 1
        except Exception:
            pass  # Best effort, continue with next track

        self._downloaded += 1
        self._last_track = track.title
        self._bus.emit(ImportTrackDownloaded(track=track, count=self._downloaded))

        # Check if all done
        if self._download_done:
            self._active = False
            self._done = True
            self._done_at = time.monotonic()
            self._playlist_id = None
            self._bus.emit(
                ImportCompleted(
                    playlist_name=self._playlist_name,
                    count=self._downloaded,
                )
            )
