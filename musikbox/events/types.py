from dataclasses import dataclass

from musikbox.domain.models import Track

# Lifecycle


@dataclass
class Tick: ...


@dataclass
class Shutdown: ...


# Input


@dataclass
class KeyPressed:
    key: str


# Playback


@dataclass
class TrackStarted:
    track: Track
    index: int


@dataclass
class TrackEnded:
    index: int


@dataclass
class PlaybackPaused: ...


@dataclass
class PlaybackResumed: ...


@dataclass
class SeekRequested:
    seconds: float


# Queue


@dataclass
class QueueLoaded:
    tracks: list[Track]


@dataclass
class TrackAddedToQueue:
    track: Track


@dataclass
class TrackRemovedFromQueue:
    index: int


@dataclass
class QueueReordered: ...


@dataclass
class JumpToTrack:
    index: int


@dataclass
class NextTrackRequested:
    auto: bool = False


@dataclass
class PreviousTrackRequested: ...


# Browse / UI state


@dataclass
class BrowseIndexChanged:
    index: int | None


@dataclass
class MoveIndexChanged:
    index: int | None


@dataclass
class UIRefreshRequested: ...


# Edit mode


@dataclass
class EditTrackRequested:
    track: Track


@dataclass
class AddToPlaylistRequested:
    track: Track


@dataclass
class SearchQueueRequested: ...


@dataclass
class SortQueueRequested: ...


@dataclass
class BrowseLibraryRequested: ...


@dataclass
class AddTrackFromLibraryRequested: ...


# Background import


@dataclass
class ImportStarted:
    playlist_name: str


@dataclass
class ImportTrackDownloaded:
    track: Track
    count: int


@dataclass
class ImportCompleted:
    playlist_name: str
    count: int


@dataclass
class ImportFailed:
    error: str


@dataclass
class ImportTrackReady:
    """Track downloaded and ready to be saved to DB (main thread)."""

    track: Track
