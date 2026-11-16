"""The special edition that presents the games (`geral especial-jogos`): one e-mail per active
person, whatever teams they follow, from the Geral, never twice.

Same rules as the announcement (`announce.py`): who got it is kept in announcements_sent under
NAME, and the unsubscribe link leaves every list."""

from datetime import datetime
from email.utils import formataddr, parseaddr

from jinja2 import Environment, FileSystemLoader, select_autoescape

from geral.config import Settings
from geral.send.resend_sender import BATCH_SIZE, UNSUBSCRIBE_PLACEHOLDER, ResendSender
from geral.web.announce import TEMPLATES, recipient
from geral.web.store import SubscriberStore

NAME = "jogos-2026-11"  # its key in announcements_sent
SUBJECT = "Os joguinhos da Geral"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html.j2"]))


def render(settings: Settings) -> tuple[str, str]:
    """HTML and text, with the unsubscribe placeholder the sender fills per person."""
    public_url = settings.PUBLIC_URL.rstrip("/")
    context = {
        "subject": SUBJECT,
        "public_url": public_url,
        "static": f"{public_url}/static/geral",
        "unsubscribe_url": UNSUBSCRIBE_PLACEHOLDER,
    }
    return (
        _env.get_template("email/especial_jogos.html.j2").render(context),
        _env.get_template("email/especial_jogos.txt.j2").render(context),
    )


def pending(store: SubscriberStore) -> list[str]:
    """Active people who have not got it yet."""
    sent = store.announced(NAME)
    return [e for e in store.everyone_active() if e not in sent]


def send(
    settings: Settings, store: SubscriberStore, emails: list[str], now: datetime, mark: bool = True
) -> int:
    """Send in batches, marking each batch once Resend accepted it; returns how many went.

    A test (`mark=False`) marks nobody, so the real send still reaches that address."""
    html, text = render(settings)
    sender = formataddr(("Geral", parseaddr(settings.NEWSLETTER_FROM)[1]))
    mail = ResendSender(settings.RESEND_API_KEY, sender, dry_run=False)
    for start in range(0, len(emails), BATCH_SIZE):
        batch = emails[start : start + BATCH_SIZE]
        mail.send(SUBJECT, html, text, [recipient(settings, e, now) for e in batch])
        if mark:
            store.mark_announced(NAME, batch, now)
    return len(emails)
