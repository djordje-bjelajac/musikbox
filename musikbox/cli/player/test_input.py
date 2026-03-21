import threading
import time

from musikbox.cli.player.input import InputHandler
from musikbox.events.bus import EventBus


def test_input_handler_starts_and_stops() -> None:
    """InputHandler can start a daemon thread and stop it cleanly."""
    bus = EventBus()
    handler = InputHandler(bus)

    # Patch _run to avoid actual terminal I/O
    started = threading.Event()
    stopped = threading.Event()

    def fake_run() -> None:
        started.set()
        while not handler._stop.is_set():
            time.sleep(0.05)
        stopped.set()

    handler._run = fake_run  # type: ignore[assignment]

    handler.start()
    assert started.wait(timeout=1.0), "Thread did not start"
    assert handler._thread is not None
    assert handler._thread.daemon is True

    handler.stop()
    assert stopped.wait(timeout=1.0), "Thread did not stop"
    assert handler._thread is None


def test_input_handler_pause_and_resume() -> None:
    """InputHandler pause/resume sets the internal event flags."""
    bus = EventBus()
    handler = InputHandler(bus)

    assert not handler._paused.is_set()
    handler.pause()
    assert handler._paused.is_set()
    handler.resume()
    assert not handler._paused.is_set()


def test_input_handler_start_is_idempotent() -> None:
    """Calling start() twice does not create a second thread."""
    bus = EventBus()
    handler = InputHandler(bus)

    def fake_run() -> None:
        while not handler._stop.is_set():
            time.sleep(0.05)

    handler._run = fake_run  # type: ignore[assignment]

    handler.start()
    thread1 = handler._thread

    handler.start()
    thread2 = handler._thread

    assert thread1 is thread2
    handler.stop()
