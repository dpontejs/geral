from datetime import UTC, datetime
from pathlib import Path

import pytest
from webkit import make_client

from geral.games.quanto_foi import by_number, convert, load_matches, pool

FIXTURES = Path(__file__).parent / "fixtures" / "brasileirao"
DAY = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)  # puzzle #9 (launch 2026-11-12)


@pytest.fixture
def matches(tmp_path):
    data = tmp_path / "brasileirao.csv"
    data.write_text(
        convert(
            (FIXTURES / "full.csv").read_text(encoding="utf-8"),
            (FIXTURES / "gols.csv").read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )
    return load_matches(data)


@pytest.fixture
def game(store, mailer, clock, matches):
    clock.now = DAY
    return make_client(store, mailer, clock, matches=matches)


def today(matches, club=None, number=9):
    return by_number(pool(matches, club), number).match


def test_game_page_shows_the_match_without_the_score(game, matches) -> None:
    match = today(matches)

    page = game.get("/jogos/quanto-foi")

    assert page.status_code == 200
    assert match.home in page.text and match.away in page.text and "#9" in page.text
    assert match.stadium in page.text
    for scorer in match.home_scorers + match.away_scorers:
        assert scorer not in page.text
    assert match.home_coach not in page.text or not match.home_coach


def test_team_edition_page(game, matches) -> None:
    match = today(matches, "Vasco")

    page = game.get("/jogos/quanto-foi/vasco")

    assert page.status_code == 200 and "Vasco" in page.text
    assert match.home in page.text and match.away in page.text


@pytest.mark.parametrize("edition", ["abc", "xyz"])
def test_unknown_or_abc_edition_is_404(game, edition) -> None:
    assert game.get(f"/jogos/quanto-foi/{edition}").status_code == 404
    assert (
        game.post(f"/api/jogos/quanto-foi/{edition}/9", json={"guesses": [[0, 0]]}).status_code
        == 404
    )


def test_api_judges_guesses(game, matches) -> None:
    match = today(matches)
    answer = [match.home_goals, match.away_goals]

    miss = game.post("/api/jogos/quanto-foi/geral/9", json={"guesses": [[9, 9]]}).json()
    hit = game.post("/api/jogos/quanto-foi/geral/9", json={"guesses": [[9, 9], answer]}).json()

    assert miss["solved"] is False and miss["reveal"] is None
    assert miss["rows"][0][0]["status"] in {"perto", "longe"}
    assert hit["solved"] is True and hit["reveal"]["home_goals"] == match.home_goals


def test_api_answers_past_puzzles(game) -> None:
    assert game.post("/api/jogos/quanto-foi/geral/3", json={"guesses": [[0, 0]]}).status_code == 200


@pytest.mark.parametrize("number", [0, 10])
def test_api_rejects_future_or_zero_puzzle(game, number) -> None:
    response = game.post(f"/api/jogos/quanto-foi/geral/{number}", json={"guesses": [[0, 0]]})

    assert response.status_code == 404


@pytest.mark.parametrize("guesses", [[], [[0, 0]] * 7, [[-1, 0]], [[21, 0]], [[1]], "2x1"])
def test_api_rejects_bad_guesses(game, guesses) -> None:
    response = game.post("/api/jogos/quanto-foi/geral/9", json={"guesses": guesses})

    assert response.status_code == 422


def test_day_follows_brasilia_time(game, clock) -> None:
    clock.now = datetime(2026, 11, 21, 1, 0, tzinfo=UTC)  # still the 20th in Brasília

    assert "#9" in game.get("/jogos/quanto-foi").text
    assert (
        game.post("/api/jogos/quanto-foi/geral/10", json={"guesses": [[0, 0]]}).status_code == 404
    )


def test_before_launch_the_first_puzzle_is_shown(game, clock) -> None:
    clock.now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

    assert "#1" in game.get("/jogos/quanto-foi").text


def test_portal_links_the_game(game) -> None:
    page = game.get("/").text

    assert 'href="/jogos/quanto-foi"' in page
    assert "7 a 0" not in page
