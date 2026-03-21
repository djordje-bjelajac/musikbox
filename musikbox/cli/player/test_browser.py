from musikbox.adapters.fake_player import FakePlayer
from musikbox.cli.player.browser import LibraryBrowser
from musikbox.cli.player.input import InputHandler
from musikbox.events.bus import EventBus
from musikbox.events.types import BrowseLibraryRequested
from musikbox.services.playback_service import PlaybackService


def test_browser_subscribes_to_browse_library_requested() -> None:
    """LibraryBrowser registers a handler for BrowseLibraryRequested."""
    bus = EventBus()
    input_handler = InputHandler(bus)
    player = FakePlayer()
    service = PlaybackService(player)

    class FakeApp:
        library_service = None
        playlist_service = None

    _browser = LibraryBrowser(bus, input_handler, service, FakeApp())

    handlers = bus._handlers.get(BrowseLibraryRequested, [])
    assert len(handlers) > 0, "No handler registered for BrowseLibraryRequested"
