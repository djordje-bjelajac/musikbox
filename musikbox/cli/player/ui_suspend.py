import os
import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType

from musikbox.events.bus import EventBus
from musikbox.events.types import UIRefreshRequested

from .input import InputHandler

_SETTLE_SECONDS = 0.15


def _suspend_renderer(renderer: object | None) -> None:
    if renderer is None:
        return
    if hasattr(renderer, "suspend"):
        renderer.suspend()
    elif hasattr(renderer, "pause"):
        renderer.pause()


def _resume_renderer(renderer: object | None) -> None:
    if renderer is not None and hasattr(renderer, "resume"):
        renderer.resume()


@contextmanager
def suspend_ui(
    input_handler: InputHandler,
    renderer: object | None,
    bus: EventBus,
) -> Iterator[None]:
    """Hand the terminal to a modal, then take it back.

    The renderer is suspended before the input handler so the alternate screen
    is left before the tty mode changes, and resumed after it for the same
    reason in reverse. The restore path runs even if the modal raises.
    """
    _suspend_renderer(renderer)
    input_handler.pause()
    time.sleep(_SETTLE_SECONDS)
    try:
        yield
    finally:
        input_handler.resume()
        _resume_renderer(renderer)
        time.sleep(_SETTLE_SECONDS)
        bus.emit(UIRefreshRequested())


def install_suspend_handlers(renderer: object, input_handler: InputHandler) -> None:
    """Leave and re-enter the alternate screen across Ctrl-Z / fg.

    Without this the process would be stopped while still owning the alternate
    screen, leaving the shell painting into it.
    """
    if not hasattr(signal, "SIGTSTP"):
        return

    def _on_stop(signum: int, frame: FrameType | None) -> None:
        _suspend_renderer(renderer)
        input_handler.pause()
        signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTSTP)

    def _on_cont(signum: int, frame: FrameType | None) -> None:
        signal.signal(signal.SIGTSTP, _on_stop)
        input_handler.resume()
        _resume_renderer(renderer)

    signal.signal(signal.SIGTSTP, _on_stop)
    signal.signal(signal.SIGCONT, _on_cont)
