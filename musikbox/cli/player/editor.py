import select
import shutil
import sys
import termios
import time
import tty

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from musikbox.domain.models import SearchFilter, Track
from musikbox.events.bus import EventBus
from musikbox.events.types import (
    AddToPlaylistRequested,
    AddTrackFromLibraryRequested,
    BrowseIndexChanged,
    EditTrackRequested,
    QueueReordered,
    SearchQueueRequested,
    SortQueueRequested,
    TrackAddedToQueue,
    UIRefreshRequested,
)
from musikbox.services.playback_service import PlaybackService

from .input import InputHandler

# Camelot mapping for display in track pickers
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


def _sort_key(track: Track, field: str) -> tuple[int, str]:
    if field == "key":
        return _camelot_sort_key(track.key)
    value = getattr(track, field, None)
    if value is None:
        return (1, "")
    if isinstance(value, float):
        return (0, f"{value:020.4f}")
    return (0, str(value).lower())


def _camelot_sort_key(key: str | None) -> tuple[int, str]:
    if key is None:
        return (99, "Z")
    camelot = _KEY_TO_CAMELOT.get(key)
    if camelot is not None:
        return camelot
    if len(key) >= 2 and key[-1] in ("A", "B"):
        try:
            num = int(key[:-1])
            return (num, key[-1])
        except ValueError:
            pass
    return (99, "Z")


console = Console()


