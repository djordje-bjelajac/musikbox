import pytest

from musikbox.domain.models import PlayableSource
from musikbox.domain.ports.player import Player


def test_player_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        Player()  # type: ignore[abstract]


def test_concrete_player_can_be_instantiated() -> None:
    class FakePlayer(Player):
        def play(self, source: PlayableSource) -> None:
            pass

        def pause(self) -> None:
            pass

        def resume(self) -> None:
            pass

        def seek(self, seconds: float) -> None:
            pass

        def stop(self) -> None:
            pass

        def is_playing(self) -> bool:
            return False

        def is_paused(self) -> bool:
            return False

        def position(self) -> float:
            return 0.0

        def duration(self) -> float:
            return 0.0

    player = FakePlayer()
    assert isinstance(player, Player)
