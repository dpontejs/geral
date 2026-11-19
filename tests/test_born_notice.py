"""`geral avisar-pedido`: who asked for a team gets one e-mail when it is born, with its first
edition and the link to subscribe; nobody is subscribed and nobody gets it twice."""

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx
from typer.testing import CliRunner

import geral.__main__ as cli
from geral.config import get_settings
from geral.send.resend_sender import RESEND_BATCH_URL, UNSUBSCRIBE_PLACEHOLDER
from geral.web.store import SubscriberStore
from geral.web.team_requests import TeamRequestStore

NOW = datetime(2026, 11, 19, 18, tzinfo=UTC)
EDITION = (
    "<html><body><table><tr><td height=\"5\" style='x'></td></tr>"
    "<tr><td>O CSA venceu o CRB.</td></tr>"
    f"<tr><td><a href='{UNSUBSCRIBE_PLACEHOLDER}'>sair</a></td></tr></table></body></html>"
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "geral.db"
    for name, value in {
        "SUBSCRIBERS_DB": str(path),
        "RESEND_API_KEY": "re_test",
        "NEWSLETTER_FROM": "Geral <geral@geral.test>",
        "PUBLIC_URL": "https://geral.test",
        "SUBSCRIBE_SECRET": "s3cret",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    store = SubscriberStore(path)
    store.set_latest_edition(
        "csa", "Azulão News — Notícias — 19/11/2026: CSA vence", EDITION, "O CSA venceu.", NOW
    )
    requests = TeamRequestStore(path)
    requests.add("CSA", "net1", "Ana@X.com", NOW)
    requests.add("csa ", "net2", "bia@x.com", NOW)
    requests.add("CSA", "net3", None, NOW)  # a vote without e-mail
    requests.add("CSA", "net4", "sub@x.com", NOW)
    requests.add("Remo", "net1", "remo@x.com", NOW)  # another team
    store.request("sub@x.com", ["csa"], NOW)
    store.confirm("sub@x.com", NOW)  # already subscribed: nothing to tell
    yield store
    get_settings.cache_clear()


def notify(*args: str):
    return CliRunner().invoke(cli.app, ["avisar-pedido", "--team", "csa", *args])


def emails(route) -> list[dict]:
    return [e for call in route.calls for e in json.loads(call.request.content)]


def ok(request: httpx.Request) -> httpx.Response:
    batch = json.loads(request.content)
    return httpx.Response(200, json={"data": [{"id": f"id{i}"} for i in range(len(batch))]})


@respx.mock
def test_without_send_counts_who_is_waiting(db) -> None:
    route = respx.post(RESEND_BATCH_URL)

    result = notify()

    assert result.exit_code == 0, result.output
    assert "2 esperam o aviso da Azulão News" in result.output
    assert not route.called


@respx.mock
def test_send_gives_each_requester_the_first_edition_and_the_link_to_subscribe(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)

    result = notify("--send")

    assert result.exit_code == 0, result.output
    sent = emails(route)
    assert sorted(e["to"][0] for e in sent) == ["ana@x.com", "bia@x.com"]
    first = sent[0]
    assert first["from"] == "Azulão News <azulao@geral.test>"
    assert (
        first["subject"]
        == "Seu pedido foi atendido: Azulão News — Notícias — 19/11/2026: CSA vence"
    )
    assert "A Azulão News nasceu!" in first["html"] and "O CSA venceu o CRB." in first["html"]
    assert (
        "https://geral.test/t/csa" in first["html"] and "https://geral.test/t/csa" in first["text"]
    )
    assert "pediu o CSA" in first["text"]
    assert UNSUBSCRIBE_PLACEHOLDER not in first["html"]


@respx.mock
def test_a_second_run_sends_nothing_again(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)
    notify("--send")

    again = notify("--send")

    assert len(emails(route)) == 2
    assert "0 esperam" in again.output


@respx.mock
def test_without_an_edition_nothing_is_sent(db) -> None:
    db._run("DELETE FROM editions")
    route = respx.post(RESEND_BATCH_URL)

    result = notify("--send")

    assert result.exit_code == 1
    assert "primeira edição" in result.output
    assert not route.called


@respx.mock
def test_to_sends_a_test_to_that_address_only_and_marks_nobody(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)

    notify("--to", "dono@x.com")

    assert [e["to"][0] for e in emails(route)] == ["dono@x.com"]
    assert "2 esperam" in notify().output
