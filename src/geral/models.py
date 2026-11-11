from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from geral.teams import Team


class Article(BaseModel):
    """Normalized article metadata and extracted content."""

    url: str
    title: str
    source: str
    published_at: datetime
    summary_hint: str | None = None
    content: str | None = None
    image_url: str | None = None
    # team: main news; saiba_mais: the club's other sports; brasil: Brazilian football
    section: Literal["team", "saiba_mais", "brasil"] = "team"
    category: str | None = None


class Brief(BaseModel):
    """Short item for the "Saiba mais" and "Brasil afora" sections."""

    title: str
    summary: str
    url: str
    source: str
    category: str | None = None


class Topic(BaseModel):
    """Grouped news topic summarized by LLM."""

    title: str
    summary: str
    articles: list[Article] = Field(default_factory=list)
    importance: int = 1
    image_url: str | None = None

    def model_post_init(self, __context: object) -> None:
        if self.image_url is None and self.articles:
            main_image = self.articles[0].image_url
            if main_image and main_image.startswith("https://"):
                self.image_url = main_image


class MatchEvent(BaseModel):
    """Event occurring during a match (goal, card, substitution)."""

    minute: int
    extra_minute: int | None = None
    team: str
    player: str
    type: str
    detail: str | None = None


class MatchStats(BaseModel):
    """Detailed statistics and info of a completed match."""

    fixture_id: int
    competition: str
    date: datetime
    home: str
    away: str
    home_goals: int
    away_goals: int
    home_penalties: int | None = None  # shoot-out, when the tie went to penalties
    away_penalties: int | None = None
    venue: str | None = None
    is_home: bool = True  # our team played at home
    home_logo: str | None = None
    away_logo: str | None = None
    events: list[MatchEvent] = Field(default_factory=list)
    statistics: dict[str, tuple[str, str]] = Field(default_factory=dict)
    lineups: dict[str, list[str]] = Field(default_factory=dict)
    # team -> [(category in pt-BR, player, value)]
    leaders: dict[str, list[tuple[str, str, str]]] = Field(default_factory=dict)

    @property
    def ours(self) -> str:
        """Our team's name as ESPN writes it (keys of `lineups` and `leaders`)."""
        return self.home if self.is_home else self.away


class NextMatch(BaseModel):
    """Information about the upcoming match."""

    opponent: str
    competition: str
    date: datetime
    venue: str | None = None
    is_home: bool = True
    opponent_logo: str | None = None
    match_id: str | None = None  # the ESPN event: the bolão only opens for the edition's match


class StandingRow(BaseModel):
    """Single row in a league standing table."""

    position: int
    team: str
    points: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_diff: int
    goals_for: int = 0
    goals_against: int = 0
    is_ours: bool = False


class FormResult(BaseModel):
    """Our team's result in a recent match, from our point of view."""

    result: Literal["V", "E", "D"]
    opponent: str
    score: str
    competition: str
    date: datetime


class MatchPreview(BaseModel):
    """Pre-game numbers: both teams' last five and the last head-to-head games, newest first."""

    opponent: str
    team_form: list[FormResult] = Field(default_factory=list)
    opponent_form: list[FormResult] = Field(default_factory=list)
    head_to_head: list[FormResult] = Field(default_factory=list)


class PlayerRanking(BaseModel):
    """One of our players' position in a league leaderboard."""

    category: str
    player: str
    position: int
    value: int


class TeamMoment(BaseModel):
    """Recent form, league campaign and player rankings."""

    form: list[FormResult] = Field(default_factory=list)
    standing: StandingRow | None = None
    gap: str | None = None
    rankings: list[PlayerRanking] = Field(default_factory=list)
    league: str | None = None  # the table's competition, for the "Campanha" line


class Edition(BaseModel):
    """Newsletter edition temporal window and description."""

    kind: Literal["pre", "post", "news"]
    start: datetime
    end: datetime
    label: str
    match_id: str | None = None  # pre/post: the ESPN event
    league: str | None = None


class RankRow(BaseModel):
    """One player in a team's bolão ranking (nickname only: never the e-mail)."""

    nickname: str
    points: int
    exact: int


class BolaoSummary(BaseModel):
    """A team's bolão after a match: who nailed the score, the season top 5 and the titles.

    Scores are from our team's side (our goals, their goals)."""

    our_goals: int
    their_goals: int
    exact: list[str]
    top: list[RankRow]
    king: str | None = None
    cold_foot: str | None = None


class Newsletter(BaseModel):
    """Full newsletter content ready for rendering and dispatch."""

    team: Team
    edition: Edition
    intro: str
    headline: str = ""
    analysis: str = ""
    moment: TeamMoment | None = None
    topics: list[Topic] = Field(default_factory=list)
    learn_more: list[Brief] = Field(default_factory=list)
    around_brazil: list[Brief] = Field(default_factory=list)
    last_match: MatchStats | None = None
    next_match: NextMatch | None = None
    standings: list[StandingRow] = Field(default_factory=list)
    table_name: str | None = None  # competition of `standings` (ESPN league or a ge table)
    preview: MatchPreview | None = None  # pre-game only
    lineups: str = ""  # pre-game: probable line-ups, from the news
    tips: list[str] = Field(default_factory=list)  # pre-game: the press's predictions
    outlook: str = ""  # pre-game: "O que esperar"
    broadcast: str = ""  # pre-game: where to watch
    bolao_open: bool = False  # pre-game: the page takes bets on this match
    bolao: BolaoSummary | None = None  # post-game: the bolão result
