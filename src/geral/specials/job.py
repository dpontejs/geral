"""The nightly job: keep each team's stories collection at about TARGET ready stories.

It runs when fewer than LOW are left, or every Sunday. Sources already seen (used or refused) are
skipped; kinds are interleaved so a round does not bring ten idols. Each story is written by the
model from its passage and checked by the verifier: a refusal is kept too, with the reason.
"""

import logging
import random
import re
from datetime import date
from itertools import zip_longest

import httpx
from pydantic import BaseModel, Field

from geral.config import Settings
from geral.send import recipients
from geral.specials import sources
from geral.specials.birthdays import birthdays
from geral.specials.sources import Passage
from geral.specials.verifier import NUMBER, unsupported
from geral.specials.writer import StoryDraft, write_story
from geral.summarizer.client import LLMClient, LLMError
from geral.teams import Team

logger = logging.getLogger(__name__)

TARGET = 10
LOW = 8
MAX_CALLS = 20  # model calls per team per round
MIN_WORDS, MAX_WORDS = 100, 200  # the prompt asks for 120 to 180
SUNDAY = 6


class TopUpReport(BaseModel):
    team: str
    accepted: int = 0
    rejected: int = 0
    skipped_reason: str | None = None
    problems: list[str] = Field(default_factory=list)
    stories: list[StoryDraft] = Field(default_factory=list)  # accepted ones (dry run preview)


def _interleaved(found: list[Passage], today: date) -> list[Passage]:
    rng = random.Random(today.isoformat())
    by_kind: dict[str, list[Passage]] = {}
    for p in found:
        by_kind.setdefault(p.kind, []).append(p)
    for group in by_kind.values():
        rng.shuffle(group)
    return [p for row in zip_longest(*by_kind.values()) for p in row if p is not None]


MONTHS = (
    "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro"
).split()


def checked_date(fact_date: str, source: str) -> str:
    """The fact's date as far as the source backs it: day and month only when they are in it
    ("14 de junho" or "14/06"), the year only when it is in it, else nothing."""
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})-(\d{2}))?", fact_date.strip())
    if not match or match.group(1) not in NUMBER.findall(source):
        return ""
    year, month, day = match.groups()
    if month is None:
        return year
    d, m = int(day), int(month)
    try:
        date(int(year), m, d)
    except ValueError:
        return year  # "31/06" in the source: the year is all that holds
    spelled = rf"\b0?{d}º? de {MONTHS[m - 1]}\b" if 1 <= m <= 12 else None
    numeric = rf"\b0?{d}/0?{m}\b"
    found = (spelled and re.search(spelled, source, re.IGNORECASE)) or re.search(numeric, source)
    return fact_date if found else year


def refusal(story: StoryDraft, passage: Passage, team: Team) -> str | None:
    """Why the verifier refuses the story, or None."""
    allowed = [team.name, team.newsletter, team.fans, *team.club_terms]
    text = f"{story.title}\n{story.body}\n{story.summary}"
    missing = unsupported(text, f"{passage.title}\n{passage.text}", allowed)
    if missing:
        return "fora da fonte: " + ", ".join(missing)
    if team.excludes(text):
        return "cita termo excluído"
    terms = [team.name, *team.club_terms]
    if not any(re.search(rf"\b{re.escape(t)}\b", story.body, re.IGNORECASE) for t in terms):
        return "não fala do clube"
    words = len(story.body.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        return f"tamanho: {words} palavras"
    return None


def top_up(
    team: Team, settings: Settings, llm: LLMClient, wiki: httpx.Client, today: date
) -> TopUpReport:
    report = TopUpReport(team=team.slug)
    keep = not settings.DRY_RUN
    try:
        if settings.SUBSCRIBERS_API_TOKEN or keep:
            unused = recipients.stories_count(settings, team.slug)
            seen = recipients.story_sources(settings, team.slug)
        else:  # a local dry run without the page: as if the collection were empty
            unused, seen = 0, set()
    except httpx.HTTPError as e:
        logger.error("Stories of %s: the page did not answer: %s", team.slug, e)
        report.skipped_reason = "portal fora do ar"
        return report
    if unused >= LOW and today.weekday() != SUNDAY:
        report.skipped_reason = f"acervo com {unused} histórias"
        return report
    need = TARGET - unused
    try:
        found = sources.passages(wiki, team)
    except httpx.HTTPError as e:
        logger.error("Stories of %s: Wikipedia did not answer: %s", team.slug, e)
        report.skipped_reason = "Wikipédia fora do ar"
        return report
    # The idols' birthdays ("Neste dia") are refreshed whenever the sources are read.
    try:
        born = birthdays(wiki, found)
        if keep and born:
            recipients.save_birthdays(settings, team.slug, born)
    except httpx.HTTPError as e:
        report.problems.append(f"aniversários: {e}")
    if need <= 0:
        report.skipped_reason = f"acervo com {unused} histórias"
        return report
    fresh = [p for p in found if p.key not in seen]
    for calls, passage in enumerate(_interleaved(fresh, today)):
        if report.accepted >= need or calls >= MAX_CALLS:
            break
        try:
            story = write_story(passage, team, llm)
        except LLMError as e:
            report.problems.append(f"Gemini: {e}")
            break
        story = story.model_copy(
            update={"fact_date": checked_date(story.fact_date, f"{passage.title}\n{passage.text}")}
        )
        reason = refusal(story, passage, team)
        if keep:
            try:
                kept = recipients.add_story(
                    settings, team.slug, story.model_dump() | {"rejected_reason": reason}
                )
            except httpx.HTTPError as e:
                report.problems.append(f"portal: {e}")
                break
            if not kept:
                continue  # its source was already there (another run): not a new story
        if reason:
            report.rejected += 1
            logger.info("Story refused (%s): %s", passage.title, reason)
        else:
            report.accepted += 1
            report.stories.append(story)
    return report
