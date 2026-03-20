from musikbox.adapters.fake_genre_lookup import FakeGenreLookup
from musikbox.domain.ports.genre_lookup import GenreLookup


def test_fake_genre_lookup_returns_default_genre() -> None:
    lookup = FakeGenreLookup()

    genre, confidence = lookup.lookup("Any Title", artist="Any Artist")

    assert genre == "Electronic"
    assert confidence == 0.9


def test_fake_genre_lookup_implements_port() -> None:
    lookup = FakeGenreLookup()

    assert isinstance(lookup, GenreLookup)
