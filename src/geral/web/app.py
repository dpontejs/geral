"""The Geral page: portal, sign-up to one or more teams, confirmation and unsubscribe per team.

Run with `uvicorn geral.web.app:create_app --factory`. Behind Caddy, start uvicorn with
`--proxy-headers` so the rate limit sees the visitor's IP.
"""

import hmac
import logging
import os
import re
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape
from pydantic import BaseModel, Field

from geral.config import Settings, get_settings
from geral.send.resend_sender import UNSUBSCRIBE_PLACEHOLDER
from geral.teams import Team, load_teams
from geral.web.bolao import TZ, BolaoStore
from geral.web.mailer import Mailer, MailError, mailer_from_settings
from geral.web.scoreboard import animation_svg
from geral.web.store import RequestResult, SubscriberStore, normalize
from geral.web.tokens import make_token, read_token
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
SCORE_RE = re.compile(r"^(\d)-(\d)$")
STATIC = Path(__file__).resolve().parents[1] / "static"
# The scoreboard clock: Brasília time, no daylight saving since 2019 (no tzdata in the image).
BRASILIA = timezone(timedelta(hours=-3))

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
# Jinja only autoescapes .html by default; ours end in .html.j2 and show user input.
templates.env.autoescape = select_autoescape(["html.j2"])
templates.env.globals["scoreboard_animation"] = animation_svg


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


class BolaoMatchIn(BaseModel):
    opponent: str
    home: bool  # our team plays at home
    kickoff: datetime


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


def create_app(
    settings: Settings | None = None,
    store: SubscriberStore | None = None,
    mailer: Mailer | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    teams: dict[str, Team] | None = None,
    bolao: BolaoStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    secret = settings.SUBSCRIBE_SECRET
    if not secret:
        raise RuntimeError("SUBSCRIBE_SECRET is required to sign confirmation links")
    store = store or SubscriberStore(settings.SUBSCRIBERS_DB)
    mailer = mailer or mailer_from_settings(settings)
    bolao = bolao or BolaoStore(store.path)  # same SQLite: the ranking joins the subscriptions
    catalog = teams if teams is not None else load_teams()
    limiter = RateLimiter(SIGNUPS_PER_IP, SIGNUP_WINDOW)
    public_url = settings.PUBLIC_URL.rstrip("/")

    def link(path: str, purpose: str, email: str) -> str:
        token = make_token(secret, purpose, email, now())
        return f"{public_url}{path}?{urlencode({'token': token})}"

    def page(request: Request, name: str, status: int = 200, **context) -> HTMLResponse:
        context.setdefault("public_url", public_url)
        return templates.TemplateResponse(request, name, context, status_code=status)

    def message(request: Request, title: str, text: str, status: int = 200, **extra):
        return page(request, "message.html.j2", status, title=title, text=text, **extra)

    def portal(request: Request, status: int = 200, **context) -> HTMLResponse:
        counts = store.counts()
        return page(
            request,
            "index.html.j2",
            status,
            teams=list(catalog.values()),
            editions=store.latest_editions(),
            counts=counts,
            ranking=sorted(catalog.values(), key=lambda t: (-counts.get(t.slug, 0), t.newsletter)),
            clock=now().astimezone(BRASILIA),
            **context,
        )

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # Brands (mascot, e-mail logo, link preview) of the hub and of every team.
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def index(request: Request):
        return portal(request)

    @app.get("/t/{team}", response_class=HTMLResponse)
    def team_page(request: Request, team: str):
        """The team's latest edition, to read on the site; personal links point to the portal."""
        edition = store.latest_edition(team) if team in catalog else None
        if edition is None:
            return message(
                request,
                "Edição não encontrada",
                "Essa torcida ainda não tem edição publicada. Volte para a Geral e se inscreva "
                "para receber a primeira.",
                status=404,
            )
        return HTMLResponse(edition.html.replace(UNSUBSCRIBE_PLACEHOLDER, f"{public_url}/"))

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
        chosen = [catalog[s] for s in dict.fromkeys(map(str, form.getlist("team"))) if s in catalog]
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
        names = ", ".join(t.newsletter for t in (new_teams or teams_of(email)))
        text = f"Pronto: você está na Geral e vai receber {names} antes e depois de cada jogo."
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
        return None

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

    # --- bolão ---------------------------------------------------------------------------------

    def bettor(request: Request, token: str, team: str, match_id: str):
        """(email, team, match) behind a bet link, or the error page to return instead."""
        email = read_token(secret, "bet", token, now())
        if email is None:
            return None, message(
                request,
                "Link inválido",
                "Não reconhecemos esse link de palpite. Use a cartela de uma edição.",
                status=400,
            )
        club = catalog.get(team)
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
            elif not bolao.set_nickname(email, nickname):
                problem = "Esse apelido já é de outra pessoa. Escolha outro."
            if problem:
                return bet_page(
                    request, 409, mode="confirm", nickname=None, problem=problem, **context
                )
        bolao.place_bet(email, club.slug, match.match_id, score, now())
        return bet_page(request, mode="done", nickname=bolao.nickname(email), **context)

    @app.get("/bolao/{team}", response_class=HTMLResponse)
    def ranking(request: Request, team: str, t: str = ""):
        club = catalog.get(team)
        if club is None:
            return message(request, "Torcida não encontrada", "Volte para a Geral.", status=404)
        email = read_token(secret, "bet", t, now()) if t else None
        me = bolao.nickname(email) if email else None
        season = now().astimezone(TZ).year
        rows = bolao.ranking(team, season)
        return page(request, "bolao.html.j2", rows=rows, me=me, season=season, team=club)

    @app.put("/api/teams/{team}/bolao/matches/{match_id}", status_code=204)
    def register_match(request: Request, team: str, match_id: str, match: BolaoMatchIn):
        if not authorized(request):
            return unauthorized()
        if team not in catalog:
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

    @app.get("/version.json")
    def version():
        commit = os.environ.get("GIT_SHA", "dev")
        return JSONResponse({"commit": commit}, headers={"Cache-Control": "no-store"})

    @app.get("/health")
    def health():
        store.counts()  # fails loudly if the database is unreachable
        return {"status": "ok"}

    return app
