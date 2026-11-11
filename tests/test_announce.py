"""`geral announce`: one e-mail per subscriber about the Geral, a text for those who came from
the Urubu News and another for everyone else; a second run sends nothing again."""

import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from typer.testing import CliRunner

import geral.__main__ as cli
from geral.config import get_settings
from geral.send.resend_sender import RESEND_BATCH_URL
from geral.web.store import SubscriberStore
from geral.web.tokens import read_token

BEFORE_MOVE = datetime(2026, 10, 20, 12, tzinfo=UTC)
AFTER_MOVE = datetime(2026, 11, 11, 16, tzinfo=UTC)
CUTOFF = "2026-11-11T15:00:00+00:00"


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "geral.db"
    for name, value in {
        "SUBSCRIBERS_DB": str(path),
        "RESEND_API_KEY": "re_test",
        "NEWSLETTER_FROM": "Geral <geral@geral.test>",
        "PUBLIC_URL": "https://geral.test",
        "SUBSCRIBE_SECRET": "s3cret",
        "LEGACY_TEAM": "flamengo",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    store = SubscriberStore(path)

    def follow(email: str, teams: list[str], when: datetime) -> None:
        store.request(email, teams, when)
        store.confirm(email, when)

    follow("urubu@x.com", ["flamengo"], BEFORE_MOVE)  # came with the import
    follow("both@x.com", ["vasco"], BEFORE_MOVE)
    follow("both@x.com", ["flamengo"], BEFORE_MOVE)  # Geral reader who also came from the Urubu
    follow("geral@x.com", ["vasco", "palmeiras"], BEFORE_MOVE)
    follow("newfla@x.com", ["flamengo", "abc"], AFTER_MOVE)  # joined the Flamengo on the Geral
    store.request("pending@x.com", ["vasco"], AFTER_MOVE)  # never confirmed
    return store


def announce(*args: str):
    return CliRunner().invoke(cli.app, ["announce", "--moved-in-before", CUTOFF, *args])


def emails(route) -> list[dict]:
    return [e for call in route.calls for e in json.loads(call.request.content)]


def ok(request: httpx.Request) -> httpx.Response:
    batch = json.loads(request.content)
    return httpx.Response(200, json={"data": [{"id": f"id{i}"} for i in range(len(batch))]})


@respx.mock
def test_without_send_only_shows_the_audiences(db, tmp_path) -> None:
    route = respx.post(RESEND_BATCH_URL)

    result = announce()

    assert result.exit_code == 0, result.output
    assert not route.called
    assert "2 vindos da Urubu News" in result.output
    assert "2 da Geral" in result.output
    assert (tmp_path / "out" / "anuncio-flamengo.html").exists()
    assert (tmp_path / "out" / "anuncio-geral.html").exists()


@respx.mock
def test_send_gives_each_active_person_one_email_with_the_text_of_their_group(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)

    result = announce("--send")

    assert result.exit_code == 0, result.output
    sent = {e["to"][0]: e for e in emails(route)}
    assert sorted(sent) == ["both@x.com", "geral@x.com", "newfla@x.com", "urubu@x.com"]
    for email in ("urubu@x.com", "both@x.com"):
        assert sent[email]["from"] == "Urubu News <geral@geral.test>"
        assert "faz parte da Geral" in sent[email]["subject"]
    for email in ("geral@x.com", "newfla@x.com"):
        assert sent[email]["from"] == "Geral <geral@geral.test>"
        assert "Urubu News" in sent[email]["subject"]


@respx.mock
def test_every_email_carries_its_own_unsubscribe_link(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)

    announce("--send")

    for email in emails(route):
        url = email["headers"]["List-Unsubscribe"].strip("<>")
        token = parse_qs(urlparse(url).query)["token"][0]
        assert read_token("s3cret", "unsubscribe", token, datetime.now(UTC)) == email["to"][0]
        assert url in email["text"]


@respx.mock
def test_a_second_run_sends_nothing_again(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)
    announce("--send")
    first = len(emails(route))

    result = announce("--send")

    assert result.exit_code == 0, result.output
    assert len(emails(route)) == first
    assert "0 vindos da Urubu News" in result.output


@respx.mock
def test_a_failed_send_is_not_marked_and_goes_out_on_the_next_run(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(return_value=httpx.Response(422, json={}))

    assert announce("--send").exit_code != 0

    route.reset()
    route.mock(side_effect=ok)
    announce("--send")
    assert len(emails(route)) == 4


@respx.mock
def test_to_sends_both_versions_to_that_address_only_and_marks_nobody(db) -> None:
    route = respx.post(RESEND_BATCH_URL).mock(side_effect=ok)

    result = announce("--to", "me@x.com")

    assert result.exit_code == 0, result.output
    sent = emails(route)
    assert [e["to"][0] for e in sent] == ["me@x.com", "me@x.com"]
    assert {e["from"] for e in sent} == {
        "Urubu News <geral@geral.test>",
        "Geral <geral@geral.test>",
    }
    assert db.announced("geral") == set()
