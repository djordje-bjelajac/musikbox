from musikbox.domain.models import PlayableSource, Track
from musikbox.domain.ports.track_source_resolver import TrackSourceResolver


class RemoteStreamResolver(TrackSourceResolver):
    """Resolve tracks to a remote stream URL (client-output mode)."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def resolve(self, track: Track) -> PlayableSource:
        track_id = track.id.value
        return PlayableSource(
            track_id=track_id,
            locator=f"{self._base_url}/tracks/{track_id}/stream",
            is_local=False,
        )
