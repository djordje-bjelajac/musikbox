class MusikboxError(Exception):
    """Base exception for all musikbox errors."""


class TrackNotFoundError(MusikboxError):
    """Raised when a track cannot be found in the repository."""


class DownloadError(MusikboxError):
    """Raised when a download operation fails."""


class AnalysisError(MusikboxError):
    """Raised when audio analysis fails."""


class UnsupportedFormatError(MusikboxError):
    """Raised when an unsupported audio format is encountered."""


class ConfigError(MusikboxError):
    """Raised when configuration is invalid or missing."""


class PlaylistNotFoundError(MusikboxError):
    """Raised when a playlist cannot be found in the repository."""


class DatabaseError(MusikboxError):
    """Raised when a database operation fails."""


class MetadataWriteError(MusikboxError):
    """Raised when writing metadata tags to a file fails."""
