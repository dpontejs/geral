from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

import geral.__main__ as cli
from geral.config import get_settings
from geral.schedule import Fixture
from geral.send.recipients import LatestEdition
from geral.stats.espn import StatsUnavailable
from geral.teams import get_team

TZ = ZoneInfo("America/Sao_Paulo")
BAHIA = Fixture(
    match_id="bahia",
    league="bra.1",
    kickoff=datetime(2026, 10, 18, 18, 30, tzinfo=TZ),
    time_valid=True,
    state="pre",
    home="Bahia",
    away="Flamengo",
)
LAST_SENT = datetime(2026, 10, 16, 19, 11, tzinfo=TZ)
REAL_FIXTURES = cli._fixtures  # conftest swaps it for an empty calendar in every test


@pytest.fixture
def calendar(monkeypatch):
    monkeypatch.setattr(cli, "_fixtures", lambda team, settings, now: [BAHIA])
    latest = LatestEdition(subject="Urubu News — Novidades: algo", published_at=LAST_SENT)
    monkeypatch.setattr(cli, "_latest", lambda settings, team: latest)
    return monkeypatch


def test_due_prints_the_due_slot(calendar) -> None:
    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 12, 45, tzinfo=TZ))
    result = CliRunner().invoke(cli.app, ["due", "--team", "flamengo"])

    assert result.exit_code == 0, result.output
    assert result.stdout == "pre\t2026-10-18\tPré-jogo — 18/10/2026\n"


def test_due_prints_nothing_when_nothing_is_due(calendar) -> None:
    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 10, 0, tzinfo=TZ))
    result = CliRunner().invoke(cli.app, ["due", "--team", "flamengo"])

    assert result.exit_code == 0, result.output
    assert result.stdout == ""


def test_due_prints_nothing_when_espn_fails(calendar) -> None:
    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 12, 45, tzinfo=TZ))

    def down(team, settings, now):
        raise StatsUnavailable("espn down")

    calendar.setattr(cli, "_fixtures", down)

    result = CliRunner().invoke(cli.app, ["due", "--team", "flamengo"])

    assert result.exit_code == 0, result.output
    assert result.stdout == ""


def test_run_pre_without_slot_that_day_exits_1(calendar) -> None:
    result = CliRunner().invoke(
        cli.app, ["run", "--team", "flamengo", "--edition", "pre", "--date", "2026-10-20"]
    )

    assert result.exit_code == 1
    assert "Nenhuma edição Pré-jogo prevista em 20/10/2026" in result.output


def test_due_does_not_repeat_the_edition_just_sent(calendar) -> None:
    # Sent at 12:31; ESPN then moves the kickoff to 19:00, so the pre-game slot becomes 13:00.
    moved = BAHIA.model_copy(update={"kickoff": datetime(2026, 10, 18, 19, 0, tzinfo=TZ)})
    sent = LatestEdition(
        subject="Urubu News — Pré-jogo — 18/10/2026: Flamengo visita o Bahia",
        published_at=datetime(2026, 10, 18, 12, 31, tzinfo=TZ),
    )
    calendar.setattr(cli, "_fixtures", lambda team, settings, now: [moved])
    calendar.setattr(cli, "_latest", lambda settings, team: sent)
    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 13, 5, tzinfo=TZ))

    result = CliRunner().invoke(cli.app, ["due", "--team", "flamengo"])

    assert result.stdout == ""


def no_build(*args, **kwargs):
    raise AssertionError("nothing is due: the edition must not be built")


def test_run_auto_without_due_slot_exits_without_building(calendar) -> None:
    from geral import pipeline

    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 10, 0, tzinfo=TZ))
    calendar.setattr(pipeline, "build_newsletter", no_build)

    result = CliRunner().invoke(cli.app, ["run", "--team", "flamengo", "--edition", "auto"])

    assert result.exit_code == 0, result.output
    assert "Nenhuma edição agendada agora" in result.output


def test_run_auto_without_calendar_exits_without_building(calendar) -> None:
    from geral import pipeline

    def down(team, settings, now):
        raise StatsUnavailable("espn down")

    calendar.setattr(cli, "_fixtures", down)
    calendar.setattr(pipeline, "build_newsletter", no_build)

    result = CliRunner().invoke(cli.app, ["run", "--team", "flamengo", "--edition", "auto"])

    assert result.exit_code == 0, result.output
    assert "Agenda da ESPN indisponível" in result.output


