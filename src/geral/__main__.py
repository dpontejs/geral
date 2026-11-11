import logging
import os
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

import httpx
import typer
from rich.console import Console
from rich.table import Table

from geral import __version__, pipeline
from geral.config import get_settings
from geral.edition import edition_from_slot, resolve_match_edition
from geral.models import Edition, Newsletter
from geral.render.renderer import render
from geral.report import ProblemCollector, RunReport
from geral.schedule import LABELS, TZ, Fixture, Slot, label_of, plan
from geral.schedule import due as due_slot
from geral.send.recipients import (
    LatestEdition,
    latest_edition,
    preview_summary,
    publish_latest_edition,
    register_match,
    report_result,
    resolve_recipients,
)
from geral.send.resend_sender import (
    UNSUBSCRIBE_PLACEHOLDER,
    ResendSender,
    SendError,
    build_subject,
)
from geral.stats.espn import ESPNStatsClient, StatsUnavailable
from geral.stats.table import standings_window
from geral.summarizer.client import LLMError
from geral.teams import Team, UnknownTeam, get_team, load_teams
from geral.web.store import SubscriberStore

logger = logging.getLogger("geral.run")

app = typer.Typer(help="Geral: one football newsletter per team", no_args_is_help=True)

TeamOption = Annotated[str, typer.Option("--team", help="Team slug from teams.toml (e.g. vasco)")]

EditionOption = Annotated[
    Literal["auto", "pre", "post", "news"],
    typer.Option(help="Edition kind; auto = the one the match calendar has due now"),
]
NoteOption = Annotated[
    str | None, typer.Option(help='Announcement shown in a "Novidades" box (manual sends)')
]
DateOption = Annotated[
    datetime | None,
    typer.Option(formats=["%Y-%m-%d"], help="Reference date (default: today)"),
]


@app.callback()
def main() -> None:
    """Geral CLI root callback."""


@app.command()
def version() -> None:
    """Print the geral version."""
    typer.echo(f"geral v{__version__}")


@app.command()
def collect(
    team: TeamOption,
    edition: EditionOption = "auto",
    date: DateOption = None,
) -> None:
    """Collect the edition's articles and print them as a table."""
    _setup_logging()
    club = _team(team)
    resolved = _resolve(club, edition, date)
    articles = pipeline.collect_articles(resolved, club)

    table = Table(title=f"{resolved.label} ({len(articles)} artigos)")
    table.add_column("Fonte")
    table.add_column("Data")
    table.add_column("Título")
    for article in articles:
        table.add_row(article.source, article.published_at.strftime("%d/%m %H:%M"), article.title)
    Console(width=160).print(table)


@app.command()
def stats(
    team: TeamOption,
    edition: EditionOption = "auto",
    date: DateOption = None,
) -> None:
    """Print the edition's last match, next match and league table."""
    _setup_logging()
    club = _team(team)
    resolved = _resolve(club, edition, date)
    settings = get_settings()
    client = ESPNStatsClient(club, tz_name=settings.TIMEZONE)
    console = Console(width=120)
    console.rule(resolved.label)

    match = client.get_last_match(resolved.start, resolved.end)
    if match is None:
        console.print("Nenhuma partida finalizada na janela da edição.")
    else:
        console.print(
            f"[bold]{match.home} {match.home_goals} x {match.away_goals} {match.away}[/bold]"
            f" — {match.competition}, {match.date:%d/%m %H:%M}"
            + (f", {match.venue}" if match.venue else "")
        )
        for event in match.events:
            if event.type == "goal":
                extra = f"+{event.extra_minute}" if event.extra_minute else ""
                detail = f" ({event.detail})" if event.detail else ""
                console.print(f"  ⚽ {event.minute}'{extra} {event.player} — {event.team}{detail}")
        if match.statistics:
            table = Table(title="Estatísticas")
            table.add_column(match.home, justify="right")
            table.add_column("")
            table.add_column(match.away)
            for label, (home, away) in match.statistics.items():
                table.add_row(home, label, away)
            console.print(table)

    next_match = client.get_next_match(resolved.end)
    if next_match is None:
        console.print("Próximo jogo: não encontrado.")
    else:
        console.print(
            f"Próximo jogo: {next_match.opponent} ({'casa' if next_match.is_home else 'fora'})"
            f" — {next_match.competition}, {next_match.date:%d/%m %H:%M}"
            + (f", {next_match.venue}" if next_match.venue else "")
        )

    rows = standings_window(client.get_standings())
    if rows:
        table = Table(title=club.league_name)
        for column in ("#", "Time", "P", "J", "V", "E", "D", "SG"):
            table.add_column(column)
        for r in rows:
            style = "bold red" if r.is_ours else None
            values = (r.position, r.team, r.points, r.played, r.won, r.drawn, r.lost, r.goals_diff)
            table.add_row(*map(str, values), style=style)
        console.print(table)


