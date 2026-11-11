from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from geral.config import Settings
from geral.send.resend_sender import UNSUBSCRIBE_PLACEHOLDER
from geral.web.app import create_app
from geral.web.mailer import MailError
from geral.web.store import SubscriberStore
from geral.web.tokens import make_token, read_token

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

    def send_edition(self, email, team, subject, html, text, unsubscribe_url) -> None:
        if self.fail_editions:
            raise MailError("Resend is down")
        self.editions.append((email, team.slug, subject, html, text, unsubscribe_url))

    def send_notification(self, to, subject, text) -> None:
        self.notifications.append((to, subject, text))


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def store(tmp_path) -> SubscriberStore:
    return SubscriberStore(tmp_path / "subscribers.db")


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def clock() -> Clock:
    return Clock()


def make_client(store, mailer, clock, **settings) -> TestClient:
    defaults = {"SUBSCRIBERS_API_TOKEN": API_TOKEN, "PUBLIC_URL": "https://geral.test"}
    config = Settings(SUBSCRIBE_SECRET=SECRET, **(defaults | settings))
    app = create_app(settings=config, store=store, mailer=mailer, now=clock)
    return TestClient(app, base_url="https://geral.test")


@pytest.fixture
def client(store, mailer, clock) -> TestClient:
    return make_client(store, mailer, clock)


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


# --- inscrição -------------------------------------------------------------------------------


def test_subscribe_with_two_teams_creates_pending_subscriptions_and_sends_one_confirmation(
    client, store, mailer
) -> None:
    response = sign_up(client, " Ana@Example.com ", ["vasco", "nautico", "vasco"])

    assert response.status_code == 200 and "Confira seu e-mail" in response.text
    assert store.get(ANA).status == "pending"
    assert store.pending_teams(ANA) == ["nautico", "vasco"]
    [(email, url, teams)] = mailer.sent
    assert email == ANA and teams == ["nautico", "vasco"]
    assert url.startswith("https://geral.test/confirm?token=")


@pytest.mark.parametrize("teams", [[], ["flamenguinho"]])
def test_subscribe_rejects_no_team_or_unknown_team(client, store, mailer, teams) -> None:
    response = sign_up(client, ANA, teams)

    assert response.status_code == 400
    assert "Escolha pelo menos uma torcida" in response.text
    assert store.get(ANA) is None and mailer.sent == []


def test_subscribe_same_page_for_active_email(client, mailer) -> None:
    sign_up(client)
    confirm_last(client, mailer)

    response = sign_up(client)

    assert "Confira seu e-mail" in response.text
    assert len(mailer.sent) == 1


def test_honeypot_and_invalid_email_send_nothing(client, store, mailer) -> None:
    bot = client.post("/subscribe", data={"email": ANA, "team": "vasco", "website": "x"})
    bad = sign_up(client, "não é e-mail")

    assert "Confira seu e-mail" in bot.text
    assert bad.status_code == 400 and "e-mail válido" in bad.text
    assert store.get(ANA) is None and mailer.sent == []


def test_rate_limit_per_ip(client, mailer) -> None:
    for i in range(5):
        sign_up(client, f"fa{i}@example.com")

    assert sign_up(client, "fa9@example.com").status_code == 429
    assert len(mailer.sent) == 5


def test_mail_failure_shows_error_and_allows_retry(client, mailer) -> None:
    mailer.fail = True
    assert sign_up(client).status_code == 502

    mailer.fail = False
    assert "Confira seu e-mail" in sign_up(client).text
    assert len(mailer.sent) == 1


# --- confirmação e boas-vindas ---------------------------------------------------------------


