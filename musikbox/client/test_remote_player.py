from __future__ import annotations

import json as json_module
from collections.abc import Callable

import httpx

from musikbox.client.remote_player import RemotePlayer
from musikbox.client.transport import HttpTransport
from musikbox.domain.models import PlayableSource
from musikbox.domain.ports.player import Player


def _player(handler: Callable[[httpx.Request], httpx.Response]) -> RemotePlayer:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    transport = HttpTransport("http://testserver", client=client)
    return RemotePlayer(transport)


def _source(track_id: str = "track-1") -> PlayableSource:
    return PlayableSource(track_id=track_id, locator="", is_local=False)


def test_player_isinstance_implements_player_port() -> None:
    player = _player(lambda request: httpx.Response(200, json={}))
    assert isinstance(player, Player)


def test_play_posts_track_id_to_play_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/player/play"
        captured["body"] = json_module.loads(request.content)
        return httpx.Response(200, json={})

    player = _player(handler)
    player.play(_source("track-7"))
    assert captured["body"] == {"track_id": "track-7"}


def test_pause_posts_to_pause_endpoint() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json={})

    player = _player(handler)
    player.pause()
    assert captured == {"method": "POST", "path": "/player/pause"}


def test_resume_posts_to_resume_endpoint() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json={})

    player = _player(handler)
    player.resume()
    assert captured == {"method": "POST", "path": "/player/resume"}


def test_stop_posts_to_stop_endpoint() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json={})

    player = _player(handler)
    player.stop()
    assert captured == {"method": "POST", "path": "/player/stop"}


def test_seek_posts_seconds_to_seek_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/player/seek"
        captured["body"] = json_module.loads(request.content)
        return httpx.Response(200, json={})

    player = _player(handler)
    player.seek(12.5)
    assert captured["body"] == {"seconds": 12.5}


def test_is_playing_parses_true_from_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/player/status"
        return httpx.Response(200, json={"is_playing": True, "is_paused": False})

    player = _player(handler)
    assert player.is_playing() is True


def test_is_playing_when_false_returns_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"is_playing": False})

    player = _player(handler)
    assert player.is_playing() is False


def test_is_paused_parses_true_from_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"is_playing": False, "is_paused": True})

    player = _player(handler)
    assert player.is_paused() is True


def test_position_parses_float_from_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"position": 42.5, "duration": 180.0})

    player = _player(handler)
    assert player.position() == 42.5


def test_duration_parses_float_from_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"position": 42.5, "duration": 180.0})

    player = _player(handler)
    assert player.duration() == 180.0


def test_position_parses_integer_status_value_as_float() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"position": 10})

    player = _player(handler)
    assert player.position() == 10.0


def test_is_playing_with_non_200_status_returns_false_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"is_playing": True})

    player = _player(handler)
    assert player.is_playing() is False


def test_is_paused_with_non_200_status_returns_false_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    player = _player(handler)
    assert player.is_paused() is False


def test_position_with_non_200_status_returns_zero_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"position": 99.0})

    player = _player(handler)
    assert player.position() == 0.0


def test_duration_with_non_200_status_returns_zero_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    player = _player(handler)
    assert player.duration() == 0.0


def test_is_playing_when_transport_errors_returns_false_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    player = _player(handler)
    assert player.is_playing() is False


def test_is_paused_when_transport_errors_returns_false_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    player = _player(handler)
    assert player.is_paused() is False


def test_position_when_transport_errors_returns_zero_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    player = _player(handler)
    assert player.position() == 0.0


def test_duration_when_transport_errors_returns_zero_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    player = _player(handler)
    assert player.duration() == 0.0


def test_status_with_non_dict_body_returns_safe_defaults() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "a", "dict"])

    player = _player(handler)
    assert player.is_playing() is False
    assert player.position() == 0.0