@app.command()
def preview(
    team: TeamOption,
    edition: EditionOption = "auto",
    date: DateOption = None,
    out: Annotated[
        Path | None, typer.Option(help="HTML output path (default: out/<team>-<date>.html)")
    ] = None,
    open_browser: Annotated[
        bool, typer.Option("--open", help="Open the HTML in the browser")
    ] = False,
    note: NoteOption = None,
) -> None:
    """Build the full newsletter without sending it and save HTML and text."""
    _setup_logging()
    club = _team(team)
    resolved = _resolve(club, edition, date)
    settings = get_settings()
    newsletter = pipeline.build_newsletter(
        resolved, club, settings, published_topics=_published_topics(settings, club)
    )
    html_path = out or Path("out") / f"{club.slug}-{resolved.end:%Y-%m-%d}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    _bolao(newsletter, settings, club, write=False)
    html, text = render(
        newsletter,
        unsubscribe_url=pipeline.unsubscribe_url(settings),
        logo_url=_brand_logo(settings, club),
        note=note,
        page_url=settings.PUBLIC_URL,
    )

    html_path.write_text(html, encoding="utf-8")
    html_path.with_suffix(".txt").write_text(text, encoding="utf-8")
    typer.echo(f"Preview saved to {html_path} and {html_path.with_suffix('.txt')}")
    if open_browser:
        webbrowser.open(html_path.resolve().as_uri())


@app.command()
def due(
    team: Annotated[str | None, typer.Option("--team", help="One team (slug)")] = None,
    all_teams: Annotated[
        bool, typer.Option("--all", help="Every team with subscribers (on the page's server)")
    ] = False,
) -> None:
    """Print the edition due now: "kind<TAB>YYYY-MM-DD<TAB>label" for --team, one
    "slug<TAB>kind<TAB>YYYY-MM-DD<TAB>label" line per team for --all; nothing when none is due."""
    _setup_logging()
    if (team is None) == (not all_teams):
        typer.echo("Use --team <slug> ou --all.", err=True)
        raise typer.Exit(code=2)
    settings = get_settings()
    now = _now()
    if not all_teams:
        club = _team(team)
        slot = _due_slot(club, settings, now, _latest(settings, club))
        if slot is not None:
            typer.echo(f"{slot.kind}\t{slot.send_at:%Y-%m-%d}\t{slot.label}")
        return
    # Runs next to the page (VPS): subscribers and each team's last edition come from its database.
    store = SubscriberStore(settings.SUBSCRIBERS_DB)
    counts = store.counts()
    for club in load_teams().values():
        if not club.listed or not counts.get(club.slug):
            continue  # hidden (moving in) or nobody follows it: no edition, no Gemini cost
        edition = store.latest_edition(club.slug)
        latest = (
            LatestEdition(subject=edition.subject, published_at=edition.published_at)
            if edition
            else None
        )
        slot = _due_slot(club, settings, now, latest)
        if slot is not None:
            typer.echo(f"{club.slug}\t{slot.kind}\t{slot.send_at:%Y-%m-%d}\t{slot.label}")


