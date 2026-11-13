from datetime import UTC, datetime

import pytest
from webkit import make_client

from geral.games import quem_e
from geral.games.onde_jogou import load
from geral.teams import load_teams

DAY = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)  # puzzle #8 (launch 2026-11-11)
API = "/api/jogos/quem-e"


@pytest.fixture
def game(store, mailer, clock):
    clock.now = DAY
    return make_client(store, mailer, clock)


def today(edition="geral", number=8):
    data = load()
    teams = {slug: t.name for slug, t in load_teams().items() if t.listed}
    return data, quem_e.by_number(quem_e.pool(data, edition, teams), number)


def test_game_page_shows_the_career_not_the_name(game) -> None:
    data, jogador = today()

    page = game.get("/jogos/quem-e").text

    assert "#8" in page and page.count('class="slot"') == len(jogador.clubes)
    for stint in jogador.clubes:
        assert data.clubes[stint.clube].nome in page
    assert jogador.wikidata not in page.split('id="qe-player-data"')[0]
    assert f'class="lamp player">{jogador.nome}<' not in page


def test_team_edition_page(game) -> None:
    assert game.get("/jogos/quem-e/flamengo").status_code == 200


@pytest.mark.parametrize("edition", ["nautico", "xyz"])
def test_edition_without_players_is_404(game, edition) -> None:
    assert game.get(f"/jogos/quem-e/{edition}").status_code == 404
    assert game.post(f"{API}/{edition}/8", json={"palpites": ["Q1"]}).status_code == 404


def test_api_judges_player_guesses(game) -> None:
    data, jogador = today()
    other = next(j for j in data.jogadores if j.wikidata != jogador.wikidata)

    miss = game.post(f"{API}/geral/8", json={"palpites": [other.wikidata]}).json()
    hit = game.post(f"{API}/geral/8", json={"palpites": [other.wikidata, jogador.wikidata]}).json()

    assert miss["rows"] == [{"nome": other.nome, "certo": False}] and miss["reveal"] is None
    assert hit["solved"] and hit["reveal"]["nome"] == jogador.nome


def test_api_rejects_unknown_player(game) -> None:
    assert game.post(f"{API}/geral/8", json={"palpites": ["Q0"]}).status_code == 422


@pytest.mark.parametrize("body", [{"palpites": "Q1"}, {"palpites": ["Q1"] * 7}, {}])
def test_api_rejects_malformed_bodies(game, body) -> None:
    assert game.post(f"{API}/geral/8", json=body).status_code == 422


@pytest.mark.parametrize("number", [0, 9])
def test_api_rejects_future_or_zero_puzzle(game, number) -> None:
    data, jogador = today()

    response = game.post(f"{API}/geral/{number}", json={"palpites": [jogador.wikidata]})

    assert response.status_code == 404


def test_portal_links_who_game(game) -> None:
    assert 'href="/jogos/quem-e"' in game.get("/").text


def test_a_frozen_answer_wins_over_the_daily_order(store, mailer, clock, monkeypatch) -> None:
    from geral.games import calendario

    data, today_player = today()
    frozen = next(j for j in quem_e.pool(data, "geral", {}) if j.wikidata != today_player.wikidata)
    monkeypatch.setattr(
        calendario, "load", lambda path=None: {"quem-e": {"geral": [""] * 7 + [frozen.wikidata]}}
    )
    clock.now = DAY
    client = make_client(store, mailer, clock)

    verdict = client.post(f"{API}/geral/8", json={"palpites": [frozen.wikidata]}).json()
    page = client.get("/jogos/quem-e").text

    assert verdict["solved"]
    assert page.count('class="slot"') == len(frozen.clubes)


def test_api_gives_up_with_or_without_guesses(game) -> None:
    data, jogador = today()
    other = next(j for j in data.jogadores if j.wikidata != jogador.wikidata)

    early = game.post(f"{API}/geral/8", json={"palpites": [], "desistiu": True}).json()
    later = game.post(
        f"{API}/geral/8", json={"palpites": [other.wikidata], "desistiu": True}
    ).json()

    for verdict in (early, later):
        assert verdict["over"] and not verdict["solved"]
        assert verdict["reveal"]["nome"] == jogador.nome


def test_api_needs_a_guess_unless_giving_up(game) -> None:
    assert game.post(f"{API}/geral/8", json={"palpites": []}).status_code == 422


def test_game_page_has_a_give_up_button(game) -> None:
    page = game.get("/jogos/quem-e").text

    assert 'id="qe-give-up"' in page and ">Desistir<" in page


def selector(page: str) -> set[str]:
    import json

    raw = page.split('id="qe-player-data">')[1].split("</script>")[0]
    return {p["id"] for p in json.loads(raw)}


def test_team_only_players_are_picked_only_in_their_edition(game) -> None:
    data = load()
    abc_only = {j.wikidata for j in data.jogadores if j.edicoes == ("abc",)}
    assert abc_only

    assert not selector(game.get("/jogos/quem-e").text) & abc_only
    assert abc_only <= selector(game.get("/jogos/quem-e/abc").text)
