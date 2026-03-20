from click.testing import CliRunner

from musikbox.cli.main import cli
from musikbox.cli.play import play


def test_play_help_shows_options() -> None:
    runner = CliRunner()
    result = runner.invoke(play, ["--help"])

    assert result.exit_code == 0
    assert "--all" in result.output
    assert "--key" in result.output
    assert "--genre" in result.output
    assert "--bpm-range" in result.output
    assert "--sort-by" in result.output
    assert "TRACK_ID" in result.output


def test_play_command_is_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "play" in result.output
