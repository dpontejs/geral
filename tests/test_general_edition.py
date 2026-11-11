"""Edição geral: the summary, the e-mail and the command (docs/features/edicao-geral.md)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fakes import FakeLLMClient
from typer.testing import CliRunner

import geral.__main__ as cli
from geral.general.collect import SerieWeek
from geral.general.edition import GeneralSummary, build_general, week_window
from geral.general.render import render_general
from geral.models import Article, StandingRow
from geral.send.resend_sender import UNSUBSCRIBE_PLACEHOLDER
from geral.stats.ge_models import Game
from geral.summarizer.client import LLMError

TZ = ZoneInfo("America/Sao_Paulo")
START, END = datetime(2026, 11, 2, 8, tzinfo=TZ), datetime(2026, 11, 9, 8, tzinfo=TZ)


def game(home: str, hg: int, ag: int, away: str, pens: tuple | None = None) -> Game:
    return Game(
        id=hash((home, away)) % 10_000, competition="Série A",
        kickoff=datetime(2026, 11, 8, 16, tzinfo=TZ), time_valid=True, home=home, away=away,
        home_id=1, away_id=2, home_goals=hg, away_goals=ag, venue=None,
        home_penalties=pens[0] if pens else None, away_penalties=pens[1] if pens else None,
    )  # fmt: skip


def row(position: int, team: str) -> StandingRow:
    return StandingRow(
        position=position, team=team, points=70 - position, played=33, won=20, drawn=5,
        lost=8, goals_diff=10,
    )  # fmt: skip


def article(n: int, title: str) -> Article:
    return Article(
        url=f"https://ge.globo.com/futebol/noticia/{n}.ghtml", title=title, source="ge",
        published_at=datetime(2026, 11, 8, 20, tzinfo=TZ), summary_hint=f"Resumo {n}",
    )  # fmt: skip


WEEKS = [
    SerieWeek(
        name="Série A",
        results=[game("Flamengo", 2, 1, "Palmeiras"), game("Vasco", 0, 0, "Botafogo")],
        table_top=[row(1, "Flamengo"), row(2, "Palmeiras")],
        table_bottom=[row(19, "Sport"), row(20, "Juventude")],
        news=[article(1, "Flamengo vence o clássico"), article(2, "Palmeiras perde a ponta")],
    ),
    SerieWeek(
        name="Série D",
        results=[game("ABC", 1, 1, "Uberlândia", pens=(2, 4))],
        phase="Final",
        news=[article(3, "Uberlândia é campeão")],
    ),
]


def responder(prompt, schema):
    assert schema is GeneralSummary
    return {
        "headline": "Flamengo abre vantagem",
        "intro": "Semana de clássico no Rio e final na Série D.",
        "series": [
            {"name": "Série A", "summary": "O Flamengo venceu o Palmeiras.", "picks": [2, 1, 9]},
            {"name": "Série D", "summary": "O Uberlândia levou nos pênaltis.", "picks": [1]},
        ],
    }


def test_week_window_is_last_monday_to_this_monday_at_eight() -> None:
    assert week_window(datetime(2026, 11, 9).date()) == (START, END)


def test_general_summary_prompt_lists_results_tables_and_numbered_news() -> None:
    llm = FakeLLMClient(responder)

    build_general(START, END, WEEKS, llm)

    prompt = llm.prompts[0]
    assert "Série A" in prompt and "Flamengo 2 x 1 Palmeiras" in prompt
    assert "ABC 1 x 1 Uberlândia (pênaltis 2 x 4)" in prompt
    assert "1º Flamengo" in prompt and "20º Juventude" in prompt
    assert "Fase: Final" in prompt
    assert "[1] Flamengo vence o clássico" in prompt and "[2] Palmeiras perde a ponta" in prompt


def test_build_general_uses_the_summary_and_picks_by_number() -> None:
    edition = build_general(START, END, WEEKS, FakeLLMClient(responder))

    assert edition.headline == "Flamengo abre vantagem"
    serie_a, serie_d = edition.series
    assert serie_a.summary == "O Flamengo venceu o Palmeiras."
    assert [a.title for a in serie_a.picks] == [
        "Palmeiras perde a ponta",
        "Flamengo vence o clássico",
    ]
    assert [a.title for a in serie_d.picks] == ["Uberlândia é campeão"]
    assert edition.label == "Edição geral — 09/11/2026"


def test_build_general_keeps_results_when_the_llm_fails() -> None:
    def broken(prompt, schema):
        raise LLMError("quota")

    edition = build_general(START, END, WEEKS, FakeLLMClient(broken))

    assert edition.headline == "O futebol brasileiro da semana"
    assert edition.series[0].summary == ""
    assert [a.title for a in edition.series[0].picks] == [
        "Flamengo vence o clássico", "Palmeiras perde a ponta",
    ]  # fmt: skip
    assert edition.series[0].week.results


def test_render_general_has_each_series_results_table_and_picked_news() -> None:
    edition = build_general(START, END, WEEKS, FakeLLMClient(responder))

    html, text = render_general(edition, logo_url="https://geral.test/static/geral/logo-email.png")

    pieces = (
        "Série A", "Série D", "Flamengo", "Palmeiras", "Juventude", "Final",
        "Uberlândia é campeão", "O Flamengo venceu o Palmeiras.", "Pênaltis 2 x 4",
    )  # fmt: skip
    for piece in pieces:
        assert piece in html, piece
    assert "logo-email.png" in html
    assert "https://ge.globo.com/futebol/noticia/2.ghtml" in html
    assert "Flamengo 2 x 1 Palmeiras" in text and "SÉRIE D" in text


def test_edicao_geral_preview_writes_html_without_sending(monkeypatch, tmp_path) -> None:
    sent = []
    monkeypatch.setattr(cli, "collect_week", lambda start, end: WEEKS)
    monkeypatch.setattr(cli, "get_llm_client", lambda settings: FakeLLMClient(responder))
    monkeypatch.setattr(cli.ResendSender, "send", lambda self, *a: sent.append(a) or [])
    out = tmp_path / "geral.html"

    result = CliRunner().invoke(
        cli.app, ["edicao-geral", "--date", "2026-11-09", "--out", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert "Flamengo abre vantagem" in out.read_text()
    assert sent == []


def test_edicao_geral_send_uses_recipients(monkeypatch, tmp_path) -> None:
    sent = []
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "dono@example.com")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("RESEND_API_KEY", "key")
    monkeypatch.setattr(cli, "collect_week", lambda start, end: WEEKS)
    monkeypatch.setattr(cli, "get_llm_client", lambda settings: FakeLLMClient(responder))

    def send(self, subject, html, text, recipients):
        sent.append((self.sender, subject, [r.email for r in recipients]))
        return ["id1"]

    monkeypatch.setattr(cli.ResendSender, "send", send)

    result = CliRunner().invoke(
        cli.app,
        ["edicao-geral", "--date", "2026-11-09", "--out", str(tmp_path / "g.html"), "--send"],
    )

    assert result.exit_code == 0, result.output
    ((sender, subject, emails),) = sent
    assert sender.startswith("Geral <")
    assert subject == "Geral — Edição geral — 09/11/2026: Flamengo abre vantagem"
    assert emails == ["dono@example.com"]


def test_edicao_geral_with_nothing_this_week_sends_nothing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "collect_week", lambda start, end: [])

    result = CliRunner().invoke(
        cli.app, ["edicao-geral", "--date", "2026-11-09", "--out", str(tmp_path / "g.html")]
    )

    assert result.exit_code == 0
    assert "Nada na semana" in result.output


def test_build_general_matches_series_names_loosely() -> None:
    def loose(prompt, schema):
        return {
            "headline": "H",
            "series": [{"name": "serie a", "summary": "Resumo da A.", "picks": [1]}],
        }

    edition = build_general(START, END, WEEKS, FakeLLMClient(loose))

    assert edition.series[0].summary == "Resumo da A."


def test_build_general_without_an_llm_keeps_results() -> None:
    edition = build_general(START, END, WEEKS, None)

    assert edition.headline == "O futebol brasileiro da semana"
    assert edition.series[0].week.results


def test_edicao_geral_without_gemini_key_still_builds(monkeypatch, tmp_path) -> None:
    def no_key(settings):
        raise LLMError("GEMINI_API_KEY is not set")

    monkeypatch.setattr(cli, "collect_week", lambda start, end: WEEKS)
    monkeypatch.setattr(cli, "get_llm_client", no_key)
    out = tmp_path / "g.html"

    result = CliRunner().invoke(
        cli.app, ["edicao-geral", "--date", "2026-11-09", "--out", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert "Flamengo 2 x 1 Palmeiras" in out.with_suffix(".txt").read_text()


def test_edicao_geral_publish_only_puts_it_on_the_portal_without_sending(
    monkeypatch, tmp_path
) -> None:
    # The first edition: on the page (and in the welcome e-mail) before any Monday send.
    sent, published = [], []
    monkeypatch.setenv("SUBSCRIBERS_API_TOKEN", "tok")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr(cli, "collect_week", lambda start, end: WEEKS)
    monkeypatch.setattr(cli, "get_llm_client", lambda settings: FakeLLMClient(responder))
    monkeypatch.setattr(cli.ResendSender, "send", lambda self, *a: sent.append(a) or [])
    monkeypatch.setattr(cli, "resolve_recipients", lambda *a: pytest.fail("no recipients"))
    monkeypatch.setattr(
        cli,
        "publish_latest_edition",
        lambda settings, team, subject, html, text: published.append((team, subject, html)),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "edicao-geral",
            "--date",
            "2026-11-09",
            "--out",
            str(tmp_path / "g.html"),
            "--publish-only",
        ],
    )

    assert result.exit_code == 0, result.output
    assert sent == []
    ((team, subject, html),) = published
    assert team == "geral"
    assert subject == "Geral — Edição geral — 09/11/2026: Flamengo abre vantagem"
    assert UNSUBSCRIBE_PLACEHOLDER in html


def test_edicao_geral_publish_only_needs_the_portal_token(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SUBSCRIBERS_API_TOKEN", raising=False)

    result = CliRunner().invoke(
        cli.app,
        [
            "edicao-geral",
            "--date",
            "2026-11-09",
            "--out",
            str(tmp_path / "g.html"),
            "--publish-only",
        ],
    )

    assert result.exit_code != 0
    assert "SUBSCRIBERS_API_TOKEN" in result.output
