import json
import re
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from geral.stats.cbf import CBF_GAMES_URL, CBF_PAGE_URL, CBFGoals

FIXTURES = Path(__file__).parent / "fixtures" / "cbf"
PAGE = CBF_PAGE_URL.format(path="campeonato-brasileiro/serie-d", year=2026)
ABC = 20042
EMPTY = {"grupos": [], "jogos": []}


def games_url(phase: int, n: int) -> str:
    return CBF_GAMES_URL.format(competition="1260635", round=n, phase=phase)


@pytest.fixture
def cbf() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.get(PAGE).mock(
            return_value=httpx.Response(200, text=(FIXTURES / "page_seried.html").read_text())
        )
        for phase, n in ((2075, 1), (2075, 2), (2080, 1), (2080, 2)):
            router.get(games_url(phase, n)).mock(
                return_value=httpx.Response(
                    200, text=(FIXTURES / f"seried_{phase}_r{n}.json").read_text()
                )
            )
        overrides: dict[str, dict] = {}  # url -> body, for rounds a test wants to change
        router.get(url__regex=re.escape("https://www.cbf.com.br/api/cbf/jogos/")).mock(
            side_effect=lambda request: httpx.Response(
                200, json=overrides.get(str(request.url), EMPTY)
            )
        )
        router.overrides = overrides
        yield router


def goals(day: date, ours: str = "ABC", theirs: str = "Luverdense") -> list:
    return CBFGoals(httpx.Client()).goals(
        "campeonato-brasileiro/serie-d", day, ABC, ours=ours, theirs=theirs
    )


def test_cbf_goals_of_our_match_with_minutes_and_sides(cbf) -> None:
    events = goals(date(2026, 7, 26))

    assert [(e.minute, e.player, e.team) for e in events] == [
        (11, "Igor Bahia", "ABC"),
        (23, "Wallyson", "ABC"),
        (33, "Douglas", "Luverdense"),
        (74, "Brunao", "ABC"),
        (76, "Brunao", "ABC"),
    ]
    assert all(e.type == "goal" and e.detail is None for e in events)


def test_cbf_penalty_goal_has_detail(cbf) -> None:
    events = goals(date(2026, 8, 16), theirs="Nacional")

    assert [(e.minute, e.player, e.detail) for e in events] == [(34, "Wallyson", "Pênalti")]


def test_cbf_first_half_stoppage_time(cbf) -> None:
    events = goals(date(2026, 8, 8), theirs="Nacional")

    assert [(e.minute, e.extra_minute) for e in events] == [(21, None), (45, None), (47, None)]


def test_cbf_own_goal_counts_for_the_other_side() -> None:
    from geral.stats.cbf import _goal

    event = _goal(
        {"tipo": "GOL", "resultado": "CT", "clube_id": "20042", "atleta_apelido": "Zé",
         "tempo_jogo": "2", "minutos": "48:00"},
        team_id=ABC, ours="ABC", theirs="Nacional",
    )  # fmt: skip

    assert (event.team, event.detail) == ("Nacional", "Contra")
    assert (event.minute, event.extra_minute) == (90, 3)


def test_cbf_no_match_that_day_is_empty(cbf) -> None:
    assert goals(date(2026, 7, 27)) == []


def test_cbf_page_down_is_empty(cbf) -> None:
    cbf.get(PAGE).mock(return_value=httpx.Response(500))

    assert goals(date(2026, 7, 26)) == []


def test_cbf_stops_after_finding_the_match(cbf) -> None:
    goals(date(2026, 8, 16), theirs="Nacional")

    rounds = [str(c.request.url) for c in cbf.calls if "/api/cbf/" in str(c.request.url)]
    assert rounds[-1] == games_url(2080, 2)


def test_cbf_older_parallel_phase_does_not_end_the_search(cbf) -> None:
    # Playoff (2090) and semifinal (2089) run side by side: a playoff round older than the
    # match must not stop the search before the semifinal.
    older = json.loads((FIXTURES / "seried_2075_r1.json").read_text())
    cbf.overrides[games_url(2090, 2)] = older

    events = goals(date(2026, 8, 16), theirs="Nacional")

    assert [e.player for e in events] == ["Wallyson"]