def _due_slot(club: Team, settings, now: datetime, latest: LatestEdition | None) -> Slot | None:
    """The slot due now for one team; an unknown calendar (ESPN down) means nothing is due."""
    try:
        fixtures = _fixtures(club, settings, now)
    except StatsUnavailable as e:
        logger.error("Calendar of %s unavailable, nothing is due: %s", club.slug, e)
        return None
    sent_at, sent_label = (
        (latest.published_at, label_of(latest.subject)) if latest else (None, None)
    )
    return due_slot(plan(fixtures, now, sent_at, sent_label), now)


@app.command()
def run(
    team: TeamOption,
    edition: EditionOption = "auto",
    date: DateOption = None,
    skip_if_sent: Annotated[
        bool,
        typer.Option(
            "--skip-if-sent", help="Do nothing if the page already has this edition (retries)"
        ),
    ] = False,
    note: NoteOption = None,
    publish_only: Annotated[
        bool,
        typer.Option(
            "--publish-only",
            help="Build and publish on the page (portal, welcome e-mails) without sending",
        ),
    ] = False,
) -> None:
    """Build, render, save to out/ and send the newsletter (respects DRY_RUN)."""
    _setup_logging()
    club = _team(team)
    if publish_only and not get_settings().SUBSCRIBERS_API_TOKEN:
        typer.echo(
            "--publish-only precisa de SUBSCRIBERS_API_TOKEN para publicar no portal.", err=True
        )
        raise typer.Exit(code=2)
    resolved = _resolve(club, edition, date)
    settings = get_settings()
    report = RunReport(edition=f"{club.newsletter} — {resolved.label}", outcome="interrompida")
    if skip_if_sent and _already_sent(settings, club, resolved.label):
        report.outcome = "já enviada por outro disparo"
        typer.echo(f"{resolved.label}: já enviada, nada a fazer.")
        _publish_report(report)
        return
    try:
        llm = pipeline.get_llm_client(settings)
    except LLMError:
        llm = None  # build_newsletter logs the failure and keeps the stats sections

    with ProblemCollector() as problems:
        try:
            # Resolved before building: a team nobody follows costs no collection, no Gemini.
            resolved_recipients = None if publish_only else resolve_recipients(settings, club.slug)
            if resolved_recipients and not resolved_recipients.recipients and not settings.DRY_RUN:
                report.outcome = "nada a enviar: sem inscritos"
                typer.echo(f"{resolved.label}: nada a enviar, sem inscritos na {club.newsletter}.")
                return
            newsletter = pipeline.build_newsletter(
                resolved,
                club,
                settings,
                llm=llm,
                report=report,
                published_topics=_published_topics(settings, club),
            )
            _fill_report(report, newsletter)
            if resolved.kind == "post" and newsletter.last_match is None:
                report.outcome = "não enviada: partida não encerrada"
                typer.echo(f"{resolved.label}: partida não encerrada, nada a enviar.")
                return
            if pipeline.is_empty(newsletter):
                report.outcome = "nada para enviar (sem notícias e sem partida)"
                typer.echo(f"Nada para enviar em {resolved.label}: sem notícias e sem partida.")
                raise typer.Exit(code=1)

            # The page link only shows up once subscriptions are live (API token configured).
            subscribe = settings.PUBLIC_URL.rstrip("/") if settings.SUBSCRIBERS_API_TOKEN else None
            _bolao(newsletter, settings, club, write=not settings.DRY_RUN)

            def render_edition(note: str | None) -> tuple[str, str]:
                return render(
                    newsletter,
                    unsubscribe_url=UNSUBSCRIBE_PLACEHOLDER,
                    subscribe_url=subscribe,
                    logo_url=_brand_logo(settings, club),
                    note=note,
                    page_url=subscribe,
                )

            html, text = render_edition(note)
            mailto = pipeline.unsubscribe_url(settings)
            html_path = Path("out") / f"{club.slug}-{resolved.end:%Y-%m-%d}.html"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html.replace(UNSUBSCRIBE_PLACEHOLDER, mailto), encoding="utf-8")
            html_path.with_suffix(".txt").write_text(
                text.replace(UNSUBSCRIBE_PLACEHOLDER, mailto), encoding="utf-8"
            )

            plain_subject = build_subject(newsletter)
            if publish_only:
                # First edition of a new team (or a refresh): portal and welcome e-mails only.
                plain_html, plain_text = render_edition(None) if note else (html, text)
                publish_latest_edition(settings, club.slug, plain_subject, plain_html, plain_text)
                report.outcome = "publicada no portal (sem envio)"
                typer.echo(
                    f"{resolved.label}: publicada no portal, sem envio; cópia em {html_path}"
                )
                return
            recipients = resolved_recipients.recipients
            report.recipients = len(recipients)
            report.subscribers = resolved_recipients.from_api
            # The page keeps the plain edition: new subscribers get no stale announcement.
            subject = f"Novidades! {plain_subject}" if note else plain_subject
            try:
                ids = ResendSender.from_settings(settings, club).send(
                    subject, html, text, recipients
                )
            except SendError as e:
                report.outcome = f"falha no envio: {e}"
                typer.echo(f"Falha no envio: {e}")
                raise typer.Exit(code=2) from e
            if ids and settings.SUBSCRIBERS_API_TOKEN:
                try:
                    plain_html, plain_text = render_edition(None) if note else (html, text)
                    publish_latest_edition(
                        settings, club.slug, plain_subject, plain_html, plain_text
                    )
                except httpx.HTTPError as e:
                    logger.warning(
                        "Could not publish the latest edition for new subscribers: %s", e
                    )
            noun = "destinatário" if len(ids) == 1 else "destinatários"
            status = f"enviada para {len(ids)} {noun}" if ids else "não enviada (DRY_RUN)"
            report.outcome = status
            typer.echo(f"{resolved.label}: {status}; cópia em {html_path}")
        finally:
            usage = getattr(llm, "usage", None)
            if usage is not None:
                report.llm_calls = usage.calls
                report.input_tokens = usage.input_tokens
                report.output_tokens = usage.output_tokens
            report.problems = problems.messages
            _publish_report(report)


