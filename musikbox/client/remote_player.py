from __future__ import annotations

from musikbox.client.transport import HttpTransport, ensure_ok
from musikbox.domain.exceptions import RemoteServiceError
from musikbox.domain.models import PlayableSource
from musikbox.domain.ports.player import Player


class RemotePlayer(Player):
    """Player that drives playback on a remote server (server-output mode)."""

    def __init__(self, transport: HttpTransport) -> None:
        self._http = transport

    def play(self, source: PlayableSource) -> None:
        ensure_ok(self._http.post("/player/play", json={"track_id": source.track_id}))

    def pause(self) -> None:
        ensure_ok(self._http.post("/player/pause"))

    def resume(self) -> None:
        ensure_ok(self._http.post("/player/resume"))

    def stop(self) -> None:
        ensure_ok(self._http.post("/player/stop"))

    def seek(self, seconds: float) -> None:
        ensure_ok(self._http.post("/player/seek", json={"seconds": seconds}))

    def _status(self) -> dict[str, object]:
        # Status is polled on hot paths (TUI tick); never raise from here.
        try:
            response = self._http.get("/player/status")
            if response.status_code != 200:
                return {}
            data = response.json()
            return data if isinstance(data, dict) else {}
        except RemoteServiceError:
            return {}

    def _float(self, key: str) -> float:
        value = self._status().get(key)
        return float(value) if isinstance(value, (int, float)) else 0.0

    def is_playing(self) -> bool:
        return bool(self._status().get("is_playing", False))

    def is_paused(self) -> bool:
        return bool(self._status().get("is_paused", False))

    def position(self) -> float:
        return self._float("position")

    def duration(self) -> float:
        return self._float("duration")
