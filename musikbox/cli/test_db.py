import sqlite3
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from musikbox.cli.main import cli


def test_db_init_creates_database(tmp_path: Path) -> None:
    db_path = tmp_path / "musikbox.db"

    @dataclass
    class FakeConfig:
        db_path: Path

    @dataclass
    class FakeApp:
        config: FakeConfig

    fake_app = FakeApp(config=FakeConfig(db_path=db_path))

    runner = CliRunner()
    with patch("musikbox.cli.main.create_app", return_value=fake_app):
        result = runner.invoke(cli, ["db", "init"])

    assert result.exit_code == 0
    assert "Database initialized" in result.output

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'")
    tables = cursor.fetchall()
    conn.close()

    assert len(tables) == 1
