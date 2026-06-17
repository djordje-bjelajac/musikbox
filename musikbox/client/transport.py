from __future__ import annotations

import httpx

from musikbox.domain.exceptions import RemoteServiceError


class HttpTransport:
    """Thin httpx wrapper that translates transport failures to domain errors.

    A pre-built ``httpx.Client`` may be injected (e.g. with a MockTransport in
    tests); otherwise one is created bound to ``base_url``.
    """

    def __init__(
        self,
        base_url: str,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = (
            client
            if client is not None
            else httpx.Client(base_url=self._base_url, timeout=timeout)
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    def get(
        self,
        path: str,
        params: dict[str, str | int | float | bool | None] | None = None,
    ) -> httpx.Response:
        try:
            return self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise RemoteServiceError(f"GET {path} failed: {exc}") from exc

    def post(self, path: str, json: dict[str, object] | None = None) -> httpx.Response:
        try:
            return self._client.post(path, json=json)
        except httpx.HTTPError as exc:
            raise RemoteServiceError(f"POST {path} failed: {exc}") from exc


def ensure_ok(response: httpx.Response) -> httpx.Response:
    """Raise RemoteServiceError for any non-2xx response, else return it."""
    if response.status_code < 400:
        return response
    message = f"server returned {response.status_code}"
    try:
        body = response.json()
        if isinstance(body, dict) and "message" in body:
            message = f"{body.get('error_code', 'Error')}: {body['message']}"
    except ValueError:
        pass
    raise RemoteServiceError(message)
