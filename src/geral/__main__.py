import logging
import os
import webbrowser
from datetime import datetime
from email.utils import formataddr, parseaddr
from pathlib import Path
from typing import Annotated, Literal

import httpx
import typer
from rich.console import Console
from rich.table import Table

from geral import __version__, pipeline
from geral.central.build import build_snapshot
from geral.config import get_settings
from geral.edition import edition_from_slot, resolve_match_edition
from geral.general import GENERAL_EDITION, GENERAL_SLUG
from geral.general.collect import collect_week
from geral.general.edition import build_general, due_general, general_label, week_window
from geral.general.render import render_general
from geral.models import Edition, Newsletter
from geral.render.renderer import render
from geral.report import ProblemCollector, RunReport
from geral.schedule import (
    DEFAULT_WINDOW,
    LABELS,
    TZ,
    Fixture,
    Slot,
    Stage,
    built_before,
    due_stage,
    due_stages,
    label_of,
    plan,
)
from geral.schedule import due as due_slot
from geral.send.recipients import (
    LatestEdition,
    fetch_banner,
    fetch_draft,
    fetch_note,
    latest_edition,
    mailto_unsubscribe,
    make_banner,
    mark_draft_sent,
    preview_summary,
    publish_latest_edition,
    register_match,
    report_result,
    resolve_recipients,
    save_draft,
)
from geral.send.resend_sender import (
    UNSUBSCRIBE_PLACEHOLDER,
    ResendSender,
    SendError,
    build_subject,
)
from geral.stats.combined import stats_client_for
from geral.stats.espn import StatsUnavailable
from geral.stats.table import standings_window
from geral.summarizer.client import LLMError, get_llm_client
from geral.teams import Team, UnknownTeam, get_team, load_teams
from geral.web import announce as announcements
from geral.web import especial
from geral.web.legacy import import_single_team
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
    client = stats_client_for(club, tz_name=settings.TIMEZONE)
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
        table = Table(title=getattr(client, "table_name", None) or club.league_name)
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
        resolved, club, settings, published_topics=_published_topics(settings, club, resolved)
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
    released = store.released_due(now)
    for club in load_teams().values():
        if not club.listed or not counts.get(club.slug):
            continue  # hidden (moving in) or nobody follows it: no edition, no Gemini cost
        edition = store.latest_edition(club.slug)
        latest = (
            LatestEdition(subject=edition.subject, published_at=edition.published_at)
            if edition
            else None
        )
        slots = _plan_for(club, settings, now, latest)
        # Every stage due (a build must not hide a send that has not gone out); the stage goes
        # last, so a trigger that reads only 4 columns keeps working.
        for slot, stage in due_stages(slots, now) if slots is not None else []:
            typer.echo(f"{club.slug}\t{slot.kind}\t{slot.send_at:%Y-%m-%d}\t{slot.label}\t{stage}")
        # Let go by the owner after its send time: it goes out now, once.
        for d in (d for d in released if d.team == club.slug):
            # The release time in the label: each release is a new row for the trigger.
            label = f"{d.label} (solta {d.released_at.astimezone(TZ):%d/%m %H:%M})"
            typer.echo(f"{club.slug}\t{d.kind}\t{d.day}\t{label}\trelease")
    if counts.get(GENERAL_SLUG):  # the edição geral: Mondays at 8h, for its subscribers
        edition = store.latest_edition(GENERAL_SLUG)
        monday = due_general(now, edition.subject if edition else None)
        if monday is not None:
            typer.echo(f"{GENERAL_SLUG}\tnews\t{monday:%Y-%m-%d}\t{general_label(monday)}\tall")


def _plan_for(
    club: Team, settings, now: datetime, latest: LatestEdition | None
) -> list[Slot] | None:
    """The team's planned slots; an unknown calendar (ESPN down) is None: nothing is due."""
    try:
        fixtures = _fixtures(club, settings, now)
    except StatsUnavailable as e:
        logger.error("Calendar of %s unavailable, nothing is due: %s", club.slug, e)
        return None
    sent_at, sent_label = (
        (latest.published_at, label_of(latest.subject)) if latest else (None, None)
    )
    return plan(fixtures, now, sent_at, sent_label, weekdays=club.news_weekdays)


