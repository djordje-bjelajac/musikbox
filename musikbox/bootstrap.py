from dataclasses import dataclass

from musikbox.config.settings import Config, load_config


@dataclass
class App:
    """Holds service instances. Services will be wired in Phase 3."""

    config: Config


def create_app() -> App:
    """Build the application object graph."""
    config = load_config()
    return App(config=config)
