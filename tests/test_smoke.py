from typer.testing import CliRunner

from resenha import __version__
from resenha.__main__ import app

runner = CliRunner()


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "resenha v0.1.0" in result.stdout
