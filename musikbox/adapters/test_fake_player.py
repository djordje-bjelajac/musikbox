from pathlib import Path

import pytest

from musikbox.adapters.fake_player import FakePlayer
from musikbox.domain.ports.player import Player


@pytest.fixture()
def player() -> FakePlayer:
    return FakePlayer()


def test_fake_player_implements_player_port(player: FakePlayer) -> None:
    assert isinstance(player, Player)


def test_fake_player_play_sets_state(player: FakePlayer, tmp_path: Path) -> None:
    audio_file = tmp_path / "song.mp3"
    audio_file.touch()

    player.play(audio_file)

    assert player.is_playing() is True
    assert player.is_paused() is False
    assert player.position() == 0.0
    assert player.duration() > 0.0


def test_fake_player_pause_resume_toggles(player: FakePlayer, tmp_path: Path) -> None:
    audio_file = tmp_path / "song.mp3"
    audio_file.touch()

    player.play(audio_file)
    assert player.is_playing() is True

    player.pause()
    assert player.is_playing() is False
    assert player.is_paused() is True

    player.resume()
    assert player.is_playing() is True
    assert player.is_paused() is False


def test_fake_player_stop_resets_state(player: FakePlayer, tmp_path: Path) -> None:
    audio_file = tmp_path / "song.mp3"
    audio_file.touch()

    player.play(audio_file)
    player.stop()

    assert player.is_playing() is False
    assert player.is_paused() is False
    assert player.position() == 0.0


def test_fake_player_position_and_duration(player: FakePlayer, tmp_path: Path) -> None:
    assert player.position() == 0.0
    assert player.duration() == 0.0

    audio_file = tmp_path / "song.mp3"
    audio_file.touch()
    player.play(audio_file)

    assert player.duration() == 180.0
    assert player.position() == 0.0
