"""Edição geral 4b: sign-up on the portal and the Monday send (docs/features/edicao-geral.md)."""

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from fakes import FakeLLMClient
from test_general_edition import WEEKS, responder
from typer.testing import CliRunner
from webkit import AUTH, NOW, confirm_last, publish, sign_up, token_of

import geral.__main__ as cli
from geral.config import get_settings
from geral.send.resend_sender import RESEND_BATCH_URL

TZ = ZoneInfo("America/Sao_Paulo")

# --- portal ----------------------------------------------------------------------------------


def test_portal_offers_the_general_edition_in_the_ticket(client) -> None:
    page = client.get("/").text

    assert 'name="team" value="geral"' in page
    assert 'href="/t/geral"' not in page  # nothing to read yet

    publish(client, "geral", "Geral — Edição geral — 09/11/2026: Flamengo dispara")

    assert 'href="/t/geral"' in client.get("/").text


def test_general_edition_stays_out_of_the_scoreboard(client, store) -> None:
    store.request("ana@example.com", ["geral"], NOW)
    store.confirm("ana@example.com", NOW)

    board = client.get("/").text.split('id="placar"', 1)[1].split("</section>", 1)[0]

    assert "Geral" not in re.findall(r'class="name">([^<]+)<', board)


def test_sign_up_for_the_general_edition(client, mailer, store) -> None:
    sign_up(client, teams=("geral", "vasco"))

    assert mailer.sent[-1][2] == ["geral", "vasco"]
    confirm_last(client, mailer)
    assert set(store.teams_of("ana@example.com")) == {"geral", "vasco"}


def test_subscribers_api_and_latest_edition_for_the_general_edition(client, store) -> None:
    store.request("ana@example.com", ["geral"], NOW)
    store.confirm("ana@example.com", NOW)
    publish(client, "geral", "Geral — Edição geral — 09/11/2026: Flamengo dispara")

    listed = client.get("/api/subscribers", params={"team": "geral"}, headers=AUTH).json()

    assert [s["email"] for s in listed] == ["ana@example.com"]
    assert client.get("/t/geral").status_code == 200


def test_unsubscribe_from_the_general_edition_only(client, mailer, store) -> None:
    sign_up(client, teams=("geral", "vasco"))
    confirm_last(client, mailer)
    url = client.get("/api/subscribers", params={"team": "geral"}, headers=AUTH).json()[0][
        "unsubscribe_url"
    ]

    client.post("/unsubscribe", params={"token": token_of(url)})

    assert store.teams_of("ana@example.com") == ["vasco"]


def test_welcome_for_the_general_edition_has_its_own_text(client, mailer) -> None:
    publish(client, "geral", "Geral — Edição geral — 09/11/2026: Flamengo dispara")
    sign_up(client, teams=("geral",))

    confirm_last(client, mailer)

    (welcome,) = [e for e in mailer.editions if e[1] == "geral"]
    assert "Boas-vindas à Edição geral!" in welcome[4]
    assert "Toda segunda" in welcome[4]


def test_requesting_geral_as_a_team_is_not_already_here(client) -> None:
    assert "Já tem!" not in client.post("/pedir", data={"team": "Geral"}).text


# --- due --all -------------------------------------------------------------------------------


@pytest.fixture
def geral_db(monkeypatch, tmp_path):
    from geral.web.store import SubscriberStore

    db = tmp_path / "subscribers.db"
    monkeypatch.setenv("SUBSCRIBERS_DB", str(db))
    monkeypatch.setattr(cli, "_fixtures", lambda team, settings, now: [])
    return SubscriberStore(db)


def due_at(monkeypatch, when: datetime) -> list[str]:
    monkeypatch.setattr(cli, "_now", lambda: when)
    result = CliRunner().invoke(cli.app, ["due", "--all"])
    assert result.exit_code == 0, result.output
    return [line for line in result.stdout.splitlines() if line.startswith("geral\t")]


def test_due_all_lists_the_general_edition_on_monday_morning(geral_db, monkeypatch) -> None:
    geral_db.request("ana@example.com", ["geral"], NOW)
    geral_db.confirm("ana@example.com", NOW)

    assert due_at(monkeypatch, datetime(2026, 11, 16, 8, 10, tzinfo=TZ)) == [
        "geral\tnews\t2026-11-16\tEdição geral — 16/11/2026"
    ]
    assert due_at(monkeypatch, datetime(2026, 11, 16, 7, 50, tzinfo=TZ)) == []
    assert due_at(monkeypatch, datetime(2026, 11, 16, 11, 30, tzinfo=TZ)) == []
    assert due_at(monkeypatch, datetime(2026, 11, 17, 8, 10, tzinfo=TZ)) == []


def test_due_all_skips_the_general_edition_already_sent(geral_db, monkeypatch) -> None:
    geral_db.request("ana@example.com", ["geral"], NOW)
    geral_db.confirm("ana@example.com", NOW)
    geral_db.set_latest_edition(
        "geral", "Geral — Edição geral — 16/11/2026: x", "<p>x</p>", "x",
        datetime(2026, 11, 16, 8, 5, tzinfo=TZ),
    )  # fmt: skip

    assert due_at(monkeypatch, datetime(2026, 11, 16, 8, 30, tzinfo=TZ)) == []


def test_due_all_without_general_subscribers_lists_nothing(geral_db, monkeypatch) -> None:
    assert due_at(monkeypatch, datetime(2026, 11, 16, 8, 10, tzinfo=TZ)) == []


