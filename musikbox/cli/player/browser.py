import select
import shutil
import sys
import termios
import time
import tty
from collections import defaultdict

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from musikbox.domain.models import Track
from musikbox.events.bus import EventBus
from musikbox.events.types import (
    BrowseLibraryRequested,
    TrackAddedToQueue,
    UIRefreshRequested,
)
from musikbox.services.playback_service import PlaybackService

from .input import InputHandler

# Camelot mapping for display
_KEY_TO_CAMELOT: dict[str, tuple[int, str]] = {
    "G#m": (1, "A"),
    "Abm": (1, "A"),
    "D#m": (2, "A"),
    "Ebm": (2, "A"),
    "A#m": (3, "A"),
    "Bbm": (3, "A"),
    "Fm": (4, "A"),
    "Cm": (5, "A"),
    "Gm": (6, "A"),
    "Dm": (7, "A"),
    "Am": (8, "A"),
    "Em": (9, "A"),
    "Bm": (10, "A"),
    "F#m": (11, "A"),
    "Gbm": (11, "A"),
    "C#m": (12, "A"),
    "Dbm": (12, "A"),
    "B": (1, "B"),
    "F#": (2, "B"),
    "Gb": (2, "B"),
    "C#": (3, "B"),
    "Db": (3, "B"),
    "Ab": (4, "B"),
    "G#": (4, "B"),
    "Eb": (5, "B"),
    "D#": (5, "B"),
    "Bb": (6, "B"),
    "A#": (6, "B"),
    "F": (7, "B"),
    "C": (8, "B"),
    "G": (9, "B"),
    "D": (10, "B"),
    "A": (11, "B"),
    "E": (12, "B"),
}


def _to_camelot_str(key: str | None) -> str:
    if key is None:
        return "-"
    camelot = _KEY_TO_CAMELOT.get(key)
    if camelot is not None:
        return f"{camelot[0]}{camelot[1]}"
    return "-"


console = Console()


class _Node:
    """Tree node for the library browser."""

    def __init__(
        self,
        label: str,
        indent: int,
        kind: str,
        data: object = None,
        children_fn: object = None,
    ) -> None:
        self.label = label
        self.indent = indent
        self.kind = kind  # "category", "group", "track"
        self.data = data  # Track for "track" nodes
        self.expanded = False
        self.children_fn = children_fn  # callable -> list[_Node]
        self.children: list[_Node] = []


