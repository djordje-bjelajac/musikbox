from musikbox.cli.player.importer import Importer
from musikbox.cli.player.input import InputHandler
from musikbox.events.bus import EventBus
from musikbox.events.types import ImportTrackReady


def test_importer_subscribes_to_import_track_ready() -> None:
    """Importer registers a handler for ImportTrackReady."""
    bus = EventBus()
    input_handler = InputHandler(bus)

    class FakeApp:
        library_service = None
        playlist_service = None

    _importer = Importer(bus, input_handler, FakeApp())

    handlers = bus._handlers.get(ImportTrackReady, [])
    assert len(handlers) > 0, "No handler registered for ImportTrackReady"