def test_confirm_activates_teams_and_welcomes_with_each_latest_edition(
    client, store, mailer
) -> None:
    publish(client, "vasco", "Pós-jogo do Vasco")
    sign_up(client, ANA, ["vasco", "abc"])  # ABC has no edition yet

    response = confirm_last(client, mailer)

    assert response.status_code == 200 and "Inscrição confirmada" in response.text
    assert store.teams_of(ANA) == ["abc", "vasco"]
    [(email, team, subject, html, text, unsubscribe)] = mailer.editions
    assert (email, team) == (ANA, "vasco")
    assert subject == "Boas-vindas! Pós-jogo do Vasco"
    assert "Boas-vindas à Almirante News!" in html and text.startswith("Boas-vindas")
    assert read_token(SECRET, "unsubscribe:vasco", token_of(unsubscribe), NOW) == ANA


def test_confirm_twice_does_not_welcome_again(client, mailer) -> None:
    publish(client, "vasco")
    sign_up(client)
    confirm_last(client, mailer)

    again = confirm_last(client, mailer)

    assert again.status_code == 200
    assert len(mailer.editions) == 1


def test_active_subscriber_adding_a_team_needs_confirmation(client, store, mailer) -> None:
    publish(client, "vasco")
    publish(client, "abc")
    sign_up(client, ANA, ["vasco"])
    confirm_last(client, mailer)

    sign_up(client, ANA, ["vasco", "abc"])

    assert store.teams_of(ANA) == ["vasco"]
    assert mailer.sent[-1][2] == ["abc"]
    confirm_last(client, mailer)
    assert store.teams_of(ANA) == ["abc", "vasco"]
    assert [e[1] for e in mailer.editions] == ["vasco", "abc"]  # only the new team welcomed


def test_confirm_rejects_expired_or_forged_token(client, store, mailer, clock) -> None:
    sign_up(client)
    token = token_of(mailer.sent[-1][1])

    assert client.get("/confirm", params={"token": token + "x"}).status_code == 400
    clock.now = NOW + timedelta(days=8)
    assert client.get("/confirm", params={"token": token}).status_code == 400
    assert store.get(ANA).status == "pending"


def test_welcome_failure_keeps_the_subscription(client, store, mailer) -> None:
    publish(client, "vasco")
    sign_up(client)
    mailer.fail_editions = True

    assert confirm_last(client, mailer).status_code == 200
    assert store.teams_of(ANA) == ["vasco"]


def test_first_confirmation_notifies_the_owner(store, mailer, clock) -> None:
    client = make_client(store, mailer, clock, NOTIFY_EMAIL="dono@example.com")
    sign_up(client, ANA, ["vasco", "nautico"])
    confirm_last(client, mailer)
    confirm_last(client, mailer)

    [(to, subject, text)] = mailer.notifications
    assert to == "dono@example.com" and ANA in subject
    assert "Almirante News" in text and "Timbu News" in text


# --- descadastro -----------------------------------------------------------------------------


def unsubscribe_token(team: str | None, email: str = ANA) -> str:
    purpose = f"unsubscribe:{team}" if team else "unsubscribe"
    return make_token(SECRET, purpose, email, NOW)


def active(client, mailer, teams=("vasco", "nautico")) -> None:
    sign_up(client, ANA, teams)
    confirm_last(client, mailer)


def test_unsubscribe_get_does_not_unsubscribe(client, store, mailer) -> None:
    active(client, mailer)

    page = client.get("/unsubscribe", params={"token": unsubscribe_token("nautico")})

    assert page.status_code == 200
    assert "Timbu News" in page.text and "Sair de todas" in page.text
    assert store.teams_of(ANA) == ["nautico", "vasco"]


def test_team_unsubscribe_leaves_the_other_teams(client, store, mailer) -> None:
    active(client, mailer)

    response = client.post("/unsubscribe", params={"token": unsubscribe_token("nautico")})

    assert response.status_code == 200 and "Timbu News" in response.text
    assert store.teams_of(ANA) == ["vasco"]


def test_one_click_post_unsubscribes_from_that_team(client, store, mailer) -> None:
    active(client, mailer)

    client.post(
        "/unsubscribe",
        params={"token": unsubscribe_token("vasco")},
        data={"List-Unsubscribe": "One-Click"},
    )

    assert store.teams_of(ANA) == ["nautico"]


