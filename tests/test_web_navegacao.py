"""Finding the way around: the edition page in the site's frame, home links, the games page."""

import re
from datetime import UTC, datetime

import pytest
from webkit import make_client, publish

DAY = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)  # puzzle #8 of every game
GAMES = ["craque-do-dia", "onde-jogou", "quem-e"]


@pytest.fixture
def site(store, mailer, clock):
    clock.now = DAY
    return make_client(store, mailer, clock)


def test_edition_page_wears_the_site_and_embeds_the_newsletter(client) -> None:
    publish(client, "abc", "Elefante News — Notícias — 09/11/2026: ABC acerta com goleiro")

    page = client.get("/t/abc").text

    assert "<header>" in page and "Elefante News" in page
    assert "ABC acerta com goleiro" in page
    assert '<iframe class="edition-frame" src="/t/abc/edicao"' in page
    assert 'href="/">← Voltar para a Geral</a>' in page


def test_raw_edition_opens_its_links_outside_the_frame(client) -> None:
    publish(client, "abc")

    raw = client.get("/t/abc/edicao")

    assert raw.status_code == 200 and '<base target="_top">' in raw.text


def test_raw_edition_of_a_team_without_one_is_404(client) -> None:
    assert client.get("/t/vasco/edicao").status_code == 404


@pytest.mark.parametrize(
    "path", ["/jogos", "/jogos/quem-e", "/jogos/craque-do-dia/geral/2", "/pedir", "/bolao/vasco"]
)
def test_inner_pages_link_back_home_from_the_header(site, path) -> None:
    page = site.get(path).text

    assert '<a href="/">Início</a>' in page.split("</header>")[0]


def test_home_needs_no_link_to_itself_and_its_header_leads_to_the_games(site) -> None:
    page = site.get("/").text
    header = page.split("</header>")[0]

    assert '<a href="/">Início</a>' not in header
    assert '<a href="/jogos">Joguinhos</a>' in header
    assert 'href="/jogos">Todos os joguinhos →</a>' in page  # from the break section


def test_games_page_shows_every_game_with_todays_number_and_editions(site) -> None:
    page = site.get("/jogos")

    assert page.status_code == 200
    for path in GAMES:
        assert f'href="/jogos/{path}"' in page.text
        assert f'href="/jogos/{path}/vasco"' in page.text
    assert page.text.count("#8") >= 3


def test_game_pages_switch_between_games_keeping_the_edition(site) -> None:
    page = site.get("/jogos/quem-e/vasco").text
    tabs = page.split('class="game-tabs"')[1].split("</nav>")[0]

    assert 'href="/jogos/onde-jogou/vasco"' in tabs
    assert 'href="/jogos/craque-do-dia/vasco"' in tabs
    assert 'href="/jogos/quem-e/vasco" aria-current="page"' in tabs
    assert 'href="/jogos">Todos os joguinhos' in tabs


def test_game_tabs_on_the_geral_edition_lead_to_each_games_geral(site) -> None:
    page = site.get("/jogos/quem-e").text
    tabs = page.split('class="game-tabs"')[1].split("</nav>")[0]

    assert 'href="/jogos/onde-jogou"' in tabs and 'href="/jogos/craque-do-dia"' in tabs


def test_edition_page_headline_drops_the_names_already_on_the_page(client) -> None:
    publish(client, "geral", "Geral — Edição geral — 09/11/2026: Flamengo lidera")

    page = client.get("/t/geral").text

    assert "<b>09/11/2026: Flamengo lidera</b>" in page


def section(page: str, marker: str) -> str:
    return page.split(marker)[1].split("</section>")[0]


def test_home_break_holds_only_the_games(site) -> None:
    intervalo = section(site.get("/").text, 'id="intervalo"')

    for path in GAMES:
        assert f'href="/jogos/{path}"' in intervalo
    assert "Edição geral" not in intervalo and 'href="/pedir"' not in intervalo


def test_general_edition_sits_with_the_torcidas_and_the_request_has_its_own_strip(site) -> None:
    torcidas = section(site.get("/").text, 'id="torcidas"')

    assert "<h3>Edição geral</h3>" in torcidas
    assert '<a class="pedir-strip" href="/pedir">' in torcidas


def test_games_page_cards_are_one_link_each_that_lights_up(site) -> None:
    page = site.get("/jogos").text

    for path in GAMES:
        assert f'<a class="hub-main" href="/jogos/{path}">' in page
    assert ".hub-card:hover" in site.get("/static/geral/jogos.css").text


def test_ticket_team_buttons_share_one_size(site) -> None:
    assert re.search(r"\.picks \{[^}]*grid-template-columns: repeat\(auto-fill", site.get("/").text)


def test_scripts_and_styles_carry_a_version_so_browsers_drop_old_copies(site) -> None:
    page = site.get("/jogos/quem-e").text

    css = re.search(r'href="/static/geral/jogos\.css\?v=([0-9a-f]{8})"', page)
    js = re.search(r'src="/static/geral/quem-e\.js\?v=([0-9a-f]{8})"', page)
    assert css and js and css.group(1) == js.group(1)
    assert site.get(f"/static/geral/jogos.css?v={css.group(1)}").status_code == 200


def test_text_boxes_span_the_board_below_them(site) -> None:
    home = site.get("/").text
    css = site.get("/static/geral/jogos.css").text

    assert re.search(r"\.hero \.lead \{[^}]*max-width: none", home)
    assert re.search(r"\.jogo \.lead \{[^}]*max-width: none", css)
