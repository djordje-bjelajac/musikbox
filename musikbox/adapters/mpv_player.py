from collections.abc import Callable
from pathlib import Path

try:
    import mpv
except ImportError as _import_err:
    raise ImportError(
        "python-mpv is required for playback. "
        "Install with: uv pip install 'musikbox[playback]' "
        "and ensure mpv is installed: brew install mpv"
    ) from _import_err

from musikbox.domain.ports.player import Player


class MpvPlayer(Player):
    """Player implementation using python-mpv (libmpv)."""

    def __init__(self) -> None:
        self._mpv = mpv.MPV(video=False, terminal=False, input_terminal=False)
        self._on_track_end: Callable[[], None] | None = None

        @self._mpv.event_callback("end-file")
        def _on_end_file(event: object) -> None:
            try:
                reason = getattr(getattr(event, "event", None), "reason", None)
                if reason is not None and str(reason) == "eof":
                    if self._on_track_end is not None:
                        self._on_track_end()
            except Exception:
                # Best-effort: if we can't parse the event, skip
                pass

    @property
    def on_track_end(self) -> Callable[[], None] | None:
        return self._on_track_end

    @on_track_end.setter
    def on_track_end(self, callback: Callable[[], None] | None) -> None:
        self._on_track_end = callback

    def play(self, file_path: Path) -> None:
        self._mpv.play(str(file_path))

    def pause(self) -> None:
        self._mpv.pause = True

    def resume(self) -> None:
        self._mpv.pause = False

    def seek(self, seconds: float) -> None:
        try:
            self._mpv.seek(seconds, reference="relative")
        except Exception:
            pass

    def stop(self) -> None:
        self._mpv.stop()

    def is_playing(self) -> bool:
        return not self._mpv.core_idle and not self._mpv.pause

    def is_paused(self) -> bool:
        return bool(self._mpv.pause)

    def position(self) -> float:
        return float(self._mpv.playback_time or 0.0)

    def duration(self) -> float:
        return float(self._mpv.duration or 0.0)

    def close(self) -> None:
        """Terminate the mpv instance and release resources."""
        self._mpv.terminate()
