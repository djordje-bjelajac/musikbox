from musikbox.domain.ports.genre_lookup import GenreLookup


class FakeGenreLookup(GenreLookup):
    """Genre lookup that returns hardcoded results for testing."""

    def lookup(self, title: str, artist: str | None = None) -> tuple[str, float]:
        return ("Electronic", 0.9)
