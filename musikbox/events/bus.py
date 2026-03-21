import queue
from collections import defaultdict
from collections.abc import Callable


class EventBus:
    def __init__(self) -> None:
        self._queue: queue.Queue[object] = queue.Queue()
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

    def emit(self, event: object) -> None:
        """Thread-safe: puts event on the queue."""
        self._queue.put(event)

    def poll(self, timeout: float = 0.05) -> object | None:
        """Non-blocking: returns next event or None."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def dispatch(self, event: object) -> None:
        """Call all handlers registered for this event type."""
        for handler in self._handlers.get(type(event), []):
            handler(event)