def _due_slot(club: Team, settings, now: datetime, latest: LatestEdition | None) -> Slot | None:
    slots = _plan_for(club, settings, now, latest)
    return due_slot(slots, now) if slots is not None else None


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
    stage: Annotated[
        Literal["all", "build", "send", "auto", "release"],
        typer.Option(
            help="build: keep a draft for review; send: send the draft; all: both now;"
            " auto: the stage the match calendar has due now; release: send the draft of"
            " --edition/--date that the owner let go after its time"
        ),
    ] = "all",
) -> None:
    """Build, render, save to out/ and send the newsletter (respects DRY_RUN)."""
    _setup_logging()
    club = _team(team)
    if (publish_only or stage != "all") and not get_settings().SUBSCRIBERS_API_TOKEN:
        option = "--publish-only" if publish_only else f"--stage {stage}"
        typer.echo(f"{option} precisa de SUBSCRIBERS_API_TOKEN para falar com o portal.", err=True)
        raise typer.Exit(code=2)
    if stage == "auto":
        resolved, stage = _resolve_stage(club)
    elif stage == "release":
        resolved, stage = _released_edition(club, edition, date), "send"
    else:
        resolved = _resolve(club, edition, date)
    _run_stage(
        stage, club, resolved, skip_if_sent=skip_if_sent, note=note, publish_only=publish_only
    )


def _released_edition(club: Team, edition: str, date: datetime | None) -> Edition:
    """The edition kept in the draft of that kind and day (its own window, label and match)."""
    if edition == "auto" or date is None:
        typer.echo("--stage release precisa de --edition e --date.", err=True)
        raise typer.Exit(code=2)
    key = Edition(kind=edition, start=date, end=date.replace(tzinfo=TZ), label="")
    try:
        draft = fetch_draft(get_settings(), club.slug, key)
    except (httpx.HTTPError, ValueError) as e:
        typer.echo(f"O portal não respondeu ({e}).")
        raise typer.Exit(code=2) from e
    if draft is None:
        typer.echo(f"Sem rascunho de {LABELS[edition]} em {date:%d/%m/%Y}.")
        raise typer.Exit(code=1)
    return draft.newsletter.edition


def _since_last_send(edition: Edition, latest: LatestEdition | None) -> Edition:
    """Widen the window back to the last edition really sent (an edition held and never let go
    in between must not swallow its news)."""
    if latest is None or latest.published_at >= edition.end:
        return edition
    start = built_before(latest.published_at, label_of(latest.subject))
    return edition.model_copy(update={"start": start}) if start < edition.start else edition


def _resolve_stage(club: Team) -> tuple[Edition, Stage]:
    """The edition and stage due now (none: exit 0)."""
    settings, now = get_settings(), _now()
    try:
        fixtures = _fixtures(club, settings, now)
    except StatsUnavailable as e:
        typer.echo(f"Agenda da ESPN indisponível: {e}")
        raise typer.Exit(code=0) from e
    latest = _latest(settings, club)
    sent_at, sent_label = (
        (latest.published_at, label_of(latest.subject)) if latest else (None, None)
    )
    due = due_stage(plan(fixtures, now, sent_at, sent_label, weekdays=club.news_weekdays), now)
    if due is None:
        typer.echo("Nenhuma edição agendada agora.")
        raise typer.Exit(code=0)
    slot, stage = due
    return _since_last_send(edition_from_slot(slot), latest), stage


