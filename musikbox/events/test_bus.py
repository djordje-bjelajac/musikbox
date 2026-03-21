import threading

from musikbox.events.bus import EventBus
from musikbox.events.types import KeyPressed, PlaybackPaused, Tick, TrackEnded


def test_subscribe_and_dispatch():
    bus = EventBus()
    received: list[object] = []
    bus.subscribe(KeyPressed, received.append)

    event = KeyPressed(key="q")
    bus.dispatch(event)

    assert len(received) == 1
    assert received[0] is event


def test_emit_and_poll():
    bus = EventBus()
    event = Tick()
    bus.emit(event)

    polled = bus.poll(timeout=0.01)
    assert polled is event


def test_poll_returns_none_on_empty():
    bus = EventBus()
    assert bus.poll(timeout=0.01) is None


def test_multiple_handlers_for_same_event():
    bus = EventBus()
    first: list[object] = []
    second: list[object] = []
    bus.subscribe(KeyPressed, first.append)
    bus.subscribe(KeyPressed, second.append)

    event = KeyPressed(key="n")
    bus.dispatch(event)

    assert len(first) == 1
    assert len(second) == 1


def test_unrelated_event_not_dispatched():
    bus = EventBus()
    received: list[object] = []
    bus.subscribe(KeyPressed, received.append)

    bus.dispatch(PlaybackPaused())

    assert len(received) == 0


def test_emit_from_another_thread():
    bus = EventBus()
    event = TrackEnded(index=3)

    thread = threading.Thread(target=bus.emit, args=(event,))
    thread.start()
    thread.join()

    polled = bus.poll(timeout=1.0)
    assert polled is event
