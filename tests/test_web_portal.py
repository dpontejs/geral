import re

import pytest
from webkit import AUTH, NOW, publish

from geral.send.resend_sender import UNSUBSCRIBE_PLACEHOLDER


def test_portal_lists_catalog_teams_with_last_edition_and_counts(client, store) -> None:
    publish(client, "nautico", "Timbu News — Pós-jogo — 08/11/2026: Náutico perde para o CRB")
    store.request("ana@example.com", ["nautico", "vasco"], NOW)
    store.confirm("ana@example.com", NOW)

    page = client.get("/").text

    for name in ("Almirante News", "Porco News", "Elefante News", "Timbu News"):
        assert name in page
    assert 'src="/static/nautico/icon-512.png"' in page
    assert "Náutico perde para o CRB" in page and "Pós-jogo — 08/11/2026" in page
    assert 'href="/t/nautico"' in page
    assert "1 na Geral" in page
    assert 'name="team" value="vasco"' in page


def test_portal_scoreboard_ranks_teams_by_subscribers(client, store) -> None:
    store.request("ana@example.com", ["nautico", "vasco"], NOW)
    store.confirm("ana@example.com", NOW)
    store.request("bia@example.com", ["nautico"], NOW)
    store.confirm("bia@example.com", NOW)

    page = client.get("/").text
    board = page.split('id="placar"', 1)[1].split("</section>", 1)[0]

    rows = re.findall(r'class="name">([^<]+)</span><span class="n">(\d+)<', board)
    assert rows[:2] == [("Timbu", "2"), ("Almirante", "1")]
    assert {name for name, _ in rows} == {"Timbu", "Almirante", "Porco", "Elefante", "Urubu"}


def test_portal_scoreboard_keeps_the_names_in_lamp_yellow(client) -> None:
    board = client.get("/").text.split('id="placar"', 1)[1].split("</section>", 1)[0]

    assert 'class="dot"' not in board and 'class="bar"' not in board
    assert "--team-lamp" not in board and '<li><span class="name">' in board


def test_portal_scoreboard_clock_shows_brasilia_time(client) -> None:
    page = client.get("/").text

    # the colon is two lamps drawn in CSS: the font's colon looked like a "+"
    assert (
        '<time class="clock" datetime="2026-11-10T09:00-03:00" aria-label="09:00">'
        '09<span class="colon" aria-hidden="true"></span>00</time>'
    ) in page


def test_portal_scoreboard_plays_the_goal_animation(client) -> None:
    page = client.get("/").text

    assert '<svg class="lance"' in page


def test_portal_without_edition_says_first_edition_soon(client) -> None:
    page = client.get("/").text

    assert "Primeira edição em breve" in page
    assert 'href="/t/' not in page


def test_portal_keeps_email_and_picks_after_an_error(client) -> None:
    page = client.post("/subscribe", data={"email": "ruim", "team": ["abc"]}).text

    assert 'value="ruim"' in page
    assert 'value="abc" checked' in page


def test_team_page_shows_latest_edition_without_personal_links(client) -> None:
    publish(client, "abc", "Elefante News — Notícias — 09/11/2026: ABC acerta com goleiro")

    page = client.get("/t/abc")

    assert page.status_code == 200
    assert UNSUBSCRIBE_PLACEHOLDER not in page.text
    assert 'href="https://geral.test/"' in page.text


@pytest.mark.parametrize("slug", ["vasco", "xyz"])
def test_team_page_unknown_or_empty_is_404(client, slug) -> None:
    page = client.get(f"/t/{slug}")

    assert page.status_code == 404 and "Voltar para a Geral" in page.text


@pytest.mark.parametrize(
    "path",
    ["geral/icon-512.png", "geral/logo-email.png", "vasco/og-image.png", "abc/logo-email.png"],
)
def test_static_brand_files_are_served(client, path) -> None:
    response = client.get(f"/static/{path}")

    assert response.status_code == 200 and response.headers["content-type"] == "image/png"


def test_favicon_points_to_the_geral_icon(client) -> None:
    response = client.get("/favicon.ico", follow_redirects=False)

    assert response.headers["location"] == "/static/geral/icon-512.png"


def test_portal_explains_the_name(client) -> None:
    page = client.get("/").text

    assert 'id="por-que-geral"' in page
    assert "Por que Geral?" in page
    assert "Maracanã" in page and "geraldino" in page


def test_team_page_drops_the_bet_card(client) -> None:
    from geral.send.resend_sender import BET_TOKEN_PLACEHOLDER

    html = f"<!--bolao--><a href='/palpite?t={BET_TOKEN_PLACEHOLDER}'>2x1</a><!--/bolao-->"
    edition = {"subject": "S", "html": html + UNSUBSCRIBE_PLACEHOLDER, "text": "t"}
    client.put("/api/teams/vasco/latest-edition", json=edition, headers=AUTH)

    page = client.get("/t/vasco").text

    assert "palpite" not in page and BET_TOKEN_PLACEHOLDER not in page


def test_unlisted_team_is_hidden_from_portal_and_signup(store, mailer, clock) -> None:
    # A team moving in (as the Urubu News did) stays hidden until its switch.
    from webkit import make_client

    from geral.teams import load_teams

    catalog = load_teams()
    catalog["nautico"] = catalog["nautico"].model_copy(update={"listed": False})
    client = make_client(store, mailer, clock, teams=catalog)

    page = client.get("/").text
    signup = client.post("/subscribe", data={"email": "ana@x.com", "team": ["nautico"]})

    assert "Timbu News" not in page and 'value="nautico"' not in page
    assert signup.status_code == 400 and store.get("ana@x.com") is None


def test_portal_clock_never_breaks_between_hours_and_minutes(client) -> None:
    # The drawn colon is an element of its own: without nowrap a narrow column split "17:04".
    page = client.get("/").text

    assert re.search(r"\.clock \{[^}]*white-space: nowrap", page)
