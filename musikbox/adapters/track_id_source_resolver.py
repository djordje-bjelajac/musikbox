from musikbox.domain.models import PlayableSource, Track
from musikbox.domain.ports.track_source_resolver import TrackSourceResolver


class TrackIdSourceResolver(TrackSourceResolver):
    """Resolve tracks to their identity only (server-output mode).

    Used with RemotePlayer, which forwards playback to the server by track id;
    no locator is needed because the server resolves the file locally.
    """

    def resolve(self, track: Track) -> PlayableSource:
        return PlayableSource(track_id=track.id.value, locator="", is_local=False)
