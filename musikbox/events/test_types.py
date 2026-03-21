import dataclasses
from datetime import datetime
from pathlib import Path

from musikbox.domain.models import Track, TrackId
from musikbox.events import types


def _all_event_classes() -> list[type]:
    return [
        obj
        for name in dir(types)
        if not name.startswith("_")
        for obj in [getattr(types, name)]
        if isinstance(obj, type) and obj.__module__ == types.__name__
    ]


def test_all_events_are_dataclasses():
    event_classes = _all_event_classes()
    assert len(event_classes) > 0
    for cls in event_classes:
        assert dataclasses.is_dataclass(cls), f"{cls.__name__} is not a dataclass"


def _make_track() -> Track:
    return Track(
        id=TrackId(),
        title="Test",
        artist="Artist",
        album=None,
        duration_seconds=180.0,
        file_path=Path("/tmp/test.mp3"),
        format="mp3",
        bpm=None,
        key=None,
        genre=None,
        mood=None,
        source_url=None,
        downloaded_at=None,
        analyzed_at=None,
        created_at=datetime.now(),
    )


def test_key_pressed_has_key_field():
    event = types.KeyPressed(key="q")
    assert event.key == "q"


def test_track_started_has_track_and_index():
    track = _make_track()
    event = types.TrackStarted(track=track, index=5)
    assert event.track is track
    assert event.index == 5
