from datetime import datetime, timedelta
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
    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 14, 45, tzinfo=TZ))
    result = CliRunner().invoke(cli.app, ["due", "--team", "flamengo"])

    assert result.exit_code == 0, result.output
    assert result.stdout == "pre\t2026-10-18\tPré-jogo — 18/10/2026\n"


def test_due_prints_nothing_when_nothing_is_due(calendar) -> None:
    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 10, 0, tzinfo=TZ))
    result = CliRunner().invoke(cli.app, ["due", "--team", "flamengo"])

    assert result.exit_code == 0, result.output
    assert result.stdout == ""


def test_due_prints_nothing_when_espn_fails(calendar) -> None:
    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 14, 45, tzinfo=TZ))

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
    # Sent at 14:31; ESPN then moves the kickoff to 19:00, so the pre-game slot becomes 15:00.
    moved = BAHIA.model_copy(update={"kickoff": datetime(2026, 10, 18, 19, 0, tzinfo=TZ)})
    sent = LatestEdition(
        subject="Urubu News — Pré-jogo — 18/10/2026: Flamengo visita o Bahia",
        published_at=datetime(2026, 10, 18, 14, 31, tzinfo=TZ),
    )
    calendar.setattr(cli, "_fixtures", lambda team, settings, now: [moved])
    calendar.setattr(cli, "_latest", lambda settings, team: sent)
    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 15, 5, tzinfo=TZ))

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

    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 14, 45, tzinfo=TZ))
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
    monkeypatch.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 14, 45, tzinfo=TZ))
    return SubscriberStore(db)


def follow(store, email: str, teams: list[str]) -> None:
    store.request(email, teams, LAST_SENT)
    store.confirm(email, LAST_SENT)


def test_due_all_lists_only_teams_with_subscribers(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco", "nautico"])

    result = CliRunner().invoke(cli.app, ["due", "--all"])

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        "vasco\tpre\t2026-10-18\tPré-jogo — 18/10/2026\tsend",
        "nautico\tpre\t2026-10-18\tPré-jogo — 18/10/2026\tsend",
    ]


