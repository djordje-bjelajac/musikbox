import ast
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from musikbox.adapters.local_source_resolver import LocalSourceResolver
from musikbox.cli.player.render_state import RenderState
from musikbox.cli.player.renderer import Renderer
from musikbox.cli.player.viewport import Viewport
from musikbox.domain.models import Track, TrackId
from musikbox.events.bus import EventBus
from musikbox.services.playback_service import PlaybackService

# Renderer attributes that are deliberately NOT part of the render fingerprint:
# collaborators, caches, and internal paint bookkeeping. Adding an attribute here
# is an explicit statement that it can never change what the panel displays.
_NON_FINGERPRINT_ATTRS: frozenset[str] = frozenset(
    {
        "_service",
        "_console",
        "_live",
        "_playlist_repo",
        "_cached_track_id",
        "_has_playlist",
        "_import_done_at",
        "_bus",
        "_dirty",
        "_last_state",
        "_last_paint_at",
        "_viewport",
    }
)

# Renderer attribute -> RenderState field that fingerprints it.
_ATTR_TO_FIELD: dict[str, str] = {
    "_browse_index": "browse_index",
    "_move_index": "move_index",
    "_cached_playlists": "playlists_label",
    "_import_active": "import_signature",
    "_import_done": "import_signature",
    "_import_name": "import_signature",
    "_import_count": "import_signature",
    "_import_last_track": "import_signature",
    "_import_error": "import_signature",
}


def _make_track(title: str = "Test Track", bpm: float | None = 128.0) -> Track:
    return Track(
        id=TrackId(),
        title=title,
        artist="Test Artist",
        album="Test Album",
        duration_seconds=240.0,
        file_path=Path("/tmp/test.mp3"),
        format="mp3",
        bpm=bpm,
        key="Am",
        genre="Techno",
        mood=None,
        source_url=None,
        downloaded_at=None,
        analyzed_at=None,
        created_at=datetime.now(),
    )


def _make_service(
    tracks: list[Track] | None = None,
    position: float = 60.0,
    duration: float = 240.0,
    paused: bool = False,
) -> PlaybackService:
    player = MagicMock()
    player.is_paused.return_value = paused
    player.is_playing.return_value = not paused
    player.position.return_value = position
    player.duration.return_value = duration
    service = PlaybackService(player, LocalSourceResolver())
    if tracks:
        service.load_queue(tracks)
    return service


def _make_renderer(service: PlaybackService) -> Renderer:
    return Renderer(EventBus(), service)


@pytest.fixture
def viewport() -> Viewport:
    return Viewport(columns=120, lines=40)


def test_capture_with_no_track_returns_empty_state(viewport: Viewport) -> None:
    service = _make_service()
    renderer = _make_renderer(service)

    state = RenderState.capture(service, renderer, viewport)

    assert state.track_key == ""
    assert state.position_seconds == 0
    assert state.duration_seconds == 0
    assert state.filled_cells == 0
    assert state.queue_index == 0
    assert state.queue_signature == ()
    assert state.browse_index == -1
    assert state.move_index == -1
    assert state.playlists_label == ""
    assert state.columns == 120
    assert state.lines == 40


def test_capture_with_zero_duration_does_not_raise(viewport: Viewport) -> None:
    service = _make_service([_make_track()], position=0.0, duration=0.0)
    renderer = _make_renderer(service)

    state = RenderState.capture(service, renderer, viewport)

    assert state.filled_cells == 0
    assert state.duration_seconds == 0


def test_identical_inputs_produce_equal_states(viewport: Viewport) -> None:
    track = _make_track()
    service = _make_service([track])
    renderer = _make_renderer(service)

    first = RenderState.capture(service, renderer, viewport)
    second = RenderState.capture(service, renderer, viewport)

    assert first == second
    assert first.track_key == track.id.value


def test_sub_second_position_change_produces_equal_state() -> None:
    # columns=123 -> bar_width = 100. 60.0s/240s = 25.0% -> 25 cells;
    # 60.4s/240s = 25.166% -> still 25 cells. The state must not change.
    viewport = Viewport(columns=123, lines=40)
    assert viewport.progress_bar_width() == 100

    track = _make_track()
    service_a = _make_service([track], position=60.0)
    service_b = _make_service([track], position=60.4)
    renderer_a = _make_renderer(service_a)
    renderer_b = _make_renderer(service_b)

    state_a = RenderState.capture(service_a, renderer_a, viewport)
    state_b = RenderState.capture(service_b, renderer_b, viewport)

    # Guard the premise: the equality below must come from identical cell counts,
    # not from some unrelated field being dropped.
    assert state_a.filled_cells == state_b.filled_cells == 25
    assert state_a == state_b


def test_whole_second_position_change_produces_different_state(viewport: Viewport) -> None:
    track = _make_track()
    service_a = _make_service([track], position=60.0)
    service_b = _make_service([track], position=61.0)

    state_a = RenderState.capture(service_a, _make_renderer(service_a), viewport)
    state_b = RenderState.capture(service_b, _make_renderer(service_b), viewport)

    assert state_a != state_b
    assert state_a.position_seconds == 60
    assert state_b.position_seconds == 61


def test_pause_toggle_produces_different_state(viewport: Viewport) -> None:
    track = _make_track()
    service_a = _make_service([track], paused=False)
    service_b = _make_service([track], paused=True)

    state_a = RenderState.capture(service_a, _make_renderer(service_a), viewport)
    state_b = RenderState.capture(service_b, _make_renderer(service_b), viewport)

    assert state_a.is_paused is False
    assert state_b.is_paused is True
    assert state_a != state_b


