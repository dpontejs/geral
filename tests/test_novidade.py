"""`geral novidade`: an announcement on top of each team's next edition, once (Central, 2026-11)."""

from datetime import timedelta

import pytest
from typer.testing import CliRunner
from webkit import AUTH, NOW

import geral.__main__ as cli
from geral.config import get_settings
from geral.web.notes import NoteStore

TEXT = "A Geral agora tem uma Central."


@pytest.fixture
def notes(store) -> NoteStore:
    return NoteStore(store.path)


def test_note_is_pending_until_the_team_publishes_an_edition(client, store, notes) -> None:
    store.set_latest_edition("vasco", "Antes", "<p>", "t", NOW - timedelta(days=1))
    notes.create(TEXT, NOW)

    before = client.get("/api/teams/vasco/note", headers=AUTH).json()
    fresh_team = client.get("/api/teams/flamengo/note", headers=AUTH).json()
    store.set_latest_edition("vasco", "Depois", "<p>", "t", NOW + timedelta(hours=5))
    after = client.get("/api/teams/vasco/note", headers=AUTH).json()

    assert before == {"text": TEXT} and fresh_team == {"text": TEXT}
    assert after == {"text": None}


def test_note_api_requires_the_token(client) -> None:
    assert client.get("/api/teams/vasco/note").status_code == 401


def test_cancelled_note_is_gone(client, notes) -> None:
    notes.create(TEXT, NOW)
    notes.cancel()
    assert client.get("/api/teams/vasco/note", headers=AUTH).json() == {"text": None}


def test_novidade_command_creates_and_cancels(tmp_path, monkeypatch) -> None:
    db = tmp_path / "subs.db"
    monkeypatch.setenv("SUBSCRIBERS_DB", str(db))
    get_settings.cache_clear()

    created = CliRunner().invoke(cli.app, ["novidade", TEXT])
    pending = NoteStore(db).latest()
    cancelled = CliRunner().invoke(cli.app, ["novidade", "--cancelar"])

    assert created.exit_code == 0 and "próxima edição" in created.output
    assert pending is not None and pending.text == TEXT
    assert cancelled.exit_code == 0 and NoteStore(db).latest() is None