def _run_stage(
    stage: str,
    club: Team,
    resolved: Edition,
    *,
    skip_if_sent: bool,
    note: str | None,
    publish_only: bool,
) -> None:
    settings = get_settings()
    report = RunReport(edition=f"{club.newsletter} — {resolved.label}", outcome="interrompida")
    if skip_if_sent and _already_sent(settings, club, resolved.label):
        report.outcome = "já enviada por outro disparo"
        typer.echo(f"{resolved.label}: já enviada, nada a fazer.")
        _publish_report(report)
        return
    llm = None
    with ProblemCollector() as problems:
        try:
            draft = None
            if stage in ("build", "send"):
                try:
                    draft = fetch_draft(settings, club.slug, resolved)
                except (httpx.HTTPError, ValueError) as e:
                    report.outcome = (
                        f"não {'montada' if stage == 'build' else 'enviada'}: portal fora do ar"
                    )
                    typer.echo(f"{resolved.label}: o portal não respondeu ({e}).")
                    raise typer.Exit(code=2) from e
            if stage == "build" and draft is not None:
                report.outcome = "rascunho já montado"
                typer.echo(f"{resolved.label}: rascunho já montado, nada a fazer.")
                return
            if draft is not None and draft.sent_at is not None:
                report.outcome = "já enviada"
                typer.echo(f"{resolved.label}: já enviada, nada a fazer.")
                return
            if draft is not None and draft.held:
                report.outcome = "segurada na revisão"
                typer.echo(f"{resolved.label}: segurada na revisão, não enviada.")
                return
            try:
                llm = pipeline.get_llm_client(settings)
            except LLMError:
                llm = None  # build_newsletter logs the failure and keeps the stats sections
            # Resolved before building: a team nobody follows costs no collection, no Gemini.
            resolved_recipients = None if publish_only else resolve_recipients(settings, club.slug)
            if resolved_recipients and not resolved_recipients.recipients and not settings.DRY_RUN:
                report.outcome = "nada a enviar: sem inscritos"
                typer.echo(f"{resolved.label}: nada a enviar, sem inscritos na {club.newsletter}.")
                return
            if draft is not None:
                newsletter = pipeline.drop_topics(draft.newsletter, draft.removed_topics, llm)
                if draft.removed_topics:
                    typer.echo(f"Revisão: {len(draft.removed_topics)} tópico(s) tirado(s).")
            else:
                newsletter = pipeline.build_newsletter(
                    resolved,
                    club,
                    settings,
                    llm=llm,
                    report=report,
                    published_topics=_published_topics(settings, club, resolved),
                )
                if not publish_only:  # the page and the welcome e-mails stay plain
                    newsletter.note = fetch_note(settings, club.slug)
                if stage == "send":
                    typer.echo(f"{resolved.label}: sem revisão (rascunho ausente), montada agora.")
            if newsletter.banner is None and not publish_only:
                # `geral especial`: also at send time, for a banner set after the draft was built
                if found := fetch_banner(settings, club.slug):
                    newsletter.banner = make_banner(newsletter, *found)
            _fill_report(report, newsletter)
            if resolved.kind == "post" and newsletter.last_match is None:
                report.outcome = "não enviada: partida não encerrada"
                typer.echo(f"{resolved.label}: partida não encerrada, nada a enviar.")
                return
            if draft is not None and draft.removed_topics and pipeline.is_empty(newsletter):
                # The owner's choice, not a failure: marked done so the backup won't retry it.
                report.outcome = "não enviada: todos os tópicos tirados na revisão"
                typer.echo(f"{resolved.label}: todos os tópicos tirados na revisão, não enviada.")
                if not settings.DRY_RUN:
                    mark_draft_sent(settings, club.slug, resolved)
                return
            if pipeline.is_empty(newsletter):
                report.outcome = "nada para enviar (sem notícias e sem partida)"
                typer.echo(f"Nada para enviar em {resolved.label}: sem notícias e sem partida.")
                raise typer.Exit(code=1)
            if stage == "build":
                _keep_draft(settings, club, newsletter, report)
                return
            ids = _deliver(
                newsletter, club, settings, report, resolved_recipients, note, publish_only
            )
            if draft is not None and ids:
                try:
                    mark_draft_sent(settings, club.slug, resolved)
                except httpx.HTTPError as e:
                    logger.warning("Could not mark the draft as sent: %s", e)
        finally:
            usage = getattr(llm, "usage", None)
            if usage is not None:
                report.llm_calls = usage.calls
                report.input_tokens = usage.input_tokens
                report.output_tokens = usage.output_tokens
            report.problems = problems.messages
            _publish_report(report)


def _keep_draft(settings, club: Team, newsletter: Newsletter, report: RunReport) -> None:
    """Keep the built edition on the page for review; a dry run only writes the local preview."""
    _render_preview(settings, club, newsletter)
    if settings.DRY_RUN:
        report.outcome = "rascunho não gravado (DRY_RUN)"
        typer.echo(f"{newsletter.edition.label}: rascunho montado, não gravado (DRY_RUN).")
        return
    try:
        saved = save_draft(settings, club.slug, newsletter, _now())
    except httpx.HTTPError as e:
        report.outcome = "rascunho não gravado: portal fora do ar"
        typer.echo(f"{newsletter.edition.label}: rascunho não gravado ({e}).")
        raise typer.Exit(code=2) from e
    send_at = newsletter.edition.end.astimezone(TZ)
    status = "rascunho montado" if saved else "rascunho já montado"
    report.outcome = f"{status}, sai às {send_at:%H:%M}"
    typer.echo(f"{newsletter.edition.label}: {status}, sai às {send_at:%d/%m %H:%M}.")