def _bolao(newsletter: Newsletter, settings, team: Team, write: bool) -> None:
    """Open the team's bolão on the pre-game and fetch its result for the post-game.

    Only real sends (and --publish-only) write to the page; previews and dry runs read a summary
    that is not stored. A page failure leaves the edition without the card or the board.
    """
    if not settings.SUBSCRIBERS_API_TOKEN:
        return
    edition, upcoming, played = newsletter.edition, newsletter.next_match, newsletter.last_match
    try:
        # Only the edition's own match: a rescheduled game or an earlier one in another
        # competition must not open (or close) the bolão with the wrong opponent and deadline.
        if edition.kind == "pre" and upcoming and upcoming.match_id == edition.match_id:
            if write:
                register_match(
                    settings,
                    team.slug,
                    edition.match_id,
                    upcoming.opponent,
                    upcoming.is_home,
                    upcoming.date,
                )
            newsletter.bolao_open = True
        elif (
            edition.kind == "post"
            and played
            and (edition.match_id is None or str(played.fixture_id) == edition.match_id)
        ):
            score = (
                (played.home_goals, played.away_goals)
                if played.is_home
                else (played.away_goals, played.home_goals)
            )
            summarize = report_result if write else preview_summary
            newsletter.bolao = summarize(settings, team.slug, str(played.fixture_id), *score)
    except (httpx.HTTPError, ValueError) as e:  # ValueError: a reply that isn't a summary
        logger.warning("Bolão left out of the edition, the page failed: %s", e)


