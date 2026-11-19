"""Which special sections an edition gets: a draw seeded by the edition, so a rebuild agrees.

The story goes in news editions only; "Nesta semana" (facts within 3 days of the send) in every
edition of the team. With a section, the news are capped at TOPICS_WITH_SECTION topics.
"""

import logging
import random
from collections.abc import Callable
from datetime import date

import httpx
from pydantic import BaseModel, Field

from geral.config import Settings
from geral.models import Edition, Story
from geral.schedule import TZ
from geral.send import recipients
from geral.teams import Team

logger = logging.getLogger(__name__)

STORY_CHANCE = 0.8
ON_THIS_DAY_CHANCE = 0.7
TOPICS_WITH_SECTION = 6


class Sections(BaseModel):
    story: Story | None = None
    on_this_day: list[str] = Field(default_factory=list)
    max_topics: int | None = None  # the news cap when there is a section


def on_this_day_line(fact: dict, send_day: date) -> str | None:
    """'Há 92 anos, em 19/08/1934: <summary>' (the anniversary nearest to the send day);
    None for a fact of this year."""
    when = date.fromisoformat(fact["date"])
    years = (
        min(
            (y for y in (send_day.year - 1, send_day.year, send_day.year + 1)),
            key=lambda y: abs((date(y, when.month, min(when.day, 28)) - send_day).days),
        )
        - when.year
    )
    if years < 1:
        return None
    return f"Há {years} anos, em {when:%d/%m/%Y}: {fact['summary']}"


def pick_sections(
    edition: Edition,
    team: Team,
    *,
    draw: Callable[[], dict | None],
    facts: Callable[[], list[dict]],
    force_story: bool = False,
) -> Sections:
    # Each part fails on its own: a reserved story is kept when "Neste dia" fails.
    rng = random.Random(f"{team.slug}|{edition.label}")
    story = None
    wants_story = rng.random() < STORY_CHANCE
    if edition.kind == "news" and (wants_story or force_story):
        try:
            drawn = draw()
            story = Story(**drawn) if drawn else None
        except (httpx.HTTPError, ValueError) as e:  # ValueError: a reply that isn't a story
            logger.warning("Story left out, the page failed: %s", e)
    lines = []
    # The forced draw (a second chance for the story) does not draw "Neste dia" again.
    if not force_story and rng.random() < ON_THIS_DAY_CHANCE:
        send_day = edition.end.astimezone(TZ).date()
        try:
            found = sorted(facts(), key=lambda f: f["date"])
            lines = [line for f in found if (line := on_this_day_line(f, send_day))]
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning("Neste dia left out, the page failed: %s", e)
    has_section = story is not None or bool(lines)
    return Sections(
        story=story, on_this_day=lines, max_topics=TOPICS_WITH_SECTION if has_section else None
    )


def from_page(settings: Settings) -> Callable[..., Sections]:
    """The sections of an edition, from the collection on the page (a failure: no section).

    A dry run peeks at a story without reserving it.
    """

    def specials(edition: Edition, team: Team, second_chance: bool = False) -> Sections:
        return pick_sections(
            edition,
            team,
            draw=lambda: recipients.draw_story(
                settings, team.slug, edition.label, reserve=not settings.DRY_RUN
            ),
            facts=lambda: recipients.on_this_day(
                settings, team.slug, edition.end.astimezone(TZ).date()
            ),
            force_story=second_chance,
        )

    return specials
