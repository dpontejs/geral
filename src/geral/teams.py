"""Team catalog: every newsletter of the hub is one entry of teams.toml."""

import re
import tomllib
from functools import cached_property, lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATALOG = Path(__file__).with_name("teams.toml")
ESPN_LOGO_URL = "https://a.espncdn.com/i/teamlogos/soccer/500/{id}.png"
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

# ESPN league code -> name shown in the newsletter.
LEAGUES = {
    "bra.1": "Brasileirão",
    "bra.2": "Série B",
    "conmebol.libertadores": "Libertadores",
    "conmebol.sudamericana": "Sul-Americana",
    "bra.copa_do_brazil": "Copa do Brasil",
    "bra.copa_do_nordeste": "Copa do Nordeste",
    "bra.camp.carioca": "Carioca",
    "bra.camp.paulista": "Paulistão",
    "bra.supercopa_do_brazil": "Supercopa",
    "fifa.cwc": "Mundial de Clubes",
}


class UnknownTeam(LookupError):
    """Slug not in the catalog; the message lists the valid ones."""


class Team(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str  # "Náutico"
    newsletter: str  # "Timbu News"
    fans: str  # "alvirrubros"
    espn_id: int = Field(gt=0)
    ge_url: str
    news_query: str  # Google News search
    keywords: tuple[str, ...]  # words that make a title or text about the team
    accent: str  # brand color in the e-mail
    leagues: tuple[str, ...] = Field(min_length=1)  # ESPN league codes, all tracked
    # League of the table, campaign and player rankings; None when ESPN has no table for it.
    league: str | None = None
    other_sports: dict[str, str] = Field(default_factory=dict)  # name -> Google News query
    # False: in the catalog but not on the portal, the sign-up or `due --all` (a team moving in).
    listed: bool = True
    # Sender mailbox (before the @; the domain comes from NEWSLETTER_FROM). One per newsletter so
    # each has its own avatar in Gmail (a Google account per address, created by the owner).
    sender: str | None = None

    @field_validator("accent")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not HEX_COLOR.match(v):
            raise ValueError(f"accent must be #RRGGBB, got {v!r}")
        return v

    @model_validator(mode="after")
    def _known_leagues(self) -> "Team":
        unknown = [code for code in (*self.leagues, self.league) if code and code not in LEAGUES]
        if unknown:
            raise ValueError(f"unknown ESPN leagues {unknown}; add them to LEAGUES")
        if self.league and self.league not in self.leagues:
            raise ValueError(f"league {self.league!r} must be one of leagues")
        return self

    @property
    def league_name(self) -> str | None:
        return LEAGUES[self.league] if self.league else None

    def sender_address(self, base: str) -> str:
        """`almirante@<base's domain>`; the base address itself when the team has no mailbox."""
        if not self.sender:
            return base
        return f"{self.sender}@{base.rpartition('@')[2]}"

    @property
    def logo(self) -> str:
        return ESPN_LOGO_URL.format(id=self.espn_id)

    @cached_property
    def pattern(self) -> re.Pattern[str]:
        words = "|".join(re.escape(k) for k in sorted(self.keywords, key=len, reverse=True))
        return re.compile(rf"(?<!\w)(?:{words})(?!\w)", re.IGNORECASE)

    def mentions(self, text: str) -> bool:
        return bool(self.pattern.search(text))

    def __hash__(self) -> int:
        return hash(self.slug)


class _Catalog(BaseModel):
    teams: dict[str, Team]

    @model_validator(mode="after")
    def _unique_espn_ids(self) -> "_Catalog":
        seen: dict[int, str] = {}
        for slug, team in self.teams.items():
            if team.espn_id in seen:
                raise ValueError(f"espn_id {team.espn_id} used by {seen[team.espn_id]} and {slug}")
            seen[team.espn_id] = slug
        return self


def load_teams(path: Path | None = None) -> dict[str, Team]:
    raw = tomllib.loads((path or CATALOG).read_text(encoding="utf-8"))
    return _Catalog(teams={slug: {"slug": slug, **data} for slug, data in raw.items()}).teams


@lru_cache
def _default_teams() -> dict[str, Team]:
    return load_teams()


def get_team(slug: str) -> Team:
    teams = _default_teams()
    try:
        return teams[slug]
    except KeyError:
        raise UnknownTeam(f"unknown team {slug!r}; valid: {', '.join(sorted(teams))}") from None
