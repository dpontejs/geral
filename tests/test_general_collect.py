"""Edição geral: the week of each série from ge (docs/features/edicao-geral.md)."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from geral.general.collect import collect_week, cut_table
from geral.models import StandingRow

FIXTURES = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("America/Sao_Paulo")
POTIGUAR_PAGE = "https://ge.globo.com/rn/futebol/campeonato-potiguar/"
SERIE_D_PAGE = "https://ge.globo.com/futebol/brasileirao-serie-d/"
POTIGUAR = "https://api.globoesporte.globo.com/tabela/51e46731-98b0-499f-b7e7-7d53554e30e4/fase"
SERIE_D = "https://api.globoesporte.globo.com/tabela/5b2a5692-2d5c-47e8-8b24-be84447b62fd/fase"
FEED = (
    "https://falkor-cda.bastian.globo.com/tenants/ge/instances/"
    "4b8faafe-65bb-4857-8f02-b73ede244276/posts/page/{n}"
)
FEED_LINE = f'<script>var feed = "{FEED.split("/page/")[0].removeprefix("https://")}";</script>'


def text(path: str) -> str:
    return (FIXTURES / path).read_text(encoding="utf-8")


def json_response(path: str) -> httpx.Response:
    return httpx.Response(200, text=text(path), headers={"content-type": "application/json"})


@pytest.fixture
def ge() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.get(POTIGUAR_PAGE).mock(
            return_value=httpx.Response(200, text=text("ge_tables/page_potiguar.html") + FEED_LINE)
        )
        for phase, file in (
            ("primeira-fase-potiguar-2026", "primeira-fase"),
            ("quartas-de-final-potiguar-2026", "quartas-de-final"),
            ("semifinal-potiguar-2026", "semifinal"),
            ("final-potiguar-2026", "final"),
        ):
            router.get(f"{POTIGUAR}/{phase}/classificacao/").mock(
                return_value=json_response(f"ge_tables/potiguar_{file}.json")
            )
        for n in range(1, 8):
            router.get(f"{POTIGUAR}/primeira-fase-potiguar-2026/rodada/{n}/jogos/").mock(
                return_value=json_response(f"ge_tables/potiguar_primeira-fase_r{n}.json")
            )
        router.get(f"{POTIGUAR}/primeira-fase-potiguar-2026/rodada/8/jogos/").mock(
            return_value=httpx.Response(200, json=[])
        )
        for n in (1, 2):
            router.get(FEED.format(n=n)).mock(
                return_value=json_response(f"ge_feed/abc_page{n}.json")
            )
        router.get(FEED.format(n=3)).mock(return_value=httpx.Response(200, json={"items": []}))
        router.get(SERIE_D_PAGE).mock(
            return_value=httpx.Response(200, text=text("ge_tables/page_seried.html"))
        )
        router.get(f"{SERIE_D}/primeira-fase-brasileiro-seried-2026/classificacao/").mock(
            return_value=json_response("ge_tables/seried_primeira-fase.json")
        )
        for n in range(1, 12):
            router.get(f"{SERIE_D}/primeira-fase-brasileiro-seried-2026/rodada/{n}/jogos/").mock(
                return_value=json_response(f"ge_tables/seried_primeira-fase_r{n}.json")
            )
        yield router


def week(start: datetime, end: datetime, series: dict[str, str]) -> list:
    return collect_week(start, end, series=series, client=httpx.Client(), tz=TZ)


def test_collect_week_results_in_the_window_only(ge) -> None:
    weeks = week(
        datetime(2026, 3, 16, 8, tzinfo=TZ), datetime(2026, 3, 23, 8, tzinfo=TZ),
        {"Potiguar": POTIGUAR_PAGE},
    )  # fmt: skip

    (potiguar,) = weeks
    assert [(g.home, g.home_goals, g.away_goals, g.away) for g in potiguar.results] == [
        ("América-RN", 1, 1, "ABC"),
        ("ABC", 1, 1, "América-RN"),
    ]
    assert (potiguar.results[1].home_penalties, potiguar.results[1].away_penalties) == (2, 4)


def test_collect_week_knockout_shows_the_phase_without_table(ge) -> None:
    (potiguar,) = week(
        datetime(2026, 3, 16, 8, tzinfo=TZ), datetime(2026, 3, 23, 8, tzinfo=TZ),
        {"Potiguar": POTIGUAR_PAGE},
    )  # fmt: skip

    assert potiguar.phase == "Final"
    assert potiguar.table_top == [] and potiguar.table_bottom == []


def test_collect_week_groups_phase_shows_the_phase_without_table(ge) -> None:
    (serie_d,) = week(
        datetime(2026, 4, 1, 8, tzinfo=TZ), datetime(2026, 4, 8, 8, tzinfo=TZ),
        {"Série D": SERIE_D_PAGE},
    )  # fmt: skip

    assert serie_d.phase == "Primeira fase"
    assert serie_d.table_top == []
    assert serie_d.results  # the first round, 04-05/04


def test_collect_week_news_from_the_series_page_feed(ge) -> None:
    (potiguar,) = week(
        datetime(2026, 11, 4, 8, tzinfo=TZ), datetime(2026, 11, 11, 8, tzinfo=TZ),
        {"Potiguar": POTIGUAR_PAGE},
    )  # fmt: skip

    assert potiguar.results == []
    assert 1 <= len(potiguar.news) <= 8
    dates = [a.published_at for a in potiguar.news]
    assert dates == sorted(dates, reverse=True)
    assert all(datetime(2026, 11, 4, 8, tzinfo=TZ) <= d < datetime(2026, 11, 11, 8, tzinfo=TZ)
               for d in dates)  # fmt: skip


def test_collect_week_skips_series_without_games_or_news(ge) -> None:
    weeks = week(
        datetime(2026, 12, 1, 8, tzinfo=TZ), datetime(2026, 12, 8, 8, tzinfo=TZ),
        {"Potiguar": POTIGUAR_PAGE, "Série D": SERIE_D_PAGE},
    )  # fmt: skip

    assert weeks == []


def test_collect_week_one_series_failing_is_skipped(ge) -> None:
    ge.get(SERIE_D_PAGE).mock(return_value=httpx.Response(503))

    weeks = week(
        datetime(2026, 3, 16, 8, tzinfo=TZ), datetime(2026, 3, 23, 8, tzinfo=TZ),
        {"Potiguar": POTIGUAR_PAGE, "Série D": SERIE_D_PAGE},
    )  # fmt: skip

    assert [w.name for w in weeks] == ["Potiguar"]


def test_collect_week_all_series_failing_is_an_error(ge) -> None:
    ge.get(POTIGUAR_PAGE).mock(return_value=httpx.Response(503))

    with pytest.raises(RuntimeError):
        week(
            datetime(2026, 3, 16, 8, tzinfo=TZ), datetime(2026, 3, 23, 8, tzinfo=TZ),
            {"Potiguar": POTIGUAR_PAGE},
        )  # fmt: skip


def row(position: int) -> StandingRow:
    return StandingRow(
        position=position, team=f"Time {position}", points=60 - position, played=30, won=10,
        drawn=5, lost=15, goals_diff=0,
    )  # fmt: skip


def test_cut_table_keeps_the_top_and_the_bottom_four() -> None:
    top, bottom = cut_table([row(i) for i in range(20, 0, -1)])

    assert [r.position for r in top] == [1, 2, 3, 4]
    assert [r.position for r in bottom] == [17, 18, 19, 20]


def test_cut_table_short_table_is_shown_whole() -> None:
    top, bottom = cut_table([row(i) for i in range(1, 9)])

    assert [r.position for r in top] == list(range(1, 9)) and bottom == []


def test_collect_week_reads_more_feed_pages_than_a_team(ge) -> None:
    from geral.collectors.ge import MAX_FEED_PAGES
    from geral.general.collect import FEED_PAGES

    assert FEED_PAGES > MAX_FEED_PAGES