def test_last_team_out_unsubscribes_the_email(client, store, mailer) -> None:
    active(client, mailer, ["vasco"])

    client.post("/unsubscribe", params={"token": unsubscribe_token("vasco")})

    assert store.get(ANA).status == "unsubscribed"


def test_leave_all_from_a_team_link(client, store, mailer) -> None:
    active(client, mailer)

    client.post("/unsubscribe", params={"token": unsubscribe_token("nautico"), "all": "1"})

    assert store.get(ANA).status == "unsubscribed"


def test_general_token_leaves_every_team(client, store, mailer) -> None:
    active(client, mailer)

    client.post("/unsubscribe", params={"token": unsubscribe_token(None)})

    assert store.get(ANA).status == "unsubscribed"


def test_team_token_cannot_unsubscribe_another_team(client, store, mailer) -> None:
    active(client, mailer)
    nautico = unsubscribe_token("nautico")

    # A token signed for one team only ever names that team: a team parameter is ignored.
    client.post("/unsubscribe", params={"token": nautico, "team": "vasco"})
    client.post("/unsubscribe", params={"token": nautico + "x"})

    assert store.teams_of(ANA) == ["vasco"]


def test_unsubscribe_rejects_invalid_token(client) -> None:
    assert client.get("/unsubscribe", params={"token": "x"}).status_code == 400
    assert client.post("/unsubscribe", params={"token": "x"}).status_code == 400


# --- API -------------------------------------------------------------------------------------


def test_api_subscribers_lists_only_active_in_that_team_and_requires_token(client, mailer) -> None:
    active(client, mailer, ["vasco"])
    sign_up(client, "b@example.com", ["vasco"])  # pending
    sign_up(client, "c@example.com", ["nautico"])
    confirm_last(client, mailer)

    assert client.get("/api/subscribers", params={"team": "vasco"}).status_code == 401
    rows = client.get("/api/subscribers", params={"team": "vasco"}, headers=AUTH).json()

    assert [r["email"] for r in rows] == [ANA]
    assert read_token(SECRET, "unsubscribe:vasco", token_of(rows[0]["unsubscribe_url"]), NOW)


def test_api_subscribers_unknown_team_is_404(client) -> None:
    response = client.get("/api/subscribers", params={"team": "xyz"}, headers=AUTH)

    assert response.status_code == 404


def test_api_disabled_without_configured_token(store, mailer, clock) -> None:
    client = make_client(store, mailer, clock, SUBSCRIBERS_API_TOKEN=None)

    response = client.get("/api/subscribers", params={"team": "vasco"}, headers=AUTH)

    assert response.status_code == 401


def test_latest_edition_is_kept_per_team(client) -> None:
    assert client.get("/api/teams/vasco/latest-edition", headers=AUTH).status_code == 404
    publish(client, "vasco", "Do Vasco")
    publish(client, "abc", "Do ABC")

    vasco = client.get("/api/teams/vasco/latest-edition", headers=AUTH).json()

    assert vasco["subject"] == "Do Vasco" and vasco["published_at"].startswith("2026-11-10")
    assert client.get("/api/teams/vasco/latest-edition").status_code == 401


def test_publish_requires_the_unsubscribe_placeholder_and_a_known_team(client) -> None:
    edition = {"subject": "S", "html": "<p>sem marcador</p>", "text": "t"}

    bad_html = client.put("/api/teams/vasco/latest-edition", json=edition, headers=AUTH)
    edition["html"] = UNSUBSCRIBE_PLACEHOLDER
    bad_team = client.put("/api/teams/xyz/latest-edition", json=edition, headers=AUTH)

    assert bad_html.status_code == 422 and bad_team.status_code == 404


# --- operação --------------------------------------------------------------------------------


def test_health(client) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_app_refuses_to_start_without_secret(store, mailer) -> None:
    with pytest.raises(RuntimeError):
        create_app(settings=Settings(SUBSCRIBE_SECRET=None), store=store, mailer=mailer)


def test_get_subscribe_goes_back_to_the_portal(client) -> None:
    response = client.get("/subscribe", follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/"