class LibraryBrowser:
    """Interactive library tree browser -- Artists/Albums/Genres/Playlists."""

    def __init__(
        self,
        bus: EventBus,
        input_handler: InputHandler,
        playback_service: PlaybackService,
        app: object,
    ) -> None:
        self._bus = bus
        self._input_handler = input_handler
        self._service = playback_service
        self._app = app
        self._playlist_name: str | None = None
        self._playlist_service: object | None = None
        self._renderer: object | None = None

        bus.subscribe(BrowseLibraryRequested, self._on_browse_library)

    @property
    def playlist_name(self) -> str | None:
        return self._playlist_name

    @playlist_name.setter
    def playlist_name(self, value: str | None) -> None:
        self._playlist_name = value

    @property
    def playlist_service(self) -> object | None:
        return self._playlist_service

    @playlist_service.setter
    def playlist_service(self, value: object | None) -> None:
        self._playlist_service = value

    def _on_browse_library(self, _event: BrowseLibraryRequested) -> None:
        self._input_handler.pause()
        if self._renderer and hasattr(self._renderer, "pause"):
            self._renderer.pause()
        time.sleep(0.15)
        try:
            self._browse_library()
        finally:
            self._input_handler.resume()
            if self._renderer and hasattr(self._renderer, "resume"):
                self._renderer.resume()
            time.sleep(0.15)
            self._bus.emit(UIRefreshRequested())

    def _browse_library(self) -> None:
        """Interactive library browser with expand/collapse tree navigation."""
        lib = self._app.library_service
        all_tracks = lib.list_tracks(limit=10_000)
        playlists = (
            self._app.playlist_service.list_playlists() if self._app.playlist_service else []
        )

        by_artist: dict[str, list[Track]] = defaultdict(list)
        by_genre: dict[str, list[Track]] = defaultdict(list)
        by_album: dict[str, list[Track]] = defaultdict(list)

        for t in all_tracks:
            by_artist[t.artist or "Unknown"].append(t)
            if t.genre and t.genre != "Unknown":
                by_genre[t.genre].append(t)
            if t.album:
                by_album[t.album].append(t)

        def make_track_nodes(tracks: list[Track], indent: int) -> list[_Node]:
            nodes = []
            for t in tracks:
                artist_str = f" -- {t.artist}" if t.artist else ""
                bpm_str = f"{t.bpm:.0f}" if t.bpm else "---"
                cam = _to_camelot_str(t.key)
                label = f"{bpm_str:>3} {cam:>3}  {t.title}{artist_str}"
                nodes.append(_Node(label, indent, "track", data=t))
            return nodes

        def make_artist_children() -> list[_Node]:
            nodes = []
            for name in sorted(by_artist.keys()):
                tracks = by_artist[name]
                n = _Node(f"{name} ({len(tracks)})", 1, "group")
                albums: dict[str, list[Track]] = defaultdict(list)
                no_album: list[Track] = []
                for t in tracks:
                    if t.album:
                        albums[t.album].append(t)
                    else:
                        no_album.append(t)

                def make_artist_tracks(
                    albums: dict[str, list[Track]], no_album: list[Track]
                ) -> list[_Node]:
                    result: list[_Node] = []
                    for alb_name in sorted(albums.keys()):
                        alb_node = _Node(f"💿 {alb_name}", 2, "group")
                        alb_tracks = albums[alb_name]
                        alb_node.children_fn = lambda at=alb_tracks: make_track_nodes(at, 3)
                        result.append(alb_node)
                    result.extend(make_track_nodes(no_album, 2))
                    return result

                n.children_fn = lambda a=albums, na=no_album: make_artist_tracks(a, na)
                nodes.append(n)
            return nodes

        def make_genre_children() -> list[_Node]:
            nodes = []
            for name in sorted(by_genre.keys()):
                tracks = by_genre[name]
                n = _Node(f"{name} ({len(tracks)})", 1, "group")
                n.children_fn = lambda t=tracks: make_track_nodes(t, 2)
                nodes.append(n)
            return nodes

        def make_album_children() -> list[_Node]:
            nodes = []
            for name in sorted(by_album.keys()):
                tracks = by_album[name]
                n = _Node(f"{name} ({len(tracks)})", 1, "group")
                n.children_fn = lambda t=tracks: make_track_nodes(t, 2)
                nodes.append(n)
            return nodes

        def make_playlist_children() -> list[_Node]:
            nodes = []
            for pl in playlists:
                n = _Node(f"{pl.name}", 1, "group")
                pl_id = pl.id

                def make_pl_tracks(pid: str = pl_id) -> list[_Node]:
                    try:
                        tracks = self._app.playlist_service.get_playlist_tracks_by_id(pid)
                    except Exception:
                        try:
                            tracks = self._app.playlist_service.get_playlist_tracks(pl.name)
                        except Exception:
                            tracks = []
                    return make_track_nodes(tracks, 2)

                n.children_fn = make_pl_tracks
                nodes.append(n)
            return nodes

        root_nodes = [
            _Node("Artists", 0, "category"),
            _Node("Albums", 0, "category"),
            _Node("Genres", 0, "category"),
            _Node("Playlists", 0, "category"),
        ]
        root_nodes[0].children_fn = make_artist_children
        root_nodes[1].children_fn = make_album_children
        root_nodes[2].children_fn = make_genre_children
        root_nodes[3].children_fn = make_playlist_children

        def flatten(nodes: list[_Node]) -> list[_Node]:
            result: list[_Node] = []
            for n in nodes:
                result.append(n)
                if n.expanded and n.children:
                    result.extend(flatten(n.children))
            return result

        selected = 0
        term_height = shutil.get_terminal_size().lines
        max_visible = max(5, term_height - 6)
        added_msg: str | None = None
        added_at: float = 0.0

        def build_panel() -> Panel:
            nonlocal added_msg
            visible = flatten(root_nodes)
            if not visible:
                return Panel("[dim]Empty library[/dim]", title="Library Browser")

            scroll_top = max(0, selected - max_visible // 2)
            scroll_top = min(scroll_top, max(0, len(visible) - max_visible))
            scroll_bottom = min(len(visible), scroll_top + max_visible)

            lines: list[Text] = []
            for i in range(scroll_top, scroll_bottom):
                node = visible[i]
                prefix = "  " * node.indent
                if node.kind == "track":
                    icon = "  "
                elif node.expanded:
                    icon = "▼ "
                else:
                    icon = "▶ "

                label = f"{prefix}{icon}{node.label}"
                style = "bold reverse" if i == selected else ""
                if node.kind == "category":
                    style = (style + " bold cyan").strip() if i == selected else "bold cyan"
                lines.append(Text(label, style=style))

            footer_parts = [
                (" j/k: navigate  ", "dim"),
                ("Enter: expand/add  ", "bold"),
                ("q: back", "dim"),
            ]

            footer = Text.assemble(*footer_parts)

            parts: list[object] = [*lines, Text("")]

            if added_msg and time.monotonic() - added_at < 3:
                parts.append(Text(f"  {added_msg}", style="bold green"))
                parts.append(Text(""))
            else:
                added_msg = None

            parts.append(footer)
            return Panel(Group(*parts), title="Library Browser", expand=True)

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setcbreak(fd)
            with Live(build_panel(), console=console, refresh_per_second=10) as live:
                while True:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if not ready:
                        live.update(build_panel())
                        continue

                    ch = sys.stdin.read(1)
                    if not ch:
                        continue

                    visible = flatten(root_nodes)
                    if ch == "j":
                        selected = min(len(visible) - 1, selected + 1)
                    elif ch == "k":
                        selected = max(0, selected - 1)
                    elif ch in ("\r", "\n"):
                        if selected < len(visible):
                            node = visible[selected]
                            if node.kind == "track":
                                track = node.data
                                self._service._queue.append(track)
                                if self._playlist_name and self._playlist_service:
                                    try:
                                        self._playlist_service.add_track(
                                            self._playlist_name, track.id.value
                                        )
                                    except Exception:
                                        pass
                                self._bus.emit(TrackAddedToQueue(track=track))
                                added_msg = f"Added: {track.title}"
                                added_at = time.monotonic()
                            else:
                                if node.expanded:
                                    node.expanded = False
                                else:
                                    if not node.children and node.children_fn:
                                        node.children = node.children_fn()
                                    node.expanded = True
                    elif ch in ("q", "Q", "\x03"):
                        return

                    live.update(build_panel())
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
