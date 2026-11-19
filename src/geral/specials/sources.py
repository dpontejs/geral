"""Passages of the pt Wikipedia a story can be written from, each with a key of its own.

- clube: sections of the club article (or subsections under one) about its symbols, mascot,
  stadium, fans, anthem, kit, and its curiosities;
- jogo: the subsections of the club's "História" and the historic-games sections of its classics;
- idolo: articles linking to the club whose text calls the player an "ídolo" near the club's name
  (intro and "Carreira" only).

Short sections are left out: too little text is where a model starts making things up.
"""

import re
from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from geral.games import mediawiki
from geral.teams import Team

PTWIKI = "https://pt.wikipedia.org/w/api.php"
MIN_WORDS = 80
MAX_WORDS = 600
IDOL_DISTANCE = 150  # characters between "ídolo" and a club term
IDOL_CANDIDATES = 50
HEADING = re.compile(r"^(={2,}) *(.+?) *\1 *$", re.MULTILINE)
CLUB_SECTIONS = re.compile(
    r"símbolo|mascote|estádio|sede|torcida|hino|uniforme|curiosidade", re.IGNORECASE
)
GAME_SECTIONS = re.compile(
    r"jogos? históricos?|goleadas?|primeiro jogo|finais|final\b", re.IGNORECASE
)

Kind = Literal["jogo", "idolo", "clube"]


class Passage(BaseModel):
    kind: Kind
    key: str  # url#section: a source already used (or refused) is never tried again
    title: str
    url: str
    text: str
    qid: str | None = None  # the page's Wikidata item (idols: their birth date)


class Section(BaseModel):
    h2: str  # "" for the introduction
    h3: str | None
    text: str

    @property
    def name(self) -> str:
        return self.h3 or self.h2

    @property
    def path(self) -> str:
        return f"{self.h2}/{self.h3}" if self.h3 else self.h2


def url_of(title: str) -> str:
    return "https://pt.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))


def extract_page(client: httpx.Client, title: str) -> tuple[str, str | None]:
    """The article as plain text ("== Heading ==" lines included; "" when it does not exist)
    and its Wikidata id."""
    data = mediawiki.api(
        client,
        PTWIKI,
        {
            "action": "query",
            "prop": "extracts|pageprops",
            "ppprop": "wikibase_item",
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
        },
    )
    pages = data.get("query", {}).get("pages", [])
    if not pages:
        return "", None
    return pages[0].get("extract", ""), pages[0].get("pageprops", {}).get("wikibase_item")


def extract(client: httpx.Client, title: str) -> str:
    return extract_page(client, title)[0]


def sections(text: str) -> list[Section]:
    found, h2, h3, start = [], "", None, 0
    for heading in HEADING.finditer(text):
        level, name = heading.groups()
        if len(level) > 3:
            continue  # deeper headings stay inside their section
        found.append(Section(h2=h2, h3=h3, text=text[start : heading.start()].strip()))
        if len(level) == 2:
            h2, h3 = name, None
        else:
            h3 = name
        start = heading.end()
    found.append(Section(h2=h2, h3=h3, text=text[start:].strip()))
    return found


def _passage(
    kind: Kind, title: str, section: str | None, text: str, path: str | None = None
) -> Passage | None:
    """`path` ("História/Anos 60") makes the key; `section` is what the reader sees."""
    words = text.split()
    if len(words) < MIN_WORDS:
        return None
    url = url_of(title)
    key = f"{url}#{(path or section).replace(' ', '_')}" if section else url
    shown = f"{title} — {section}" if section else title
    return Passage(kind=kind, key=key, title=shown, url=url, text=" ".join(words[:MAX_WORDS]))


def _club(title: str, text: str) -> list[Passage]:
    found = []
    for s in sections(text):
        if s.h2 == "História" and s.h3:
            found.append(_passage("jogo", title, s.h3, s.text, s.path))
        # The heading or the section above it ("Sedes e estádios" > "O Mutange").
        elif s.h2 and CLUB_SECTIONS.search(s.path):
            found.append(_passage("clube", title, s.name, s.text, s.path))
    return [p for p in found if p]


def _classic(title: str, text: str) -> list[Passage]:
    found = [
        _passage("jogo", title, s.name, s.text, s.path)
        for s in sections(text)
        if s.h2 and GAME_SECTIONS.search(s.name)
    ]
    return [p for p in found if p]


def _is_idol(text: str, club_terms: tuple[str, ...]) -> bool:
    terms = "|".join(re.escape(t) for t in club_terms)
    near = rf"ídolo.{{0,{IDOL_DISTANCE}}}(?:{terms})|(?:{terms}).{{0,{IDOL_DISTANCE}}}ídolo"
    return re.search(near, text, re.IGNORECASE | re.DOTALL) is not None


def _idol(title: str, text: str, club_terms: tuple[str, ...]) -> Passage | None:
    parts = sections(text)
    career = [s for s in parts if s.h2.startswith("Carreira")]
    if not career or not _is_idol(text, club_terms):
        return None  # without a career section it is not a player's article
    body = "\n\n".join([parts[0].text, *(s.text for s in career)])
    passage = _passage("idolo", title, None, body)
    # The part about the club may be past the cut: then the model would only see other clubs.
    if passage is None or not _names_club(passage.text, club_terms):
        return None
    return passage


def _names_club(text: str, club_terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(t)}\b", text, re.IGNORECASE) for t in club_terms)


def idol_titles(client: httpx.Client, team: Team) -> list[str]:
    data = mediawiki.api(
        client,
        PTWIKI,
        {
            "action": "query",
            "list": "search",
            "srsearch": f'"ídolo" linksto:"{team.wikipedia}"',
            "srlimit": IDOL_CANDIDATES,
        },
    )
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def passages(client: httpx.Client, team: Team) -> list[Passage]:
    """Every passage of the team's sources, long enough to tell a story."""
    if not team.wikipedia:
        return []
    found = _club(team.wikipedia, extract(client, team.wikipedia))
    for classic in team.classics:
        found += _classic(classic, extract(client, classic))
    for title in idol_titles(client, team):
        if title == team.wikipedia or title in team.classics:
            continue
        text, qid = extract_page(client, title)
        idol = _idol(title, text, team.club_terms)
        if idol:
            found.append(idol.model_copy(update={"qid": qid}))
    return found
