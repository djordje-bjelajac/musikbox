from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from musikbox.domain.exceptions import PlaybackUnavailableError
from musikbox.domain.ports.player import Player
from musikbox.server.dtos import PlayCommand, PlayerStatusDTO, SeekCommand

if TYPE_CHECKING:
    from musikbox.server.app import ServerServices

_OK = {"status": "ok"}


def create_player_router(services: ServerServices) -> APIRouter:
    router = APIRouter(prefix="/player")

    def _require_player() -> Player:
        if services.player is None:
            raise PlaybackUnavailableError("server-side playback is not available on this server")
        return services.player

    @router.post("/play")
    def play(cmd: PlayCommand) -> dict[str, str]:
        player = _require_player()
        track = services.library_service.get_track(cmd.track_id)
        player.play(services.source_resolver.resolve(track))
        return _OK

    @router.post("/pause")
    def pause() -> dict[str, str]:
        _require_player().pause()
        return _OK

    @router.post("/resume")
    def resume() -> dict[str, str]:
        _require_player().resume()
        return _OK

    @router.post("/stop")
    def stop() -> dict[str, str]:
        _require_player().stop()
        return _OK

    @router.post("/seek")
    def seek(cmd: SeekCommand) -> dict[str, str]:
        _require_player().seek(cmd.seconds)
        return _OK

    @router.get("/status")
    def status() -> PlayerStatusDTO:
        player = _require_player()
        return PlayerStatusDTO(
            position=player.position(),
            duration=player.duration(),
            is_playing=player.is_playing(),
            is_paused=player.is_paused(),
        )

    return router
