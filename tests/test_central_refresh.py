from datetime import datetime
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

import geral.__main__ as cli
from geral.central.models import CentralSnapshot
from geral.central.refresh import Refresher, snapshot_path
from geral.central.store import load_snapshot, save_snapshot
from geral.config import Settings

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def fake_build(now, previous):
    return CentralSnapshot(updated_at=now, series=[])


def test_refresher_run_once_writes_snapshot(tmp_path) -> None:
    path = tmp_path / "central.json"
    assert Refresher(path, 600, build=fake_build, clock=lambda: NOW).run_once() is True
    assert load_snapshot(path).updated_at == NOW


def test_refresher_survives_build_error(tmp_path) -> None:
    path = tmp_path / "central.json"
    old = CentralSnapshot(updated_at=datetime(2026, 11, 20, tzinfo=NOW.tzinfo), series=[])
    save_snapshot(path, old)

    def broken(now, previous):
        assert previous == old  # the last snapshot is handed over
        raise RuntimeError("ge down")

    assert Refresher(path, 600, build=broken, clock=lambda: NOW).run_once() is False
    assert load_snapshot(path) == old


def test_snapshot_path_defaults_next_to_the_database() -> None:
    assert (
        str(snapshot_path(Settings(SUBSCRIBERS_DB="/data/subscribers.db"))) == "/data/central.json"
    )
    assert str(snapshot_path(Settings(CENTRAL_SNAPSHOT="/tmp/x.json"))) == "/tmp/x.json"


def test_refresh_is_off_in_tests() -> None:
    assert Settings().CENTRAL_REFRESH == 0


def test_central_command_writes_out(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "build_snapshot", fake_build)
    out = tmp_path / "c.json"
    result = CliRunner().invoke(cli.app, ["central", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert load_snapshot(out) is not None
