from musikbox.domain.models import PlayableSource, Track
from musikbox.domain.ports.track_source_resolver import TrackSourceResolver


class LocalSourceResolver(TrackSourceResolver):
    """Resolve tracks to their local filesystem path (local and server modes)."""

    def resolve(self, track: Track) -> PlayableSource:
        return PlayableSource(
            track_id=track.id.value,
            locator=str(track.file_path),
            is_local=True,
        )