def test_due_all_prints_build_then_send_for_the_same_slot(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco"])

    def due_at(hour: int, minute: int) -> str:
        with pytest.MonkeyPatch.context() as m:
            m.setattr(cli, "_now", lambda: datetime(2026, 10, 18, hour, minute, tzinfo=TZ))
            return CliRunner().invoke(cli.app, ["due", "--all"]).stdout

    # kick-off 18:30: built at 12:30, sent at 14:30
    assert due_at(12, 40) == "vasco\tpre\t2026-10-18\tPré-jogo — 18/10/2026\tbuild\n"
    assert due_at(14, 40) == "vasco\tpre\t2026-10-18\tPré-jogo — 18/10/2026\tsend\n"


def test_due_all_prints_every_due_stage(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco"])
    yesterday = BAHIA.model_copy(
        update={"match_id": "a", "kickoff": datetime(2026, 10, 17, 20, 0, tzinfo=TZ)}
    )
    today = BAHIA.model_copy(
        update={"match_id": "b", "kickoff": datetime(2026, 10, 18, 19, 30, tzinfo=TZ)}
    )
    with pytest.MonkeyPatch.context() as m:
        m.setattr(cli, "_fixtures", lambda team, settings, now: [yesterday, today])
        m.setattr(cli, "_now", lambda: datetime(2026, 10, 18, 13, 40, tzinfo=TZ))
        result = CliRunner().invoke(cli.app, ["due", "--all"])

    assert result.stdout.splitlines() == [
        "vasco\tpost\t2026-10-18\tPós-jogo — 18/10/2026\tsend",
        "vasco\tpre\t2026-10-18\tPré-jogo — 18/10/2026\tbuild",
    ]


def test_due_all_stage_is_the_last_column(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco"])

    [line] = CliRunner().invoke(cli.app, ["due", "--all"]).stdout.splitlines()

    team, kind, day, label, stage = line.split("\t")
    assert (team, kind, day, stage) == ("vasco", "pre", "2026-10-18", "send")


def test_due_all_uses_each_team_latest_edition(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco", "nautico"])
    sent = datetime(2026, 10, 18, 14, 30, tzinfo=TZ)
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


def test_run_news_without_slot_today_builds_an_extra_edition(calendar) -> None:
    from geral import pipeline

    seen = {}

    def fake_build(edition, team, settings, **kwargs):
        seen["edition"] = edition
        raise RuntimeError("stop after resolving")

    now = datetime(2026, 10, 20, 14, 30, tzinfo=TZ)
    calendar.setattr(cli, "_now", lambda: now)
    calendar.setattr(pipeline, "build_newsletter", fake_build)

    CliRunner().invoke(cli.app, ["run", "--team", "flamengo", "--edition", "news"])

    edition = seen["edition"]
    assert (edition.kind, edition.label) == ("news", "Notícias — 20/10/2026")
    assert (edition.start, edition.end) == (LAST_SENT, now)  # since the last send
    assert edition.match_id is None


def test_run_news_without_slot_on_another_day_still_exits_1(calendar) -> None:
    calendar.setattr(cli, "_now", lambda: datetime(2026, 10, 20, 14, 30, tzinfo=TZ))

    result = CliRunner().invoke(
        cli.app, ["run", "--team", "flamengo", "--edition", "news", "--date", "2026-10-21"]
    )

    assert result.exit_code == 1
    assert "Nenhuma edição Notícias prevista em 21/10/2026" in result.output


def test_extra_news_edition_keeps_the_next_monday(calendar) -> None:
    from geral.schedule import plan

    sent = datetime(2026, 11, 11, 15, 0, tzinfo=TZ)

    slots = plan([], sent, sent, "Notícias — 11/11/2026")

    assert slots[0].label == "Notícias — 16/11/2026"


def test_rerun_of_todays_extra_edition_keeps_the_window_before_todays_send(calendar) -> None:
    from geral import pipeline

    seen = {}

    def fake_build(edition, team, settings, **kwargs):
        seen["edition"] = edition
        raise RuntimeError("stop after resolving")

    now = datetime(2026, 10, 20, 19, 0, tzinfo=TZ)
    sent_today = LatestEdition(
        subject="Urubu News — Notícias — 20/10/2026: x",
        published_at=datetime(2026, 10, 20, 18, 5, tzinfo=TZ),
        text="",
    )
    calendar.setattr(cli, "_now", lambda: now)
    calendar.setattr(cli, "_latest", lambda settings, team: sent_today)
    calendar.setattr(pipeline, "build_newsletter", fake_build)

    CliRunner().invoke(cli.app, ["run", "--team", "flamengo", "--edition", "news"])

    assert seen["edition"].start == now - timedelta(days=3)  # not 18:05 today
    assert seen["edition"].label == "Notícias — 20/10/2026"


def test_released_draft_after_send_at_is_due_for_send(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco"])
    geral_db.save_draft(
        "vasco",
        "post",
        "2026-10-17",
        "Pós-jogo — 17/10/2026",
        "{}",
        datetime(2026, 10, 17, 8, 0, tzinfo=TZ),
        datetime(2026, 10, 17, 13, 0, tzinfo=TZ),
    )
    draft = geral_db.draft("vasco", "post", "2026-10-17")
    geral_db.set_held(draft.id, True, datetime(2026, 10, 17, 9, 0, tzinfo=TZ))
    geral_db.set_held(draft.id, False, datetime(2026, 10, 18, 14, 40, tzinfo=TZ))  # a day late

    lines = CliRunner().invoke(cli.app, ["due", "--all"]).stdout.splitlines()

    assert "vasco\tpost\t2026-10-17\tPós-jogo — 17/10/2026 (solta 18/10 14:40)\trelease" in lines


def test_next_window_starts_at_last_real_send() -> None:
    from geral.models import Edition

    edition = Edition(
        kind="news",
        start=datetime(2026, 10, 21, 8, 0, tzinfo=TZ),  # the build of a held edition never sent
        end=datetime(2026, 10, 25, 13, 0, tzinfo=TZ),
        label="Notícias — 25/10/2026",
    )
    sent = LatestEdition(subject="Urubu News — Pós-jogo — 19/10/2026: x", published_at=LAST_SENT)

    widened = cli._since_last_send(edition, sent)

    assert widened.start == LAST_SENT - timedelta(hours=5)
    assert cli._since_last_send(edition, None) == edition
    later = LatestEdition(subject="x", published_at=datetime(2026, 10, 25, 13, 2, tzinfo=TZ))
    assert cli._since_last_send(edition, later) == edition


def test_a_second_late_release_is_a_new_row(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["vasco"])
    geral_db.save_draft(
        "vasco",
        "post",
        "2026-10-18",
        "Pós-jogo — 18/10/2026",
        "{}",
        datetime(2026, 10, 18, 8, 0, tzinfo=TZ),
        datetime(2026, 10, 18, 13, 0, tzinfo=TZ),
    )
    draft = geral_db.draft("vasco", "post", "2026-10-18")

    def release_row(at: datetime) -> str:
        geral_db.set_held(draft.id, True, at)
        geral_db.set_held(draft.id, False, at)
        out = CliRunner().invoke(cli.app, ["due", "--all"]).stdout.splitlines()
        return next(line for line in out if line.endswith("\trelease"))

    first = release_row(datetime(2026, 10, 18, 14, 0, tzinfo=TZ))
    second = release_row(datetime(2026, 10, 18, 14, 40, tzinfo=TZ))

    assert first != second  # the trigger dispatches each row once: a new release is a new row
    assert second.split("\t")[:3] == ["vasco", "post", "2026-10-18"]


def test_due_all_gives_thursday_news_to_specials_teams_only(geral_db) -> None:
    follow(geral_db, "ana@example.com", ["abc", "vasco"])
    monday = datetime(2026, 10, 19, 13, 2, tzinfo=TZ)
    for team, name in (("abc", "Elefante News"), ("vasco", "Almirante News")):
        geral_db.set_latest_edition(team, f"{name} — Notícias — 19/10/2026: x", "h", "t", monday)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(cli, "_fixtures", lambda team, settings, now: [])
        m.setattr(cli, "_now", lambda: datetime(2026, 10, 22, 13, 10, tzinfo=TZ))
        lines = CliRunner().invoke(cli.app, ["due", "--all"]).stdout.splitlines()

    assert lines == ["abc\tnews\t2026-10-22\tNotícias — 22/10/2026\tsend"]


def test_run_news_on_a_thursday_resolves_for_specials() -> None:
    from datetime import date

    from geral.edition import resolve_match_edition

    edition = resolve_match_edition(
        "news", date(2026, 10, 22), [], datetime(2026, 10, 19, 13, 2, tzinfo=TZ), weekdays=(0, 3)
    )

    assert edition is not None and edition.label == "Notícias — 22/10/2026"


def test_draft_published_before_send_at_is_due_for_send(geral_db, monkeypatch) -> None:
    follow(geral_db, "ana@example.com", ["vasco"])
    geral_db.save_draft(
        "vasco",
        "news",
        "2026-10-20",
        "Notícias — 20/10/2026",
        "{}",
        datetime(2026, 10, 20, 8, 0, tzinfo=TZ),
        datetime(2026, 10, 20, 13, 0, tzinfo=TZ),
    )
    draft = geral_db.draft("vasco", "news", "2026-10-20")
    geral_db.publish_now(draft.id, datetime(2026, 10, 20, 9, 30, tzinfo=TZ))
    monkeypatch.setattr(cli, "_now", lambda: datetime(2026, 10, 20, 9, 35, tzinfo=TZ))

    lines = CliRunner().invoke(cli.app, ["due", "--all"]).stdout.splitlines()

    assert "vasco\tnews\t2026-10-20\tNotícias — 20/10/2026 (solta 20/10 09:30)\trelease" in lines