class Editor:
    """Handles track editing, playlist add, search, and sort -- modal dialogs."""

    def __init__(
        self,
        bus: EventBus,
        input_handler: InputHandler,
        playback_service: PlaybackService,
        repository: object,
        app: object,
    ) -> None:
        self._bus = bus
        self._input_handler = input_handler
        self._service = playback_service
        self._repository = repository
        self._app = app
        self._playlist_name: str | None = None
        self._playlist_service: object | None = None
        self._renderer: object | None = None  # Set by PlayerApp

        bus.subscribe(EditTrackRequested, self._on_edit_track)
        bus.subscribe(AddToPlaylistRequested, self._on_add_to_playlist)
        bus.subscribe(SearchQueueRequested, self._on_search_queue)
        bus.subscribe(SortQueueRequested, self._on_sort_queue)
        bus.subscribe(AddTrackFromLibraryRequested, self._on_add_track_from_library)

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

    def _pause_ui(self) -> None:
        self._input_handler.pause()
        if self._renderer and hasattr(self._renderer, "pause"):
            self._renderer.pause()
        time.sleep(0.15)

    def _resume_ui(self) -> None:
        self._input_handler.resume()
        if self._renderer and hasattr(self._renderer, "resume"):
            self._renderer.resume()
        time.sleep(0.15)
        self._bus.emit(UIRefreshRequested())

    def _on_edit_track(self, event: EditTrackRequested) -> None:
        self._pause_ui()
        try:
            self._edit_track(event.track)
        finally:
            self._resume_ui()

    def _on_add_to_playlist(self, event: AddToPlaylistRequested) -> None:
        self._pause_ui()
        try:
            self._add_to_playlist_interactive(event.track)
        finally:
            self._resume_ui()

    def _on_search_queue(self, _event: SearchQueueRequested) -> None:
        self._pause_ui()
        try:
            start = self._service.queue_index + 1
            match = self._search_queue(self._service.queue, start)
            if match is not None:
                self._bus.emit(BrowseIndexChanged(index=match))
        finally:
            self._resume_ui()

    def _on_sort_queue(self, _event: SortQueueRequested) -> None:
        self._pause_ui()
        try:
            self._sort_queue_interactive()
        finally:
            self._resume_ui()

    def _on_add_track_from_library(self, _event: AddTrackFromLibraryRequested) -> None:
        self._pause_ui()
        try:
            self._add_track_interactive()
        finally:
            self._resume_ui()

    def _edit_track(self, track: Track) -> None:
        """Prompt user to edit title, artist, genre of a track."""
        console.print("\n[bold]Edit track[/] (Enter to keep current, type new value to change)\n")

        new_title = input(f"  Title [{track.title}]: ").strip()
        if new_title:
            track.title = new_title

        new_artist = input(f"  Artist [{track.artist or ''}]: ").strip()
        if new_artist:
            track.artist = new_artist

        new_genre = input(f"  Genre [{track.genre or ''}]: ").strip()
        if new_genre:
            track.genre = new_genre

        self._repository.save(track)
        console.print("[green]Saved.[/green]\n")

    def _add_to_playlist_interactive(self, track: Track) -> None:
        """Pick a playlist and add the given track to it."""
        pl_service = self._app.playlist_service
        playlists = pl_service.list_playlists()

        if not playlists:
            console.print("\n  [dim]No playlists. Create one first.[/dim]\n")
            return

        selected = 0
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        term_height = shutil.get_terminal_size().lines
        max_visible = max(3, term_height - 8)

        def build_panel() -> Panel:
            lines: list[Text] = []
            scroll_top = max(0, selected - max_visible // 2)
            scroll_top = min(scroll_top, max(0, len(playlists) - max_visible))
            scroll_bottom = min(len(playlists), scroll_top + max_visible)

            for i in range(scroll_top, scroll_bottom):
                pl = playlists[i]
                style = "bold reverse" if i == selected else ""
                lines.append(Text(f"  {pl.name}", style=style))

            footer = Text.assemble(
                (" j/k: navigate  ", "dim"),
                ("Enter: add  ", "bold"),
                ("q: cancel", "dim"),
            )

            title = f"Add '{track.title}' to playlist"
            return Panel(
                Group(*lines, Text(""), footer),
                title=title,
                expand=True,
            )

        try:
            tty.setcbreak(fd)
            with Live(build_panel(), console=console, refresh_per_second=10) as live:
                while True:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if not ready:
                        continue
                    ch = sys.stdin.read(1)
                    if not ch:
                        continue
                    if ch == "j":
                        selected = min(len(playlists) - 1, selected + 1)
                        live.update(build_panel())
                    elif ch == "k":
                        selected = max(0, selected - 1)
                        live.update(build_panel())
                    elif ch in ("\r", "\n"):
                        pl = playlists[selected]
                        try:
                            pl_service.add_track(pl.name, track.id.value)
                        except Exception:
                            pass
                        console.print(f"  [green]Added to '{pl.name}'[/green]\n")
                        return
                    elif ch in ("q", "Q", "\x03"):
                        return
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _search_queue(self, queue: list[Track], start_from: int = 0) -> int | None:
        """Prompt for a search query and return the index of the first match."""
        query = input("  Search: ").strip().lower()
        if not query:
            return None

        for offset in range(len(queue)):
            i = (start_from + offset) % len(queue)
            track = queue[i]
            haystack = f"{track.title} {track.artist or ''} {track.genre or ''}".lower()
            if query in haystack:
                return i

        console.print("  [dim]No match found.[/dim]")
        time.sleep(0.5)
        return None

    def _sort_queue_interactive(self) -> None:
        """Re-sort the queue by user-specified fields."""
        console.print("\n[bold]Sort queue[/]\n")
        console.print("  Fields: title, artist, bpm, key, genre")
        sort_input = input("  Sort by (e.g. key,bpm): ").strip()
        if not sort_input:
            console.print("  [dim]Cancelled.[/dim]\n")
            return

        fields = [f.strip() for f in sort_input.split(",")]

        current = self._service.current_track()
        queue = list(self._service._queue)
        sorted_queue = sorted(queue, key=lambda t: tuple(_sort_key(t, f) for f in fields))

        self._service._queue[:] = sorted_queue

        if current:
            for i, t in enumerate(sorted_queue):
                if t.id.value == current.id.value:
                    self._service._index = i
                    break

        if self._playlist_name and self._playlist_service:
            try:
                track_ids = [t.id.value for t in sorted_queue]
                self._playlist_service.reorder_tracks(self._playlist_name, track_ids)
            except Exception:
                pass

        self._bus.emit(QueueReordered())
        console.print(f"  [green]Sorted by {sort_input}.[/green]\n")

    def _add_track_interactive(self) -> None:
        """Search library and add a track to the current queue."""
        console.print("\n[bold]Add track from library[/]\n")

        query = input("  Search: ").strip()
        if not query:
            console.print("  [dim]Cancelled.[/dim]\n")
            return

        lib = self._app.library_service
        results = lib.search_tracks(SearchFilter(query=query))

        if not results:
            console.print("  [dim]No tracks found.[/dim]\n")
            return

        picked = self._pick_track_interactive(results)
        if picked is None:
            console.print("  [dim]Cancelled.[/dim]\n")
            return

        track = results[picked]

        self._service._queue.append(track)

        if self._playlist_name and self._playlist_service:
            try:
                self._playlist_service.add_track(self._playlist_name, track.id.value)
            except Exception:
                pass

        self._bus.emit(TrackAddedToQueue(track=track))
        artist_str = f" -- {track.artist}" if track.artist else ""
        console.print(f"  [green]Added:[/] {track.title}{artist_str}\n")

    def _pick_track_interactive(self, tracks: list[Track]) -> int | None:
        """Interactive track picker with j/k navigation. Returns index or None."""
        selected = 0
        term_height = shutil.get_terminal_size().lines
        max_visible = max(5, term_height - 8)

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        def build_panel() -> Panel:
            table = Table(title=f"Search Results -- {len(tracks)} tracks", expand=True)
            table.add_column("#", justify="right", style="dim", width=4)
            table.add_column("Title")
            table.add_column("Artist", width=20)
            table.add_column("BPM", justify="right", width=6)
            table.add_column("Key", width=4)
            table.add_column("Camelot", width=7)

            scroll_top = max(0, selected - max_visible // 2)
            scroll_top = min(scroll_top, max(0, len(tracks) - max_visible))
            scroll_bottom = min(len(tracks), scroll_top + max_visible)

            for i in range(scroll_top, scroll_bottom):
                t = tracks[i]
                style = "bold reverse" if i == selected else ""
                table.add_row(
                    str(i + 1),
                    t.title,
                    t.artist or "-",
                    f"{t.bpm:.1f}" if t.bpm else "-",
                    t.key or "-",
                    _to_camelot_str(t.key),
                    style=style,
                )

            footer = Text.assemble(
                (" j/k: navigate  ", "dim"),
                ("Enter: add  ", "bold"),
                ("q: cancel", "dim"),
            )

            return Panel(Group(table, Text(""), footer), expand=True)

        try:
            tty.setcbreak(fd)
            with Live(build_panel(), console=console, refresh_per_second=10) as live:
                while True:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if not ready:
                        continue
                    ch = sys.stdin.read(1)
                    if not ch:
                        continue
                    if ch == "j":
                        selected = min(len(tracks) - 1, selected + 1)
                        live.update(build_panel())
                    elif ch == "k":
                        selected = max(0, selected - 1)
                        live.update(build_panel())
                    elif ch in ("\r", "\n"):
                        return selected
                    elif ch in ("q", "Q", "\x03"):
                        return None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
