from datetime import timedelta

import pytest
from webkit import AUTH, NOW, SECRET

from geral.web.bolao import BolaoStore
from geral.web.tokens import make_token, read_token

KICKOFF = NOW + timedelta(hours=3)


@pytest.fixture
def bolao(store) -> BolaoStore:
    bolao = BolaoStore(store.path)
    bolao.upsert_match("vasco", "m1", "Bahia", home=False, kickoff=KICKOFF)
    return bolao


def member(store, bolao, email: str, nickname: str | None = None, teams=("vasco",)) -> str:
    store.request(email, list(teams), NOW)
    store.confirm(email, NOW)
    if nickname:
        bolao.set_nickname(email, nickname)
    return make_token(SECRET, "bet", email, NOW)


def bet(client, token: str, score: str = "2-1", team: str = "vasco", match: str = "m1", **extra):
    return client.post("/palpite", data={"t": token, "c": team, "m": match, "p": score, **extra})


def ask(client, token: str, score: str = "2-1", team: str = "vasco", match: str = "m1"):
    return client.get("/palpite", params={"t": token, "c": team, "m": match, "p": score})


def test_bet_get_does_not_record(client, store, bolao) -> None:
    token = member(store, bolao, "ana@x.com", "Ana")

    response = ask(client, token)

    assert response.status_code == 200
    assert "Vasco 2 x 1 Bahia" in response.text and "Confirmar" in response.text
    assert bolao.bet("ana@x.com", "vasco", "m1") is None


def test_bet_post_records_and_overwrites_before_kickoff(client, store, bolao) -> None:
    token = member(store, bolao, "ana@x.com", "Ana")

    assert bet(client, token, "1-0").status_code == 200
    response = bet(client, token, "3-1")

    assert response.status_code == 200 and "Palpite registrado" in response.text
    assert bolao.bet("ana@x.com", "vasco", "m1") == (3, 1)


def test_other_score_form_posts_two_fields(client, store, bolao) -> None:
    token = member(store, bolao, "ana@x.com", "Ana")

    form = client.get("/palpite", params={"t": token, "c": "vasco", "m": "m1"})
    data = {"t": token, "c": "vasco", "m": "m1", "ours": "5", "theirs": "0"}
    response = client.post("/palpite", data=data)

    assert 'name="ours"' in form.text and 'name="theirs"' in form.text
    assert response.status_code == 200
    assert bolao.bet("ana@x.com", "vasco", "m1") == (5, 0)


def test_bet_after_kickoff_is_rejected(client, store, bolao, clock) -> None:
    token = member(store, bolao, "ana@x.com", "Ana")
    bet(client, token, "1-0")
    clock.now = KICKOFF

    response = bet(client, token, "3-1")
    closed = ask(client, token, "3-1")

    assert response.status_code == 409
    assert bolao.bet("ana@x.com", "vasco", "m1") == (1, 0)
    assert closed.status_code == 200 and "Bolão fechado" in closed.text
    assert "Vasco 1 x 0 Bahia" in closed.text


def test_bet_token_cannot_bet_for_someone_else(client, store, bolao) -> None:
    member(store, bolao, "ana@x.com", "Ana")
    bia = member(store, bolao, "bia@x.com", "Bia")

    bet(client, bia, "0-0", email="ana@x.com")
    forged = bet(client, make_token("other", "bet", "ana@x.com", NOW))
    unsubscribe_token = bet(client, make_token(SECRET, "unsubscribe", "ana@x.com", NOW))

    assert bolao.bet("ana@x.com", "vasco", "m1") is None
    assert bolao.bet("bia@x.com", "vasco", "m1") == (0, 0)
    assert forged.status_code == unsubscribe_token.status_code == 400


def test_bet_requires_following_that_team(client, store, bolao) -> None:
    token = member(store, bolao, "ana@x.com", "Ana", teams=("abc",))

    response = bet(client, token)

    assert response.status_code == 403 and "Almirante News" in response.text
    assert bolao.bet("ana@x.com", "vasco", "m1") is None


def test_first_bet_requires_unique_nickname(client, store, bolao) -> None:
    member(store, bolao, "ana@x.com", "Ana")
    token = member(store, bolao, "bia@x.com")

    form = ask(client, token)
    without = bet(client, token)
    taken = bet(client, token, nickname="ANA")
    ok = bet(client, token, nickname="Bia")

    assert 'name="nickname"' in form.text
    assert without.status_code == 409 and taken.status_code == 409
    assert 'name="nickname"' in taken.text
    assert ok.status_code == 200 and bolao.nickname("bia@x.com") == "Bia"


@pytest.mark.parametrize("nickname", ["ab", "x" * 21, "   "])
def test_nickname_length_is_checked(client, store, bolao, nickname) -> None:
    token = member(store, bolao, "bia@x.com")

    assert bet(client, token, nickname=nickname).status_code == 409
    assert bolao.bet("bia@x.com", "vasco", "m1") is None


def test_unsubscribed_cannot_bet(client, store, bolao) -> None:
    token = member(store, bolao, "ana@x.com", "Ana")
    store.leave_all("ana@x.com", NOW)

    response = bet(client, token)

    assert response.status_code == 403 and "inscrição inativa" in response.text.lower()
    assert bolao.bet("ana@x.com", "vasco", "m1") is None


