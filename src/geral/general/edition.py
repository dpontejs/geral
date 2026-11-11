"""The edição geral: the week's séries plus the Gemini's opening and one summary per série."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, Field

from geral.general.collect import SerieWeek
from geral.models import Article
from geral.schedule import TZ
from geral.summarizer.client import LLMClient, LLMError
from geral.summarizer.pipeline import render_prompt

logger = logging.getLogger(__name__)

SEND_TIME = time(8, 0)
MAX_PICKS = 3
FALLBACK_HEADLINE = "O futebol brasileiro da semana"


class SerieSummary(BaseModel):
    name: str
    summary: str = ""
    picks: list[int] = Field(default_factory=list)  # 1-based ids of the série's news


class GeneralSummary(BaseModel):
    headline: str
    intro: str = ""
    series: list[SerieSummary] = Field(default_factory=list)


@dataclass
class GeneralSection:
    week: SerieWeek
    summary: str = ""
    picks: list[Article] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.week.name


@dataclass
class GeneralEdition:
    start: datetime
    end: datetime
    headline: str
    intro: str
    series: list[GeneralSection]

    @property
    def label(self) -> str:
        return f"Edição geral — {self.end:%d/%m/%Y}"

    @property
    def subject(self) -> str:
        return f"Geral — {self.label}: {self.headline}"


def week_window(day: date) -> tuple[datetime, datetime]:
    """From the previous Monday at 8h to `day` (the edition's Monday) at 8h, Brasília time."""
    end = datetime.combine(day, SEND_TIME, tzinfo=TZ)
    return end - timedelta(days=7), end


def build_general(
    start: datetime, end: datetime, weeks: list[SerieWeek], llm: LLMClient
) -> GeneralEdition:
    """Ask the Gemini for the texts; if it fails, the edition keeps results and tables."""
    try:
        summary = llm.generate_json(render_prompt("geral", weeks=weeks), GeneralSummary)
    except LLMError as e:
        logger.error("Edição geral without texts, the LLM failed: %s", e)
        summary = GeneralSummary(headline=FALLBACK_HEADLINE)
    by_name = {s.name: s for s in summary.series}
    sections = []
    for week in weeks:
        texts = by_name.get(week.name)
        picks = _picks(texts.picks, week.news) if texts else []
        sections.append(
            GeneralSection(
                week=week,
                summary=texts.summary.strip() if texts else "",
                picks=picks or week.news[:MAX_PICKS],
            )
        )
    return GeneralEdition(
        start=start,
        end=end,
        headline=summary.headline.strip() or FALLBACK_HEADLINE,
        intro=summary.intro.strip(),
        series=sections,
    )


def _picks(ids: list[int], news: list[Article]) -> list[Article]:
    valid = [i for i in dict.fromkeys(ids) if 1 <= i <= len(news)]
    return [news[i - 1] for i in valid[:MAX_PICKS]]
