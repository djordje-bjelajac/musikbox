from dataclasses import dataclass

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


@dataclass
class App:
    """Holds service instances wired with their adapters."""

    config: Config
    library_service: LibraryService
    download_service: DownloadService
    analysis_service: AnalysisService
    playlist_service: PlaylistService
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
        from musikbox.adapters.mpv_player import MpvPlayer

        player = MpvPlayer()
        return PlaybackService(player)
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
