import signal
from collections.abc import Iterator
from typing import cast

import pytest

from musikbox.cli.player.input import InputHandler
from musikbox.cli.player.ui_suspend import install_suspend_handlers, suspend_ui
from musikbox.events.bus import EventBus
from musikbox.events.types import UIRefreshRequested


class _RecordingInputHandler:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def pause(self) -> None:
        self._calls.append("input.pause")

    def resume(self) -> None:
        self._calls.append("input.resume")


class _RecordingRenderer:
    """Renderer double exposing suspend()/resume()."""

    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def suspend(self) -> None:
        self._calls.append("renderer.suspend")

    def resume(self) -> None:
        self._calls.append("renderer.resume")


class _PauseOnlyRenderer:
    """Legacy renderer double with no suspend(), only pause()."""

    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def pause(self) -> None:
        self._calls.append("renderer.pause")

    def resume(self) -> None:
        self._calls.append("renderer.resume")


@pytest.fixture
def calls() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    """Time is injected, never slept on."""

    def fake_sleep(seconds: float) -> None:
        calls.append(f"sleep({seconds})")

    monkeypatch.setattr("time.sleep", fake_sleep)


@pytest.fixture(autouse=True)
def restore_signal_handlers() -> Iterator[None]:
    saved: dict[int, object] = {}
    for name in ("SIGTSTP", "SIGCONT"):
        signum = getattr(signal, name, None)
        if signum is not None:
            saved[int(signum)] = signal.getsignal(signum)
    yield
    for signum, handler in saved.items():
        if handler is not None:
            signal.signal(signum, handler)  # type: ignore[arg-type]


def _handler(calls: list[str]) -> InputHandler:
    return cast(InputHandler, _RecordingInputHandler(calls))


def _drain(bus: EventBus) -> list[object]:
    """Pull every queued event off the bus (emit only enqueues, it does not dispatch)."""
    events: list[object] = []
    while True:
        event = bus.poll(timeout=0.001)
        if event is None:
            return events
        events.append(event)


def test_suspend_ui_orders_calls_correctly(calls: list[str]) -> None:
    bus = EventBus()
    renderer = _RecordingRenderer(calls)

    with suspend_ui(_handler(calls), renderer, bus):
        calls.append("body")

    assert calls == [
        "renderer.suspend",
        "input.pause",
        "sleep(0.15)",
        "body",
        "input.resume",
        "renderer.resume",
        "sleep(0.15)",
    ]


def test_suspend_ui_without_suspend_method_falls_back_to_pause(calls: list[str]) -> None:
    bus = EventBus()
    renderer = _PauseOnlyRenderer(calls)

    with suspend_ui(_handler(calls), renderer, bus):
        calls.append("body")

    assert calls[0] == "renderer.pause"
    assert calls[1] == "input.pause"
    assert calls[-2:] == ["renderer.resume", "sleep(0.15)"]


def test_suspend_ui_resumes_when_body_raises(calls: list[str]) -> None:
    bus = EventBus()
    renderer = _RecordingRenderer(calls)

    with pytest.raises(RuntimeError, match="boom"):
        with suspend_ui(_handler(calls), renderer, bus):
            raise RuntimeError("boom")

    assert "input.resume" in calls
    assert "renderer.resume" in calls
    assert calls.index("input.resume") < calls.index("renderer.resume")


def test_suspend_ui_emits_ui_refresh_requested_on_exit(calls: list[str]) -> None:
    bus = EventBus()
    renderer = _RecordingRenderer(calls)

    with suspend_ui(_handler(calls), renderer, bus):
        assert _drain(bus) == []

    emitted = _drain(bus)
    assert len(emitted) == 1
    assert isinstance(emitted[0], UIRefreshRequested)


def test_suspend_ui_emits_ui_refresh_requested_when_body_raises(calls: list[str]) -> None:
    bus = EventBus()

    with pytest.raises(ValueError):
        with suspend_ui(_handler(calls), _RecordingRenderer(calls), bus):
            raise ValueError("nope")

    assert len(_drain(bus)) == 1


def test_suspend_ui_tolerates_none_renderer(calls: list[str]) -> None:
    bus = EventBus()

    with suspend_ui(_handler(calls), None, bus):
        calls.append("body")

    assert calls == [
        "input.pause",
        "sleep(0.15)",
        "body",
        "input.resume",
        "sleep(0.15)",
    ]
    assert len(_drain(bus)) == 1


def test_install_suspend_handlers_does_not_raise(calls: list[str]) -> None:
    install_suspend_handlers(_RecordingRenderer(calls), _handler(calls))