def _render_preview(settings, club: Team, newsletter: Newsletter) -> Path:
    subscribe = settings.PUBLIC_URL.rstrip("/") if settings.SUBSCRIBERS_API_TOKEN else None
    html, text = render(
        newsletter,
        unsubscribe_url=UNSUBSCRIBE_PLACEHOLDER,
        subscribe_url=subscribe,
        logo_url=_brand_logo(settings, club),
        note=None,
        page_url=subscribe,
    )
    return _save_copy(settings, club, newsletter, html, text)


def _save_copy(settings, club: Team, newsletter: Newsletter, html: str, text: str) -> Path:
    mailto = pipeline.unsubscribe_url(settings)
    html_path = Path("out") / f"{club.slug}-{newsletter.edition.end:%Y-%m-%d}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html.replace(UNSUBSCRIBE_PLACEHOLDER, mailto), encoding="utf-8")
    html_path.with_suffix(".txt").write_text(
        text.replace(UNSUBSCRIBE_PLACEHOLDER, mailto), encoding="utf-8"
    )
    return html_path


def _deliver(
    newsletter: Newsletter,
    club: Team,
    settings,
    report: RunReport,
    resolved_recipients,
    note: str | None,
    publish_only: bool,
) -> list[str]:
    """Bolão, render, send and publish: what a sent edition does. The ids of the e-mails sent."""
    resolved = newsletter.edition
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

    note = note or newsletter.note  # --note, or the pending `geral novidade` kept in the draft
    html, text = render_edition(note)
    html_path = _save_copy(settings, club, newsletter, html, text)

    plain_subject = build_subject(newsletter)
    if publish_only:
        # First edition of a new team (or a refresh): portal and welcome e-mails only.
        plain_html, plain_text = render_edition(None) if note else (html, text)
        publish_latest_edition(settings, club.slug, plain_subject, plain_html, plain_text)
        report.outcome = "publicada no portal (sem envio)"
        typer.echo(f"{resolved.label}: publicada no portal, sem envio; cópia em {html_path}")
        return []
    recipients = resolved_recipients.recipients
    report.recipients = len(recipients)
    report.subscribers = resolved_recipients.from_api
    # The page keeps the plain edition: new subscribers get no stale announcement.
    subject = f"Novidades! {plain_subject}" if note else plain_subject
    try:
        ids = ResendSender.from_settings(settings, club).send(subject, html, text, recipients)
    except SendError as e:
        report.outcome = f"falha no envio: {e}"
        typer.echo(f"Falha no envio: {e}")
        raise typer.Exit(code=2) from e
    if ids and settings.SUBSCRIBERS_API_TOKEN:
        try:
            plain_html, plain_text = render_edition(None) if note else (html, text)
            publish_latest_edition(settings, club.slug, plain_subject, plain_html, plain_text)
        except httpx.HTTPError as e:
            logger.warning("Could not publish the latest edition for new subscribers: %s", e)
    noun = "destinatário" if len(ids) == 1 else "destinatários"
    status = f"enviada para {len(ids)} {noun}" if ids else "não enviada (DRY_RUN)"
    report.outcome = status
    typer.echo(f"{resolved.label}: {status}; cópia em {html_path}")
    return ids


@app.command("import-legacy")
def import_legacy(
    source: Annotated[Path, typer.Argument(help="SQLite of the single-team app moving in")],
    team: TeamOption,
) -> None:
    """Bring a single-team app's subscribers, last edition and bolão in as one team (idempotent).

    Runs next to the page (the Geral's SUBSCRIBERS_DB)."""
    _setup_logging()
    club = _team(team)
    settings = get_settings()
    report = import_single_team(source, club.slug, Path(settings.SUBSCRIBERS_DB))
    typer.echo(
        f"{club.newsletter}: {report.subscribers} inscritos, {report.matches} jogos e "
        f"{report.bets} palpites do bolão; edição {'importada' if report.edition else 'mantida'}."
    )
    if report.nickname_conflicts:
        conflicts = ", ".join(report.nickname_conflicts)
        typer.echo(f"Apelidos já usados na Geral (ficaram sem apelido): {conflicts}")


