import pytest
from webkit import NOW, publish

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
