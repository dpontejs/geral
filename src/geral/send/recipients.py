"""Client of the subscription page API: who receives an edition, and the latest edition.

Recipients are the fixed list plus the page's active subscribers; after a real send the edition
is published back so new subscribers get it right after confirming.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parseaddr

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential
from tenacity.wait import wait_base

from geral.config import Settings
from geral.models import Banner, BolaoSummary, Edition, Newsletter
from geral.schedule import TZ

logger = logging.getLogger(__name__)

FETCH_ATTEMPTS = 3
TIMEOUT = 15.0


@dataclass(frozen=True)
class Recipient:
    email: str
    unsubscribe_url: str
    bet_token: str | None = None  # signs the bolão links; only page subscribers have one


@dataclass(frozen=True)
class ResolvedRecipients:
    recipients: list[Recipient]
    from_api: int
    api_failed: bool = False  # the subscriber list could not be read: only the fixed list


class _Subscriber(BaseModel):
    email: str
    unsubscribe_url: str
    bet_token: str | None = None


_subscribers = TypeAdapter(list[_Subscriber])


def mailto_unsubscribe(settings: Settings) -> str:
    """mailto: link to the sender address, for the fixed list (it has no signed link)."""
    _, address = parseaddr(settings.NEWSLETTER_FROM)
    return f"mailto:{address}?subject=Descadastrar"


def _retryable(error: BaseException) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    return isinstance(error, httpx.TransportError)


def _team_edition_url(settings: Settings, team: str) -> str:
    return settings.PUBLIC_URL.rstrip("/") + f"/api/teams/{team}/latest-edition"


def fetch_subscribers(
    settings: Settings, team: str, client: httpx.Client, wait: wait_base
) -> list[_Subscriber]:
    """Active subscribers of one team, each with that team's unsubscribe link."""
    url = settings.PUBLIC_URL.rstrip("/") + "/api/subscribers"

    def get() -> httpx.Response:
        response = client.get(
            url,
            params={"team": team},
            headers={"Authorization": f"Bearer {settings.SUBSCRIBERS_API_TOKEN}"},
        )
        response.raise_for_status()
        return response

    retrying = Retrying(
        stop=stop_after_attempt(FETCH_ATTEMPTS),
        wait=wait,
        retry=retry_if_exception(_retryable),
        reraise=True,
    )
    return _subscribers.validate_python(retrying(get).json())


def resolve_recipients(
    settings: Settings,
    team: str,
    client: httpx.Client | None = None,
    wait: wait_base | None = None,
) -> ResolvedRecipients:
    """Fixed list + the team's API subscribers, once each. If the API fails, only the fixed list."""
    mailto = mailto_unsubscribe(settings)
    merged: dict[str, Recipient] = {}
    for email in settings.NEWSLETTER_RECIPIENTS:
        merged.setdefault(email.strip().lower(), Recipient(email.strip().lower(), mailto))

    from_api = 0
    failed = False
    if settings.SUBSCRIBERS_API_TOKEN:
        try:
            subscribers = fetch_subscribers(
                settings,
                team,
                client or httpx.Client(timeout=TIMEOUT),
                wait or wait_exponential(multiplier=2, max=20),
            )
        except (httpx.HTTPError, ValidationError, ValueError) as e:
            logger.error("Could not fetch subscribers, sending to the fixed list only: %s", e)
            failed = True
        else:
            from_api = len(subscribers)
            for s in subscribers:
                email = s.email.strip().lower()
                # A subscriber's signed link beats the fixed list's mailto.
                merged[email] = Recipient(email, s.unsubscribe_url, s.bet_token)
    return ResolvedRecipients(list(merged.values()), from_api, api_failed=failed)


def publish_latest_edition(
    settings: Settings,
    team: str,
    subject: str,
    html: str,
    text: str,
    client: httpx.Client | None = None,
) -> None:
    """PUT the team's edition (unsubscribe placeholder included). Raises httpx.HTTPError."""
    url = _team_edition_url(settings, team)
    response = (client or httpx.Client(timeout=TIMEOUT)).put(
        url,
        json={"subject": subject, "html": html, "text": text},
        headers={"Authorization": f"Bearer {settings.SUBSCRIBERS_API_TOKEN}"},
    )
    response.raise_for_status()


class LatestEdition(BaseModel):
    subject: str
    published_at: datetime
    text: str = ""

    @property
    def topic_titles(self) -> list[str]:
        """The "* title" lines of the plain-text "Notícias" section."""
        titles, in_news = [], False
        for line in self.text.splitlines():
            if line.startswith("== "):
                in_news = line.strip() == "== Notícias =="
            elif in_news and line.startswith("* "):
                titles.append(line[2:].strip())
        return titles


