from datetime import UTC, datetime

import pytest
from webkit import make_client

from geral.games.craque import by_number, load_lists, pool

DAY = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)  # puzzle #9 (launch 2026-11-11)
API = "/api/jogos/craque-do-dia"


@pytest.fixture
def game(store, mailer, clock):
    clock.now = DAY
    return make_client(store, mailer, clock)


def today(edition="geral", number=9):
    return by_number(pool(load_lists(), edition), number)


def test_game_page_shows_the_length_not_the_name(game) -> None:
    craque = today()

    page = game.get("/jogos/craque-do-dia")

    assert page.status_code == 200 and "#9" in page.text
    assert page.text.count('class="tile"') == len(craque.answer)
    assert craque.completo not in page.text and craque.fato not in page.text


def test_team_edition_page(game) -> None:
    page = game.get("/jogos/craque-do-dia/vasco")

    assert page.status_code == 200
    assert page.text.count('class="tile"') == len(today("vasco").answer)


@pytest.mark.parametrize("edition", ["abc", "xyz"])  # abc: list still a draft
def test_unknown_or_draft_edition_is_404(game, edition) -> None:
    assert game.get(f"/jogos/craque-do-dia/{edition}").status_code == 404
    assert game.post(f"{API}/{edition}/9", json={"guesses": ["ZICO"]}).status_code == 404


def test_api_judges_guesses(game) -> None:
    craque = today()

    miss = game.post(f"{API}/geral/9", json={"guesses": ["Z" * len(craque.answer)]}).json()
    hit = game.post(f"{API}/geral/9", json={"guesses": [craque.nome.lower()]}).json()

    assert miss["solved"] is False and miss["reveal"] is None
    assert len(miss["rows"][0]) == len(craque.answer)
    assert hit["solved"] is True and hit["reveal"]["completo"] == craque.completo


@pytest.mark.parametrize("guesses", [[], ["ABCDEFGHIJKLMNOPQRSTU"], "ZICO"])
def test_api_rejects_malformed_bodies(game, guesses) -> None:
    assert game.post(f"{API}/geral/9", json={"guesses": guesses}).status_code == 422


def test_api_rejects_wrong_length_or_symbols(game) -> None:
    n = len(today().answer)

    for bad in ["A" * (n + 1), "1" + "A" * (n - 1), " " * n]:
        assert game.post(f"{API}/geral/9", json={"guesses": [bad]}).status_code == 422, bad
    assert game.post(f"{API}/geral/9", json={"guesses": ["A" * n] * 7}).status_code == 422


@pytest.mark.parametrize("number", [0, 10])
def test_api_rejects_future_or_zero_puzzle(game, number) -> None:
    n = len(today().answer)

    assert game.post(f"{API}/geral/{number}", json={"guesses": ["A" * n]}).status_code == 404


def test_portal_links_the_word_game(game) -> None:
    assert 'href="/jogos/craque-do-dia"' in game.get("/").text
