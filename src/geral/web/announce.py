"""One-off announcement e-mails (`geral announce`): one per active person, never twice.

People who came with a moved-in team (LEGACY_TEAM) get a text that explains the move, from
that newsletter's name; everyone else gets the Geral's. The unsubscribe link leaves every team.
"""

from dataclasses import dataclass
from datetime import datetime
from email.utils import formataddr, parseaddr
from pathlib import Path
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape

from geral.config import Settings
from geral.send.recipients import Recipient
from geral.send.resend_sender import BATCH_SIZE, UNSUBSCRIBE_PLACEHOLDER, ResendSender
from geral.teams import Team
from geral.web.store import SubscriberStore
from geral.web.tokens import make_token

NAME = "geral"  # the announcement's key in announcements_sent
GERAL_ACCENT = "#8E8B84"
TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html.j2"]))


@dataclass(frozen=True)
class Version:
    """One of the two texts: who it comes from, subject and body."""

    key: str  # the moved-in team's slug or "geral": preview file names
    team: Team | None  # sends from this newsletter's own mailbox; None: from the Geral
    subject: str
    html: str
    text: str


@dataclass(frozen=True)
class Audiences:
    moved_in: list[str]
    others: list[str]


def versions(settings: Settings, legacy: Team) -> tuple[Version, Version]:
    """The moved-in text and the Geral text, with the unsubscribe placeholder in them."""
    public_url = settings.PUBLIC_URL.rstrip("/")

    def build(moved_in: bool, key: str, sender: Team | None, subject: str, accent: str) -> Version:
        context = {
            "moved_in": moved_in,
            "team": legacy,
            "subject": subject,
            "public_url": public_url,
            "accent": accent,
            "unsubscribe_url": UNSUBSCRIBE_PLACEHOLDER,
        }
        return Version(
            key,
            sender,
            subject,
            _env.get_template("email/announce.html.j2").render(context),
            _env.get_template("email/announce.txt.j2").render(context),
        )

    return (
        build(
            True,
            legacy.slug,
            legacy,
            f"A {legacy.newsletter} agora faz parte da Geral",
            legacy.accent,
        ),
        build(
            False,
            "geral",
            None,
            f"Novidades na Geral: a {legacy.newsletter} chegou",
            GERAL_ACCENT,
        ),
    )


def audiences(store: SubscriberStore, legacy: Team, moved_in_before: datetime) -> Audiences:
    """Who still has to get the announcement, split by text."""
    came_with_it = store.active_since_before(legacy.slug, moved_in_before)
    pending = [e for e in store.everyone_active() if e not in store.announced(NAME)]
    return Audiences(
        moved_in=[e for e in pending if e in came_with_it],
        others=[e for e in pending if e not in came_with_it],
    )


def recipient(settings: Settings, email: str, now: datetime) -> Recipient:
    token = make_token(settings.SUBSCRIBE_SECRET, "unsubscribe", email, now)
    url = f"{settings.PUBLIC_URL.rstrip('/')}/unsubscribe?{urlencode({'token': token})}"
    return Recipient(email, url)


def sender(settings: Settings, version: Version) -> ResendSender:
    """Like the editions: a newsletter's name and its own mailbox (`news@`), else the Geral's."""
    base = parseaddr(settings.NEWSLETTER_FROM)[1]
    team = version.team
    name, address = (team.newsletter, team.sender_address(base)) if team else ("Geral", base)
    return ResendSender(settings.RESEND_API_KEY, formataddr((name, address)), dry_run=False)


def send(
    settings: Settings,
    store: SubscriberStore,
    version: Version,
    emails: list[str],
    now: datetime,
    mark: bool = True,
) -> int:
    """Send in batches, marking each batch once Resend accepted it; returns how many went.

    A test (`mark=False`) marks nobody, so the real send still reaches that address."""
    mail = sender(settings, version)
    for start in range(0, len(emails), BATCH_SIZE):
        batch = emails[start : start + BATCH_SIZE]
        mail.send(
            version.subject,
            version.html,
            version.text,
            [recipient(settings, e, now) for e in batch],
        )
        if mark:
            store.mark_announced(NAME, batch, now)
    return len(emails)
