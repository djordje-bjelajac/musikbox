import pytest

from musikbox.adapters.fake_player import FakePlayer
from musikbox.domain.models import PlayableSource
from musikbox.domain.ports.player import Player


def _source(locator: str = "/tmp/song.mp3") -> PlayableSource:
    return PlayableSource(track_id="t1", locator=locator, is_local=True)


@pytest.fixture()
def player() -> FakePlayer:
    return FakePlayer()


def test_fake_player_implements_player_port(player: FakePlayer) -> None:
    assert isinstance(player, Player)


def test_fake_player_play_sets_state(player: FakePlayer) -> None:
    player.play(_source())

    assert player.is_playing() is True
    assert player.is_paused() is False
    assert player.position() == 0.0
    assert player.duration() > 0.0


def test_fake_player_pause_resume_toggles(player: FakePlayer) -> None:
    player.play(_source())
    assert player.is_playing() is True

    player.pause()
    assert player.is_playing() is False
    assert player.is_paused() is True

    player.resume()
    assert player.is_playing() is True
    assert player.is_paused() is False


def test_fake_player_stop_resets_state(player: FakePlayer) -> None:
    player.play(_source())
    player.stop()

    assert player.is_playing() is False
    assert player.is_paused() is False
    assert player.position() == 0.0


def test_fake_player_position_and_duration(player: FakePlayer) -> None:
    assert player.position() == 0.0
    assert player.duration() == 0.0

    player.play(_source())

    assert player.duration() == 180.0
    assert player.position() == 0.0
