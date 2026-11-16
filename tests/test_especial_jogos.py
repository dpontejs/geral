"""`geral especial-jogos`: the special edition that presents the games, one e-mail per active
person (whatever teams they follow), never twice."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from typer.testing import CliRunner

import geral.__main__ as cli
from geral.config import get_settings
from geral.send.resend_sender import RESEND_BATCH_URL
from geral.web import especial
from geral.web.store import SubscriberStore
from geral.web.tokens import read_token

WHEN = datetime(2026, 11, 10, 12, tzinfo=UTC)
STATIC = Path(cli.__file__).parent / "static" / "geral"


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
    monkeypatch.chdir(tmp_path)
    store = SubscriberStore(path)
    for email, teams in {
        "vasco@x.com": ["vasco"],
        "two@x.com": ["vasco", "palmeiras"],
        "geral@x.com": ["geral"],
    }.items():
        store.request(email, teams, WHEN)
        store.confirm(email, WHEN)
    store.request("pending@x.com", ["vasco"], WHEN)  # never confirmed
    return store


def run(*args: str):
    return CliRunner().invoke(cli.app, ["especial-jogos", *args])


def emails(route) -> list[dict]:
    return [e for call in route.calls for e in json.loads(call.request.content)]


def ok(request: httpx.Request) -> httpx.Response:
    batch = json.loads(request.content)
    return httpx.Response(200, json={"data": [{"id": f"id{i}"} for i in range(len(batch))]})


@respx.mock
def test_without_send_only_counts_and_saves_a_preview(db, tmp_path) -> None:
    route = respx.post(RESEND_BATCH_URL)

    result = run()

    assert result.exit_code == 0, result.output
    assert not route.called
    assert "Faltam receber: 3" in result.output
    assert (tmp_path / "out" / "especial-jogos.html").exists()


@respx.mock
def test_send_gives_each_active_person_one_email_from_the_geral(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)

    result = run("--send")

    assert result.exit_code == 0, result.output
    sent = emails(route)
    assert sorted(e["to"][0] for e in sent) == ["geral@x.com", "two@x.com", "vasco@x.com"]
    assert {e["from"] for e in sent} == {"Geral <geral@geral.test>"}
    assert {e["subject"] for e in sent} == {especial.SUBJECT}


@respx.mock
def test_every_email_carries_its_own_unsubscribe_link(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)

    run("--send")

    for email in emails(route):
        url = email["headers"]["List-Unsubscribe"].strip("<>")
        token = parse_qs(urlparse(url).query)["token"][0]
        assert read_token("s3cret", "unsubscribe", token, datetime.now(UTC)) == email["to"][0]
        assert url in email["text"] and url in email["html"]


def test_the_email_presents_the_four_games_with_images_on_the_public_page(db) -> None:
    html, text = especial.render(get_settings())

    for name, path in [
        ("Craque do dia", "craque-do-dia"),
        ("Onde jogou?", "onde-jogou"),
        ("Quem é?", "quem-e"),
        ("Jogo da velha", "velha"),
    ]:
        assert name in html and name in text
        assert f"https://geral.test/jogos/{path}" in html
        assert f"https://geral.test/jogos/{path}" in text
    images = re.findall(r'src="https://geral\.test/static/geral/([^"]+)"', html)
    assert {"logo-email.png", "meio-campo.png"} <= set(images)
    assert len([i for i in images if i.startswith("jogos-")]) == 4
    for image in images:  # every image is served by the page
        assert (STATIC / image).is_file(), image


@respx.mock
def test_a_second_run_sends_nothing_again(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)
    run("--send")

    result = run("--send")

    assert result.exit_code == 0, result.output
    assert len(emails(route)) == 3
    assert "Faltam receber: 0" in result.output


@respx.mock
def test_a_failed_send_is_not_marked_and_goes_out_on_the_next_run(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(return_value=httpx.Response(422, json={}))

    assert run("--send").exit_code != 0

    route.reset()
    route.mock(side_effect=ok)
    run("--send")
    assert len(emails(route)) == 3


@respx.mock
def test_to_sends_to_that_address_only_and_marks_nobody(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)

    result = run("--to", "me@x.com")

    assert result.exit_code == 0, result.output
    assert [e["to"][0] for e in emails(route)] == ["me@x.com"]
    assert db.announced(especial.NAME) == set()