@app.command()
def announce(
    moved_in_before: Annotated[
        datetime,
        typer.Option(
            formats=["%Y-%m-%dT%H:%M:%S%z"],
            help="When the moved-in team (LEGACY_TEAM) went on the portal, e.g. "
            "2026-11-11T15:00:00+00:00: who followed it before came with the import",
        ),
    ],
    send_it: Annotated[
        bool, typer.Option("--send", help="Send to everyone who has not got it yet")
    ] = False,
    to: Annotated[
        str | None, typer.Option("--to", help="Send both versions to this address only (a test)")
    ] = None,
) -> None:
    """Announce the Geral: one e-mail per active person, never twice; without --send or --to it
    only counts the audiences and saves both versions to out/.

    Runs next to the page (the Geral's SUBSCRIBERS_DB)."""
    _setup_logging()
    settings = get_settings()
    if not settings.LEGACY_TEAM or not settings.SUBSCRIBE_SECRET:
        typer.echo("announce precisa de LEGACY_TEAM e SUBSCRIBE_SECRET.", err=True)
        raise typer.Exit(code=2)
    legacy = _team(settings.LEGACY_TEAM)
    store = SubscriberStore(settings.SUBSCRIBERS_DB)
    now = _now()
    both = announcements.versions(settings, legacy)
    found = announcements.audiences(store, legacy, moved_in_before)
    typer.echo(
        f"Faltam receber: {len(found.moved_in)} vindos da {legacy.newsletter}, "
        f"{len(found.others)} da Geral."
    )
    try:
        if to:
            for version in both:
                announcements.send(settings, store, version, [to], now, mark=False)
            typer.echo(f"As duas versões foram para {to}.")
        elif send_it:
            for version, emails in zip(both, (found.moved_in, found.others), strict=True):
                sent = announcements.send(settings, store, version, emails, now)
                typer.echo(f"{version.subject}: enviado para {sent}.")
        else:
            out = Path("out")
            out.mkdir(exist_ok=True)
            for version in both:
                (out / f"anuncio-{version.key}.html").write_text(version.html, encoding="utf-8")
                (out / f"anuncio-{version.key}.txt").write_text(version.text, encoding="utf-8")
            typer.echo("Nada enviado; prévias em out/anuncio-*. --to testa, --send envia.")
    except SendError as e:
        typer.echo(f"Falha no envio (quem já recebeu ficou marcado): {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command("especial-jogos")
def especial_jogos(
    send_it: Annotated[
        bool, typer.Option("--send", help="Send to everyone who has not got it yet")
    ] = False,
    to: Annotated[
        str | None, typer.Option("--to", help="Send it to this address only (a test)")
    ] = None,
) -> None:
    """The special edition that presents the games: one e-mail per active person, never twice;
    without --send or --to it only counts who is left and saves a preview to out/.

    Runs next to the page (the Geral's SUBSCRIBERS_DB)."""
    _setup_logging()
    settings = get_settings()
    if not settings.SUBSCRIBE_SECRET:
        typer.echo("especial-jogos precisa de SUBSCRIBE_SECRET.", err=True)
        raise typer.Exit(code=2)
    store = SubscriberStore(settings.SUBSCRIBERS_DB)
    now = _now()
    left = especial.pending(store)
    typer.echo(f"Faltam receber: {len(left)}.")
    try:
        if to:
            especial.send(settings, store, [to], now, mark=False)
            typer.echo(f"Enviado só para {to}.")
        elif send_it:
            typer.echo(
                f"{especial.SUBJECT}: enviado para {especial.send(settings, store, left, now)}."
            )
        else:
            out = Path("out")
            out.mkdir(exist_ok=True)
            html, text = especial.render(settings)
            (out / "especial-jogos.html").write_text(html, encoding="utf-8")
            (out / "especial-jogos.txt").write_text(text, encoding="utf-8")
            typer.echo("Nada enviado; prévia em out/especial-jogos.*. --to testa, --send envia.")
    except SendError as e:
        typer.echo(f"Falha no envio (quem já recebeu ficou marcado): {e}", err=True)
        raise typer.Exit(code=1) from e


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


@app.command()
def acervo(
    team: Annotated[str | None, typer.Option("--team", help="One team (slug)")] = None,
    all_teams: Annotated[
        bool, typer.Option("--all", help="Every team with special sections")
    ] = False,
) -> None:
    """Top up the stories collection of the special sections (the nightly job; respects
    DRY_RUN: then it writes nothing on the page and prints the stories it would keep)."""
    from geral.games import mediawiki
    from geral.specials import job

    _setup_logging()
    if (team is None) == (not all_teams):
        typer.echo("Use --team <slug> ou --all.", err=True)
        raise typer.Exit(code=2)
    clubs = [_team(team)] if team else [t for t in load_teams().values() if t.specials]
    settings = get_settings()
    try:
        llm = pipeline.get_llm_client(settings)
    except LLMError as e:
        typer.echo(f"Gemini indisponível: {e}")
        raise typer.Exit(code=1) from e
    with httpx.Client(headers=mediawiki.HEADERS, timeout=30) as wiki:
        for club in clubs:
            report = job.top_up(club, settings, llm, wiki, _now().date())
            line = (
                report.skipped_reason or f"{report.accepted} aceitas, {report.rejected} recusadas"
            )
            typer.echo(f"{club.slug}: {line}")
            for problem in report.problems:
                typer.echo(f"  problema: {problem}")
            if settings.DRY_RUN:
                for story in report.stories:
                    typer.echo(f"\n  [{story.kind}] {story.title} ({story.fact_date or 's/ data'})")
                    typer.echo(f"  {story.body}\n  Fonte: {story.source_title}")


@app.command("avisar-pedido")
def notify_requesters(
    team: TeamOption,
    send_it: Annotated[
        bool, typer.Option("--send", help="Send to everyone who asked and has not got it yet")
    ] = False,
    to: Annotated[
        str | None, typer.Option("--to", help="Send it to this address only (a test)")
    ] = None,
) -> None:
    """Tell who asked for the team (an e-mail on /pedir) that it was born, with its first edition
    and the link to subscribe. Nobody is subscribed and nobody gets it twice; without --send or
    --to it only counts who is waiting. Runs next to the page (SUBSCRIBERS_DB)."""
    from geral.web.mailer import MailError, mailer_from_settings
    from geral.web.store import normalize
    from geral.web.team_requests import TeamRequestStore, team_key
    from geral.web.welcome import add_born

    _setup_logging()
    club = _team(team)
    settings = get_settings()
    store = SubscriberStore(settings.SUBSCRIBERS_DB)
    found = TeamRequestStore(settings.SUBSCRIBERS_DB).position(team_key(club.name))
    asked = {normalize(e) for e in found[1].emails} if found else set()
    mark = f"pedido:{club.slug}"
    waiting = sorted(asked - set(store.active(club.slug)) - store.announced(mark))
    typer.echo(f"{len(waiting)} esperam o aviso da {club.newsletter}.")
    if not (send_it or to):
        return
    edition = store.latest_edition(club.slug)
    if edition is None:
        typer.echo(f"Publique antes a primeira edição da {club.newsletter} (run --publish-only).")
        raise typer.Exit(code=1)
    subscribe = f"{settings.PUBLIC_URL.rstrip('/')}/t/{club.slug}"
    html, text = add_born(edition.html, edition.text, club, subscribe)
    subject = f"Seu pedido foi atendido: {edition.subject}"
    mailer = mailer_from_settings(settings)
    sent = 0
    for email in [to] if to else waiting:
        try:
            mailer.send_edition(
                email, club, subject, html, text, unsubscribe_url=mailto_unsubscribe(settings)
            )
        except MailError as e:
            typer.echo(f"Falhou para {email}: {e}")
            continue
        sent += 1
        if not to:
            store.mark_announced(mark, [email], _now())
    typer.echo(f"Enviado para {sent}.")


@app.command("edicao-geral")
def edicao_geral(
    date: DateOption = None,
    out: Annotated[
        Path | None, typer.Option(help="HTML file (default: out/geral-<date>.html)")
    ] = None,
    send: Annotated[
        bool,
        typer.Option("--send", help="Send to its subscribers and the fixed list (DRY_RUN holds)"),
    ] = False,
    skip_if_sent: Annotated[
        bool, typer.Option("--skip-if-sent", help="Do nothing if this week's edition went out")
    ] = False,
    publish_only: Annotated[
        bool,
        typer.Option(
            "--publish-only",
            help="Put it on the portal (page and welcome e-mail) without sending: the first one",
        ),
    ] = False,
) -> None:
    """Build the edição geral (Série A to D) of a Monday; --send mails it and publishes it."""
    _setup_logging()
    settings = get_settings()
    if publish_only and (send or not settings.SUBSCRIBERS_API_TOKEN):
        typer.echo(
            "--publish-only precisa de SUBSCRIBERS_API_TOKEN e não combina com --send.", err=True
        )
        raise typer.Exit(code=1)
    start, end = week_window((date or _now()).date())
    label = general_label(end.date())
    if skip_if_sent and _already_sent(settings, GENERAL_EDITION, label):
        typer.echo(f"{label}: já saiu, nada a fazer.")
        return
    recipients = None
    if send:
        resolved = resolve_recipients(settings, GENERAL_SLUG)
        if resolved.api_failed and not settings.DRY_RUN:
            # Once a week: better a retry (the VPS dispatches it again) than the fixed list only.
            typer.echo(f"{label}: lista de inscritos indisponível, envio cancelado.", err=True)
            raise typer.Exit(code=1)
        recipients = resolved.recipients
        if not recipients and not settings.DRY_RUN:
            typer.echo(f"{label}: nada a enviar, sem inscritos na edição geral.")
            return
    weeks = collect_week(start, end)
    if not weeks:
        typer.echo(f"Nada na semana até {end:%d/%m/%Y}: edição geral não gerada.")
        return
    try:
        llm = get_llm_client(settings)
    except LLMError as e:  # no key: the edition goes without the texts
        logger.error("Edição geral without the Gemini: %s", e)
        llm = None
    edition = build_general(start, end, weeks, llm)
    static = f"{settings.PUBLIC_URL.rstrip('/')}/static/geral"

    def render_edition(note: str | None) -> tuple[str, str]:
        return render_general(
            edition,
            static_url=static if settings.PUBLIC_URL.startswith("https://") else None,
            unsubscribe_url=UNSUBSCRIBE_PLACEHOLDER,
            note=note,
        )

    html, text = render_edition(None)  # the page and the welcome e-mails stay plain
    mailto = mailto_unsubscribe(settings)
    path = out or Path("out") / f"geral-{end:%Y-%m-%d}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html.replace(UNSUBSCRIBE_PLACEHOLDER, mailto), encoding="utf-8")
    path.with_suffix(".txt").write_text(text.replace(UNSUBSCRIBE_PLACEHOLDER, mailto), "utf-8")
    typer.echo(f"{edition.subject}\ncópia em {path}")
    if publish_only:
        try:
            publish_latest_edition(settings, GENERAL_SLUG, edition.subject, html, text)
        except httpx.HTTPError as e:
            typer.echo(f"{edition.label}: não publicada no portal: {e}", err=True)
            raise typer.Exit(code=1) from e
        typer.echo(f"{edition.label}: publicada no portal, sem envio.")
        return
    if recipients is None:
        return
    _, address = parseaddr(settings.NEWSLETTER_FROM)
    sender = ResendSender(
        settings.RESEND_API_KEY, formataddr(("Geral", address)), dry_run=settings.DRY_RUN
    )
    note = fetch_note(settings, GENERAL_SLUG)
    mail_html, mail_text = render_edition(note) if note else (html, text)
    subject = f"Novidades! {edition.subject}" if note else edition.subject
    try:
        sender.send(subject, mail_html, mail_text, recipients)
    except SendError as e:
        typer.echo(f"Envio falhou: {e}", err=True)
        raise typer.Exit(code=1) from e
    if settings.DRY_RUN:
        typer.echo(f"{edition.label}: não enviada (DRY_RUN), {len(recipients)} destinatários.")
        return
    typer.echo(f"{edition.label}: enviada para {len(recipients)} destinatários.")
    if settings.SUBSCRIBERS_API_TOKEN:  # new subscribers get it in the welcome e-mail
        try:
            publish_latest_edition(settings, GENERAL_SLUG, edition.subject, html, text)
        except httpx.HTTPError as e:
            # Sent but not on the page: say it loudly, or a manual retry would send it again.
            typer.echo(f"{edition.label}: enviada, mas não publicada no portal: {e}", err=True)
            raise typer.Exit(code=1) from e


@app.command("especial")
def special_banner(
    team: TeamOption,
    kicker: Annotated[str | None, typer.Argument(help='Ex.: "Campeão brasileiro 2026"')] = None,
    titulo: Annotated[str, typer.Option("--titulo", help="O título grande")] = "É campeão!",
    cancelar: Annotated[
        bool, typer.Option("--cancelar", help="Tira o banner que ainda não saiu")
    ] = False,
) -> None:
    """Special banner (a title won: cup, season numbers and the deciding score) on top of the
    team's next edition, once. Runs next to the page (SUBSCRIBERS_DB)."""
    from geral.web.banners import BannerStore

    club = _team(team)
    banners = BannerStore(get_settings().SUBSCRIBERS_DB)
    if cancelar:
        banners.cancel(club.slug)
        typer.echo(f"Banner da {club.newsletter} cancelado.")
        return
    if not kicker or not kicker.strip():
        current = banners.pending(club.slug, None)
        typer.echo(f"Banner atual: {current[0]} — {current[1]}" if current else "Nenhum banner.")
        return
    banners.create(club.slug, kicker, titulo, _now())
    typer.echo(f"Banner gravado: vai no topo da próxima edição da {club.newsletter}.")


@app.command()
def novidade(
    text: Annotated[str | None, typer.Argument(help="O aviso, em pt-BR")] = None,
    cancelar: Annotated[
        bool, typer.Option("--cancelar", help="Tira o aviso que ainda não saiu")
    ] = False,
) -> None:
    """Announcement in the "Novidades" box on top of the next edition of every team and of the
    edição geral, once each. Runs next to the page (SUBSCRIBERS_DB); a new one replaces the old."""
    from geral.web.notes import NoteStore

    notes = NoteStore(get_settings().SUBSCRIBERS_DB)
    if cancelar:
        notes.cancel()
        typer.echo("Aviso cancelado: as próximas edições saem sem ele.")
        return
    if not text or not text.strip():
        current = notes.latest()
        typer.echo(f"Aviso atual: {current.text}" if current else "Nenhum aviso pendente.")
        return
    notes.create(text, _now())
    typer.echo("Aviso gravado: vai no topo da próxima edição de cada time e da edição geral.")


@app.command()
def central(
    out: Annotated[
        Path | None, typer.Option("--out", help="Where to write it (default: the site's file)")
    ] = None,
) -> None:
    """Rebuild the Central snapshot (tables, rounds, summaries of the four séries) now. The site
    does it by itself every CENTRAL_REFRESH seconds; this is for a first run or a check."""
    from geral.central.refresh import Refresher, snapshot_path

    _setup_logging()
    path = out or snapshot_path(get_settings())
    if not Refresher(path, 0, build=build_snapshot).run_once():
        raise typer.Exit(code=1)
    typer.echo(f"Central atualizada em {path}")


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
        slot = due_slot(plan(fixtures, now, sent_at, sent_label, weekdays=team.news_weekdays), now)
        if slot is None:
            typer.echo("Nenhuma edição agendada agora.")
            raise typer.Exit(code=0)
        return _since_last_send(edition_from_slot(slot), latest)
    day = date.date() if date else now.date()
    last_sent = latest.published_at if latest else None
    resolved = resolve_match_edition(
        edition,  # type: ignore[arg-type]
        day,
        fixtures,
        last_sent,
        weekdays=team.news_weekdays,
    )
    if resolved is None and edition == "news" and day == now.date():
        # An extra news edition, asked by hand: from the last send (or the default window) to
        # now. The planned editions go on; the next news one counts from this send.
        # A send made today is ignored, as for planned editions: re-running today's extra
        # edition keeps the window it had, instead of starting at that send.
        before_today = last_sent is not None and last_sent.date() < now.date()
        start = last_sent if before_today else now - DEFAULT_WINDOW
        return Edition(
            kind="news", start=start, end=now, label=f"{LABELS['news']} — {now:%d/%m/%Y}"
        )
    if resolved is None:
        typer.echo(f"Nenhuma edição {LABELS[edition]} prevista em {day:%d/%m/%Y}.")
        raise typer.Exit(code=1)
    return _since_last_send(resolved, latest)


def _now() -> datetime:
    return datetime.now(TZ)


def _fixtures(team: Team, settings, now: datetime) -> list[Fixture]:
    return stats_client_for(team, tz_name=settings.TIMEZONE).get_fixtures(now)


def _published_topics(settings, team: Team, edition: Edition) -> list[str]:
    """Topics of the edition already sent, so the model does not repeat them.

    None when that edition is this one: a re-run must not drop its own topics.
    """
    latest = _latest(settings, team)
    if latest is None or label_of(latest.subject) == edition.label:
        return []
    return latest.topic_titles


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
