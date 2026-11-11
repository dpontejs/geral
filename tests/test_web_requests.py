"""Pedido de time: who can't find their team asks for it (docs/features/pedido-de-time.md)."""

import re

import pytest
from fastapi.testclient import TestClient
from webkit import AUTH

from geral.web.mailer import MailError
from geral.web.team_requests import TeamRequestStore, team_key


def ask(client: TestClient, team: str, email: str = "", **extra):
    return client.post("/pedir", data={"team": team, "email": email, **extra})


def votes(store) -> dict[str, int]:
    requests = TeamRequestStore(store.path)
    return {r.name: r.votes for r in requests.top(50, min_votes=1)}


def from_ip(client: TestClient, ip: str) -> TestClient:
    return TestClient(client.app, base_url="https://geral.test", client=(ip, 50000))


def test_team_key_ignores_case_accents_punctuation_and_spaces() -> None:
    assert team_key("Sampaio Corrêa") == team_key("sampaio  correa!") == "sampaio correa"


def test_request_counts_one_vote_per_network(client, store) -> None:
    ask(client, "Sampaio Corrêa", "ana@example.com")
    ask(client, "Sampaio Corrêa", "bia@example.com")  # made-up e-mails do not add votes
    ask(client, "Sampaio Corrêa")

    assert votes(store) == {"Sampaio Corrêa": 1}


def test_ipv6_requests_count_once_per_64_block(client, store) -> None:
    ask(from_ip(client, "2001:db8:1:2::1"), "Remo")
    ask(from_ip(client, "2001:db8:1:2::ff"), "Remo")
    ask(from_ip(client, "2001:db8:1:3::1"), "Remo")

    assert votes(store) == {"Remo": 2}


def test_request_name_variants_share_a_vote_count(client, store) -> None:
    ask(from_ip(client, "10.0.0.1"), "Sampaio Corrêa")
    ask(from_ip(client, "10.0.0.2"), "Sampaio Corrêa")
    ask(from_ip(client, "10.0.0.3"), "sampaio correa")

    assert votes(store) == {"Sampaio Corrêa": 3}  # shown as the most typed form


def test_request_again_with_email_keeps_the_email(client, store) -> None:
    ask(client, "Remo")
    ask(client, "Remo", "ana@example.com")

    listed = client.get("/api/team-requests", headers=AUTH).json()
    assert listed == [{"key": "remo", "name": "Remo", "votes": 1, "emails": ["ana@example.com"]}]


def test_request_answer_shows_position_and_votes(client) -> None:
    ask(from_ip(client, "10.0.0.1"), "Remo")
    ask(from_ip(client, "10.0.0.2"), "Remo")

    page = ask(client, "Paysandu", "ana@example.com").text

    assert "Pedido anotado" in page
    assert "Paysandu" in page and "1 pedido" in page and "2º" in page
    assert "quando a torcida nascer" in page


def test_request_for_a_team_already_in_the_geral_points_to_it(client, store) -> None:
    for name in ("Vasco", "almirante news", "vasco"):
        page = ask(client, name, "ana@example.com")

        assert page.status_code == 200
        assert "Já tem!" in page.text and 'href="/t/vasco"' in page.text

    assert votes(store) == {}


def test_request_with_a_shared_nickname_counts_a_vote(client, store) -> None:
    # "Rubro-Negro" is the Flamengo's, the Sport's and the Vitória's: not a match.
    page = ask(client, "Rubro-Negro")

    assert "Pedido anotado" in page.text
    assert votes(store) == {"Rubro-Negro": 1}


def test_request_for_an_unlisted_catalog_team_points_to_it(store, mailer, clock) -> None:
    from webkit import make_client

    from geral.teams import load_teams

    teams = load_teams()
    teams["vasco"] = teams["vasco"].model_copy(update={"listed": False})
    page = ask(make_client(store, mailer, clock, teams=teams), "Vasco")

    assert "Já tem!" in page.text
    assert votes(store) == {}


def test_request_in_another_alphabet_gets_its_own_message(client, store) -> None:
    page = ask(client, "日本")

    assert page.status_code == 400
    assert "letras do nosso alfabeto" in page.text


