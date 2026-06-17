from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from musikbox.client.transport import HttpTransport, ensure_ok
from musikbox.domain.exceptions import RemoteServiceError


def _transport(handler: Callable[[httpx.Request], httpx.Response]) -> HttpTransport:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    return HttpTransport("http://testserver", client=client)


def test_base_url_with_trailing_slash_is_stripped() -> None:
    transport = HttpTransport("http://testserver/")
    assert transport.base_url == "http://testserver"


def test_get_with_2xx_returns_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/ping"
        return httpx.Response(200, json={"ok": True})

    transport = _transport(handler)
    response = transport.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_get_passes_params_to_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("limit") == "5"
        return httpx.Response(200, json=[])

    transport = _transport(handler)
    response = transport.get("/tracks", params={"limit": 5})
    assert response.status_code == 200


def test_post_with_2xx_returns_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/player/play"
        return httpx.Response(200, json={"started": True})

    transport = _transport(handler)
    response = transport.post("/player/play", json={"track_id": "t-1"})
    assert response.status_code == 200
    assert response.json() == {"started": True}


def test_post_sends_json_body() -> None:
    import json as json_module

    def handler(request: httpx.Request) -> httpx.Response:
        assert json_module.loads(request.content) == {"track_id": "t-1"}
        return httpx.Response(200, json={})

    transport = _transport(handler)
    transport.post("/player/play", json={"track_id": "t-1"})


def test_get_when_connection_fails_raises_remote_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = _transport(handler)
    with pytest.raises(RemoteServiceError):
        transport.get("/ping")


def test_post_when_connection_fails_raises_remote_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = _transport(handler)
    with pytest.raises(RemoteServiceError):
        transport.post("/player/play", json={})


def test_get_when_timeout_raises_remote_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    transport = _transport(handler)
    with pytest.raises(RemoteServiceError):
        transport.get("/ping")


def test_ensure_ok_with_200_returns_same_response() -> None:
    response = httpx.Response(200, json={"ok": True})
    assert ensure_ok(response) is response


def test_ensure_ok_with_299_returns_response() -> None:
    response = httpx.Response(299)
    assert ensure_ok(response) is response


def test_ensure_ok_with_404_raises_remote_service_error() -> None:
    response = httpx.Response(404, json={"detail": "nope"})
    with pytest.raises(RemoteServiceError):
        ensure_ok(response)


def test_ensure_ok_with_500_raises_remote_service_error() -> None:
    response = httpx.Response(500)
    with pytest.raises(RemoteServiceError):
        ensure_ok(response)


def test_ensure_ok_with_error_response_body_includes_code_and_message() -> None:
    response = httpx.Response(400, json={"error_code": "BadRequest", "message": "bad params"})
    with pytest.raises(RemoteServiceError) as exc_info:
        ensure_ok(response)
    text = str(exc_info.value)
    assert "BadRequest" in text
    assert "bad params" in text


def test_ensure_ok_with_message_only_body_defaults_error_code() -> None:
    response = httpx.Response(400, json={"message": "bad params"})
    with pytest.raises(RemoteServiceError) as exc_info:
        ensure_ok(response)
    text = str(exc_info.value)
    assert "Error" in text
    assert "bad params" in text


def test_ensure_ok_with_non_json_body_includes_status_code() -> None:
    response = httpx.Response(503, text="Service Unavailable")
    with pytest.raises(RemoteServiceError) as exc_info:
        ensure_ok(response)
    assert "503" in str(exc_info.value)