# --- edicao-geral --send ---------------------------------------------------------------------

API = "https://geral.test/api/subscribers"
LATEST = "https://geral.test/api/teams/geral/latest-edition"


@pytest.fixture
def send_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("NEWSLETTER_FROM", "Geral <news@geral.test>")
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "")
    monkeypatch.setenv("SUBSCRIBERS_API_TOKEN", "api-token")
    monkeypatch.setenv("PUBLIC_URL", "https://geral.test")
    get_settings.cache_clear()
    collected = []
    monkeypatch.setattr(cli, "collect_week", lambda start, end: collected.append(1) or WEEKS)
    monkeypatch.setattr(cli, "get_llm_client", lambda settings: FakeLLMClient(responder))
    yield collected
    get_settings.cache_clear()


def subscribers(*emails: str) -> list[dict]:
    return [
        {"email": e, "unsubscribe_url": f"https://geral.test/unsubscribe?token={e}"} for e in emails
    ]


def run_send(*extra: str):
    return CliRunner().invoke(cli.app, ["edicao-geral", "--date", "2026-11-09", "--send", *extra])


@respx.mock
def test_send_goes_to_subscribers_with_their_link_and_publishes(send_env) -> None:
    respx.get(API, params={"team": "geral"}).mock(
        return_value=httpx.Response(200, json=subscribers("ana@example.com"))
    )
    resend = respx.post(RESEND_BATCH_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "e1"}]})
    )
    published = respx.put(LATEST).mock(return_value=httpx.Response(204))

    result = run_send()

    assert result.exit_code == 0, result.output
    (email,) = json.loads(resend.calls[0].request.content)
    assert email["to"] == ["ana@example.com"]
    assert "https://geral.test/unsubscribe?token=ana@example.com" in email["html"]
    assert published.called
    assert "Edição geral — 09/11/2026" in json.loads(published.calls[0].request.content)["subject"]


@respx.mock
def test_send_without_subscribers_stops_before_collecting(send_env) -> None:
    respx.get(API, params={"team": "geral"}).mock(return_value=httpx.Response(200, json=[]))

    result = run_send()

    assert result.exit_code == 0, result.output
    assert "sem inscritos" in result.output
    assert send_env == []


@respx.mock
def test_send_skip_if_sent_does_not_redo_the_week(send_env) -> None:
    respx.get(API, params={"team": "geral"}).mock(
        return_value=httpx.Response(200, json=subscribers("ana@example.com"))
    )
    respx.get(LATEST).mock(
        return_value=httpx.Response(
            200,
            json={
                "subject": "Geral — Edição geral — 09/11/2026: x",
                "published_at": "2026-11-09T08:05:00-03:00",
                "text": "",
            },
        )
    )

    result = run_send("--skip-if-sent")

    assert result.exit_code == 0, result.output
    assert "já saiu" in result.output
    assert send_env == []


@respx.mock
def test_dry_run_send_does_not_publish(send_env, monkeypatch) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    get_settings.cache_clear()
    respx.get(API, params={"team": "geral"}).mock(
        return_value=httpx.Response(200, json=subscribers("ana@example.com"))
    )
    published = respx.put(LATEST).mock(return_value=httpx.Response(204))

    result = run_send()

    assert result.exit_code == 0, result.output
    assert not published.called


# --- review: the edição geral is not a torcida ---------------------------------------------


def test_games_do_not_treat_the_general_edition_as_a_team(client) -> None:
    page = client.get("/jogos/onde-jogou").text

    assert "passagens pelo Geral" not in page


def test_portal_total_counts_only_torcidas(client, store) -> None:
    store.request("ana@example.com", ["geral"], NOW)
    store.confirm("ana@example.com", NOW)
    store.request("bia@example.com", ["vasco"], NOW)
    store.confirm("bia@example.com", NOW)

    page = client.get("/").text

    assert "Nº 000002" in page  # the next ticket after one torcida subscriber


def test_confirming_only_the_general_edition_says_every_monday(client, mailer) -> None:
    sign_up(client, teams=("geral",))

    page = confirm_last(client, mailer).text

    assert "vai receber a Edição geral toda segunda de manhã." in page
    assert "Edição geral antes e depois de cada jogo" not in page


def test_bolao_has_no_general_edition(client) -> None:
    assert client.get("/bolao/geral").status_code == 404
    match = {"opponent": "X", "home": True, "kickoff": "2026-11-16T16:00:00-03:00"}
    assert (
        client.put("/api/teams/geral/bolao/matches/1", json=match, headers=AUTH).status_code == 404
    )


@respx.mock
def test_send_fails_loudly_when_publishing_fails(send_env) -> None:
    respx.get(API, params={"team": "geral"}).mock(
        return_value=httpx.Response(200, json=subscribers("ana@example.com"))
    )
    respx.post(RESEND_BATCH_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "e"}]})
    )
    respx.put(LATEST).mock(return_value=httpx.Response(500))

    result = run_send()

    assert result.exit_code == 1
    assert "não publicada" in result.output


@respx.mock
def test_send_stops_when_the_subscribers_api_fails(send_env, monkeypatch) -> None:
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "dono@example.com")
    get_settings.cache_clear()
    respx.get(API, params={"team": "geral"}).mock(return_value=httpx.Response(503))
    resend = respx.post(RESEND_BATCH_URL).mock(return_value=httpx.Response(200, json={"data": []}))

    result = run_send()

    assert result.exit_code == 1
    assert not resend.called
    assert send_env == []
