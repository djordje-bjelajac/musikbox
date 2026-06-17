from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from musikbox.config.settings import Config
from musikbox.domain.exceptions import (
    ConfigError,
    DatabaseError,
    MusikboxError,
    PlaybackUnavailableError,
    PlaylistNotFoundError,
    TrackNotFoundError,
    UnsupportedFormatError,
)
from musikbox.domain.ports.player import Player
from musikbox.domain.ports.repository import TrackRepository
from musikbox.domain.ports.track_source_resolver import TrackSourceResolver
from musikbox.server.dtos import ErrorResponse
from musikbox.server.routers.player import create_player_router
from musikbox.server.routers.stream import create_stream_router
from musikbox.server.routers.tracks import create_tracks_router
from musikbox.services.library_service import LibraryService


@dataclass
class ServerServices:
    """Holds the server-side object graph for the HTTP API."""

    config: Config
    library_service: LibraryService
    repository: TrackRepository
    player: Player | None
    source_resolver: TrackSourceResolver


def base_url(request: Request) -> str:
    """The externally reachable base URL the client used to reach the server."""
    return str(request.base_url).rstrip("/")


def _error_response(exc: Exception, status_code: int) -> JSONResponse:
    body = ErrorResponse(error_code=type(exc).__name__, message=str(exc))
    return JSONResponse(status_code=status_code, content=body.model_dump())


_STATUS_BY_EXCEPTION: list[tuple[type[MusikboxError], int]] = [
    (TrackNotFoundError, 404),
    (PlaylistNotFoundError, 404),
    (UnsupportedFormatError, 415),
    (ConfigError, 400),
    (DatabaseError, 503),
    (PlaybackUnavailableError, 503),
]


def _register_exception_handlers(api: FastAPI) -> None:
    def _make_handler(status_code: int) -> Callable[[Request, Exception], JSONResponse]:
        def handler(request: Request, exc: Exception) -> JSONResponse:
            return _error_response(exc, status_code)

        return handler

    for exc_type, status_code in _STATUS_BY_EXCEPTION:
        api.add_exception_handler(exc_type, _make_handler(status_code))

    # Fallback for any other domain error.
    api.add_exception_handler(MusikboxError, _make_handler(500))


def create_api(services: ServerServices) -> FastAPI:
    """Build the FastAPI application wired to the given server services."""
    api = FastAPI(title="musikbox", version="0.1.0")
    api.include_router(create_tracks_router(services))
    api.include_router(create_stream_router(services))
    api.include_router(create_player_router(services))
    _register_exception_handlers(api)
    return api
