import atexit
import select
import sys
import termios
import threading
import time
import tty

from musikbox.events.bus import EventBus
from musikbox.events.types import KeyPressed


class InputHandler:
    """Background thread reading stdin in cbreak mode, emitting KeyPressed events."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self._old_settings: list | None = None

    def start(self) -> None:
        """Start the input reading thread."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._paused.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the input reading thread and restore terminal."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def pause(self) -> None:
        """Pause input reading and restore terminal (for modal dialogs)."""
        self._paused.set()

    def resume(self) -> None:
        """Resume input reading in cbreak mode."""
        self._paused.clear()

    def _run(self) -> None:
        """Background thread: read characters from stdin in cbreak mode.

        Uses cbreak (not raw) so terminal output processing still works,
        allowing Rich Live to render correctly.
        """
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        self._old_settings = old_settings

        def restore_terminal() -> None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        atexit.register(restore_terminal)

        try:
            tty.setcbreak(fd)
            buf = ""
            while not self._stop.is_set():
                if self._paused.is_set():
                    restore_terminal()
                    while self._paused.is_set() and not self._stop.is_set():
                        time.sleep(0.1)
                    if not self._stop.is_set():
                        tty.setcbreak(fd)
                    continue

                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    # Flush any incomplete escape sequence
                    for c in buf:
                        self._bus.emit(KeyPressed(c))
                    buf = ""
                    continue

                ch = sys.stdin.read(1)
                if not ch:
                    continue

                buf += ch

                # Accumulate escape sequences
                if buf == "\x1b" or buf == "\x1b[":
                    continue
                if buf == "\x1b[C":
                    self._bus.emit(KeyPressed("RIGHT"))
                    buf = ""
                    continue
                if buf == "\x1b[D":
                    self._bus.emit(KeyPressed("LEFT"))
                    buf = ""
                    continue
                if buf.startswith("\x1b"):
                    # Unknown escape sequence, discard
                    buf = ""
                    continue

                # Regular character
                self._bus.emit(KeyPressed(buf))
                buf = ""
        finally:
            restore_terminal()
