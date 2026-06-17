import pytest

from musikbox.domain.models import PlayableSource, Track
from musikbox.domain.ports.track_source_resolver import TrackSourceResolver


def test_track_source_resolver_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        TrackSourceResolver()  # type: ignore[abstract]


def test_concrete_track_source_resolver_can_be_instantiated() -> None:
    class FakeResolver(TrackSourceResolver):
        def resolve(self, track: Track) -> PlayableSource:
            return PlayableSource(
                track_id=track.id.value,
                locator=str(track.file_path),
                is_local=True,
            )

    resolver = FakeResolver()
    assert isinstance(resolver, TrackSourceResolver)
