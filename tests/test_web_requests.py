"""Pedido de time: who can't find their team asks for it (docs/features/pedido-de-time.md)."""

import re

from fastapi.testclient import TestClient
from webkit import AUTH

from geral.web.team_requests import TeamRequestStore, team_key


def ask(client: TestClient, team: str, email: str = "", **extra):
    return client.post("/pedir", data={"team": team, "email": email, **extra})


def votes(store) -> dict[str, int]:
    requests = TeamRequestStore(store.path)
    return {r.name: r.votes for r in requests.top(50)}


def from_ip(client: TestClient, ip: str) -> TestClient:
    return TestClient(client.app, base_url="https://geral.test", client=(ip, 50000))


def test_team_key_ignores_case_accents_punctuation_and_spaces() -> None:
    assert team_key("Sampaio Corrêa") == team_key("sampaio  correa!") == "sampaio correa"


def test_request_counts_one_vote_per_person(client, store) -> None:
    ask(client, "Sampaio Corrêa", "ana@example.com")
    ask(client, "Sampaio Corrêa", "ANA@example.com ")

    assert votes(store) == {"Sampaio Corrêa": 1}


def test_request_name_variants_share_a_vote_count(client, store) -> None:
    ask(client, "Sampaio Corrêa", "ana@example.com")
    ask(client, "Sampaio Corrêa", "bia@example.com")
    ask(client, "sampaio correa", "caio@example.com")

    assert votes(store) == {"Sampaio Corrêa": 3}  # shown as the most typed form


def test_anonymous_request_counts_once_per_ip(client, store) -> None:
    ask(client, "Remo")
    ask(client, "Remo")
    ask(from_ip(client, "10.0.0.2"), "Remo")

    assert votes(store) == {"Remo": 2}


def test_request_again_with_email_keeps_the_email(client, store) -> None:
    ask(client, "Remo", "ana@example.com")
    ask(client, "Remo", "ana@example.com")

    listed = client.get("/api/team-requests", headers=AUTH).json()
    assert listed == [{"key": "remo", "name": "Remo", "votes": 1, "emails": ["ana@example.com"]}]


def test_request_answer_shows_position_and_votes(client) -> None:
    ask(client, "Remo", "ana@example.com")
    ask(client, "Remo", "bia@example.com")

    page = ask(client, "Paysandu", "ana@example.com").text

    assert "Pedido anotado" in page
    assert "Paysandu" in page and "1 pedido" in page and "2º" in page
    assert "quando a torcida nascer" in page


def test_request_for_a_team_already_in_the_geral_points_to_it(client, store) -> None:
    for name in ("Vasco", "almirante news", "Cruzmaltino"):
        page = ask(client, name, "ana@example.com")

        assert page.status_code == 200
        assert "Já tem!" in page.text and 'href="/t/vasco"' in page.text

    assert votes(store) == {}


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
    ask(client, "Remo", "ana@example.com")
    ask(client, "Remo", "bia@example.com")
    ask(client, "Paysandu", "caio@example.com")

    page = client.get("/pedir").text

    assert re.search(r"Remo.*2 pedidos.*Paysandu.*1 pedido", page, re.S)
    assert "example.com" not in page
    assert 'name="team"' in page and 'name="email"' in page and 'name="website"' in page


def test_api_team_requests_needs_token_and_lists_emails(client) -> None:
    ask(client, "Remo", "ana@example.com")
    ask(client, "Remo")

    assert client.get("/api/team-requests").status_code == 401
    listed = client.get("/api/team-requests", headers=AUTH).json()
    assert listed == [{"key": "remo", "name": "Remo", "votes": 2, "emails": ["ana@example.com"]}]


def test_portal_card_links_to_request_page_with_top_request(client) -> None:
    page = client.get("/").text
    assert 'href="/pedir"' in page

    ask(client, "Remo", "ana@example.com")

    card = client.get("/").text.split('href="/pedir"', 1)[1].split("</a>", 1)[0]
    assert "Remo" in card