@pytest.mark.parametrize("score", ["9-10", "abc", "-1-0", "2", "2-1-0", ""])
def test_bet_rejects_malformed_score(client, store, bolao, score) -> None:
    token = member(store, bolao, "ana@x.com", "Ana")

    assert bet(client, token, score).status_code == 400
    assert ask(client, token, score).status_code in (200, 400)  # no score: "outro placar"
    assert bolao.bet("ana@x.com", "vasco", "m1") is None


def test_unknown_match_or_team_is_404(client, store, bolao) -> None:
    token = member(store, bolao, "ana@x.com", "Ana")

    assert ask(client, token, "1-0", match="nope").status_code == 404
    assert bet(client, token, "1-0", match="nope").status_code == 404
    assert bet(client, token, "1-0", team="xyz").status_code == 404


def test_nickname_is_escaped(client, store, bolao) -> None:
    # The form refuses markup now, but nicknames imported from an older app never went through it.
    token = member(store, bolao, "ana@x.com")
    bolao.set_nickname("ana@x.com", "<b>Ana</b>")
    bet(client, token)

    page = client.get("/bolao/vasco", params={"t": token})

    assert "&lt;b&gt;Ana&lt;/b&gt;" in page.text and "<b>Ana</b>" not in page.text


def test_ranking_highlights_the_reader(client, store, bolao) -> None:
    ana = member(store, bolao, "ana@x.com", "Ana")
    bia = member(store, bolao, "bia@x.com", "Bia")
    bet(client, ana, "2-1")
    bet(client, bia, "0-0")
    bolao.summary("vasco", "m1", (2, 1), persist=True)

    page = client.get("/bolao/vasco", params={"t": bia})
    anonymous = client.get("/bolao/vasco")

    assert page.status_code == anonymous.status_code == 200
    assert "Almirante News" in page.text
    assert page.text.index("Ana") < page.text.index("Bia")
    assert 'class="me"' in page.text and 'class="me"' not in anonymous.text
    assert "ana@x.com" not in page.text
    assert client.get("/bolao/xyz").status_code == 404


MATCH = {"opponent": "Bahia", "home": True, "kickoff": KICKOFF.isoformat()}
API = "/api/teams/vasco/bolao/matches"


def test_api_bolao_requires_token(client) -> None:
    assert client.put(f"{API}/m2", json=MATCH).status_code == 401
    assert client.get(f"{API}/m1/summary?ours=1&theirs=0").status_code == 401
    result = {"our_goals": 1, "their_goals": 0}
    assert client.put(f"{API}/m1/result", json=result).status_code == 401


def test_subscribers_carry_bet_token(client, store, bolao) -> None:
    member(store, bolao, "ana@x.com")

    [row] = client.get("/api/subscribers", params={"team": "vasco"}, headers=AUTH).json()

    assert read_token(SECRET, "bet", row["bet_token"], NOW) == "ana@x.com"


def test_register_match_then_report_result(client, store, bolao) -> None:
    token = member(store, bolao, "ana@x.com", "Ana")
    assert client.put(f"{API}/m2", json=MATCH, headers=AUTH).status_code == 204
    bet(client, token, "2-0", match="m2")

    response = client.put(f"{API}/m2/result", json={"our_goals": 2, "their_goals": 0}, headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["exact"] == ["Ana"]
    assert body["top"][0] == {"nickname": "Ana", "points": 5, "exact": 1}
    assert bolao.match("vasco", "m2").opponent == "Bahia"


def test_result_for_unknown_match_or_team_is_404(client, bolao) -> None:
    result = {"our_goals": 1, "their_goals": 0}

    response = client.put(f"{API}/nope/result", json=result, headers=AUTH)
    summary = client.get(f"{API}/nope/summary?ours=1&theirs=0", headers=AUTH)
    team = client.put("/api/teams/xyz/bolao/matches/m2", json=MATCH, headers=AUTH)

    assert response.status_code == summary.status_code == team.status_code == 404
    assert bolao.match("vasco", "nope") is None


def test_summary_preview_does_not_persist(client, store, bolao) -> None:
    token = member(store, bolao, "ana@x.com", "Ana")
    bet(client, token, "1-0")

    response = client.get(f"{API}/m1/summary?ours=1&theirs=0", headers=AUTH)

    assert response.status_code == 200 and response.json()["exact"] == ["Ana"]
    assert bolao.match("vasco", "m1").our_goals is None


@pytest.mark.parametrize("nickname", ["x\nbit.ly/golpe", "bit.ly/golpe", "ana<script>", "a://b"])
def test_nickname_rejects_links_and_line_breaks(client, store, bolao, nickname) -> None:
    token = member(store, bolao, "bia@x.com")

    assert bet(client, token, nickname=nickname).status_code == 409
    assert bolao.nickname("bia@x.com") is None


@pytest.mark.parametrize("nickname", ["Zé do Rádio", "D'Ávila", "Fla-Flu 81", "joão_2"])
def test_nickname_accepts_names(client, store, bolao, nickname) -> None:
    token = member(store, bolao, "bia@x.com")

    assert bet(client, token, nickname=nickname).status_code == 200


def test_match_kickoff_without_timezone_is_refused(client) -> None:
    naive = {"opponent": "Bahia", "home": True, "kickoff": "2026-11-15T21:30:00"}

    assert client.put(f"{API}/m3", json=naive, headers=AUTH).status_code == 422
