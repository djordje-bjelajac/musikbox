from datetime import datetime
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from musikbox.cli.playlist import playlist
from musikbox.domain.models import Playlist


def _make_mock_app() -> MagicMock:
    return MagicMock()


def _make_playlist(name: str = "My Playlist") -> Playlist:
    now = datetime(2025, 6, 1, 12, 0, 0)
    return Playlist(id="pl-1", name=name, created_at=now, updated_at=now)


def test_playlist_help_shows_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(playlist, ["--help"])

    assert result.exit_code == 0
    assert "create" in result.output
    assert "list" in result.output
    assert "show" in result.output
    assert "add" in result.output
    assert "remove" in result.output
    assert "delete" in result.output


@patch("musikbox.cli.playlist.console")
def test_playlist_create_command(mock_console: MagicMock) -> None:
    mock_app = _make_mock_app()
    mock_app.playlist_service.create_playlist.return_value = _make_playlist("Friday Set")

    runner = CliRunner()
    result = runner.invoke(playlist, ["create", "Friday Set"], obj=mock_app)

    assert result.exit_code == 0
    mock_app.playlist_service.create_playlist.assert_called_once_with("Friday Set")


@patch("musikbox.cli.playlist.console")
def test_playlist_list_command(mock_console: MagicMock) -> None:
    mock_app = _make_mock_app()
    playlists = [_make_playlist("Alpha"), _make_playlist("Beta")]
    mock_app.playlist_service.list_playlists.return_value = playlists
    mock_app.playlist_service.get_playlist_tracks.return_value = []

    runner = CliRunner()
    result = runner.invoke(playlist, ["list"], obj=mock_app)

    assert result.exit_code == 0
    mock_app.playlist_service.list_playlists.assert_called_once()