def test_request_rejects_bad_name_and_email(client, store) -> None:
    assert ask(client, "X").status_code == 400
    assert ask(client, "a" * 41).status_code == 400
    assert ask(client, "<script>alert(1)</script>").status_code == 400
    assert ask(client, "Remo", "não-é-email").status_code == 400

    assert votes(store) == {}


def test_request_honeypot_counts_nothing(client, store) -> None:
    page = ask(client, "Remo", website="http://spam.example")

    assert page.status_code == 200
    assert votes(store) == {}


def test_request_rate_limit_per_ip(client) -> None:
    answers = [ask(client, f"Time {chr(65 + i)}").status_code for i in range(11)]

    assert answers[:10] == [200] * 10
    assert answers[10] == 429


def test_request_page_lists_top_requests_without_emails(client) -> None:
    for i in range(4):
        ask(from_ip(client, f"10.0.0.{i}"), "Remo", f"r{i}@example.com")
    for i in range(3):
        ask(from_ip(client, f"10.0.1.{i}"), "Paysandu", f"p{i}@example.com")
    ask(client, "Palavrão Qualquer")  # one vote: not shown in public

    page = client.get("/pedir").text

    assert re.search(r"Remo.*4 pedidos.*Paysandu.*3 pedidos", page, re.S)
    assert "Palavrão" not in page
    assert "example.com" not in page
    assert 'name="team"' in page and 'name="email"' in page and 'name="website"' in page


def test_api_team_requests_needs_token_and_lists_emails(client) -> None:
    ask(client, "Remo", "ana@example.com")
    ask(from_ip(client, "10.0.0.2"), "Remo")

    assert client.get("/api/team-requests").status_code == 401
    listed = client.get("/api/team-requests", headers=AUTH).json()
    assert listed == [{"key": "remo", "name": "Remo", "votes": 2, "emails": ["ana@example.com"]}]


def test_portal_card_links_to_request_page_with_top_request(client) -> None:
    page = client.get("/").text
    assert 'href="/pedir"' in page

    ask(client, "Remo")
    card = client.get("/").text.split('href="/pedir"', 1)[1].split("</a>", 1)[0]
    assert "Remo" not in card  # under 3 votes it stays out of the home

    for i in range(2, 4):
        ask(from_ip(client, f"10.0.0.{i}"), "Remo")
    card = client.get("/").text.split('href="/pedir"', 1)[1].split("</a>", 1)[0]
    assert "Remo" in card


# --- found by hand: one request, then "Ver os mais pedidos" looked empty ---------------------


def test_request_page_explains_the_list_while_no_team_has_three(client) -> None:
    ask(client, "Remo", "ana@example.com")

    page = client.get("/pedir").text

    assert "Nenhum time chegou a 3 pedidos ainda" in page


def test_request_answer_says_when_the_team_shows_up_in_the_list(client) -> None:
    page = ask(client, "Remo", "ana@example.com").text

    assert "aparece na lista dos mais pedidos quando juntar 3 pedidos" in page


# --- the owner hears about every new request --------------------------------------------------


@pytest.fixture
def notified(store, mailer, clock):
    from webkit import make_client

    return make_client(store, mailer, clock, NOTIFY_EMAIL="dono@example.com")


def test_new_request_notifies_the_owner(notified, mailer) -> None:
    ask(notified, "Remo", "ana@example.com")

    ((to, subject, text),) = mailer.notifications
    assert to == "dono@example.com"
    assert subject == "Pedido de time: Remo"
    assert "1 pedido" in text and "ana@example.com" in text


def test_repeated_request_does_not_notify_again(notified, mailer) -> None:
    ask(notified, "Remo")
    ask(notified, "Remo", "ana@example.com")

    assert len(mailer.notifications) == 1


def test_request_notification_failure_keeps_the_request(notified, mailer, store) -> None:
    def broken(to, subject, text):
        raise MailError("Resend is down")

    mailer.send_notification = broken

    assert ask(notified, "Remo").status_code == 200
    assert votes(store) == {"Remo": 1}
