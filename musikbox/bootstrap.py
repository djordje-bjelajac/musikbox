from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from musikbox.adapters.essentia_analyzer import EssentiaAnalyzer
from musikbox.adapters.fake_analyzer import FakeAnalyzer
from musikbox.adapters.metadata_writer import MutagenMetadataWriter
from musikbox.adapters.musicbrainz_genre_lookup import MusicBrainzGenreLookup
from musikbox.adapters.sqlite_playlist_repository import SqlitePlaylistRepository
from musikbox.adapters.sqlite_repository import SqliteRepository
from musikbox.adapters.ytdlp_downloader import YtdlpDownloader
from musikbox.config.settings import Config, load_config
from musikbox.domain.ports.analyzer import Analyzer
from musikbox.domain.ports.genre_lookup import GenreLookup
from musikbox.services.analysis_service import AnalysisService
from musikbox.services.download_service import DownloadService
from musikbox.services.library_service import LibraryService
from musikbox.services.playback_service import PlaybackService
from musikbox.services.playlist_service import PlaylistService

if TYPE_CHECKING:
    from musikbox.client.transport import HttpTransport
    from musikbox.domain.ports.player import Player
    from musikbox.server.app import ServerServices


@dataclass
class App:
    """Holds service instances wired with their adapters.

    In client mode the download/analysis/playlist services are absent (the
    server owns those heavy operations), so they are optional.
    """

    config: Config
    library_service: LibraryService
    download_service: DownloadService | None
    analysis_service: AnalysisService | None
    playlist_service: PlaylistService | None
    playback_service: PlaybackService | None
    genre_lookup: object | None
    enricher: object | None


def _create_analyzer(config: Config) -> Analyzer:
    """Create the best available analyzer.

    Tries LibrosaAnalyzer first, then EssentiaAnalyzer, falls back to FakeAnalyzer.
    """
    try:
        import librosa  # noqa: F401

        from musikbox.adapters.librosa_analyzer import LibrosaAnalyzer

        return LibrosaAnalyzer()
    except ImportError:
        pass

    try:
        import essentia  # noqa: F401

        return EssentiaAnalyzer(model_dir=config.analysis.model_dir)
    except ImportError:
        return FakeAnalyzer()


def _create_genre_lookup() -> GenreLookup:
    """Create a MusicBrainz genre lookup adapter. No API key required."""
    return MusicBrainzGenreLookup()


def _create_playback_service() -> PlaybackService | None:
    """Create a PlaybackService with MpvPlayer, or None if mpv is unavailable."""
    try:
        from musikbox.adapters.local_source_resolver import LocalSourceResolver
        from musikbox.adapters.mpv_player import MpvPlayer

        player = MpvPlayer()
        return PlaybackService(player, LocalSourceResolver())
    except (ImportError, OSError):
        return None


def create_app() -> App:
    """Build the application object graph."""
    config = load_config()
    repository = SqliteRepository(config.db_path)
    playlist_repository = SqlitePlaylistRepository(config.db_path)
    library_service = LibraryService(repository)

    analyzer = _create_analyzer(config)
    metadata_writer = MutagenMetadataWriter()

    genre_lookup = _create_genre_lookup()

    downloader = YtdlpDownloader(
        audio_quality=config.download.audio_quality,
        cookies_from_browser=config.download.cookies_from_browser,
    )
    download_service = DownloadService(
        downloader=downloader,
        analyzer=analyzer,
        repository=repository,
        music_dir=config.music_dir,
        default_format=config.download.default_format,
        auto_analyze=config.auto_analyze,
        genre_lookup=genre_lookup,
    )

    analysis_service = AnalysisService(
        analyzer=analyzer,
        repository=repository,
        metadata_writer=metadata_writer,
        write_tags=config.analysis.write_tags,
        key_notation=config.analysis.key_notation,
        genre_lookup=genre_lookup,
    )

    playback_service = _create_playback_service()

    playlist_service = PlaylistService(
        playlist_repository=playlist_repository,
        track_repository=repository,
        download_service=download_service,
    )

    enricher = None
    if config.anthropic_api_key:
        try:
            import anthropic  # noqa: F401

            from musikbox.adapters.haiku_enricher import HaikuEnricher

            enricher = HaikuEnricher(api_key=config.anthropic_api_key)
        except ImportError:
            pass

    return App(
        config=config,
        library_service=library_service,
        download_service=download_service,
        analysis_service=analysis_service,
        playlist_service=playlist_service,
        playback_service=playback_service,
        genre_lookup=genre_lookup,
        enricher=enricher,
    )


def _enable_wal(db_path: Path) -> None:
    """Best-effort enable SQLite WAL so clients can read while the server writes."""
    import sqlite3

    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def _create_server_player() -> Player | None:
    """Create an MpvPlayer for server-side output, or None if unavailable."""
    try:
        from musikbox.adapters.mpv_player import MpvPlayer

        return MpvPlayer()
    except (ImportError, OSError):
        return None


def bootstrap_server() -> ServerServices:
    """Build the server-side object graph for the HTTP API (ServerServices)."""
    from musikbox.adapters.local_source_resolver import LocalSourceResolver
    from musikbox.server.app import ServerServices

    config = load_config()
    _enable_wal(config.db_path)
    repository = SqliteRepository(config.db_path)
    library_service = LibraryService(repository)
    player = _create_server_player()
    return ServerServices(
        config=config,
        library_service=library_service,
        repository=repository,
        player=player,
        source_resolver=LocalSourceResolver(),
    )


def _create_client_playback_service(
    config: Config, transport: HttpTransport
) -> PlaybackService | None:
    """Build a client PlaybackService for the configured output target."""
    from musikbox.client.remote_player import RemotePlayer

    if config.output_target == "server":
        from musikbox.adapters.track_id_source_resolver import TrackIdSourceResolver

        return PlaybackService(RemotePlayer(transport), TrackIdSourceResolver())

    # Client output: render locally from the server's stream URL.
    try:
        from musikbox.adapters.mpv_player import MpvPlayer

        player = MpvPlayer()
    except (ImportError, OSError):
        return None

    from musikbox.adapters.remote_stream_resolver import RemoteStreamResolver

    assert config.server_url is not None
    return PlaybackService(player, RemoteStreamResolver(config.server_url))


def build_client_playback_service(config: Config) -> PlaybackService | None:
    """(Re)build a client playback service for the given config (e.g. output override)."""
    from musikbox.client.transport import HttpTransport
    from musikbox.domain.exceptions import ConfigError

    if not config.server_url:
        raise ConfigError("MUSIKBOX_SERVER_URL must be set when MUSIKBOX_MODE=client")
    return _create_client_playback_service(config, HttpTransport(config.server_url))


def bootstrap_client() -> App:
    """Build the client-side object graph (remote repository + player)."""
    from musikbox.client.http_track_repository import HttpTrackRepository
    from musikbox.client.transport import HttpTransport
    from musikbox.domain.exceptions import ConfigError

    config = load_config()
    if not config.server_url:
        raise ConfigError("MUSIKBOX_SERVER_URL must be set when MUSIKBOX_MODE=client")

    transport = HttpTransport(config.server_url)
    repository = HttpTrackRepository(transport)
    library_service = LibraryService(repository)
    playback_service = _create_client_playback_service(config, transport)

    return App(
        config=config,
        library_service=library_service,
        download_service=None,
        analysis_service=None,
        playlist_service=None,
        playback_service=playback_service,
        genre_lookup=None,
        enricher=None,
    )
