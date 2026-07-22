from dataclasses import dataclass
from typing import TYPE_CHECKING

from musikbox.services.playback_service import PlaybackService

from .viewport import Viewport

if TYPE_CHECKING:
    from .renderer import Renderer


@dataclass(frozen=True)
class RenderState:
    """Comparable fingerprint of everything the player panel displays.

    Two equal states render identically, so an equal state means the frame can
    be skipped entirely. Time-derived values are quantised to the granularity
    the UI can actually show -- whole seconds for the timestamps, filled-cell
    count for the progress bar -- so sub-second drift does not force a repaint.

    Every renderer attribute that reaches ``_build_panel`` must be represented
    here. An omission silently swallows a real update.
    """

    track_key: str
    is_paused: bool
    position_seconds: int
    duration_seconds: int
    filled_cells: int
    queue_index: int
    queue_signature: tuple[str, ...]
    browse_index: int
    move_index: int
    playlists_label: str
    import_signature: tuple[bool, bool, str, int, str, str]
    pan_offset: int
    columns: int
    lines: int

    @staticmethod
    def capture(
        service: PlaybackService,
        renderer: "Renderer",
        viewport: Viewport,
    ) -> "RenderState":
        """Build a fingerprint from the current service, renderer and viewport."""
        import_signature = (
            renderer._import_active,
            renderer._import_done,
            renderer._import_name,
            renderer._import_count,
            renderer._import_last_track,
            renderer._import_error or "",
        )
        browse_index = -1 if renderer._browse_index is None else renderer._browse_index
        move_index = -1 if renderer._move_index is None else renderer._move_index

        track = service.current_track()
        if track is None:
            return RenderState(
                track_key="",
                is_paused=False,
                position_seconds=0,
                duration_seconds=0,
                filled_cells=0,
                queue_index=0,
                queue_signature=(),
                browse_index=browse_index,
                move_index=move_index,
                playlists_label=renderer._cached_playlists,
                import_signature=import_signature,
                pan_offset=renderer._pan_offset,
                columns=viewport.columns,
                lines=viewport.lines,
            )

        pos = service.position()
        dur = service.duration()
        # Mirrors the arithmetic in Renderer._build_panel exactly -- the bar's
        # true display granularity is the filled-cell count, not the position.
        progress_pct = (pos / dur * 100) if dur > 0 else 0
        bar_width = viewport.progress_bar_width()
        filled_cells = int(bar_width * progress_pct / 100)

        return RenderState(
            track_key=track.id.value,
            is_paused=service.is_paused(),
            position_seconds=int(pos),
            duration_seconds=int(dur),
            filled_cells=filled_cells,
            queue_index=service.queue_index,
            queue_signature=tuple(t.id.value for t in service.queue),
            browse_index=browse_index,
            move_index=move_index,
            playlists_label=renderer._cached_playlists,
            import_signature=import_signature,
            pan_offset=renderer._pan_offset,
            columns=viewport.columns,
            lines=viewport.lines,
        )
