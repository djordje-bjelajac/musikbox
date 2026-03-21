from musikbox.events.bus import EventBus
from musikbox.events.types import (
    AddToPlaylistRequested,
    AddTrackFromLibraryRequested,
    BrowseIndexChanged,
    BrowseLibraryRequested,
    EditTrackRequested,
    ImportStarted,
    JumpToTrack,
    KeyPressed,
    MoveIndexChanged,
    PlaybackPaused,
    PlaybackResumed,
    QueueReordered,
    SearchQueueRequested,
    SeekRequested,
    Shutdown,
    SortQueueRequested,
    TrackEnded,
    TrackRemovedFromQueue,
    TrackStarted,
)
from musikbox.services.playback_service import PlaybackService


class PlaybackControls:
    """Maps key events to playback actions and manages queue state."""

    def __init__(
        self,
        bus: EventBus,
        playback_service: PlaybackService,
    ) -> None:
        self._bus = bus
        self._service = playback_service
        self._browse_index: int | None = None
        self._move_index: int | None = None
        self._has_playlist: bool = False

        bus.subscribe(KeyPressed, self._on_key)
        bus.subscribe(TrackEnded, self._on_track_ended)

    @property
    def browse_index(self) -> int | None:
        return self._browse_index

    @property
    def move_index(self) -> int | None:
        return self._move_index

    @property
    def has_playlist(self) -> bool:
        return self._has_playlist

    @has_playlist.setter
    def has_playlist(self, value: bool) -> None:
        self._has_playlist = value

    def _on_key(self, event: KeyPressed) -> None:
        ch = event.key
        queue_len = len(self._service.queue)

        # Move mode handling
        if self._move_index is not None:
            self._handle_move_mode(ch, queue_len)
            return

        if ch == " ":
            self._toggle_pause()
        elif ch == "j":
            self._browse_down(queue_len)
        elif ch == "k":
            self._browse_up()
        elif ch in ("\r", "\n") and self._browse_index is not None:
            self._jump_to_browsed()
        elif ch == "n":
            self._next_track()
        elif ch == "p":
            self._previous_track()
        elif ch in ("LEFT", ",", "<"):
            self._bus.emit(SeekRequested(seconds=-10))
            self._service.seek(-10)
        elif ch in ("RIGHT", ".", ">"):
            self._bus.emit(SeekRequested(seconds=10))
            self._service.seek(10)
        elif ch == "/":
            self._bus.emit(SearchQueueRequested())
        elif ch == "e":
            self._emit_edit_track()
        elif ch == "l":
            self._emit_add_to_playlist()
        elif ch == "s":
            self._bus.emit(SortQueueRequested())
        elif ch == "a":
            self._bus.emit(AddTrackFromLibraryRequested())
        elif ch == "b":
            self._bus.emit(BrowseLibraryRequested())
        elif ch == "i":
            self._bus.emit(ImportStarted(playlist_name=""))
        elif ch == "m" and self._has_playlist and self._browse_index is not None:
            self._move_index = self._browse_index
            self._bus.emit(MoveIndexChanged(index=self._move_index))
        elif ch in ("x", "\x7f") and self._has_playlist and self._browse_index is not None:
            self._remove_track(queue_len)
        elif ch in ("q", "\x03"):
            self._bus.emit(Shutdown())

    def _on_track_ended(self, event: TrackEnded) -> None:
        result = self._service.next_track(auto=True)
        if result is None:
            self._bus.emit(Shutdown())
        else:
            self._browse_index = None
            self._bus.emit(BrowseIndexChanged(index=None))
            self._bus.emit(TrackStarted(track=result, index=self._service.queue_index))

    def _toggle_pause(self) -> None:
        was_paused = self._service.is_paused()
        self._service.pause_resume()
        if was_paused:
            self._bus.emit(PlaybackResumed())
        else:
            self._bus.emit(PlaybackPaused())

    def _browse_down(self, queue_len: int) -> None:
        if self._browse_index is None:
            self._browse_index = self._service.queue_index
        self._browse_index = min(queue_len - 1, self._browse_index + 1)
        self._bus.emit(BrowseIndexChanged(index=self._browse_index))

    def _browse_up(self) -> None:
        if self._browse_index is None:
            self._browse_index = self._service.queue_index
        self._browse_index = max(0, self._browse_index - 1)
        self._bus.emit(BrowseIndexChanged(index=self._browse_index))

    def _jump_to_browsed(self) -> None:
        assert self._browse_index is not None
        self._bus.emit(JumpToTrack(index=self._browse_index))
        queue = self._service.queue
        if 0 <= self._browse_index < len(queue):
            track = queue[self._browse_index]
            self._service._index = self._browse_index
            self._service._mark_manual_change()
            self._service._player.play(track.file_path)
            self._bus.emit(TrackStarted(track=track, index=self._browse_index))
        self._browse_index = None
        self._bus.emit(BrowseIndexChanged(index=None))

    def _next_track(self) -> None:
        result = self._service.next_track()
        if result is None:
            self._bus.emit(Shutdown())
        else:
            self._browse_index = None
            self._bus.emit(BrowseIndexChanged(index=None))
            self._bus.emit(TrackStarted(track=result, index=self._service.queue_index))

    def _previous_track(self) -> None:
        result = self._service.previous_track()
        if result is not None:
            self._browse_index = None
            self._bus.emit(BrowseIndexChanged(index=None))
            self._bus.emit(TrackStarted(track=result, index=self._service.queue_index))

    def _emit_edit_track(self) -> None:
        if self._browse_index is not None:
            track = self._service.queue[self._browse_index]
        else:
            track = self._service.current_track()
        if track:
            self._bus.emit(EditTrackRequested(track=track))

    def _emit_add_to_playlist(self) -> None:
        if self._browse_index is not None:
            track = self._service.queue[self._browse_index]
        else:
            track = self._service.current_track()
        if track:
            self._bus.emit(AddToPlaylistRequested(track=track))

    def _remove_track(self, queue_len: int) -> None:
        assert self._browse_index is not None
        if queue_len <= 1:
            return
        self._bus.emit(TrackRemovedFromQueue(index=self._browse_index))
        # Adjust browse index to stay in bounds
        new_len = queue_len - 1
        self._browse_index = min(self._browse_index, new_len - 1)
        self._bus.emit(BrowseIndexChanged(index=self._browse_index))

    def _handle_move_mode(self, ch: str, queue_len: int) -> None:
        assert self._move_index is not None
        if ch == "j" and self._move_index < queue_len - 1:
            self._move_index += 1
            self._bus.emit(MoveIndexChanged(index=self._move_index))
            self._bus.emit(QueueReordered())
        elif ch == "k" and self._move_index > 0:
            self._move_index -= 1
            self._bus.emit(MoveIndexChanged(index=self._move_index))
            self._bus.emit(QueueReordered())
        elif ch in ("\r", "\n"):
            # Drop: confirm new position
            self._browse_index = self._move_index
            self._move_index = None
            self._bus.emit(MoveIndexChanged(index=None))
            self._bus.emit(BrowseIndexChanged(index=self._browse_index))
            self._bus.emit(QueueReordered())
        elif ch in ("\x1b", "m"):
            # Cancel move
            self._browse_index = self._move_index
            self._move_index = None
            self._bus.emit(MoveIndexChanged(index=None))
            self._bus.emit(BrowseIndexChanged(index=self._browse_index))
