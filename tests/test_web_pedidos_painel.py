"""The owner's view of the team requests: a signed link in each request e-mail, top 5 inline."""

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from webkit import SECRET, make_client

from geral.web.tokens import make_token


def ask(client: TestClient, team: str, email: str = "", ip: str = "10.0.0.1"):
    voter = TestClient(client.app, base_url="https://geral.test", client=(ip, 50000))
    return voter.post("/pedir", data={"team": team, "email": email})


@pytest.fixture
def owner(store, mailer, clock):
    return make_client(store, mailer, clock, NOTIFY_EMAIL="dono@example.com")


def panel_link(mailer) -> str:
    text = mailer.notifications[-1][2]
    found = re.search(r"https://geral\.test(/pedidos\?t=[\w.\-]+)", text)
    assert found, text
    return found.group(1)


def test_request_email_lists_the_top_five(owner, mailer) -> None:
    for n, team in enumerate(["Remo", "Paysandu", "Sampaio", "Moto Club", "Tuna Luso", "Águia"]):
        for voter in range(6 - n):
            ask(owner, team, ip=f"10.0.{n}.{voter}")

    text = mailer.notifications[-1][2]

    assert re.search(
        r"1\. Remo · 6.*2\. Paysandu · 5.*3\. Sampaio · 4.*4\. Moto Club · 3.*5\. Tuna Luso · 2",
        text,
        re.S,
    )
    assert "Águia ·" not in text  # sixth: only on the page


def test_request_email_links_to_the_panel_instead_of_the_api(owner, mailer) -> None:
    ask(owner, "Remo")

    text = mailer.notifications[-1][2]

    assert "token da API" not in text
    assert panel_link(mailer).startswith("/pedidos?t=")


def test_panel_shows_every_request_without_addresses(owner, mailer, clock) -> None:
    ask(owner, "Remo", "ana@example.com")
    ask(owner, "Remo", "bia@example.com", ip="10.0.0.2")
    clock.now += timedelta(days=2)
    ask(owner, "Águia", ip="10.0.0.3")  # a single vote: hidden on /pedir, shown here
    last = clock.now.strftime("%d/%m")

    page = owner.get(panel_link(mailer))

    assert page.status_code == 200
    assert re.search(r"Remo.*2 pedidos.*2 esperam aviso.*Águia.*1 pedido\b", page.text, re.S)
    assert last in page.text
    assert "example.com" not in page.text
    assert '<meta name="robots" content="noindex">' in page.text
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "no-referrer"


def test_panel_without_a_valid_link_is_404(owner, mailer, clock) -> None:
    ask(owner, "Remo")
    good = panel_link(mailer)
    bet = make_token(SECRET, "bet", "dono@example.com", clock.now)
    other = make_token(SECRET, "team-requests", "outro@example.com", clock.now)

    assert owner.get("/pedidos").status_code == 404
    assert owner.get(good[:-3] + "xyz").status_code == 404
    assert owner.get(f"/pedidos?t={bet}").status_code == 404  # signed for another purpose
    assert owner.get(f"/pedidos?t={other}").status_code == 404  # not for the owner's address


def test_panel_link_expires_after_thirty_days(owner, mailer, clock) -> None:
    ask(owner, "Remo")
    link = panel_link(mailer)

    clock.now += timedelta(days=29)
    assert owner.get(link).status_code == 200
    clock.now += timedelta(days=2)
    assert owner.get(link).status_code == 404


def test_panel_is_404_when_no_owner_is_set(client, clock) -> None:
    token = make_token(SECRET, "team-requests", "", clock.now)

    assert client.get(f"/pedidos?t={token}").status_code == 404