def test_run_auto_resolves_the_due_slot(calendar) -> None:
    from geral import pipeline

    seen = {}

    def fake_build(edition, team, settings, **kwargs):
        seen["edition"] = edition
        raise RuntimeError("stop after resolving")

    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 12, 45, tzinfo=TZ))
    calendar.setattr(pipeline, "build_newsletter", fake_build)

    CliRunner().invoke(cli.app, ["run", "--team", "flamengo", "--edition", "auto"])

    assert seen["edition"].label == "Pré-jogo — 18/10/2026"
    assert seen["edition"].match_id == "bahia"


def test_old_fixed_editions_are_gone(calendar) -> None:
    result = CliRunner().invoke(cli.app, ["run", "--team", "flamengo", "--edition", "monday"])

    assert result.exit_code == 2


# --- due --all: every team with subscribers, from the page's own database -------------------


def match_for(team: str) -> Fixture:
    return BAHIA.model_copy(update={"match_id": f"m-{team}", "away": team})


@pytest.fixture
def geral_db(monkeypatch, tmp_path):
    from geral.web.store import SubscriberStore

    db = tmp_path / "subscribers.db"
    monkeypatch.setenv("SUBSCRIBERS_DB", str(db))
    monkeypatch.setattr(cli, "_fixtures", lambda team, settings, now: [match_for(team.slug)])
    monkeypatch.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 12, 45, tzinfo=TZ))
    return SubscriberStore(db)


def follow(store, email: str, teams: list[str]) -> None:
    store.request(email, teams, LAST_SENT)
    store.confirm(email, LAST_SENT)


def test_due_all_lists_only_teams_with_subscribers(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco", "nautico"])

    result = CliRunner().invoke(cli.app, ["due", "--all"])

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        "vasco\tpre\t2026-10-18\tPré-jogo — 18/10/2026",
        "nautico\tpre\t2026-10-18\tPré-jogo — 18/10/2026",
    ]


def test_due_all_uses_each_team_latest_edition(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco", "nautico"])
    sent = datetime(2026, 10, 18, 12, 30, tzinfo=TZ)
    geral_db.set_latest_edition(
        "vasco", "Almirante News — Pré-jogo — 18/10/2026: x", "h", "t", sent
    )

    result = CliRunner().invoke(cli.app, ["due", "--all"])

    assert [line.split("\t")[0] for line in result.stdout.splitlines()] == ["nautico"]


def test_due_all_prints_nothing_when_nothing_is_due(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco"])
    with pytest.MonkeyPatch.context() as m:
        m.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 10, 0, tzinfo=TZ))
        result = CliRunner().invoke(cli.app, ["due", "--all"])

    assert result.exit_code == 0 and result.stdout == ""


def test_due_all_when_espn_fails_for_a_team_the_others_go_on(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco", "abc"])

    def fixtures(team, settings, now):
        if team.slug == "vasco":
            raise StatsUnavailable("espn down")
        return [match_for(team.slug)]

    with pytest.MonkeyPatch.context() as m:
        m.setattr(cli, "_fixtures", fixtures)
        result = CliRunner().invoke(cli.app, ["due", "--all"])

    assert result.exit_code == 0, result.output
    assert [line.split("\t")[0] for line in result.stdout.splitlines()] == ["abc"]


def test_due_needs_a_team_or_all() -> None:
    result = CliRunner().invoke(cli.app, ["due"])

    assert result.exit_code == 2


def test_due_all_skips_unlisted_teams(geral_db, monkeypatch) -> None:
    from geral.teams import load_teams

    catalog = load_teams()
    catalog["nautico"] = catalog["nautico"].model_copy(update={"listed": False})
    monkeypatch.setattr(cli, "load_teams", lambda: catalog)
    follow(geral_db, "ana@example.com", ["nautico", "vasco"])

    result = CliRunner().invoke(cli.app, ["due", "--all"])

    assert [line.split("\t")[0] for line in result.stdout.splitlines()] == ["vasco"]


def test_due_fixtures_come_from_espn_and_ge(monkeypatch) -> None:
    ge_match = BAHIA.model_copy(update={"match_id": "350926", "league": "ge:Potiguar"})

    class Sources:
        def get_fixtures(self, now):
            return [ge_match]

    seen = []
    monkeypatch.setattr(cli, "stats_client_for", lambda team, **kw: seen.append(team) or Sources())

    fixtures = REAL_FIXTURES(get_team("abc"), get_settings(), datetime(2026, 3, 20, tzinfo=TZ))

    assert fixtures == [ge_match]
    assert seen == [get_team("abc")]
