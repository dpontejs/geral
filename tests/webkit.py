"""Helpers shared by the web app tests (fixtures live in conftest.py)."""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from geral.config import Settings
from geral.send.resend_sender import UNSUBSCRIBE_PLACEHOLDER
from geral.web.app import create_app
from geral.web.mailer import MailError

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
SECRET = "test-secret"
API_TOKEN = "api-token"
AUTH = {"Authorization": f"Bearer {API_TOKEN}"}
ANA = "ana@example.com"


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, list[str]]] = []
        self.editions: list[tuple[str, str, str, str, str, str]] = []
        self.notifications: list[tuple[str, str, str]] = []
        self.fail = False
        self.fail_editions = False

    def send_confirmation(self, email, confirm_url, teams) -> None:
        if self.fail:
            raise MailError("Resend is down")
        self.sent.append((email, confirm_url, [t.slug for t in teams]))

    def send_edition(
        self, email, team, subject, html, text, unsubscribe_url, bet_token=None
    ) -> None:
        if self.fail_editions:
            raise MailError("Resend is down")
        self.editions.append((email, team.slug, subject, html, text, unsubscribe_url, bet_token))

    def send_notification(self, to, subject, text) -> None:
        self.notifications.append((to, subject, text))


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def make_client(store, mailer, clock, teams=None, matches=None, **settings) -> TestClient:
    defaults = {"SUBSCRIBERS_API_TOKEN": API_TOKEN, "PUBLIC_URL": "https://geral.test"}
    config = Settings(SUBSCRIBE_SECRET=SECRET, **(defaults | settings))
    app = create_app(
        settings=config, store=store, mailer=mailer, now=clock, teams=teams, matches=matches
    )
    return TestClient(app, base_url="https://geral.test")


def sign_up(client: TestClient, email: str = ANA, teams=("vasco",)):
    return client.post("/subscribe", data={"email": email, "team": list(teams)})


def token_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


def confirm_last(client: TestClient, mailer: FakeMailer):
    return client.get("/confirm", params={"token": token_of(mailer.sent[-1][1])})


def publish(client: TestClient, team: str, subject: str = "Pós-jogo") -> None:
    html = f'<table><tr><td height="5">x</td></tr></table><a href="{UNSUBSCRIBE_PLACEHOLDER}">s</a>'
    edition = {"subject": subject, "html": html, "text": f"sair: {UNSUBSCRIBE_PLACEHOLDER}"}
    assert (
        client.put(f"/api/teams/{team}/latest-edition", json=edition, headers=AUTH).status_code
        == 204
    )
