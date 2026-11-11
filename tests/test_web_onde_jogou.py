from datetime import UTC, datetime

import pytest
from webkit import make_client

from geral.games.onde_jogou import by_number, load, pool
from geral.teams import load_teams

DAY = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)  # puzzle #8 (launch 2026-11-12)
API = "/api/jogos/onde-jogou"


@pytest.fixture
def game(store, mailer, clock):
    clock.now = DAY
    return make_client(store, mailer, clock)


def today(edition="geral", number=8):
    data = load()
    teams = {slug: t.name for slug, t in load_teams().items() if t.listed}
    return data, by_number(pool(data, edition, teams), number)


def test_game_page_shows_the_player_and_years_not_the_clubs(game) -> None:
    data, jogador = today()

    page = game.get("/jogos/onde-jogou")

    assert page.status_code == 200 and "#8" in page.text and jogador.nome in page.text
    assert page.text.count('class="slot"') == len(jogador.clubes)
    assert f">{jogador.clubes[0].inicio}" in page.text
    # every club name is in the autocomplete list, so none may be shown as an answer
    assert 'class="slot-club"' not in page.text


def test_team_edition_page(game) -> None:
    data, jogador = today("vasco")

    page = game.get("/jogos/onde-jogou/vasco")

    assert page.status_code == 200 and jogador.nome in page.text


@pytest.mark.parametrize("edition", ["abc", "xyz"])
def test_edition_without_players_is_404(game, edition) -> None:
    assert game.get(f"/jogos/onde-jogou/{edition}").status_code == 404
    assert game.post(f"{API}/{edition}/8", json={"palpites": ["Vasco"]}).status_code == 404


def test_api_judges_club_guesses(game) -> None:
    data, jogador = today()
    first = data.clubes[jogador.clubes[0].clube].nome

    verdict = game.post(f"{API}/geral/8", json={"palpites": [first.lower()]}).json()
    over = game.post(f"{API}/geral/8", json={"palpites": [first], "desistiu": True}).json()

    assert verdict["achados"] == 1 and verdict["slots"][0]["clube"] == first
    assert not verdict["over"]
    assert over["over"] and all(s["clube"] for s in over["slots"])


def test_api_rejects_unknown_club_without_counting_it(game) -> None:
    response = game.post(f"{API}/geral/8", json={"palpites": ["Clube Que Não Existe"]})

    assert response.status_code == 422
    assert "Clube Que Não Existe" in response.json()["detail"]


@pytest.mark.parametrize("body", [{"palpites": "Vasco"}, {"palpites": ["x" * 61]}, {}])
def test_api_rejects_malformed_bodies(game, body) -> None:
    assert game.post(f"{API}/geral/8", json=body).status_code == 422


@pytest.mark.parametrize("number", [0, 9])
def test_api_rejects_future_or_zero_puzzle(game, number) -> None:
    assert game.post(f"{API}/geral/{number}", json={"palpites": ["Vasco"]}).status_code == 404


def test_portal_links_the_career_game(game) -> None:
    assert 'href="/jogos/onde-jogou"' in game.get("/").text
