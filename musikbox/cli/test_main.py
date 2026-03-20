
from click.testing import CliRunner

from musikbox.cli.main import cli


def test_cli_help_shows_all_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "download" in result.output
    assert "analyze" in result.output
    assert "library" in result.output
    assert "db" in result.output


def test_cli_version_or_help_exits_cleanly() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "musikbox" in result.output
