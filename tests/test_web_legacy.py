"""Links of e-mails a single-team app (the Urubu News) already sent keep working in the Geral."""

from datetime import timedelta
from pathlib import Path

import pytest
from webkit import NOW, make_client

from geral.web.bolao import BolaoStore
from geral.web.tokens import make_token

OLD = "urubu-secret"
ANA = "ana@example.com"
STATIC = Path(__file__).parents[1] / "src" / "geral" / "static"


@pytest.fixture
def legacy(store, mailer, clock):
    return make_client(
        store,
        mailer,
        clock,
        LEGACY_TEAM="flamengo",
        LEGACY_SUBSCRIBE_SECRET=OLD,
        LEGACY_HOSTS="urubunews.test,flamengo.test",
    )


def follower(store, teams=("flamengo", "vasco")) -> None:
    store.request(ANA, list(teams), NOW)
    store.confirm(ANA, NOW)


def test_legacy_unsubscribe_token_leaves_flamengo_only(legacy, store) -> None:
    follower(store)
    token = make_token(OLD, "unsubscribe", ANA, NOW)

    page = legacy.get("/unsubscribe", params={"token": token})
    assert page.status_code == 200 and "Urubu News" in page.text
    assert store.teams_of(ANA) == ["flamengo", "vasco"]  # GET only asks

    legacy.post("/unsubscribe", params={"token": token})

    assert store.teams_of(ANA) == ["vasco"]


def test_legacy_one_click_post(legacy, store) -> None:
    follower(store, ["flamengo"])
    token = make_token(OLD, "unsubscribe", ANA, NOW)

    legacy.post("/unsubscribe", params={"token": token}, data={"List-Unsubscribe": "One-Click"})

    assert store.get(ANA).status == "unsubscribed"


def test_legacy_bet_link_without_team_bets_on_flamengo(legacy, store) -> None:
    follower(store, ["flamengo"])
    bolao = BolaoStore(store.path)
    bolao.upsert_match("flamengo", "m1", "Bahia", home=True, kickoff=NOW + timedelta(hours=3))
    bolao.set_nickname(ANA, "Ana")
    token = make_token(OLD, "bet", ANA, NOW)

    ask = legacy.get("/palpite", params={"t": token, "m": "m1", "p": "2-1"})
    legacy.post("/palpite", data={"t": token, "m": "m1", "p": "2-1"})

    assert ask.status_code == 200 and "Flamengo 2 x 1 Bahia" in ask.text
    assert bolao.bet(ANA, "flamengo", "m1") == (2, 1)


def test_legacy_ranking_link_goes_to_the_team_ranking(legacy) -> None:
    response = legacy.get("/bolao", params={"t": "TOKEN"}, follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/bolao/flamengo?t=TOKEN"


@pytest.mark.parametrize("name", ["logo-email.png", "icon-512.png", "og-image.png"])
def test_legacy_static_paths_serve_the_urubu_brand(legacy, name) -> None:
    response = legacy.get(f"/static/{name}")

    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.content == (STATIC / "flamengo" / name).read_bytes()


def test_legacy_host_root_redirects_to_geral(legacy) -> None:
    old = legacy.get("/", headers={"host": "urubunews.test"}, follow_redirects=False)
    new = legacy.get("/", follow_redirects=False)

    assert old.status_code == 301 and old.headers["location"] == "https://geral.test/"
    assert new.status_code == 200


def test_without_legacy_settings_old_links_are_invalid(client, store) -> None:
    follower(store)

    response = client.post(
        "/unsubscribe", params={"token": make_token(OLD, "unsubscribe", ANA, NOW)}
    )

    assert response.status_code == 400 and store.teams_of(ANA) == ["flamengo", "vasco"]
    assert client.get("/static/logo-email.png").status_code == 404
