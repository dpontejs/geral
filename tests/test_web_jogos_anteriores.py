"""Past puzzles of every daily game: playable at their own address, not counted in the streak."""

from datetime import UTC, datetime

import pytest
from webkit import make_client

from geral.games import calendario, craque

DAY = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)  # puzzle #8 of every game (launch 2026-11-11)
GAMES = ["craque-do-dia", "onde-jogou", "quem-e"]


@pytest.fixture
def game(store, mailer, clock):
    clock.now = DAY
    return make_client(store, mailer, clock)


@pytest.mark.parametrize("path", GAMES)
def test_a_past_puzzle_has_its_own_page_marked_as_past(game, path) -> None:
    page = game.get(f"/jogos/{path}/geral/3")

    assert page.status_code == 200
    assert 'data-number="3"' in page.text and 'data-archive="1"' in page.text
    assert "13/11" in page.text and "não conta na sequência" in page.text
    assert f'href="/jogos/{path}"' in page.text  # back to today's game
    assert 'class="stats"' not in page.text


@pytest.mark.parametrize("path", GAMES)
def test_todays_number_goes_to_todays_page(game, path) -> None:
    for edition, today in (("geral", f"/jogos/{path}"), ("vasco", f"/jogos/{path}/vasco")):
        response = game.get(f"/jogos/{path}/{edition}/8", follow_redirects=False)

        assert response.status_code == 307 and response.headers["location"] == today


@pytest.mark.parametrize("path", GAMES)
@pytest.mark.parametrize("number", [0, 9])
def test_future_or_zero_puzzle_is_404(game, path, number) -> None:
    assert game.get(f"/jogos/{path}/geral/{number}").status_code == 404


@pytest.mark.parametrize("path", GAMES)
def test_todays_page_lists_the_past_puzzles_of_its_edition(game, path) -> None:
    geral = game.get(f"/jogos/{path}").text
    vasco = game.get(f"/jogos/{path}/vasco").text

    assert 'data-archive="0"' in geral and 'class="stats"' in geral
    assert all(f'href="/jogos/{path}/geral/{n}"' in geral for n in range(1, 8))
    assert f'href="/jogos/{path}/geral/8"' not in geral
    assert f'href="/jogos/{path}/vasco/7"' in vasco


def test_quem_e_past_page_shows_that_days_player(game) -> None:
    from geral.games import onde_jogou, quem_e

    data = onde_jogou.load()
    frozen = calendario.answers(calendario.load(), "quem-e", "geral")
    players = quem_e.pool(data, "geral", {})
    player = calendario.pick(players, 3, frozen, key=lambda j: j.wikidata)

    page = game.get("/jogos/quem-e/geral/3").text
    verdict = game.post("/api/jogos/quem-e/geral/3", json={"palpites": [player.wikidata]}).json()

    assert page.count('class="slot"') == len(player.clubes)
    assert verdict["solved"]


def test_craque_follows_the_frozen_calendar(store, mailer, clock, monkeypatch) -> None:
    games = craque.pool(craque.load_lists(), "geral")
    frozen = next(c for c in games if c.answer != craque.by_number(games, 3).answer)
    monkeypatch.setattr(
        calendario, "load", lambda path=None: {"craque-do-dia": {"geral": ["", "", frozen.answer]}}
    )
    clock.now = DAY
    client = make_client(store, mailer, clock)

    verdict = client.post(
        "/api/jogos/craque-do-dia/geral/3", json={"guesses": [frozen.answer]}
    ).json()

    assert verdict["solved"]


def test_freeze_craque_records_every_edition_by_answer(tmp_path) -> None:
    lists = craque.load_lists()
    path = tmp_path / "calendario.json"

    calendario.freeze_craque(path, lists, until=3)

    frozen = calendario.load(path)["craque-do-dia"]
    geral = craque.pool(lists, "geral")
    assert frozen["geral"] == [craque.by_number(geral, n).answer for n in (1, 2, 3)]
    assert set(frozen) == {"geral"} | {s for s in lists if craque.pool(lists, s)}