def latest_edition(
    settings: Settings, team: str, client: httpx.Client | None = None
) -> LatestEdition | None:
    """Subject and send time of the team's last edition, None if none. Raises httpx.HTTPError."""
    url = _team_edition_url(settings, team)
    response = (client or httpx.Client(timeout=TIMEOUT)).get(
        url, headers={"Authorization": f"Bearer {settings.SUBSCRIBERS_API_TOKEN}"}
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return LatestEdition.model_validate(response.json())


class DraftOut(BaseModel):
    """A built edition kept on the page, with what the owner decided about it."""

    label: str
    newsletter: Newsletter
    held: bool = False
    removed_topics: list[int] = []
    sent_at: datetime | None = None


def _draft_url(settings: Settings, team: str, edition: Edition, suffix: str = "") -> str:
    """Drafts are kept per kind and send day (the label has slashes: it can't be in the path)."""
    day = edition.end.astimezone(TZ).date()
    base = settings.PUBLIC_URL.rstrip("/")
    return f"{base}/api/teams/{team}/drafts/{edition.kind}/{day:%Y-%m-%d}{suffix}"


def save_draft(
    settings: Settings,
    team: str,
    newsletter: Newsletter,
    built_at: datetime,
    client: httpx.Client | None = None,
) -> bool:
    """PUT the built edition; False when it already has a draft. Raises httpx.HTTPError."""
    edition = newsletter.edition
    response = (client or httpx.Client(timeout=TIMEOUT)).put(
        _draft_url(settings, team, edition),
        json={
            "label": edition.label,
            "newsletter": newsletter.model_dump(mode="json"),
            "build_at": built_at.isoformat(),
            "send_at": edition.end.isoformat(),
        },
        headers=_auth(settings),
    )
    if response.status_code == 409:
        return False
    response.raise_for_status()
    return True


def fetch_draft(
    settings: Settings, team: str, edition: Edition, client: httpx.Client | None = None
) -> DraftOut | None:
    """The edition's draft, None if it was never built. Raises httpx.HTTPError."""
    response = (client or httpx.Client(timeout=TIMEOUT)).get(
        _draft_url(settings, team, edition), headers=_auth(settings)
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return DraftOut.model_validate(response.json())


def mark_draft_sent(
    settings: Settings, team: str, edition: Edition, client: httpx.Client | None = None
) -> None:
    response = (client or httpx.Client(timeout=TIMEOUT)).post(
        _draft_url(settings, team, edition, "/sent"), headers=_auth(settings)
    )
    response.raise_for_status()


def _bolao_url(settings: Settings, team: str, match_id: str, suffix: str = "") -> str:
    base = settings.PUBLIC_URL.rstrip("/")
    return f"{base}/api/teams/{team}/bolao/matches/{match_id}{suffix}"


def fetch_note(settings: Settings, team: str, client: httpx.Client | None = None) -> str | None:
    """The announcement for the team's next edition (`geral novidade`), if any.

    Never stops an edition: without the API or on any failure there is simply no note.
    """
    if not settings.SUBSCRIBERS_API_TOKEN:
        return None
    try:
        response = (client or httpx.Client(timeout=TIMEOUT)).get(
            settings.PUBLIC_URL.rstrip("/") + f"/api/teams/{team}/note", headers=_auth(settings)
        )
        response.raise_for_status()
        text = response.json().get("text")
    except Exception as e:  # noqa: BLE001 - an announcement is never worth a lost edition
        logger.warning("No note for %s: %s", team, e)
        return None
    return text.strip() if isinstance(text, str) and text.strip() else None


def fetch_banner(
    settings: Settings, team: str, client: httpx.Client | None = None
) -> tuple[str, str] | None:
    """(kicker, title) of the team's special banner (`geral especial`); None on any failure."""
    if not settings.SUBSCRIBERS_API_TOKEN:
        return None
    try:
        response = (client or httpx.Client(timeout=TIMEOUT)).get(
            settings.PUBLIC_URL.rstrip("/") + f"/api/teams/{team}/banner", headers=_auth(settings)
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:  # noqa: BLE001 - a banner is never worth a lost edition
        logger.warning("No banner for %s: %s", team, e)
        return None
    kicker, title = data.get("kicker"), data.get("title")
    return (kicker, title) if kicker and title else None


def make_banner(newsletter: Newsletter, kicker: str, title: str) -> Banner:
    """The banner with the season's numbers (our table row) and the score that sealed it."""
    ours = next((r for r in newsletter.standings if r.is_ours), None)
    stats = []
    if ours:
        stats = [
            (str(ours.points), "pontos"),
            (str(ours.won), "vitórias"),
            (f"{ours.goals_diff:+d}" if ours.goals_diff else "0", "saldo"),
        ]
    subtitle = ""
    if m := newsletter.last_match:
        subtitle = f"{m.home} {m.home_goals} × {m.away_goals} {m.away}"
        if m.venue:
            subtitle += f" · {m.venue}"
    return Banner(kicker=kicker, title=title, subtitle=subtitle, stats=stats)


def _auth(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.SUBSCRIBERS_API_TOKEN}"}


def register_match(
    settings: Settings,
    team: str,
    match_id: str,
    opponent: str,
    home: bool,
    kickoff: datetime,
    client: httpx.Client | None = None,
) -> None:
    """Open the team's bolão for this match until kickoff. Raises httpx.HTTPError."""
    response = (client or httpx.Client(timeout=TIMEOUT)).put(
        _bolao_url(settings, team, match_id),
        json={"opponent": opponent, "home": home, "kickoff": kickoff.isoformat()},
        headers=_auth(settings),
    )
    response.raise_for_status()


def report_result(
    settings: Settings,
    team: str,
    match_id: str,
    our_goals: int,
    their_goals: int,
    client: httpx.Client | None = None,
) -> BolaoSummary:
    """Store the final score (our side) and get the bolão summary. Raises httpx.HTTPError."""
    response = (client or httpx.Client(timeout=TIMEOUT)).put(
        _bolao_url(settings, team, match_id, "/result"),
        json={"our_goals": our_goals, "their_goals": their_goals},
        headers=_auth(settings),
    )
    response.raise_for_status()
    return BolaoSummary.model_validate(response.json())


def preview_summary(
    settings: Settings,
    team: str,
    match_id: str,
    our_goals: int,
    their_goals: int,
    client: httpx.Client | None = None,
) -> BolaoSummary:
    """The summary this score would give, without storing it (previews and dry runs)."""
    response = (client or httpx.Client(timeout=TIMEOUT)).get(
        _bolao_url(settings, team, match_id, "/summary"),
        params={"ours": our_goals, "theirs": their_goals},
        headers=_auth(settings),
    )
    response.raise_for_status()
    return BolaoSummary.model_validate(response.json())


# --- stories for the special sections (the nightly job) --------------------------------------


def _stories_url(settings: Settings, team: str, suffix: str = "") -> str:
    return settings.PUBLIC_URL.rstrip("/") + f"/api/teams/{team}/stories{suffix}"


def stories_count(settings: Settings, team: str, client: httpx.Client | None = None) -> int:
    """Stories ready and not used yet. Raises httpx.HTTPError."""
    response = (client or httpx.Client(timeout=TIMEOUT)).get(
        _stories_url(settings, team, "/count"), headers=_auth(settings)
    )
    return response.raise_for_status().json()["unused"]


def story_sources(settings: Settings, team: str, client: httpx.Client | None = None) -> set[str]:
    """Every source already turned into a story (or refused). Raises httpx.HTTPError."""
    response = (client or httpx.Client(timeout=TIMEOUT)).get(
        _stories_url(settings, team, "/sources"), headers=_auth(settings)
    )
    return set(response.raise_for_status().json())


def add_story(
    settings: Settings, team: str, story: dict, client: httpx.Client | None = None
) -> bool:
    """Keep a story or a refusal; False if its source was already there. Raises httpx.HTTPError."""
    response = (client or httpx.Client(timeout=TIMEOUT)).post(
        _stories_url(settings, team), json=story, headers=_auth(settings)
    )
    if response.status_code == 409:
        return False
    response.raise_for_status()
    return True


def draw_story(
    settings: Settings, team: str, label: str, reserve: bool, client: httpx.Client | None = None
) -> dict | None:
    """A ready story for the edition (reserved for it unless `reserve` is False), or None.
    Raises httpx.HTTPError."""
    response = (client or httpx.Client(timeout=TIMEOUT)).post(
        _stories_url(settings, team, "/draw"),
        json={"label": label, "reserve": reserve},
        headers=_auth(settings),
    )
    response.raise_for_status()
    return None if response.status_code == 204 else response.json()


def on_this_day(
    settings: Settings, team: str, day: date, client: httpx.Client | None = None
) -> list[dict]:
    """Dated facts of the team's stories around `day`. Raises httpx.HTTPError."""
    response = (client or httpx.Client(timeout=TIMEOUT)).get(
        _stories_url(settings, team, "/on-this-day"),
        params={"day": day.isoformat()},
        headers=_auth(settings),
    )
    response.raise_for_status()
    return [] if response.status_code == 204 else response.json()


def save_birthdays(
    settings: Settings, team: str, birthdays: list[dict], client: httpx.Client | None = None
) -> None:
    """The idols' birth dates for "Neste dia". Raises httpx.HTTPError."""
    response = (client or httpx.Client(timeout=TIMEOUT)).put(
        settings.PUBLIC_URL.rstrip("/") + f"/api/teams/{team}/birthdays",
        json=birthdays,
        headers=_auth(settings),
    )
    response.raise_for_status()