def _already_sent(settings, team: Team, label: str) -> bool:
    """Whether the page's latest edition is this one; unknown counts as not sent."""
    if not settings.SUBSCRIBERS_API_TOKEN:
        return False
    try:
        edition = latest_edition(settings, team.slug)
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Could not check whether the edition was already sent: %s", e)
        return False
    return edition is not None and f"— {label}" in edition.subject


STATIC = Path(__file__).parent / "static"


def _brand_logo(settings, team: Team) -> str | None:
    """The newsletter logo served by the Geral page; only on a public (https) page, since a
    local one does not load in mail clients. Without it the header shows the name in text."""
    if not settings.PUBLIC_URL.startswith("https://"):
        return None
    if not (STATIC / team.slug / "logo-email.png").exists():
        return None
    return f"{settings.PUBLIC_URL.rstrip('/')}/static/{team.slug}/logo-email.png"


def _fill_report(report: RunReport, newsletter: Newsletter) -> None:
    report.topics = [t.title for t in newsletter.topics]
    report.learn_more = len(newsletter.learn_more)
    report.around_brazil = len(newsletter.around_brazil)
    report.has_match = newsletter.last_match is not None
    report.has_next_match = newsletter.next_match is not None
    report.has_standings = bool(newsletter.standings)


def _publish_report(report: RunReport) -> None:
    """Print the run summary and, on GitHub Actions, add it to the job summary page."""
    markdown = report.to_markdown()
    typer.echo(markdown)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(markdown)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _team(slug: str) -> Team:
    """The catalog entry; an unknown slug exits with code 2 listing the valid ones."""
    try:
        return get_team(slug)
    except UnknownTeam as e:
        typer.echo(f"Time desconhecido: {e}", err=True)
        raise typer.Exit(code=2) from e


def _resolve(team: Team, edition: str, date: datetime | None) -> Edition:
    """`auto`: the slot due now (none: exit 0); a kind: its slot on `date` (default today)."""
    settings = get_settings()
    now = _now()
    try:
        fixtures = _fixtures(team, settings, now)
    except StatsUnavailable as e:
        typer.echo(f"Agenda da ESPN indisponível: {e}")
        raise typer.Exit(code=0 if edition == "auto" else 1) from e
    latest = _latest(settings, team)
    if edition == "auto":
        sent_at, sent_label = (
            (latest.published_at, label_of(latest.subject)) if latest else (None, None)
        )
        slot = due_slot(plan(fixtures, now, sent_at, sent_label), now)
        if slot is None:
            typer.echo("Nenhuma edição agendada agora.")
            raise typer.Exit(code=0)
        return edition_from_slot(slot)
    day = date.date() if date else now.date()
    last_sent = latest.published_at if latest else None
    resolved = resolve_match_edition(edition, day, fixtures, last_sent)  # type: ignore[arg-type]
    if resolved is None:
        typer.echo(f"Nenhuma edição {LABELS[edition]} prevista em {day:%d/%m/%Y}.")
        raise typer.Exit(code=1)
    return resolved


def _now() -> datetime:
    return datetime.now(TZ)


def _fixtures(team: Team, settings, now: datetime) -> list[Fixture]:
    client = ESPNStatsClient(team, tz_name=settings.TIMEZONE)
    return client.get_fixtures(now)


def _published_topics(settings, team: Team) -> list[str]:
    """Topics of the edition already sent, so the model does not repeat them."""
    latest = _latest(settings, team)
    return latest.topic_titles if latest else []


def _latest(settings, team: Team) -> LatestEdition | None:
    """The page's latest edition (subject, send time); unknown (no token, page down) is None."""
    if not settings.SUBSCRIBERS_API_TOKEN:
        return None
    try:
        return latest_edition(settings, team.slug)
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Could not read the latest edition, planning without it: %s", e)
        return None


if __name__ == "__main__":
    app()
