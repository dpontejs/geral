"""`run --stage`: build a draft first (the owner reviews it), send it later."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from fakes import FLAMENGO, FakeLLMClient
from pydantic import BaseModel
from test_run_command import ARTICLE, MATCH, enable_subscriptions, respond, sent, use
from typer.testing import CliRunner

import geral.__main__ as cli
from geral import pipeline
from geral.config import get_settings
from geral.models import Edition, Newsletter, Topic
from geral.send.recipients import LatestEdition
from geral.send.resend_sender import RESEND_BATCH_URL as RESEND_URL

TZ = ZoneInfo("America/Sao_Paulo")
DRAFT = "https://news.test/api/teams/flamengo/drafts/news/2026-10-12"
BOLAO = "https://news.test/api/teams/flamengo/bolao/matches/"
NEWS = ["run", "--team", "flamengo", "--edition", "news", "--date", "2026-10-12"]


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("NEWSLETTER_FROM", "Flamengo News <news@fla.com>")
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "a@x.com")
    get_settings.cache_clear()
    monkeypatch.setattr(pipeline, "get_llm_client", lambda settings: FakeLLMClient(respond))
    yield monkeypatch
    get_settings.cache_clear()


def run(*stage: str):
    return CliRunner().invoke(cli.app, [*NEWS, "--stage", *stage])


def drafted(removed: list[int] | None = None, held: bool = False) -> dict:
    edition = Edition(
        kind="news",
        start=datetime(2026, 10, 5, 13, tzinfo=TZ),
        end=datetime(2026, 10, 12, 13, tzinfo=TZ),
        label="Notícias — 12/10/2026",
    )
    newsletter = Newsletter(
        team=FLAMENGO,
        edition=edition,
        headline="Flamengo vence o Fla-Flu",
        intro="Vitória no clássico. E um rumor.",
        topics=[
            Topic(title="Fla-Flu", summary="O Flamengo venceu o clássico.", importance=5),
            Topic(title="Rumor de contratação", summary="Um meia é sondado.", importance=3),
        ],
    )
    return {
        "label": edition.label,
        "newsletter": newsletter.model_dump(mode="json"),
        "held": held,
        "removed_topics": removed or [],
        "sent_at": None,
    }


def no_build(*args, **kwargs):
    raise AssertionError("the edition must not be built again")


@respx.mock
def test_run_build_saves_draft_and_sends_nothing(env) -> None:
    enable_subscriptions(env)
    use(env, [ARTICLE], MATCH)
    respx.get(DRAFT).mock(return_value=httpx.Response(404))
    save = respx.put(DRAFT).mock(return_value=httpx.Response(204))
    resend = respx.post(RESEND_URL)

    result = run("build")

    assert result.exit_code == 0, result.output
    assert not resend.called
    body = json.loads(save.calls.last.request.content)
    assert body["newsletter"]["topics"][0]["summary"] == "O Flamengo venceu."
    assert "rascunho" in result.output


@respx.mock
def test_run_build_twice_keeps_first_draft(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)
    respx.get(DRAFT).mock(return_value=httpx.Response(200, json=drafted()))
    save = respx.put(DRAFT)

    result = run("build")

    assert result.exit_code == 0, result.output
    assert not save.called


@respx.mock
def test_run_build_registers_no_bolao(env) -> None:
    enable_subscriptions(env)
    use(env, [ARTICLE], MATCH)
    respx.get(DRAFT).mock(return_value=httpx.Response(404))
    respx.put(DRAFT).mock(return_value=httpx.Response(204))
    bolao = respx.route(url__startswith=BOLAO)

    assert run("build").exit_code == 0
    assert not bolao.called


@respx.mock
def test_run_send_drops_removed_topics_and_rewrites_the_opening(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)
    prompts = []

    def opening(prompt: str, schema: type[BaseModel]) -> dict:
        prompts.append(prompt)
        return {"headline": "Meia é sondado pelo Flamengo", "intro": "Um rumor. Só isso."}

    env.setattr(pipeline, "get_llm_client", lambda settings: FakeLLMClient(opening))
    respx.get(DRAFT).mock(return_value=httpx.Response(200, json=drafted(removed=[0])))
    done = respx.post(f"{DRAFT}/sent").mock(return_value=httpx.Response(204))
    respx.put("https://news.test/api/teams/flamengo/latest-edition").mock(
        return_value=httpx.Response(204)
    )
    route = respx.post(RESEND_URL).mock(return_value=sent(["e1"]))

    result = run("send")

    assert result.exit_code == 0, result.output
    [body] = json.loads(route.calls.last.request.content)
    assert body["subject"] == "Urubu News — Notícias — 12/10/2026: Meia é sondado pelo Flamengo"
    assert "Um meia é sondado." in body["html"]
    assert "O Flamengo venceu o clássico." not in body["html"]
    assert "Fla-Flu" not in prompts[0]
    assert done.called


@respx.mock
def test_run_send_without_llm_headline_is_first_kept_topic(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)

    def down(prompt: str, schema: type[BaseModel]) -> dict:
        from geral.summarizer.client import LLMError

        raise LLMError("gemini down")

    env.setattr(pipeline, "get_llm_client", lambda settings: FakeLLMClient(down))
    respx.get(DRAFT).mock(return_value=httpx.Response(200, json=drafted(removed=[0])))
    respx.post(f"{DRAFT}/sent").mock(return_value=httpx.Response(204))
    respx.put("https://news.test/api/teams/flamengo/latest-edition").mock(
        return_value=httpx.Response(204)
    )
    route = respx.post(RESEND_URL).mock(return_value=sent(["e1"]))

    result = run("send")

    assert result.exit_code == 0, result.output
    [body] = json.loads(route.calls.last.request.content)
    assert body["subject"] == "Urubu News — Notícias — 12/10/2026: Rumor de contratação"
    assert "E um rumor." not in body["html"]


@respx.mock
def test_run_send_keeps_the_opening_when_nothing_was_removed(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)
    env.setattr(pipeline, "get_llm_client", lambda settings: FakeLLMClient(no_build))
    respx.get(DRAFT).mock(return_value=httpx.Response(200, json=drafted()))
    respx.post(f"{DRAFT}/sent").mock(return_value=httpx.Response(204))
    respx.put("https://news.test/api/teams/flamengo/latest-edition").mock(
        return_value=httpx.Response(204)
    )
    route = respx.post(RESEND_URL).mock(return_value=sent(["e1"]))

    result = run("send")

    assert result.exit_code == 0, result.output
    [body] = json.loads(route.calls.last.request.content)
    assert body["subject"] == "Urubu News — Notícias — 12/10/2026: Flamengo vence o Fla-Flu"


@respx.mock
def test_run_send_without_draft_builds_and_sends(env) -> None:
    enable_subscriptions(env)
    use(env, [ARTICLE], MATCH)
    respx.get(DRAFT).mock(return_value=httpx.Response(404))
    respx.put("https://news.test/api/teams/flamengo/latest-edition").mock(
        return_value=httpx.Response(204)
    )
    route = respx.post(RESEND_URL).mock(return_value=sent(["e1"]))

    result = run("send")

    assert result.exit_code == 0, result.output
    assert route.called
    assert "sem revisão" in result.output


@respx.mock
def test_run_send_held_draft_sends_nothing(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)
    respx.get(DRAFT).mock(return_value=httpx.Response(200, json=drafted(held=True)))
    resend = respx.post(RESEND_URL)

    result = run("send")

    assert result.exit_code == 0, result.output
    assert not resend.called
    assert "segurada na revisão" in result.output


@respx.mock
def test_run_send_all_topics_removed_is_done_without_sending(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)
    respx.get(DRAFT).mock(return_value=httpx.Response(200, json=drafted(removed=[0, 1])))
    done = respx.post(f"{DRAFT}/sent").mock(return_value=httpx.Response(204))
    resend = respx.post(RESEND_URL)

    result = run("send")

    assert result.exit_code == 0, result.output  # the owner's choice, not a failure
    assert not resend.called
    assert done.called  # the backup won't try it again
    assert "todos os tópicos tirados" in result.output


@respx.mock
def test_run_send_page_down_sends_nothing(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)
    respx.get(DRAFT).mock(return_value=httpx.Response(503))
    resend = respx.post(RESEND_URL)

    result = run("send")

    assert result.exit_code == 2
    assert not resend.called


@respx.mock
def test_send_twice_sends_once(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)
    already = drafted() | {"sent_at": "2026-10-12T13:02:00-03:00"}
    respx.get(DRAFT).mock(return_value=httpx.Response(200, json=already))
    resend = respx.post(RESEND_URL)

    result = run("send")

    assert result.exit_code == 0, result.output
    assert not resend.called


def test_stages_need_the_page(env) -> None:
    env.delenv("SUBSCRIBERS_API_TOKEN", raising=False)
    get_settings.cache_clear()

    result = run("build")

    assert result.exit_code == 2
    assert "SUBSCRIBERS_API_TOKEN" in result.output


@pytest.mark.parametrize(("hour", "stage"), [(10, "build"), (14, "send")])
def test_run_auto_stage_follows_the_calendar(env, hour, stage) -> None:
    seen = {}
    env.setattr(cli, "_now", lambda: datetime(2026, 10, 12, hour, 0, tzinfo=TZ))
    last = LatestEdition(subject="x", published_at=datetime(2026, 10, 5, 13, 2, tzinfo=TZ))
    env.setattr(cli, "_latest", lambda settings, team: last)
    env.setattr(cli, "_run_stage", lambda stage, *args, **kwargs: seen.setdefault("stage", stage))
    env.setenv("SUBSCRIBERS_API_TOKEN", "api-token")
    get_settings.cache_clear()

    result = CliRunner().invoke(
        cli.app, ["run", "--team", "flamengo", "--edition", "auto", "--stage", "auto"]
    )

    assert result.exit_code == 0, result.output
    assert seen["stage"] == stage


@respx.mock
def test_run_release_sends_the_draft_of_that_day(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)
    respx.get(DRAFT).mock(return_value=httpx.Response(200, json=drafted()))
    respx.post(f"{DRAFT}/sent").mock(return_value=httpx.Response(204))
    respx.put("https://news.test/api/teams/flamengo/latest-edition").mock(
        return_value=httpx.Response(204)
    )
    route = respx.post(RESEND_URL).mock(return_value=sent(["e1"]))

    result = run("release")

    assert result.exit_code == 0, result.output
    [body] = json.loads(route.calls.last.request.content)
    assert body["subject"] == "Urubu News — Notícias — 12/10/2026: Flamengo vence o Fla-Flu"


@respx.mock
def test_run_release_without_a_draft_sends_nothing(env) -> None:
    enable_subscriptions(env)
    env.setattr(pipeline, "build_newsletter", no_build)
    respx.get(DRAFT).mock(return_value=httpx.Response(404))
    resend = respx.post(RESEND_URL)

    result = run("release")

    assert result.exit_code == 1
    assert not resend.called


@respx.mock
def test_build_keeps_the_note_in_the_draft_and_send_uses_it(env) -> None:
    enable_subscriptions(env)
    use(env, [ARTICLE], MATCH)
    respx.get(DRAFT).mock(return_value=httpx.Response(404))
    respx.get("https://news.test/api/teams/flamengo/note").mock(
        return_value=httpx.Response(200, json={"text": "A Geral agora tem uma Central."})
    )
    save = respx.put(DRAFT).mock(return_value=httpx.Response(204))

    assert run("build").exit_code == 0
    body = json.loads(save.calls.last.request.content)
    assert body["newsletter"]["note"] == "A Geral agora tem uma Central."

    respx.get(DRAFT).mock(
        return_value=httpx.Response(
            200, json=body | {"held": False, "removed_topics": [], "sent_at": None}
        )
    )
    respx.post(DRAFT + "/sent").mock(return_value=httpx.Response(204))
    respx.put("https://news.test/api/teams/flamengo/latest-edition").mock(
        return_value=httpx.Response(204)
    )
    route = respx.post(RESEND_URL).mock(return_value=sent(["e1"]))
    assert run("send").exit_code == 0
    mails = json.loads(route.calls.last.request.content)
    assert all("A Geral agora tem uma Central." in m["html"] for m in mails)
