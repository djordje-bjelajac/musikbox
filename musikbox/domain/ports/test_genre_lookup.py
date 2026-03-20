import pytest

from musikbox.domain.ports.genre_lookup import GenreLookup


def test_genre_lookup_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        GenreLookup()  # type: ignore[abstract]


def test_concrete_genre_lookup_can_be_instantiated() -> None:
    class StubGenreLookup(GenreLookup):
        def lookup(self, title: str, artist: str | None = None) -> tuple[str, float]:
            return ("Rock", 0.8)

    instance = StubGenreLookup()
    genre, confidence = instance.lookup("Test Song")
    assert genre == "Rock"
    assert confidence == 0.8
