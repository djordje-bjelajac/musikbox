import time

from musikbox.domain.models import Track
from musikbox.events.bus import EventBus
from musikbox.events.types import (
    ImportStarted,
    MoveIndexChanged,
    QueueReordered,
    Shutdown,
    Tick,
    TrackEnded,
    TrackRemovedFromQueue,
    TrackStarted,
)
from musikbox.services.playback_service import PlaybackService

from .browser import LibraryBrowser
from .controls import PlaybackControls
from .editor import Editor
from .importer import Importer
from .input import InputHandler
from .renderer import Renderer


class PlayerApp:
    """Wires all player components via the EventBus and runs the main loop."""

    def __init__(
        self,
        playback_service: PlaybackService,
        repository: object,
        app: object,
        playlist_name: str | None = None,
        playlist_service: object | None = None,
    ) -> None:
        self.bus = EventBus()
        self._stopped = False
        self._playback_service = playback_service
        self._playlist_name = playlist_name
        self._playlist_service = playlist_service

        # Create components -- each registers its own handlers
        self.input = InputHandler(self.bus)

        self.controls = PlaybackControls(self.bus, playback_service)
        self.controls.has_playlist = playlist_name is not None

        # Get playlist_repo for renderer
        pl_repo = None
        if hasattr(app, "playlist_service") and app.playlist_service:
            pl_repo = app.playlist_service._playlist_repo

        self.renderer = Renderer(self.bus, playback_service, playlist_repo=pl_repo)
        self.renderer._has_playlist = playlist_name is not None

        self.editor = Editor(self.bus, self.input, playback_service, repository, app)
        self.editor.playlist_name = playlist_name
        self.editor.playlist_service = playlist_service
        self.editor._renderer = self.renderer

        self.importer = Importer(self.bus, self.input, app)

        self.browser = LibraryBrowser(self.bus, self.input, playback_service, app)
        self.browser.playlist_name = playlist_name
        self.browser.playlist_service = playlist_service
        self.browser._renderer = self.renderer

        # Wire up mpv end-file callback to emit TrackEnded
        player = playback_service._player
        if hasattr(player, "on_track_end"):

            def _on_end() -> None:
                self.bus.emit(TrackEnded(index=playback_service.queue_index))

            player.on_track_end = _on_end

        # Wire import trigger: controls emits ImportStarted on "i" key,
        # we intercept it to prompt user and start the background download.
        self.bus.subscribe(ImportStarted, self._on_import_trigger)

        # Wire queue mutations that controls emits but doesn't execute
        self.bus.subscribe(TrackRemovedFromQueue, self._on_track_removed)
        self.bus.subscribe(MoveIndexChanged, self._on_move_index_changed)
        self.bus.subscribe(QueueReordered, self._on_queue_reordered)

        # Handle shutdown
        self.bus.subscribe(Shutdown, self._on_shutdown)

        # Polling fallback for track end detection
        self.bus.subscribe(Tick, self._check_track_finished)

        # Track move-mode state for queue swapping
        self._prev_move_index: int | None = None

    def _on_shutdown(self, event: Shutdown) -> None:
        self._stopped = True

    def _on_import_trigger(self, event: ImportStarted) -> None:
        """Controls emits ImportStarted as a trigger. We call start_import
        which prompts the user and launches the background thread.
        start_import will emit its own ImportStarted for the renderer."""
        if not self.importer.active:
            self.importer.start_import(renderer=self.renderer)

    def _on_track_removed(self, event: TrackRemovedFromQueue) -> None:
        """Remove a track from the queue and playlist."""
        idx = event.index
        queue = self._playback_service._queue
        if idx < 0 or idx >= len(queue):
            return

        removed_track = queue[idx]
        queue.pop(idx)

        # Adjust current playing index
        if idx < self._playback_service._index:
            self._playback_service._index -= 1
        elif idx == self._playback_service._index:
            if self._playback_service._index >= len(queue):
                self._playback_service._index = len(queue) - 1
            self._playback_service._mark_manual_change()
            if queue:
                self._playback_service._player.play(queue[self._playback_service._index].file_path)

        # Remove from playlist if applicable
        if self._playlist_name and self._playlist_service:
            try:
                self._playlist_service.remove_track(self._playlist_name, removed_track.id.value)
            except Exception:
                pass

    def _on_move_index_changed(self, event: MoveIndexChanged) -> None:
        """Track the move index for queue swapping."""
        new_idx = event.index
        old_idx = self._prev_move_index

        # If moving (both old and new are not None), perform the swap
        if old_idx is not None and new_idx is not None and old_idx != new_idx:
            queue = self._playback_service._queue
            if 0 <= old_idx < len(queue) and 0 <= new_idx < len(queue):
                queue[old_idx], queue[new_idx] = queue[new_idx], queue[old_idx]
                # Adjust current playing index if affected
                if self._playback_service._index == old_idx:
                    self._playback_service._index = new_idx
                elif self._playback_service._index == new_idx:
                    self._playback_service._index = old_idx

        self._prev_move_index = new_idx

    def _on_queue_reordered(self, event: QueueReordered) -> None:
        """Persist playlist order after move-mode drop."""
        # Only persist when move mode ends (move_index goes back to None)
        if self._prev_move_index is None and self._playlist_name and self._playlist_service:
            try:
                track_ids = [t.id.value for t in self._playback_service._queue]
                self._playlist_service.reorder_tracks(self._playlist_name, track_ids)
            except Exception:
                pass

    def _check_track_finished(self, event: Tick) -> None:
        """Polling fallback for track end detection."""
        player = self._playback_service._player
        if (
            hasattr(player, "track_finished")
            and player.track_finished
            and not self._playback_service._in_guard_window()
        ):
            player._track_finished = False
            self._playback_service._mark_manual_change()
            self.bus.emit(TrackEnded(index=self._playback_service.queue_index))

    def run(self, tracks: list[Track], start_index: int = 0) -> None:
        """Main event loop."""
        self._playback_service.load_queue(tracks)
        self._playback_service._index = start_index
        self._playback_service.play()

        # Start components
        self.input.start()
        self.renderer.start()

        # Emit initial event
        self.bus.emit(
            TrackStarted(track=tracks[start_index], index=start_index),
        )

        last_tick = time.monotonic()

        try:
            while not self._stopped and self._playback_service.is_active:
                event = self.bus.poll(timeout=0.05)
                if event:
                    self.bus.dispatch(event)

                now = time.monotonic()
                if now - last_tick >= 0.25:
                    self.bus.emit(Tick())
                    last_tick = now
        except KeyboardInterrupt:
            pass
        finally:
            self.renderer.stop()
            self.input.stop()
            self._playback_service.stop()
