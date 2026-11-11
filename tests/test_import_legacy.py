"""`geral import-legacy`: subscribers, last edition and bolão of a single-team app (Urubu News)."""

import sqlite3
from contextlib import closing

import pytest
from typer.testing import CliRunner

import geral.__main__ as cli
from geral.web.bolao import BolaoStore
from geral.web.store import SubscriberStore

# The Urubu News schema (flanews.web.store and flanews.web.bolao), as it is in production.
URUBU_SCHEMA = """
CREATE TABLE subscribers (email TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
    confirmation_sent_at TEXT, confirmed_at TEXT, unsubscribed_at TEXT);
CREATE TABLE editions (id INTEGER PRIMARY KEY, subject TEXT NOT NULL, html TEXT NOT NULL,
    text TEXT NOT NULL, published_at TEXT NOT NULL);
CREATE TABLE bolao_matches (match_id TEXT PRIMARY KEY, opponent TEXT NOT NULL,
    flamengo_home INTEGER NOT NULL, kickoff TEXT NOT NULL, fla_goals INTEGER, opp_goals INTEGER);
CREATE TABLE bolao_bets (email TEXT NOT NULL, match_id TEXT NOT NULL, fla_goals INTEGER NOT NULL,
    opp_goals INTEGER NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (email, match_id));
CREATE TABLE bolao_players (email TEXT PRIMARY KEY, nickname TEXT NOT NULL UNIQUE COLLATE NOCASE);
"""
CONFIRMED = "2026-10-20T12:00:00+00:00"


@pytest.fixture
def urubu(tmp_path):
    path = tmp_path / "urubu.db"
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(URUBU_SCHEMA)
        db.executemany(
            "INSERT INTO subscribers VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("ana@x.com", "active", CONFIRMED, CONFIRMED, CONFIRMED, None),
                ("bia@x.com", "active", CONFIRMED, CONFIRMED, CONFIRMED, None),
                ("pending@x.com", "pending", CONFIRMED, CONFIRMED, None, None),
                ("gone@x.com", "unsubscribed", CONFIRMED, CONFIRMED, CONFIRMED, CONFIRMED),
            ],
        )
        db.execute(
            "INSERT INTO editions VALUES (1, 'Urubu News — Pós-jogo', '<p>h</p>', 't', ?)",
            (CONFIRMED,),
        )
        db.execute(
            "INSERT INTO bolao_matches VALUES ('401', 'Bahia', 0, ?, 2, 1)",
            ("2026-11-01T21:30:00+00:00",),
        )
        db.execute(
            "INSERT INTO bolao_bets VALUES ('ana@x.com', '401', 2, 1, '2026-11-01T18:00:00+00:00')"
        )
        db.execute("INSERT INTO bolao_players VALUES ('ana@x.com', 'Ana')")
    return path


@pytest.fixture
def geral_db(tmp_path, monkeypatch):
    path = tmp_path / "geral.db"
    monkeypatch.setenv("SUBSCRIBERS_DB", str(path))
    return path


def run_import(urubu) -> object:
    return CliRunner().invoke(cli.app, ["import-legacy", str(urubu), "--team", "flamengo"])


def test_import_brings_active_subscribers_edition_and_bolao(urubu, geral_db) -> None:
    result = run_import(urubu)

    assert result.exit_code == 0, result.output
    store, bolao = SubscriberStore(geral_db), BolaoStore(geral_db)
    assert store.active("flamengo") == ["ana@x.com", "bia@x.com"]
    assert store.latest_edition("flamengo").subject == "Urubu News — Pós-jogo"
    match = bolao.match("flamengo", "401")
    assert (match.opponent, match.home, match.result) == ("Bahia", False, (2, 1))
    assert bolao.nickname("ana@x.com") == "Ana"
    assert bolao.ranking("flamengo", 2026)[0].points == 5
    assert "2 inscritos" in result.output


def test_import_twice_changes_nothing(urubu, geral_db) -> None:
    run_import(urubu)
    second = run_import(urubu)

    assert second.exit_code == 0, second.output
    assert SubscriberStore(geral_db).active("flamengo") == ["ana@x.com", "bia@x.com"]
    assert len(BolaoStore(geral_db).ranking("flamengo", 2026)) == 1


def test_import_skips_pending_and_unsubscribed(urubu, geral_db) -> None:
    run_import(urubu)

    store = SubscriberStore(geral_db)
    assert store.get("pending@x.com") is None and store.get("gone@x.com") is None


def test_import_keeps_other_teams_of_people_already_in_the_geral(urubu, geral_db) -> None:
    store = SubscriberStore(geral_db)
    store.request("ana@x.com", ["vasco"], cli._now())
    store.confirm("ana@x.com", cli._now())

    run_import(urubu)

    assert store.teams_of("ana@x.com") == ["flamengo", "vasco"]


def test_import_unknown_team_exits_2(urubu, geral_db) -> None:
    result = CliRunner().invoke(cli.app, ["import-legacy", str(urubu), "--team", "xyz"])

    assert result.exit_code == 2