def test_queue_reorder_produces_different_state(viewport: Viewport) -> None:
    first = _make_track("First")
    second = _make_track("Second")
    service_a = _make_service([first, second])
    service_b = _make_service([second, first])

    state_a = RenderState.capture(service_a, _make_renderer(service_a), viewport)
    state_b = RenderState.capture(service_b, _make_renderer(service_b), viewport)

    assert set(state_a.queue_signature) == set(state_b.queue_signature)
    assert state_a.queue_signature != state_b.queue_signature
    assert state_a != state_b


def test_browse_index_change_produces_different_state(viewport: Viewport) -> None:
    service = _make_service([_make_track(), _make_track("Other")])
    renderer = _make_renderer(service)

    before = RenderState.capture(service, renderer, viewport)
    renderer._browse_index = 1
    after = RenderState.capture(service, renderer, viewport)

    assert before.browse_index == -1
    assert after.browse_index == 1
    assert before != after


def test_move_index_change_produces_different_state(viewport: Viewport) -> None:
    service = _make_service([_make_track(), _make_track("Other")])
    renderer = _make_renderer(service)

    before = RenderState.capture(service, renderer, viewport)
    renderer._move_index = 0
    after = RenderState.capture(service, renderer, viewport)

    assert before.move_index == -1
    assert after.move_index == 0
    assert before != after


def test_playlists_label_change_produces_different_state(viewport: Viewport) -> None:
    service = _make_service([_make_track()])
    renderer = _make_renderer(service)

    before = RenderState.capture(service, renderer, viewport)
    renderer._cached_playlists = "Warmup, Peak Time"
    after = RenderState.capture(service, renderer, viewport)

    assert after.playlists_label == "Warmup, Peak Time"
    assert before != after


def test_import_progress_change_produces_different_state(viewport: Viewport) -> None:
    service = _make_service([_make_track()])
    renderer = _make_renderer(service)

    renderer._import_active = True
    renderer._import_name = "Set A"
    renderer._import_count = 1
    renderer._import_last_track = "Track One"
    before = RenderState.capture(service, renderer, viewport)

    renderer._import_count = 2
    renderer._import_last_track = "Track Two"
    after = RenderState.capture(service, renderer, viewport)

    assert before.import_signature == (True, False, "Set A", 1, "Track One", "")
    assert after.import_signature == (True, False, "Set A", 2, "Track Two", "")
    assert before != after


def test_import_error_change_produces_different_state(viewport: Viewport) -> None:
    service = _make_service([_make_track()])
    renderer = _make_renderer(service)

    before = RenderState.capture(service, renderer, viewport)
    renderer._import_active = False
    renderer._import_done = True
    renderer._import_error = "boom"
    after = RenderState.capture(service, renderer, viewport)

    assert before.import_signature[5] == ""
    assert after.import_signature[5] == "boom"
    assert before != after


def test_viewport_resize_produces_different_state() -> None:
    service = _make_service([_make_track()])
    renderer = _make_renderer(service)

    narrow = RenderState.capture(service, renderer, Viewport(columns=80, lines=24))
    wide = RenderState.capture(service, renderer, Viewport(columns=120, lines=40))

    assert narrow != wide
    assert (narrow.columns, narrow.lines) == (80, 24)
    assert (wide.columns, wide.lines) == (120, 40)


def _renderer_methods() -> dict[str, ast.FunctionDef]:
    """Every method defined on Renderer, keyed by name."""
    source = Path(__file__).with_name("renderer.py").read_text()
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == "Renderer":
            return {child.name: child for child in node.body if isinstance(child, ast.FunctionDef)}
    raise AssertionError("Renderer class not found in renderer.py")


def _build_panel_self_attrs() -> set[str]:
    """Every `self._<attr>` read while building the panel.

    Helper methods invoked from `_build_panel` are followed transitively --
    extracting a chunk of the panel into a helper must not smuggle a panel
    input past the fingerprint.
    """
    methods = _renderer_methods()
    if "_build_panel" not in methods:
        raise AssertionError("Renderer._build_panel not found in renderer.py")

    attrs: set[str] = set()
    visited: set[str] = set()
    pending: list[str] = ["_build_panel"]
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        for child in ast.walk(methods[name]):
            if (
                isinstance(child, ast.Attribute)
                and isinstance(child.value, ast.Name)
                and child.value.id == "self"
                and child.attr.startswith("_")
            ):
                if child.attr in methods:
                    pending.append(child.attr)
                else:
                    attrs.add(child.attr)
    return attrs


def test_capture_covers_every_renderer_field_used_by_build_panel() -> None:
    """Completeness invariant: an unfingerprinted panel input silently drops UI updates."""
    fields = set(RenderState.__dataclass_fields__)
    used = _build_panel_self_attrs()

    assert used, "no self._ attributes found in _build_panel - the AST scan is broken"

    for attr in sorted(used):
        if attr in _NON_FINGERPRINT_ATTRS:
            continue
        field_name = _ATTR_TO_FIELD.get(attr)
        assert field_name is not None, (
            f"Renderer._build_panel reads self.{attr} but RenderState does not fingerprint it. "
            f"Add a RenderState field for it, or add {attr!r} to _NON_FINGERPRINT_ATTRS."
        )
        assert field_name in fields, (
            f"self.{attr} maps to RenderState field {field_name!r}, which does not exist."
        )
