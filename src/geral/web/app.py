"""The Geral page: portal, sign-up to one or more teams, confirmation and unsubscribe per team.

Run with `uvicorn geral.web.app:create_app --factory`. Behind Caddy, start uvicorn with
`--proxy-headers` so the rate limit sees the visitor's IP.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import re
import secrets
import sqlite3
import unicodedata
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import BackgroundTasks, FastAPI, Form, Query, Request, Response
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from geral.central.build import SLUGS as SERIE_SLUGS
from geral.central.page import band_colors, short_day, short_time
from geral.central.refresh import Refresher, snapshot_path
from geral.central.store import load_snapshot
from geral.config import Settings, get_settings
from geral.games import calendario, craque, onde_jogou, quem_e
from geral.games.carreira import codigo as carreira_codigo
from geral.games.carreira import dados as carreira_dados
from geral.games.carreira import draft as carreira_draft
from geral.games.carreira import motor as carreira_motor
from geral.games.carreira import regras as carreira_regras
from geral.games.velha import base as velha_base
from geral.games.velha import board as velha_tabuleiro
from geral.games.velha import busca as velha_busca
from geral.games.velha import diario as velha_diario
from geral.games.velha import duelo as velha_duelo
from geral.games.velha import judge as velha_judge
from geral.general import GENERAL_EDITION, GENERAL_SLUG
from geral.models import Newsletter
from geral.render.renderer import render
from geral.send.resend_sender import UNSUBSCRIBE_PLACEHOLDER, personalize
from geral.teams import Team, load_teams
from geral.web.banners import BannerStore
from geral.web.bolao import TZ, BolaoStore
from geral.web.carreira_placar import PlacarStore
from geral.web.mailer import Mailer, MailError, mailer_from_settings
from geral.web.notes import NoteStore
from geral.web.palette import club_palette
from geral.web.scoreboard import animation_svg
from geral.web.store import RequestResult, SubscriberStore, normalize
from geral.web.team_requests import PUBLIC_MIN_VOTES, TeamRequestStore, network, team_key
from geral.web.tokens import make_token, read_token
from geral.web.velha_partidas import (
    DuelConflict,
    DuelNotFound,
    DuelStore,
    NotYourTurn,
    duel_events,
)
from geral.web.welcome import add_welcome

logger = logging.getLogger(__name__)

CONFIRM_MAX_AGE = timedelta(days=7)
SIGNUPS_PER_IP = 5
SIGNUP_WINDOW = timedelta(hours=1)
# Deliberately strict: letters, digits and the usual symbols; dot-separated domain labels.
EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
)
CONFIRMATIONS_PER_DAY = 30  # global cap: protects the Resend quota and the domain reputation
MAX_EMAIL_LENGTH = 254
WELCOME_PREFIX = "Boas-vindas! "
MIN_NICKNAME, MAX_NICKNAME = 3, 20
# Team requests: a name as people write it (accents, dots, apostrophes), and a few per IP.
TEAM_NAME_RE = re.compile(r"^[\w .'-]+$")
MIN_TEAM_NAME, MAX_TEAM_NAME = 2, 40
REQUESTS_PER_IP = 10
TOP_REQUESTS = 10
REQUESTS_IN_EMAIL = 5
PANEL_PURPOSE = "team-requests"
PANEL_MAX_AGE = timedelta(days=30)
REVIEW_PURPOSE = "review"  # the owner's review page (one link per draft e-mail)
REVIEW_MAX_AGE = timedelta(days=7)
SCORE_RE = re.compile(r"^(\d)-(\d)$")
# Shown in every follower's e-mail: letters, digits, spaces, hyphens and apostrophes only (no
# links, no line breaks).
NICKNAME_RE = re.compile(r"^[\w' -]+$")
STATIC = Path(__file__).resolve().parents[1] / "static"
# The scoreboard clock: Brasília time, no daylight saving since 2019 (no tzdata in the image).
DUELS_PER_NETWORK = 20  # jogo da velha duels created per network per hour
CARREIRAS_POR_REDE = 60  # Carreira careers counted in the Fábrica de craques per network per hour
PAST_LISTED = 30  # past puzzles linked on a game page; older ones stay playable by address
BRASILIA = timezone(timedelta(hours=-3))

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
# Jinja only autoescapes .html by default; ours end in .html.j2 and show user input.
templates.env.autoescape = select_autoescape(["html.j2"])
templates.env.globals["scoreboard_animation"] = animation_svg


def _asset_version() -> str:
    """A short hash of the site's own scripts and styles: their links change when they do, so a
    browser never keeps an old copy (`/static/geral/jogos.css?v=...`)."""
    digest = hashlib.sha256()
    for path in sorted((STATIC / "geral").glob("*.[cj]s*")):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:8]


templates.env.globals["asset_version"] = _asset_version()
templates.env.globals["band_colors"] = band_colors
templates.env.filters["short_day"] = short_day
templates.env.filters["short_time"] = short_time


class RateLimiter:
    """At most `limit` hits per key within `window` (in memory: one process, few users)."""

    def __init__(self, limit: int, window: timedelta) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, key: str, now: datetime) -> bool:
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


class EditionIn(BaseModel):
    subject: str
    html: str
    text: str


class DraftIn(BaseModel):
    label: str
    newsletter: dict  # a geral.models.Newsletter dumped as JSON
    build_at: AwareDatetime
    send_at: AwareDatetime


class StoryIn(BaseModel):
    kind: Literal["jogo", "idolo", "clube"]
    title: str
    body: str
    summary: str
    fact_date: str = Field(default="", pattern=r"^(\d{4}(-\d{2}-\d{2})?)?$")
    source_key: str
    source_url: str
    source_title: str
    rejected_reason: str | None = None  # refused by the verifier: kept so the source is skipped


class BirthdayIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    birth_date: date
    source_url: str = Field(min_length=1, max_length=500)


class DrawIn(BaseModel):
    label: str  # the edition the story goes in (a rebuild gets the same story)
    reserve: bool = True  # False for a preview: the stock is left as it is


class BolaoMatchIn(BaseModel):
    opponent: str
    home: bool  # our team plays at home
    kickoff: AwareDatetime  # compared with the page's clock: a naive time would break /palpite


class BolaoResultIn(BaseModel):
    our_goals: int = Field(ge=0)
    their_goals: int = Field(ge=0)


def parse_score(text: str) -> tuple[int, int] | None:
    """'2-1' -> (2, 1); each side 0-9, anything else is None."""
    found = SCORE_RE.match(text.strip())
    return (int(found[1]), int(found[2])) if found else None


def is_valid_email(email: str) -> bool:
    return len(email) <= MAX_EMAIL_LENGTH and EMAIL_RE.match(email) is not None


def unsubscribe_purpose(team: str | None) -> str:
    """`unsubscribe:<slug>` leaves one team (the newsletter footer); `unsubscribe` leaves all."""
    return f"unsubscribe:{team}" if team else "unsubscribe"


class PlayerGuessesIn(BaseModel):
    palpites: list[Annotated[str, Field(max_length=20)]] = Field(max_length=quem_e.MAX_GUESSES)
    desistiu: bool = False

    @model_validator(mode="after")
    def guess_or_give_up(self) -> "PlayerGuessesIn":
        if not self.palpites and not self.desistiu:
            raise ValueError("palpites: pelo menos um, ou desistiu")
        return self


class ClubGuessesIn(BaseModel):
    palpites: list[Annotated[str, Field(max_length=60)]] = Field(max_length=40)
    desistiu: bool = False


class CarreiraOfertaIn(BaseModel):
    clube: str | None = Field(default=None, max_length=40)  # the start: brings regional idols


class CarreiraIn(BaseModel):
    semente_draft: str = Field(min_length=1, max_length=40)
    semente: str | None = Field(default=None, min_length=1, max_length=40)  # drawn when absent
    craque: carreira_motor.Craque
    roubos: list[carreira_draft.Roubo] = Field(max_length=9)
    escolhas: list[int] = Field(default=[], max_length=carreira_motor.MAX_RESPOSTAS)
    # Only Completa is offered; "rapida" still comes from pages opened before it was removed.
    modo: Literal["rapida", "completa"] = "completa"
    minijogos: bool = False  # the cup final's penalty on screen; the form sends it
    # The data version the career started with (sent by the page): a deploy that changes the data
    # mid-career would replay it differently, so the page is told instead. Absent: no check.
    versao: str | None = Field(default=None, max_length=40)


class VelhaIn(BaseModel):
    chutes: list[velha_judge.Guess] = Field(max_length=velha_judge.MAX_GUESSES + 1)


class DuelTokenIn(BaseModel):
    token: str = Field(max_length=40)


class DuelMoveIn(BaseModel):
    token: str = Field(max_length=40)
    vez_n: int = Field(ge=0)
    casa: int | None = None
    jogador: str | None = Field(default=None, max_length=20)
    pular: bool = False  # pass the turn


class DuelProposalIn(BaseModel):
    token: str = Field(max_length=40)
    tipo: Literal["encerrar", "sortear"]


class DuelAnswerIn(BaseModel):
    token: str = Field(max_length=40)
    aceita: bool
    tipo: Literal["encerrar", "sortear"] | None = None  # what the player saw being proposed


class DuelIn(BaseModel):
    tabuleiro: str = Field(max_length=200)
    jogadas: list[velha_duelo.Move] = Field(max_length=60)


class WordGuessesIn(BaseModel):
    guesses: list[Annotated[str, Field(max_length=20)]] = Field(
        min_length=1, max_length=craque.MAX_GUESSES
    )


def create_app(
    settings: Settings | None = None,
    store: SubscriberStore | None = None,
    mailer: Mailer | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    teams: dict[str, Team] | None = None,
    bolao: BolaoStore | None = None,
    team_requests: TeamRequestStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    secret = settings.SUBSCRIBE_SECRET
    if not secret:
        raise RuntimeError("SUBSCRIBE_SECRET is required to sign confirmation links")
    store = store or SubscriberStore(settings.SUBSCRIBERS_DB)
    mailer = mailer or mailer_from_settings(settings)
    bolao = bolao or BolaoStore(store.path)  # same SQLite: the ranking joins the subscriptions
    team_requests = team_requests or TeamRequestStore(store.path)
    duels = DuelStore(store.path)  # jogo da velha by link: its own table in the same SQLite
    duel_limiter = RateLimiter(DUELS_PER_NETWORK, timedelta(hours=1))
    banners = BannerStore(store.path)  # `geral especial`: a title on top of one team's edition
    notes = NoteStore(store.path)  # `geral novidade`: on top of each team's next edition
    placar = PlacarStore(store.path)  # Carreira's Fábrica de craques: its own table, same SQLite
    placar_limiter = RateLimiter(CARREIRAS_POR_REDE, timedelta(hours=1))
    catalog = teams if teams is not None else load_teams()
    # Teams people can see and join; unlisted ones (moving in) still work for links and the API.
    listed = {slug: team for slug, team in catalog.items() if team.listed}
    clubs = dict(catalog)  # the torcidas only, for "already here" on team requests
    # The edição geral is joined like a team (links, API, saved edition) but is not a torcida.
    catalog = {**catalog, GENERAL_SLUG: GENERAL_EDITION}
    joinable = {**listed, GENERAL_SLUG: GENERAL_EDITION}
    legacy_team = catalog.get(settings.LEGACY_TEAM or "")
    legacy_secret = settings.LEGACY_SUBSCRIBE_SECRET if legacy_team else None
    legacy_hosts = {h.strip().lower() for h in settings.LEGACY_HOSTS.split(",") if h.strip()}

    def read_legacy(purpose: str, token: str) -> str | None:
        """E-mail in a token the moved-in app signed (its unsubscribe and bet links)."""
        return read_token(legacy_secret, purpose, token, now()) if legacy_secret else None

    limiter = RateLimiter(SIGNUPS_PER_IP, SIGNUP_WINDOW)
    request_limiter = RateLimiter(REQUESTS_PER_IP, SIGNUP_WINDOW)
    # A request for a team already here points to it, by slug, name or newsletter (nicknames
    # are often shared by several clubs). Teams moving in count as here too.
    known = {
        team_key(word): team
        for team in clubs.values()
        for word in (team.slug, team.name, team.newsletter)
    }
    public_url = settings.PUBLIC_URL.rstrip("/")

    def link(path: str, purpose: str, email: str) -> str:
        token = make_token(secret, purpose, email, now())
        return f"{public_url}{path}?{urlencode({'token': token})}"

    central_file = snapshot_path(settings)  # the Central's snapshot (docs/features/central.md)

    def page(request: Request, name: str, status: int = 200, **context) -> HTMLResponse:
        context.setdefault("public_url", public_url)
        return templates.TemplateResponse(request, name, context, status_code=status)

    def message(request: Request, title: str, text: str, status: int = 200, **extra):
        return page(request, "message.html.j2", status, title=title, text=text, **extra)

    def portal(request: Request, status: int = 200, **context) -> HTMLResponse:
        # The torcidas only: the edição geral is not one (scoreboard, totals, ticket number).
        counts = {slug: n for slug, n in store.counts().items() if slug in listed}
        return page(
            request,
            "index.html.j2",
            status,
            teams=list(listed.values()),
            general=GENERAL_EDITION,
            editions=store.latest_editions(),
            counts=counts,
            ranking=sorted(listed.values(), key=lambda t: (-counts.get(t.slug, 0), t.newsletter)),
            clock=now().astimezone(BRASILIA),
            top_request=next(iter(team_requests.top(1)), None),  # only past the public minimum
            central=load_snapshot(central_file),
            **context,
        )

    craque_pools: dict[str, list[craque.Craque]] = {}

    def craque_editions() -> dict[str, list[craque.Craque]]:
        """'geral' plus every listed team whose curated list is complete, built on first use."""
        if not craque_pools:
            lists = craque.load_lists()
            built = {"geral": craque.pool(lists, "geral")}
            for slug in listed:
                if games := craque.pool(lists, slug):
                    built[slug] = games
            craque_pools.update(built)  # published at once: a request alongside never sees half
        return craque_pools

    career_state: dict[str, object] = {}

    def careers() -> onde_jogou.Data:
        if "data" not in career_state:
            career_state["data"] = onde_jogou.load()
        return career_state["data"]

    def career_editions() -> dict[str, list[onde_jogou.Jogador]]:
        """'geral' plus every listed team with players who passed through it, built on first use."""
        if "pools" not in career_state:
            data = careers()
            names = {slug: team.name for slug, team in listed.items()}
            built = {"geral": onde_jogou.pool(data, "geral", names)}
            for slug in listed:
                if players := onde_jogou.pool(data, slug, names):
                    built[slug] = players
            career_state["pools"] = built  # published at once
        return career_state["pools"]

    def given_clubs(edition: str) -> set[str]:
        """The edition's own team, shown from the start ('geral' gives nothing)."""
        team = listed.get(edition)
        return onde_jogou.team_clubs(careers(), team.name) if team else set()

    def who_editions() -> dict[str, list[onde_jogou.Jogador]]:
        """Same editions as 'Onde jogou?', in the 'Quem é?' daily order."""
        if "who" not in career_state:
            data = careers()
            names = {slug: team.name for slug, team in listed.items()}
            career_state["who"] = {
                slug: quem_e.pool(data, slug, names) for slug in career_editions()
            }
        return career_state["who"]

    def who_number() -> int:
        return max(1, quem_e.puzzle_number(now().astimezone(BRASILIA).date()))

    def daily_player(
        game: str, edition: str, players: list[onde_jogou.Jogador], number: int
    ) -> onde_jogou.Jogador:
        """The day's player: frozen in the calendar once played, else the edition's order."""
        if "calendar" not in career_state:
            career_state["calendar"] = calendario.load()
        frozen = calendario.answers(career_state["calendar"], game, edition)
        return calendario.pick(players, number, frozen, key=lambda j: j.wikidata)

    def daily_craque(edition: str, games: list[craque.Craque], number: int) -> craque.Craque:
        """The day's craque: frozen in the calendar once played, else the edition's order."""
        if "calendar" not in career_state:
            career_state["calendar"] = calendario.load()
        frozen = calendario.answers(career_state["calendar"], "craque-do-dia", edition)
        return calendario.pick(games, number, frozen, key=lambda c: c.answer)

    velha_state: dict[str, velha_base.Base] = {}

    def velha() -> velha_base.Base:
        if "base" not in velha_state:
            velha_state["base"] = velha_base.load()
        return velha_state["base"]

    def velha_number() -> int:
        return max(1, velha_diario.puzzle_number(now().astimezone(BRASILIA).date()))

    def velha_board(number: int):
        """Board #number: frozen in the calendar once played, else the seeded draw."""
        if "calendar" not in career_state:
            career_state["calendar"] = calendario.load()
        frozen = calendario.answers(career_state["calendar"], velha_diario.GAME, "geral")
        return velha_diario.daily_board(velha(), number, frozen)

    def game_url(path: str, edition: str, number: int | None = None) -> str:
        if number is not None:
            return f"/jogos/{path}/{edition}/{number}"
        return f"/jogos/{path}" if edition == "geral" else f"/jogos/{path}/{edition}"

    def which_puzzle(
        request: Request, path: str, edition: str, asked: str | None, today: int, launch
    ) -> tuple[int, dict] | Response:
        """Today's puzzle, or a past one (`number`), with what the page needs to show which.

        Today's own number goes to today's address; a future (or zero) number is not found.
        A past puzzle is played like today's, but it doesn't count in the streak.
        """
        # "3" only: "03", "abc" or "-1" would be the same page twice or a raw error.
        number = int(asked) if asked and re.fullmatch(r"[1-9]\d{0,4}", asked) else None
        if number == today:
            return RedirectResponse(game_url(path, edition), status_code=307)
        if asked is not None and (number is None or not 1 <= number < today):
            return message(
                request,
                "Jogo não encontrado",
                "Esse número ainda não saiu. O jogo de hoje está esperando por você.",
                status=404,
                link_url=game_url(path, edition),
                link_label="Jogar o de hoje",
            )
        shown = number or today

        def day(n: int) -> str:
            return (launch + timedelta(days=n - 1)).strftime("%d/%m")

        past = [
            {"number": n, "day": day(n), "url": game_url(path, edition, n)}
            for n in range(today - 1, max(0, today - 1 - PAST_LISTED), -1)
        ]
        context = {
            "archive": number is not None,
            "day": day(shown),
            "today_url": game_url(path, edition),
            "past": past,
        }
        return shown, context

    def games() -> list[dict]:
        """The daily games, in the order the site shows them."""
        return [
            {
                "path": "craque-do-dia",
                "name": "Craque do dia",
                "desc": "Adivinhe o ídolo ou artilheiro do dia, letra por letra, em seis chutes.",
                "editions": craque_editions(),
                "number": craque_number(),
            },
            {
                "path": "onde-jogou",
                "name": "Onde jogou?",
                "desc": "Um craque por dia: diga por quais clubes ele passou antes de errar "
                "três vezes.",
                "editions": career_editions(),
                "number": career_number(),
            },
            {
                "path": "quem-e",
                "name": "Quem é?",
                "desc": "A carreira inteira no placar, clubes e anos: adivinhe o jogador em seis "
                "chutes.",
                "editions": who_editions(),
                "number": who_number(),
            },
            {
                "path": "carreira",
                "name": "Carreira",
                "desc": "Roube um atributo de cada lenda, monte seu craque e viva a carreira dele "
                "até a aposentadoria. Jogue quantas vezes quiser.",
                "editions": dict.fromkeys(carreira_edicoes(), True),
                "number": None,  # free play: no game of the day
            },
            {
                "path": "velha",
                "name": "Jogo da velha",
                "desc": "Três linhas, três colunas: ache um jogador para cada cruzamento em até "
                f"{velha_judge.MAX_GUESSES} chutes.",
                "editions": {"geral": True},  # no team edition
                "number": velha_number(),
            },
        ]

    def game_tabs(current: str, edition: str) -> list[dict]:
        """Switch games keeping the edition when the other game has it (else its geral)."""
        return [
            {
                "name": g["name"],
                "url": game_url(g["path"], edition if edition in g["editions"] else "geral"),
                "current": g["path"] == current,
            }
            for g in games()
        ]

    def career_number() -> int:
        return max(1, onde_jogou.puzzle_number(now().astimezone(BRASILIA).date()))

    def craque_number() -> int:
        return max(1, craque.puzzle_number(now().astimezone(BRASILIA).date()))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        refresher = None
        if settings.CENTRAL_REFRESH > 0:  # the Central's snapshot, rebuilt in a thread
            refresher = Refresher(central_file, settings.CENTRAL_REFRESH)
            refresher.start()
        yield
        if refresher:
            refresher.stop()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    if legacy_team:
        # Old e-mails load the moved-in app's brand from the root of /static.
        for name in ("logo-email.png", "icon-512.png", "og-image.png"):
            path = STATIC / legacy_team.slug / name

            @app.get(f"/static/{name}", include_in_schema=False)
            def legacy_brand(path: Path = path):
                return FileResponse(path, media_type="image/png")

    # Brands (mascot, e-mail logo, link preview) of the hub and of every team.
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def index(request: Request):
        if request.url.hostname and request.url.hostname.lower() in legacy_hosts:
            return RedirectResponse(f"{public_url}/", status_code=301)
        return portal(request)

    def no_edition(request: Request) -> HTMLResponse:
        return message(
            request,
            "Edição não encontrada",
            "Essa torcida ainda não tem edição publicada. Volte para a Geral e se inscreva "
            "para receber a primeira.",
            status=404,
        )

    @app.get("/t/{team}", response_class=HTMLResponse)
    def team_page(request: Request, team: str):
        """The team's latest edition inside the site's frame (header, way back home)."""
        edition = store.latest_edition(team) if team in catalog else None
        if edition is None:
            return no_edition(request)
        newsletter = catalog[team].newsletter
        # "Geral — Edição geral — 09/11/2026: ..." or "Elefante News — Notícias — ...": no names
        headline = edition.subject.removeprefix("Geral — ").removeprefix(f"{newsletter} — ")
        return page(
            request,
            "edicao.html.j2",
            team=catalog[team],
            club=club_palette(clubs.get(team)),  # the edição geral keeps the pitch
            headline=headline,
        )

    @app.get("/t/{team}/edicao", response_class=HTMLResponse)
    def team_edition(request: Request, team: str):
        """The newsletter itself, as e-mailed; personal links point to the portal."""
        edition = store.latest_edition(team) if team in catalog else None
        if edition is None:
            return no_edition(request)
        # A public page: no bet card (the links are personal) and no personal unsubscribe.
        html = personalize(edition.html, None).replace(UNSUBSCRIBE_PLACEHOLDER, f"{public_url}/")
        # Shown in a frame on /t/<team>: its links open on the whole page.
        base = '<base target="_top">'
        head = re.search(r"<head\b[^>]*>", html, re.IGNORECASE)
        if head:
            html = html[: head.end()] + base + html[head.end() :]
        else:  # after the doctype, if any: before it the page would render in quirks mode
            doctype = re.match(r"\s*<!doctype[^>]*>", html, re.IGNORECASE)
            cut = doctype.end() if doctype else 0
            html = html[:cut] + base + html[cut:]
        return HTMLResponse(html)

    @app.get("/subscribe")
    def subscribe_reload():
        # Reloading the "check your inbox" page, or a link preview, lands here.
        return RedirectResponse("/", status_code=303)

    @app.get("/favicon.ico")
    def favicon():
        return RedirectResponse("/static/geral/icon-512.png", status_code=301)

    @app.post("/subscribe", response_class=HTMLResponse)
    async def subscribe(request: Request):
        form = await request.form()
        email = normalize(str(form.get("email", "")))
        picks = dict.fromkeys(map(str, form.getlist("team")))
        chosen = [joinable[s] for s in picks if s in joinable]
        check_inbox = (
            "Confira seu e-mail",
            "Se o endereço estiver certo, você vai receber um link para confirmar a inscrição. "
            "Não chegou? Dá uma olhada no spam.",
        )
        if form.get("website"):  # honeypot: only bots fill the hidden field
            return message(request, *check_inbox)
        picked = [t.slug for t in chosen]
        if not is_valid_email(email):
            return portal(
                request, 400, error="Digite um e-mail válido.", email=email, picked=picked
            )
        if not chosen:
            return portal(
                request, 400, error="Escolha pelo menos uma torcida.", email=email, picked=picked
            )
        client_ip = request.client.host if request.client else "unknown"
        if not limiter.allow(client_ip, now()):
            return message(
                request, "Muitas tentativas", "Espere um pouco e tente de novo.", status=429
            )

        store.purge(now())
        if store.confirmations_sent_since(now() - timedelta(days=1)) >= CONFIRMATIONS_PER_DAY:
            logger.warning("Daily cap of %d confirmation e-mails reached", CONFIRMATIONS_PER_DAY)
            return message(
                request,
                "Muitas inscrições hoje",
                "Recebemos inscrições demais nas últimas horas. Tente de novo amanhã.",
                status=429,
            )
        if store.request(email, picked, now()) is RequestResult.SEND_CONFIRMATION:
            pending = [catalog[s] for s in store.pending_teams(email) if s in catalog]
            try:
                mailer.send_confirmation(email, link("/confirm", "confirm", email), pending)
            except MailError as e:
                logger.error("Confirmation e-mail failed: %s", e)
                store.forget_confirmation(email)
                return message(
                    request,
                    "Não deu para enviar",
                    "Não conseguimos enviar o e-mail de confirmação agora. Tente de novo em "
                    "alguns minutos.",
                    status=502,
                )
        return message(request, *check_inbox)

    @app.get("/confirm", response_class=HTMLResponse)
    def confirm(request: Request, token: str = ""):
        email = read_token(secret, "confirm", token, now(), max_age=CONFIRM_MAX_AGE)
        before = store.get(email) if email else None
        first_time = before is not None and before.status == "pending"
        activated = store.confirm(email, now()) if email else None
        if activated is None:
            return message(
                request,
                "Link inválido ou expirado",
                "Esse link de confirmação não vale mais. Faça a inscrição de novo no portal.",
                status=400,
            )
        new_teams = [catalog[s] for s in activated if s in catalog]
        welcomed = [team for team in new_teams if send_latest_edition(email, team)]
        if first_time:
            notify_owner(email, new_teams)
        joined = new_teams or teams_of(email)
        clubs_joined = [t for t in joined if t.slug != GENERAL_SLUG]
        parts = []
        if clubs_joined:
            names = ", ".join(t.newsletter for t in clubs_joined)
            parts.append(f"{names} antes e depois de cada jogo")
        if len(clubs_joined) < len(joined):
            parts.append(f"a {GENERAL_EDITION.newsletter} toda segunda de manhã")
        text = f"Pronto: você está na Geral e vai receber {' e '.join(parts)}."
        if welcomed:
            text += " Mandamos a última edição para o seu e-mail para você já ir lendo."
        return message(request, "Inscrição confirmada!", text)

    def teams_of(email: str) -> list[Team]:
        return [catalog[s] for s in store.teams_of(email) if s in catalog]

    def notify_owner(email: str, new_teams: list[Team]) -> None:
        if not settings.NOTIFY_EMAIL:
            return
        lines = [f"{t.newsletter}: {store.counts().get(t.slug, 0)} ativos" for t in new_teams]
        try:
            mailer.send_notification(
                settings.NOTIFY_EMAIL,
                f"Novo na Geral: {email}",
                f"{email} confirmou a inscrição.\n\n" + "\n".join(lines) + "\n",
            )
        except MailError as e:
            logger.error("New subscriber notification failed: %s", e)

    def panel_link() -> str:
        token = make_token(secret, PANEL_PURPOSE, settings.NOTIFY_EMAIL, now())
        return f"{public_url}/pedidos?{urlencode({'t': token})}"

    def notify_request(name: str, votes: int, position: int, email: str) -> None:
        """Tell the owner about a new vote for a team, like a new subscriber."""
        if not settings.NOTIFY_EMAIL:
            return
        plural = "s" if votes != 1 else ""
        try:  # the vote is already stored: a failure here only costs the owner the ranking
            top = team_requests.top(REQUESTS_IN_EMAIL, min_votes=1)
            ranking = "".join(f"{n}. {t.name} · {t.votes}\n" for n, t in enumerate(top, 1))
        except Exception:
            logger.exception("Team request ranking failed")
            ranking = "(indisponível)\n"
        try:
            mailer.send_notification(
                settings.NOTIFY_EMAIL,
                f"Pedido de time: {name}",
                f"{name}: {votes} pedido{plural}, {position}º entre os mais pedidos.\n"
                f"E-mail para avisar: {email or 'não informado'}\n\n"
                f"Mais pedidos:\n{ranking}\n"
                f"Todos os pedidos (link vale {PANEL_MAX_AGE.days} dias): {panel_link()}\n",
            )
        except MailError as e:
            logger.error("Team request notification failed: %s", e)

    def send_latest_edition(email: str, team: Team) -> bool:
        edition = store.latest_edition(team.slug)
        if edition is None:
            return False
        try:
            html, text = add_welcome(edition.html, edition.text, team)
            mailer.send_edition(
                email,
                team,
                WELCOME_PREFIX + edition.subject,
                html,
                text,
                link("/unsubscribe", unsubscribe_purpose(team.slug), email),
                # The stored edition keeps the bolão card: the newcomer can bet before kickoff.
                bet_token=make_token(secret, "bet", email, now()),
            )
        except MailError as e:
            logger.error("Welcome edition of %s failed: %s", team.slug, e)
            return False
        return True

    def read_unsubscribe(token: str) -> tuple[str, Team | None] | None:
        """(email, team) behind an unsubscribe token; team None leaves every team."""
        email = read_token(secret, unsubscribe_purpose(None), token, now())
        if email is not None:
            return email, None
        for team in catalog.values():
            email = read_token(secret, unsubscribe_purpose(team.slug), token, now())
            if email is not None:
                return email, team
        email = read_legacy("unsubscribe", token)  # the old app's list was one team
        return (email, legacy_team) if email is not None else None

    def invalid_unsubscribe(request: Request) -> HTMLResponse:
        return message(
            request,
            "Link inválido",
            "Não reconhecemos esse link de descadastro. Use o link do rodapé de uma edição.",
            status=400,
        )

    @app.get("/unsubscribe", response_class=HTMLResponse)
    def unsubscribe_form(request: Request, token: str = ""):
        # GET only asks: e-mail scanners open links, and must not unsubscribe anyone.
        found = read_unsubscribe(token)
        if found is None:
            return invalid_unsubscribe(request)
        _, team = found
        text = (
            f"Você deixa de receber a {team.newsletter}. As outras torcidas continuam."
            if team
            else "Você deixa de receber todas as newsletters da Geral."
        )
        return message(request, "Sair da lista?", text, unsubscribe_token=token, team=team)

    @app.post("/unsubscribe", response_class=HTMLResponse)
    def unsubscribe(request: Request, token: str = "", all: str = ""):
        # Also the RFC 8058 one-click target: the mail provider POSTs here directly.
        found = read_unsubscribe(token)
        if found is None:
            return invalid_unsubscribe(request)
        email, team = found
        if team is None or all:
            store.leave_all(email, now())
            return message(
                request,
                "Você saiu da Geral",
                "Não vai mais receber nenhuma newsletter. Se mudar de ideia, é só voltar.",
            )
        store.leave(email, team.slug, now())
        return message(
            request,
            "Você foi descadastrado",
            f"Não vai mais receber a {team.newsletter}. Se mudar de ideia, é só voltar.",
        )

    def authorized(request: Request) -> bool:
        expected = settings.SUBSCRIBERS_API_TOKEN
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())

    def unauthorized() -> JSONResponse:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)

    def unknown_team() -> JSONResponse:
        return JSONResponse({"detail": "unknown team"}, status_code=404)

    @app.get("/api/subscribers")
    def subscribers(request: Request, team: str = ""):
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        return [
            {
                "email": email,
                "unsubscribe_url": link("/unsubscribe", f"unsubscribe:{team}", email),
                "bet_token": make_token(secret, "bet", email, now()),
            }
            for email in store.active(team)
        ]

    @app.get("/api/teams/{team}/banner")
    def team_banner(request: Request, team: str):
        """The special banner for the team's next edition, if it has not published one since."""
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        latest = store.latest_edition(team)
        found = banners.pending(team, latest.published_at if latest else None)
        kicker, title = found or (None, None)
        return {"kicker": kicker, "title": title}

    @app.get("/api/teams/{team}/note")
    def team_note(request: Request, team: str):
        """The announcement for the team's next edition, if it has not published one since."""
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        latest = store.latest_edition(team)
        return {"text": notes.pending(latest.published_at if latest else None)}

    @app.get("/api/teams/{team}/latest-edition")
    def latest_edition(request: Request, team: str):
        # Lets a second trigger of the same run see that the edition already went out.
        if not authorized(request):
            return unauthorized()
        edition = store.latest_edition(team) if team in catalog else None
        if edition is None:
            return JSONResponse({"detail": "no edition published"}, status_code=404)
        return {
            "subject": edition.subject,
            "published_at": edition.published_at.isoformat(),
            "text": edition.text,  # the next run reads its topics to avoid repeating them
        }

    @app.put("/api/teams/{team}/latest-edition", status_code=204)
    def publish_edition(request: Request, team: str, edition: EditionIn):
        # Published by the newsletter run after each real send; sent to new subscribers.
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        if UNSUBSCRIBE_PLACEHOLDER not in edition.html:
            return JSONResponse(
                {"detail": "html must contain the unsubscribe placeholder"}, status_code=422
            )
        store.set_latest_edition(team, edition.subject, edition.html, edition.text, now())
        return Response(status_code=204)

    # --- drafts: built first, sent later (the owner reviews them in between) -------------------

    DraftKind = Literal["pre", "post", "news"]

    @app.put("/api/teams/{team}/drafts/{kind}/{day}", status_code=204)
    def save_draft(
        request: Request,
        team: str,
        kind: DraftKind,
        day: date,
        draft: DraftIn,
        background: BackgroundTasks,
    ):
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        saved = store.save_draft(
            team,
            kind,
            day.isoformat(),
            draft.label,
            json.dumps(draft.newsletter, ensure_ascii=False),
            draft.build_at,
            draft.send_at,
        )
        if not saved:
            return JSONResponse({"detail": "this edition already has a draft"}, status_code=409)
        # After the response: a slow mail provider must not fail the build that saved the draft.
        background.add_task(notify_review, team, draft)
        return Response(status_code=204)

    def notify_review(team: str, draft: DraftIn) -> None:
        """One e-mail per draft to the owner, with the review link; a failure keeps the draft."""
        if not settings.NOTIFY_EMAIL:
            return
        newsletter = Newsletter.model_validate(draft.newsletter)
        send_at = draft.send_at.astimezone(BRASILIA)
        topics = "\n".join(f"{i}. {t.title}" for i, t in enumerate(newsletter.topics, 1))
        edition = f"{newsletter.team.newsletter} — {draft.label}"
        text = (
            f"{edition} sai às {send_at:%H:%M} se você não mexer.\n\n"
            f"{topics or '(sem tópicos de notícia)'}\n\n"
            f"Revisar (segurar ou tirar tópicos; o link vale {REVIEW_MAX_AGE.days} dias):\n"
            f"{review_link()}\n"
        )
        try:
            mailer.send_notification(
                settings.NOTIFY_EMAIL,
                f"Revisar: {edition}, sai às {send_at:%H:%M}",
                text,
            )
        except MailError as e:
            logger.error("Review notice for %s failed: %s", team, e)

    @app.get("/api/teams/{team}/drafts/{kind}/{day}")
    def get_draft(request: Request, team: str, kind: DraftKind, day: date):
        if not authorized(request):
            return unauthorized()
        draft = store.draft(team, kind, day.isoformat()) if team in catalog else None
        if draft is None:
            return JSONResponse({"detail": "no draft"}, status_code=404)
        return {
            "label": draft.label,
            "newsletter": json.loads(draft.newsletter_json),
            "held": draft.held,
            "removed_topics": draft.removed_topics,
            "sent_at": draft.sent_at.isoformat() if draft.sent_at else None,
        }

    @app.post("/api/teams/{team}/drafts/{kind}/{day}/sent", status_code=204)
    def draft_sent(request: Request, team: str, kind: DraftKind, day: date):
        if not authorized(request):
            return unauthorized()
        if team not in catalog or not store.mark_draft_sent(team, kind, day.isoformat(), now()):
            return JSONResponse({"detail": "no draft"}, status_code=404)
        return Response(status_code=204)

    # --- stories for the special sections (written by the nightly job) -----------------------

    @app.post("/api/teams/{team}/stories", status_code=204)
    def add_story(request: Request, team: str, story: StoryIn):
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        if not store.add_story(team, story.model_dump(), now()):
            return JSONResponse({"detail": "this source was already used"}, status_code=409)
        return Response(status_code=204)

    @app.get("/api/teams/{team}/stories/count")
    def count_stories(request: Request, team: str):
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        return {"unused": store.unused_stories(team)}

    @app.post("/api/teams/{team}/stories/draw")
    def draw_story(request: Request, team: str, body: DrawIn):
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        story = store.draw_story(team, body.label, reserve=body.reserve)
        return story if story else Response(status_code=204)

    @app.get("/api/teams/{team}/stories/on-this-day")
    def stories_on_this_day(request: Request, team: str, day: date):
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        return store.on_this_day(team, day)

    @app.put("/api/teams/{team}/birthdays", status_code=204)
    def save_birthdays(request: Request, team: str, birthdays: list[BirthdayIn]):
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        store.save_birthdays(team, [b.model_dump(mode="json") for b in birthdays])
        return Response(status_code=204)

    @app.get("/api/teams/{team}/stories/sources")
    def story_sources(request: Request, team: str):
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
            return unknown_team()
        return store.story_sources(team)

    # --- review: the owner holds an edition or drops topics before it goes out ----------------

    def review_owner(token: str) -> bool:
        owner = read_token(secret, REVIEW_PURPOSE, token, now(), max_age=REVIEW_MAX_AGE)
        return bool(settings.NOTIFY_EMAIL) and owner == settings.NOTIFY_EMAIL

    def review_link() -> str:
        token = make_token(secret, REVIEW_PURPOSE, settings.NOTIFY_EMAIL, now())
        return f"{public_url}/revisao?{urlencode({'t': token})}"

    def not_found(request: Request) -> HTMLResponse:
        return message(request, "Página não encontrada", "Volte para a Geral.", status=404)

    def private(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"  # the link carries the token
        return response

    def kept_newsletter(draft) -> Newsletter:
        newsletter = Newsletter.model_validate_json(draft.newsletter_json)
        removed = set(draft.removed_topics)
        kept = [t for i, t in enumerate(newsletter.topics) if i not in removed]
        return newsletter.model_copy(update={"topics": kept})

    @app.get("/revisao", response_class=HTMLResponse)
    def review_page(request: Request, t: str = ""):
        if not review_owner(t):
            return not_found(request)
        drafts = []
        going = {d.id for d in store.released_due(now())}
        for d in store.pending_drafts():
            newsletter = Newsletter.model_validate_json(d.newsletter_json)
            drafts.append(
                {
                    "id": d.id,
                    "label": d.label,
                    "newsletter": newsletter.team.newsletter,
                    "held": d.held,
                    "late": d.send_at <= now(),
                    "going": d.id in going,
                    "send_at": d.send_at,
                    "topics": [
                        {"title": topic.title, "removed": i in d.removed_topics}
                        for i, topic in enumerate(newsletter.topics)
                    ],
                    "story": newsletter.story.title if newsletter.story else None,
                    "on_this_day": newsletter.on_this_day,
                }
            )
        return private(page(request, "revisao.html.j2", drafts=drafts, token=t, timezone=BRASILIA))

    @app.get("/revisao/{draft_id}/previa", response_class=HTMLResponse)
    def review_preview(request: Request, draft_id: int, t: str = ""):
        draft = store.draft_by_id(draft_id) if review_owner(t) else None
        if draft is None:
            return not_found(request)
        kept = kept_newsletter(draft)
        html, _ = render(
            kept,
            unsubscribe_url=UNSUBSCRIBE_PLACEHOLDER,
            subscribe_url=public_url,
            page_url=public_url,
            note=kept.note,  # the owner sees the announcement before it goes
        )
        html = personalize(html, None).replace(UNSUBSCRIBE_PLACEHOLDER, f"{public_url}/")
        return private(HTMLResponse(html))

    def review_action(request: Request, draft_id: int, token: str, change) -> Response:
        draft = store.draft_by_id(draft_id) if review_owner(token) else None
        if draft is None:
            return not_found(request)
        if draft.sent_at is not None:
            return message(request, "Já saiu", "Essa edição já foi enviada.", status=409)
        refused = change(draft)
        if refused is not None:
            return refused
        return RedirectResponse(f"/revisao?{urlencode({'t': token})}", status_code=303)

    @app.post("/revisao/{draft_id}/segurar")
    def review_hold(request: Request, draft_id: int, t: Annotated[str, Form()] = ""):
        def hold(draft):
            store.set_held(draft.id, True, now())

        return review_action(request, draft_id, t, hold)

    def out_of_order(request: Request, draft) -> Response | None:
        """The 409 page when a newer edition of that torcida exists (this one stays held)."""
        if any(d.build_at > draft.build_at for d in store.team_drafts(draft.team)):
            # A newer draft already carries this one's news (its window reaches back).
            text = "Já existe uma edição mais nova dessa torcida; esta fica segurada."
            return message(request, "Edição antiga", text, status=409)
        latest = store.latest_edition(draft.team)
        if latest is not None and latest.published_at > draft.send_at:
            # A newer edition went out meanwhile: this one would arrive out of order.
            text = "Já saiu uma edição mais nova dessa torcida; esta fica segurada."
            return message(request, "Edição antiga", text, status=409)
        return None

    @app.post("/revisao/{draft_id}/soltar")
    def review_release(request: Request, draft_id: int, t: Annotated[str, Form()] = ""):
        def release(draft):
            refused = out_of_order(request, draft)
            if refused is None:
                store.set_held(draft.id, False, now())
            return refused

        return review_action(request, draft_id, t, release)

    @app.post("/revisao/{draft_id}/publicar")
    def review_publish(request: Request, draft_id: int, t: Annotated[str, Form()] = ""):
        """Reviewed: it goes out at the next check (up to 10 min), without waiting its time."""

        def publish(draft):
            refused = out_of_order(request, draft)
            if refused is None:
                store.publish_now(draft.id, now())
            return refused

        return review_action(request, draft_id, t, publish)

    def topic_action(request: Request, draft_id: int, n: int, t: str, removed: bool):
        def change(draft):
            topics = Newsletter.model_validate_json(draft.newsletter_json).topics
            if not 0 <= n < len(topics):
                return not_found(request)
            store.set_topic_removed(draft.id, n, removed)
            return None

        return review_action(request, draft_id, t, change)

    def section_action(request: Request, draft_id: int, t: str, section: str):
        def change(draft):
            newsletter = Newsletter.model_validate_json(draft.newsletter_json)
            if section == "historia":
                if newsletter.story is None:
                    return not_found(request)
                store.discard_story(newsletter.story.id)  # never drawn again
                newsletter = newsletter.model_copy(update={"story": None})
            else:
                newsletter = newsletter.model_copy(update={"on_this_day": []})
            store.set_draft_newsletter(draft.id, newsletter.model_dump_json())
            return None

        return review_action(request, draft_id, t, change)

    @app.post("/revisao/{draft_id}/historia/tirar")
    def review_remove_story(request: Request, draft_id: int, t: Annotated[str, Form()] = ""):
        return section_action(request, draft_id, t, "historia")

    @app.post("/revisao/{draft_id}/neste-dia/tirar")
    def review_remove_on_this_day(request: Request, draft_id: int, t: Annotated[str, Form()] = ""):
        return section_action(request, draft_id, t, "neste-dia")

    @app.post("/revisao/{draft_id}/topicos/{n}/tirar")
    def review_remove(request: Request, draft_id: int, n: int, t: Annotated[str, Form()] = ""):
        return topic_action(request, draft_id, n, t, True)

    @app.post("/revisao/{draft_id}/topicos/{n}/voltar")
    def review_restore(request: Request, draft_id: int, n: int, t: Annotated[str, Form()] = ""):
        return topic_action(request, draft_id, n, t, False)

    # --- bolão ---------------------------------------------------------------------------------

    def bettor(request: Request, token: str, team: str, match_id: str):
        """(email, team, match) behind a bet link, or the error page to return instead."""
        email = read_token(secret, "bet", token, now()) or read_legacy("bet", token)
        if not team and legacy_team:
            team = legacy_team.slug  # the old app's links carry no team
        if email is None:
            return None, message(
                request,
                "Link inválido",
                "Não reconhecemos esse link de palpite. Use a cartela de uma edição.",
                status=400,
            )
        club = clubs.get(team)  # the bolão is the torcidas' only
        match = bolao.match(team, match_id) if club else None
        if match is None:
            return None, message(
                request, "Jogo não encontrado", "Esse jogo não está no bolão.", status=404
            )
        subscriber = store.get(email)
        if subscriber is None or subscriber.status != "active":
            return None, message(
                request,
                "Inscrição inativa",
                "O bolão é para quem está na Geral. Inscreva-se de novo para palpitar.",
                status=403,
            )
        if team not in store.teams_of(email):
            return None, message(
                request,
                "Bolão de outra torcida",
                f"Esse bolão é de quem recebe a {club.newsletter}. Entre nessa torcida no portal "
                "para palpitar.",
                status=403,
            )
        return (email, club, match), None

    def bet_page(request: Request, status: int = 200, **context) -> HTMLResponse:
        return page(request, "palpite.html.j2", status, **context)

    @app.get("/palpite", response_class=HTMLResponse)
    def bet_form(request: Request, t: str = "", c: str = "", m: str = "", p: str = ""):
        # GET only asks: e-mail scanners open every link, and must not place bets.
        found, error = bettor(request, t, c, m)
        if error:
            return error
        email, club, match = found
        context = {"match": match, "team": club, "token": t, "nickname": bolao.nickname(email)}
        if not bolao.is_open(club.slug, match.match_id, now()):
            bet = bolao.bet(email, club.slug, m)
            return bet_page(request, mode="closed", bet=bet, **context)
        if not p:
            return bet_page(request, mode="other", **context)
        score = parse_score(p)
        if score is None:
            return message(request, "Placar inválido", "Escolha um placar da cartela.", status=400)
        return bet_page(request, mode="confirm", score=score, **context)

    @app.post("/palpite", response_class=HTMLResponse)
    def place_bet(
        request: Request,
        t: str = Form(""),
        c: str = Form(""),
        m: str = Form(""),
        p: str = Form(""),
        ours: str = Form(""),
        theirs: str = Form(""),
        nickname: str = Form(""),
    ):
        found, error = bettor(request, t, c, m)
        if error:
            return error
        email, club, match = found
        score = parse_score(p or f"{ours}-{theirs}")
        if score is None:
            return message(request, "Placar inválido", "Escolha um placar da cartela.", status=400)
        context = {"match": match, "team": club, "token": t, "score": score}
        if not bolao.is_open(club.slug, match.match_id, now()):
            bet = bolao.bet(email, club.slug, m)
            return bet_page(request, 409, mode="closed", bet=bet, nickname=None, **context)
        if bolao.nickname(email) is None:
            nickname = nickname.strip()
            problem = None
            if not MIN_NICKNAME <= len(nickname) <= MAX_NICKNAME:
                problem = f"O apelido precisa ter de {MIN_NICKNAME} a {MAX_NICKNAME} caracteres."
            elif not NICKNAME_RE.match(nickname):
                problem = "Use só letras, números, espaços, hífen e apóstrofo no apelido."
            elif not bolao.set_nickname(email, nickname):
                # One nickname per e-mail: the owner of two addresses is two players.
                problem = (
                    "Esse apelido já está em uso por outro e-mail. Se você recebe a Geral em "
                    "mais de um endereço, cada um palpita separado: escolha outro apelido, como "
                    f"“{nickname} 2”, ou palpite pelo e-mail em que você começou."
                )
            if problem:
                return bet_page(
                    request, 409, mode="confirm", nickname=None, problem=problem, **context
                )
        bolao.place_bet(email, club.slug, match.match_id, score, now())
        return bet_page(request, mode="done", nickname=bolao.nickname(email), **context)

    @app.get("/bolao")
    def legacy_ranking(request: Request, t: str = ""):
        if legacy_team is None:
            return message(request, "Torcida não encontrada", "Volte para a Geral.", status=404)
        query = f"?{urlencode({'t': t})}" if t else ""
        return RedirectResponse(f"/bolao/{legacy_team.slug}{query}", status_code=301)

    @app.get("/bolao/{team}", response_class=HTMLResponse)
    def ranking(request: Request, team: str, t: str = ""):
        club = clubs.get(team)  # the bolão is the torcidas' only
        if club is None:
            return message(request, "Torcida não encontrada", "Volte para a Geral.", status=404)
        email = (read_token(secret, "bet", t, now()) or read_legacy("bet", t)) if t else None
        me = bolao.nickname(email) if email else None
        season = now().astimezone(TZ).year
        rows = bolao.ranking(team, season)
        return page(request, "bolao.html.j2", rows=rows, me=me, season=season, team=club)

    @app.put("/api/teams/{team}/bolao/matches/{match_id}", status_code=204)
    def register_match(request: Request, team: str, match_id: str, match: BolaoMatchIn):
        if not authorized(request):
            return unauthorized()
        if team not in clubs:
            return unknown_team()
        bolao.upsert_match(team, match_id, match.opponent, match.home, match.kickoff)
        return Response(status_code=204)

    @app.get("/api/teams/{team}/bolao/matches/{match_id}/summary")
    def preview_summary(request: Request, team: str, match_id: str, ours: int, theirs: int):
        if not authorized(request):
            return unauthorized()
        if bolao.match(team, match_id) is None:
            return JSONResponse({"detail": "unknown match"}, status_code=404)
        return bolao.summary(team, match_id, (ours, theirs), persist=False)

    @app.put("/api/teams/{team}/bolao/matches/{match_id}/result")
    def report_result(request: Request, team: str, match_id: str, result: BolaoResultIn):
        if not authorized(request):
            return unauthorized()
        if bolao.match(team, match_id) is None:
            return JSONResponse({"detail": "unknown match"}, status_code=404)
        score = (result.our_goals, result.their_goals)
        return bolao.summary(team, match_id, score, persist=True)

    @app.get("/central", response_class=HTMLResponse)
    def central_page(request: Request, serie: str | None = None):
        """Tables, rounds and summaries of the four séries, from the snapshot on disk."""
        snapshot = load_snapshot(central_file)
        series = snapshot.series if snapshot else []
        chosen = (
            next((s for s in series if s.slug == serie), None)
            or next((s for s in series if s.status != "over"), None)
            or next(iter(series), None)
        )
        return page(request, "central.html.j2", snapshot=snapshot, series=series, serie=chosen)

    NEWS_PER_PAGE = 12  # four rows of three on a computer

    @app.get("/central/noticias", response_class=HTMLResponse)
    def central_news(request: Request, serie: str | None = None, pagina: str | None = None):
        """The four séries' ge stories, newest first, optionally one série."""
        snapshot = load_snapshot(central_file)
        news = snapshot.news if snapshot else []
        serie = serie if serie in SERIE_SLUGS.values() else None
        matching = [n for n in news if serie is None or n.serie_slug == serie]
        total = max(1, -(-len(matching) // NEWS_PER_PAGE))
        asked = int(pagina) if pagina and pagina.isascii() and pagina.isdecimal() else 1
        number = min(max(asked, 1), total)
        shown = matching[(number - 1) * NEWS_PER_PAGE : number * NEWS_PER_PAGE]
        base = f"/central/noticias?serie={serie}&" if serie else "/central/noticias?"
        pages = [f"{base}pagina={n}" for n in range(1, total + 1)]
        names = [(slug, name) for name, slug in SERIE_SLUGS.items()]
        return page(
            request,
            "central_noticias.html.j2",
            snapshot=snapshot,
            news=shown,
            serie=serie,
            series_names=names,
            pages=pages,
            page_no=number,
        )

    @app.get("/central/noticias/{item_id}", response_class=HTMLResponse)
    def central_story(request: Request, item_id: str):
        """A story's opening inside the Geral, with the way to the whole text on ge."""
        snapshot = load_snapshot(central_file)
        news = snapshot.news if snapshot else []
        item = next((n for n in news if n.id == item_id), None)
        if item is None:
            return message(
                request,
                "Notícia não encontrada",
                "Ela já saiu do feed da Central, que guarda as notícias das últimas 48 horas.",
                status=404,
            )
        more = [n for n in news if n.serie_slug == item.serie_slug and n.id != item.id][:4]
        return page(request, "central_noticia.html.j2", item=item, more=more)

    @app.get("/jogos", response_class=HTMLResponse)
    def games_page(request: Request):
        shown = [
            g
            | {
                "url": game_url(g["path"], "geral"),
                "edition_links": [
                    ((listed[slug].name if slug in listed else "Geral"), game_url(g["path"], slug))
                    for slug in g["editions"]
                ],
            }
            for g in games()
        ]
        return page(request, "jogos.html.j2", games=shown)

    @app.get("/jogos/craque-do-dia", response_class=HTMLResponse)
    @app.get("/jogos/craque-do-dia/{edition}", response_class=HTMLResponse)
    @app.get("/jogos/craque-do-dia/{edition}/{number}", response_class=HTMLResponse)
    def craque_page(request: Request, edition: str = "geral", number: str | None = None):
        games = craque_editions().get(edition)
        if not games:
            return message(
                request,
                "Jogo não encontrado",
                "Essa torcida ainda não tem o Craque do dia. Jogue a edição geral enquanto isso.",
                status=404,
            )
        found = which_puzzle(
            request, "craque-do-dia", edition, number, craque_number(), craque.LAUNCH
        )
        if isinstance(found, Response):
            return found
        number, when = found
        return page(
            request,
            "craque.html.j2",
            edition=edition,
            tabs=game_tabs("craque-do-dia", edition),
            team=listed.get(edition),
            club=club_palette(listed.get(edition)),
            number=number,
            **when,
            letters=len(daily_craque(edition, games, number).answer),
            editions=[(slug, listed.get(slug)) for slug in craque_editions()],
            max_guesses=craque.MAX_GUESSES,
        )

    @app.post("/api/jogos/craque-do-dia/{edition}/{number}")
    def craque_guess(edition: str, number: int, body: WordGuessesIn):
        games = craque_editions().get(edition)
        if not games or not 1 <= number <= craque_number():
            return JSONResponse({"detail": "puzzle not found"}, status_code=404)
        answer = daily_craque(edition, games, number)
        if not all(craque.valid_guess(answer, g) for g in body.guesses):
            return JSONResponse(
                {"detail": f"cada chute precisa de {len(answer.answer)} letras"}, status_code=422
            )
        return craque.judge(answer, body.guesses)

    def carreira_edicoes() -> list[str]:
        return ["geral"]  # one Carreira for everyone: the fan picks the starting club

    def carreira_pagina(request: Request, edition: str, **extra) -> HTMLResponse:
        dados = carreira_dados.carregar()
        clubes = [
            {"id": c.id, "nome": c.nome}
            for c in sorted(dados.clubes.values(), key=lambda c: c.nome)
            if dados.ligas[c.liga].pais == "Brasil"
        ]
        jogo = {
            "edicao": edition,
            "atributos": [
                {"id": a, "nome": carreira_regras.NOMES[a]} for a in carreira_regras.ATRIBUTOS
            ],
            "posicoes": list(carreira_regras.POSICOES),
            "pesos": carreira_regras.PESOS,
            "clubes": clubes,
            "tacas": dados.tacas(),
            "url": public_url,
        } | extra.pop("jogo", {})
        return page(
            request,
            "carreira.html.j2",
            edition=edition,
            tabs=game_tabs("carreira", edition),
            team=listed.get(edition),
            club=club_palette(listed.get(edition)),
            editions=[(slug, listed.get(slug)) for slug in carreira_edicoes()],
            jogo=jogo,
            **extra,
        )

    @app.get("/jogos/carreira", response_class=HTMLResponse)
    def carreira_jogo(request: Request):
        return carreira_pagina(request, "geral")

    @app.get("/jogos/carreira/{edition}")
    def carreira_por_time(edition: str):
        """The team editions are gone: one Carreira, any club to start from."""
        return RedirectResponse("/jogos/carreira", status_code=301)

    @app.get("/jogos/carreira/c/{codigo}", response_class=HTMLResponse)
    def carreira_compartilhada(request: Request, codigo: str):
        dados = carreira_dados.carregar()
        try:
            aberto = carreira_codigo.decodificar(codigo, dados)
        except carreira_codigo.CodigoInvalido:
            aberto = None
        if aberto is None or aberto.edicao not in carreira_edicoes():
            return message(
                request,
                "Carreira não encontrada",
                "Esse link de carreira não abre. Que tal montar o seu craque?",
                status=404,
                link_url="/jogos/carreira",
                link_label="Jogar a Carreira",
            )
        carreira = guardada(codigo)
        if carreira is None and aberto.versao == dados.versao:
            try:
                carreira = carreira_motor.simular(dados, aberto.edicao, aberto.entrada)
            except carreira_draft.JogadaInvalida:
                carreira = None
            if carreira and carreira.final is None:  # a forged code of an unfinished career
                carreira = None
        compartilhada = {
            "codigo": codigo,
            "craque": aberto.entrada.craque.model_dump(),
            # a replayed career knows where he ended up playing; the code only has the start
            "resumo": (
                carreira_codigo.resumir(aberto.entrada, carreira) if carreira else aberto.resumo
            ).model_dump(),
            "carreira": carreira.model_dump() if carreira else None,
        }
        return carreira_pagina(
            request,
            aberto.edicao,
            compartilhada=compartilhada,
            jogo={"compartilhada": compartilhada},
        )

    @app.post("/api/jogos/carreira/{edition}/oferta")
    def carreira_oferta(edition: str, body: CarreiraOfertaIn):
        if edition not in carreira_edicoes():
            return JSONResponse({"detail": "edition not found"}, status_code=404)
        semente = secrets.token_urlsafe(8)
        dados = carreira_dados.carregar()
        lendas = carreira_draft.oferta(dados, edition, semente, body.clube)
        return {
            "versao": dados.versao,
            "semente_draft": semente,
            "lendas": [
                {
                    "nome": x.nome,
                    "notas": x.notas,
                    "regiao": x.regiao,
                    "tipo": x.tipo,
                    "resumo": x.resumo,
                }
                for x in lendas
            ],
        }

    @app.post("/api/jogos/carreira/{edition}/simular")
    def carreira_simular(request: Request, edition: str, body: CarreiraIn):
        if edition not in carreira_edicoes():
            return JSONResponse({"detail": "edition not found"}, status_code=404)
        dados = carreira_dados.carregar()
        if body.versao and body.versao != dados.versao:
            return JSONResponse(
                {
                    "detail": "A Carreira foi atualizada enquanto você jogava. Para não mudar o "
                    "que já aconteceu, comece uma carreira nova com o seu craque.",
                    "atualizado": True,
                },
                status_code=409,
            )
        entrada = carreira_motor.Entrada(
            **body.model_dump(exclude={"semente", "versao"}),
            semente=body.semente or secrets.token_urlsafe(8),
        )
        try:
            carreira = carreira_motor.simular(dados, edition, entrada)
        except carreira_draft.JogadaInvalida as erro:
            return JSONResponse({"detail": str(erro)}, status_code=422)
        codigo = contou = None
        if carreira.final:
            resumo = carreira_codigo.resumir(entrada, carreira)
            codigo = carreira_codigo.codificar(dados.versao, edition, entrada, resumo, dados)
            contou = contar_carreira(request, dados, entrada, codigo, carreira.final.nota)
            if contou and contou["novo"]:  # kept once, with the count (same cap per network)
                guardar(codigo, carreira)
        return {
            "semente": entrada.semente,
            "versao": dados.versao,
            "carreira": carreira.model_dump(),
            "codigo": codigo,
            "placar": contou,
        }

    def contar_carreira(request: Request, dados, entrada, codigo: str, nota: int) -> dict | None:
        """Count the career for its starting club (once per career, a cap per network); never
        lets the scoreboard break the game."""
        clube = entrada.craque.clube or ""
        rede = network(request.client.host if request.client else "unknown")
        try:
            novo = not placar.contou(codigo)  # a repeat neither counts nor spends the limit
            if novo and not placar_limiter.allow(rede, now()):
                return None  # the career still ends; it just does not count
            if novo:
                placar.registrar(codigo, clube, nota, now())
            carreiras, posicao = placar.posicao(clube)
        except sqlite3.Error:
            logger.exception("carreira placar: could not count a career")
            return None
        do_clube = dados.clubes.get(clube)
        return {
            "clube": do_clube.nome if do_clube else clube,
            "pelo": carreira_motor.artigos("c", do_clube)["pelo_c"] if do_clube else clube,
            "carreiras": carreiras,
            "posicao": posicao,
            "novo": novo,
        }

    def guardar(codigo: str, carreira) -> None:
        """Keep the finished career for its link; never lets the storage break the game."""
        try:
            placar.guardar(codigo, carreira.model_dump_json(), now())
        except sqlite3.Error:
            logger.exception("carreira guardada: could not keep a career")

    def guardada(codigo: str):
        """The career kept for this link (it opens even after the game's data changed)."""
        try:
            texto = placar.guardada(codigo)
            return carreira_motor.Carreira.model_validate_json(texto) if texto else None
        except (sqlite3.Error, ValueError):
            logger.exception("carreira guardada: could not read a kept career")
            return None

    @app.get("/api/jogos/carreira/placar")
    def carreira_placar():
        dados = carreira_dados.carregar()
        try:
            linhas = placar.ranking(20)
        except sqlite3.Error:
            logger.exception("carreira placar: could not read the ranking")
            return JSONResponse({"detail": "placar indisponível"}, status_code=503)
        return [
            {
                "clube": linha.clube,
                "nome": dados.clubes[linha.clube].nome
                if linha.clube in dados.clubes
                else linha.clube,
                "carreiras": linha.carreiras,
                "media": linha.media,
                "lendas": linha.lendas,
                "posicao": linha.posicao,
            }
            for linha in linhas
        ]

    @app.get("/jogos/onde-jogou", response_class=HTMLResponse)
    @app.get("/jogos/onde-jogou/{edition}", response_class=HTMLResponse)
    @app.get("/jogos/onde-jogou/{edition}/{number}", response_class=HTMLResponse)
    def onde_jogou_page(request: Request, edition: str = "geral", number: str | None = None):
        players = career_editions().get(edition)
        if not players:
            return message(
                request,
                "Jogo não encontrado",
                "Essa torcida ainda não tem o Onde jogou?. Jogue a edição geral enquanto isso.",
                status=404,
            )
        found = which_puzzle(
            request, "onde-jogou", edition, number, career_number(), onde_jogou.LAUNCH
        )
        if isinstance(found, Response):
            return found
        number, when = found
        data = careers()
        jogador = daily_player("onde-jogou", edition, players, number)
        return page(
            request,
            "onde_jogou.html.j2",
            edition=edition,
            tabs=game_tabs("onde-jogou", edition),
            team=listed.get(edition),
            club=club_palette(listed.get(edition)),
            number=number,
            **when,
            jogador=jogador,
            # Tells the page the day's player changed (data update) without naming them.
            player_key=hashlib.sha256(f"{secret}:{number}:{jogador.wikidata}".encode()).hexdigest()[
                :12
            ],
            given={qid: data.clubes[qid].nome for qid in given_clubs(edition)},
            clubs=sorted(
                (
                    {"nome": c.nome, "apelidos": list(c.apelidos), "pais": c.pais}
                    for c in data.clubes.values()
                ),
                key=lambda c: (c["pais"], c["nome"]),
            ),
            editions=[(slug, listed.get(slug)) for slug in career_editions()],
            max_wrong=onde_jogou.MAX_WRONG,
        )

    @app.post("/api/jogos/onde-jogou/{edition}/{number}")
    def onde_jogou_guess(edition: str, number: int, body: ClubGuessesIn):
        players = career_editions().get(edition)
        if not players or not 1 <= number <= career_number():
            return JSONResponse({"detail": "puzzle not found"}, status_code=404)
        data = careers()
        clubs = []
        for text in body.palpites:
            if (club := onde_jogou.resolve(data, text)) is None:
                return JSONResponse({"detail": f"Clube desconhecido: {text}"}, status_code=422)
            clubs.append(club)
        jogador = daily_player("onde-jogou", edition, players, number)
        return onde_jogou.judge(data, jogador, clubs, body.desistiu, given_clubs(edition))

    def duel_judge(code: str, jogadas: list[dict]):
        base = velha()
        return velha_duelo.judge_duel(
            base, velha_tabuleiro.parse_board(base, code), [velha_duelo.Move(**m) for m in jogadas]
        )

    def duel_view(row) -> dict:
        """What both players and the watchers see (never the tokens)."""
        base = velha()
        board = velha_tabuleiro.parse_board(base, row.tabuleiro)
        state = duel_judge(row.tabuleiro, row.jogadas)
        hidden = not row.complete  # nobody sees the board before the clock runs
        return {
            "id": row.id,
            "codigo": None if hidden else row.tabuleiro,
            "linhas": ["?"] * 3 if hidden else [c.label for c in board.rows],
            "colunas": ["?"] * 3 if hidden else [c.label for c in board.cols],
            **state.model_dump(),
            "nomes": {q: base.players[q].nome for q in state.jogadores.values()},
            "jogou": len(row.jogadas),
            "completo": row.complete,
            "revanche": row.revanche,
            "proposta": row.proposta,
            "reservada": row.reservada,
            "prazo": row.prazo.isoformat() if row.prazo else None,
            "agora": now().isoformat(),
        }

    def duel_error(error: Exception) -> JSONResponse:
        status = {DuelNotFound: 404, NotYourTurn: 403, DuelConflict: 409}.get(type(error), 422)
        return JSONResponse({"detail": str(error)}, status_code=status)

    @app.post("/api/jogos/velha/partidas")
    def velha_duel_create(request: Request):
        if not duel_limiter.allow(network(request.client.host if request.client else ""), now()):
            return JSONResponse({"detail": "too many duels, try later"}, status_code=429)
        board = velha_tabuleiro.make_board(velha(), random.Random())
        side = random.choice("XO")  # who creates is not always X (X starts)
        duel_id, token, side = duels.create(board.code, now(), side)
        return {"id": duel_id, "token": token, "lado": side}

    @app.post("/api/jogos/velha/partidas/{duel_id}/entrar")
    def velha_duel_join(duel_id: str):
        try:
            joined = duels.join(duel_id, now())
        except DuelNotFound as error:
            return duel_error(error)
        if joined is None:
            return JSONResponse({"detail": "both players are in"}, status_code=409)
        return {"token": joined[0], "lado": joined[1]}

    @app.post("/api/jogos/velha/partidas/{duel_id}/revanche")
    def velha_duel_rematch(duel_id: str, body: DuelTokenIn):
        board = velha_tabuleiro.make_board(velha(), random.Random())
        try:
            new_id, token, side = duels.rematch(duel_id, body.token, now(), duel_judge, board.code)
        except (DuelNotFound, NotYourTurn, DuelConflict) as error:
            return duel_error(error)
        return {"id": new_id, "token": token, "lado": side}

    @app.post("/api/jogos/velha/partidas/{duel_id}/jogada")
    def velha_duel_move(duel_id: str, body: DuelMoveIn):
        move = {"estouro": True} if body.pular else {"casa": body.casa, "jogador": body.jogador}
        try:
            row = duels.play(duel_id, body.token, body.vez_n, move, now(), duel_judge)
        except (DuelNotFound, NotYourTurn, DuelConflict, ValueError) as error:
            return duel_error(error)
        return duel_view(row)

    @app.post("/api/jogos/velha/partidas/{duel_id}/propor")
    def velha_duel_propose(duel_id: str, body: DuelProposalIn):
        try:
            return duel_view(duels.propose(duel_id, body.token, body.tipo, now(), duel_judge))
        except (DuelNotFound, NotYourTurn, DuelConflict) as error:
            return duel_error(error)

    @app.post("/api/jogos/velha/partidas/{duel_id}/responder")
    def velha_duel_answer(duel_id: str, body: DuelAnswerIn):
        board = velha_tabuleiro.make_board(velha(), random.Random())  # used by a new draw
        try:
            row = duels.answer(
                duel_id, body.token, body.aceita, now(), duel_judge, board.code, body.tipo
            )
        except (DuelNotFound, NotYourTurn, DuelConflict) as error:
            return duel_error(error)
        return duel_view(row)

    @app.get("/api/jogos/velha/partidas/{duel_id}")
    def velha_duel_state(duel_id: str):
        try:
            return duel_view(duels.get(duel_id, now(), duel_judge))
        except DuelNotFound as error:
            return duel_error(error)

    @app.get("/api/jogos/velha/partidas/{duel_id}/eventos")
    def velha_duel_events(duel_id: str):
        try:
            duels.get(duel_id, now(), duel_judge)
        except DuelNotFound as error:
            return duel_error(error)

        async def load() -> dict:
            row = await asyncio.to_thread(duels.get, duel_id, now(), duel_judge)
            return duel_view(row)

        return StreamingResponse(
            duel_events(load, asyncio.sleep),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Before `/jogos/velha/{edition}/{number}`, or "p" would be read as an edition.
    @app.get("/jogos/velha/p/{duel_id}", response_class=HTMLResponse)
    def velha_duel_link_page(request: Request, duel_id: str):
        try:
            duels.get(duel_id, now(), duel_judge)
        except DuelNotFound:
            return message(
                request,
                "Duelo não encontrado",
                "Esse duelo não existe ou já passou de um dia. Desafie alguém de novo.",
                status=404,
                link_url="/jogos/velha/duelo",
                link_label="Novo duelo",
            )
        return page(
            request,
            "velha_partida.html.j2",
            edition="geral",
            tabs=game_tabs("velha", "geral"),
            archive=False,
            duel_id=duel_id,
            seconds=velha_duelo.SECONDS,
        )

    # The duel before `/jogos/velha/{edition}`, or "duelo" would be read as an edition.
    @app.get("/jogos/velha/duelo", response_class=HTMLResponse)
    def velha_duel_page(request: Request):
        return page(
            request,
            "velha_duelo.html.j2",
            edition="geral",
            tabs=game_tabs("velha", "geral"),
            archive=False,
            seconds=velha_duelo.SECONDS,
        )

    @app.get("/api/jogos/velha/tabuleiro")
    def velha_new_board():
        board = velha_tabuleiro.make_board(velha(), random.Random())  # fresh, not the day's
        return {
            "codigo": board.code,
            "linhas": [c.label for c in board.rows],
            "colunas": [c.label for c in board.cols],
        }

    @app.post("/api/jogos/velha/duelo")
    def velha_duel(body: DuelIn):
        base = velha()
        try:
            board = velha_tabuleiro.parse_board(base, body.tabuleiro)
            state = velha_duelo.judge_duel(base, board, body.jogadas)
        except ValueError as error:  # GuessError too: a bad board or move
            return JSONResponse({"detail": str(error)}, status_code=422)
        names = {q: base.players[q].nome for q in state.jogadores.values()}
        return state.model_dump() | {"nomes": names}

    @app.get("/jogos/velha", response_class=HTMLResponse)
    @app.get("/jogos/velha/{edition}", response_class=HTMLResponse)
    @app.get("/jogos/velha/{edition}/{number}", response_class=HTMLResponse)
    def velha_page(request: Request, edition: str = "geral", number: str | None = None):
        if edition != "geral":
            return message(
                request,
                "Jogo não encontrado",
                "O jogo da velha é um só para todas as torcidas. Jogue o de hoje.",
                status=404,
                link_url=game_url("velha", "geral"),
                link_label="Jogar o de hoje",
            )
        found = which_puzzle(request, "velha", edition, number, velha_number(), velha_diario.LAUNCH)
        if isinstance(found, Response):
            return found
        number, when = found
        board = velha_board(number)
        return page(
            request,
            "velha.html.j2",
            edition=edition,
            tabs=game_tabs("velha", edition),
            number=number,
            **when,
            board=board,
            max_guesses=velha_judge.MAX_GUESSES,
        )

    @app.get("/api/jogos/velha/jogadores")
    def velha_search(q: Annotated[str, Query(max_length=60)] = ""):
        return [
            {
                "id": p.id,
                "nome": p.nome,
                "anos": p.anos,
                "posicao": velha_base.POSITIONS[p.posicoes[0]] if p.posicoes else "",
            }
            for p in velha_busca.search(velha(), q)
        ]

    @app.post("/api/jogos/velha/{edition}/{number}")
    def velha_guess(edition: str, number: int, body: VelhaIn):
        if edition != "geral" or not 1 <= number <= velha_number():
            return JSONResponse({"detail": "puzzle not found"}, status_code=404)
        base = velha()
        try:
            verdict = velha_judge.judge_solo(base, velha_board(number), body.chutes)
        except velha_judge.GuessError as error:
            return JSONResponse({"detail": str(error)}, status_code=422)
        shown = set(verdict.casas.values())
        for cell in verdict.revelacao or []:
            shown |= {a.id for a in cell.top}
        return verdict.model_dump() | {"nomes": {q: base.players[q].nome for q in shown}}

    @app.get("/jogos/quem-e", response_class=HTMLResponse)
    @app.get("/jogos/quem-e/{edition}", response_class=HTMLResponse)
    @app.get("/jogos/quem-e/{edition}/{number}", response_class=HTMLResponse)
    def quem_e_page(request: Request, edition: str = "geral", number: str | None = None):
        players = who_editions().get(edition)
        if not players:
            return message(
                request,
                "Jogo não encontrado",
                "Essa torcida ainda não tem o Quem é?. Jogue a edição geral enquanto isso.",
                status=404,
            )
        found = which_puzzle(request, "quem-e", edition, number, who_number(), quem_e.LAUNCH)
        if isinstance(found, Response):
            return found
        number, when = found
        data = careers()
        jogador = daily_player("quem-e", edition, players, number)
        return page(
            request,
            "quem_e.html.j2",
            edition=edition,
            tabs=game_tabs("quem-e", edition),
            team=listed.get(edition),
            club=club_palette(listed.get(edition)),
            number=number,
            **when,
            jogador=jogador,
            clubes=data.clubes,
            player_key=hashlib.sha256(
                f"{secret}:quem-e:{number}:{jogador.wikidata}".encode()
            ).hexdigest()[:12],
            players=sorted(
                (
                    {"id": j.wikidata, "nome": j.nome}
                    for j in data.jogadores
                    if not j.edicoes or edition in j.edicoes  # team-only players stay home
                ),
                key=lambda p: p["nome"],
            ),
            editions=[(slug, listed.get(slug)) for slug in who_editions()],
            max_guesses=quem_e.MAX_GUESSES,
        )

    @app.post("/api/jogos/quem-e/{edition}/{number}")
    def quem_e_guess(edition: str, number: int, body: PlayerGuessesIn):
        players = who_editions().get(edition)
        if not players or not 1 <= number <= who_number():
            return JSONResponse({"detail": "puzzle not found"}, status_code=404)
        data = careers()
        known = {j.wikidata for j in data.jogadores}
        if unknown := [q for q in body.palpites if q not in known]:
            return JSONResponse({"detail": f"Jogador desconhecido: {unknown[0]}"}, status_code=422)
        jogador = daily_player("quem-e", edition, players, number)
        return quem_e.judge(data, jogador, body.palpites, body.desistiu)

    @app.get("/pedir", response_class=HTMLResponse)
    def request_page(request: Request):
        return page(
            request,
            "pedir.html.j2",
            top=team_requests.top(TOP_REQUESTS),
            min_votes=PUBLIC_MIN_VOTES,
        )

    @app.post("/pedir", response_class=HTMLResponse)
    async def request_team(request: Request):
        form = await request.form()
        name = " ".join(unicodedata.normalize("NFC", str(form.get("team", ""))).split())
        email = normalize(str(form.get("email", "")))

        def again(error: str) -> HTMLResponse:
            top = team_requests.top(TOP_REQUESTS)
            return page(
                request, "pedir.html.j2", 400, error=error, team=name, email=email, top=top,
                min_votes=PUBLIC_MIN_VOTES,
            )  # fmt: skip

        if form.get("website"):  # honeypot: only bots fill the hidden field
            return message(request, "Pedido anotado", "Valeu! Seu pedido foi anotado.")
        valid_name = MIN_TEAM_NAME <= len(name) <= MAX_TEAM_NAME and TEAM_NAME_RE.match(name)
        if not valid_name:
            return again("Escreva o nome do time (de 2 a 40 letras).")
        if not team_key(name):
            return again("Escreva o nome com letras do nosso alfabeto, como em português.")
        if email and not is_valid_email(email):
            return again("Digite um e-mail válido, ou deixe em branco.")
        if team := known.get(team_key(name)):
            return message(
                request,
                "Já tem!",
                f"O {team.name} já está na Geral: é a {team.newsletter}.",
                link_url=f"/t/{team.slug}",
                link_label=f"Ver a {team.newsletter}",
            )
        voter_network = network(request.client.host if request.client else "unknown")
        if not request_limiter.allow(voter_network, now()):
            return message(
                request, "Muitos pedidos", "Espere um pouco e tente de novo.", status=429
            )
        voter = hmac.new(secret.encode(), voter_network.encode(), "sha256").hexdigest()
        new_vote = team_requests.add(name, voter, email or None, now())
        position, requested = team_requests.position(team_key(name)) or (0, None)
        votes = requested.votes if requested else 1
        shown = requested.name if requested else name
        text = (
            f"{shown} está em {position}º entre os mais pedidos,"
            f" com {votes} pedido{'s' if votes != 1 else ''}."
        )
        if votes < PUBLIC_MIN_VOTES:
            text += (
                f" Ele aparece na lista dos mais pedidos quando juntar {PUBLIC_MIN_VOTES} pedidos."
            )
        if new_vote:
            notify_request(shown, votes, position, email)
        if email:
            text += " Você recebe um e-mail só, quando a torcida nascer."
        return message(
            request, "Pedido anotado", text, link_url="/pedir", link_label="Ver os mais pedidos"
        )

    @app.get("/pedidos", response_class=HTMLResponse)
    def requests_panel(request: Request, t: str = ""):
        """Every request, for the owner: reached only by the signed link in the request e-mail."""
        owner = read_token(secret, PANEL_PURPOSE, t, now(), max_age=PANEL_MAX_AGE)
        if not settings.NOTIFY_EMAIL or owner != settings.NOTIFY_EMAIL:
            return message(request, "Página não encontrada", "Volte para a Geral.", status=404)
        response = page(
            request,
            "pedidos.html.j2",
            teams=team_requests.top(limit=10_000, min_votes=1),
            min_votes=PUBLIC_MIN_VOTES,
            timezone=BRASILIA,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"  # the link carries the token
        return response

    @app.post("/api/team-requests/panel-link")
    def send_panel_link(request: Request):
        """E-mail the owner a fresh link to /pedidos (the link itself never leaves by HTTP)."""
        if not authorized(request):
            return unauthorized()
        if not settings.NOTIFY_EMAIL:
            return JSONResponse({"detail": "NOTIFY_EMAIL is not set"}, status_code=409)
        mailer.send_notification(
            settings.NOTIFY_EMAIL,
            "Pedidos de time",
            f"Todos os pedidos (link vale {PANEL_MAX_AGE.days} dias): {panel_link()}\n",
        )
        return {"sent": True}

    @app.get("/api/team-requests")
    def list_team_requests(request: Request):
        if not authorized(request):
            return unauthorized()
        return [
            {"key": t.key, "name": t.name, "votes": t.votes, "emails": t.emails}
            for t in team_requests.top(limit=10_000, min_votes=1)
        ]

    @app.get("/version.json")
    def version():
        commit = os.environ.get("GIT_SHA", "dev")
        return JSONResponse({"commit": commit}, headers={"Cache-Control": "no-store"})

    @app.get("/health")
    def health():
        store.counts()  # fails loudly if the database is unreachable
        return {"status": "ok"}

    return app
