import json
from datetime import date

import httpx
import pytest
import respx
from fakes import FakeLLMClient

from geral.config import Settings
from geral.specials import job
from geral.specials.sources import Passage
from geral.summarizer.client import LLMError
from geral.teams import get_team

API = "https://geral.test/api/teams/nautico/stories"
MONDAY, SUNDAY = date(2026, 11, 16), date(2026, 11, 22)
TEXT = " ".join(["O Náutico venceu o Sport por 7 a 3 em 1947 nos Aflitos."] * 14)


def passage(n: int, kind: str = "jogo") -> Passage:
    return Passage(kind=kind, key=f"k{n}", title=f"Trecho {n}", url=f"https://w/{n}", text=TEXT)


def settings() -> Settings:
    return Settings(
        SUBSCRIBERS_API_TOKEN="api-token", PUBLIC_URL="https://geral.test", DRY_RUN=False
    )


def faithful(prompt, schema):
    return {"title": "O sete a três", "body": TEXT, "summary": "Uma goleada.", "fact_date": "1947"}


def page(unused: int, seen: list[str]):
    respx.get(f"{API}/count").mock(return_value=httpx.Response(200, json={"unused": unused}))
    respx.get(f"{API}/sources").mock(return_value=httpx.Response(200, json=seen))
    return respx.post(API).mock(return_value=httpx.Response(204))


@pytest.fixture
def sources(monkeypatch):
    found = [passage(n, kind) for n, kind in enumerate(["jogo", "idolo", "clube"] * 2)]
    monkeypatch.setattr(job.sources, "passages", lambda client, team: found)
    return found


def posted(route) -> list[dict]:
    return [json.loads(call.request.content) for call in route.calls]


@respx.mock
def test_job_tops_up_to_10_and_skips_used_sources(sources) -> None:
    route = page(unused=7, seen=["k0"])

    report = job.top_up(
        get_team("nautico"), settings(), FakeLLMClient(faithful), httpx.Client(), MONDAY
    )

    keys = [s["source_key"] for s in posted(route)]
    assert len(keys) == 3 and "k0" not in keys
    assert report.accepted == 3 and report.rejected == 0
    assert all(s["rejected_reason"] is None for s in posted(route))


@respx.mock
def test_job_interleaves_the_kinds(sources) -> None:
    route = page(unused=7, seen=[])

    job.top_up(get_team("nautico"), settings(), FakeLLMClient(faithful), httpx.Client(), MONDAY)

    assert sorted(s["kind"] for s in posted(route)) == ["clube", "idolo", "jogo"]


@respx.mock
def test_job_does_nothing_with_8_or_more_unless_sunday(sources) -> None:
    route = page(unused=8, seen=[])
    llm = FakeLLMClient(faithful)

    report = job.top_up(get_team("nautico"), settings(), llm, httpx.Client(), MONDAY)

    assert llm.prompts == [] and not route.called
    assert report.skipped_reason == "acervo com 8 histórias"
    job.top_up(get_team("nautico"), settings(), llm, httpx.Client(), SUNDAY)
    assert len(posted(route)) == 2


@respx.mock
def test_job_records_rejections_with_the_reason(sources) -> None:
    route = page(unused=7, seen=[])

    def invents(prompt, schema):
        return faithful(prompt, schema) | {"body": TEXT + " Em 1999, o atacante Bita fez 3 gols."}

    report = job.top_up(
        get_team("nautico"), settings(), FakeLLMClient(invents), httpx.Client(), MONDAY
    )

    stories = posted(route)
    assert report.rejected == len(stories) == 6 and report.accepted == 0  # tried every source
    assert "1999" in stories[0]["rejected_reason"] and "Bita" in stories[0]["rejected_reason"]


@respx.mock
def test_job_drops_a_fact_date_not_in_the_source(sources) -> None:
    route = page(unused=7, seen=[])

    def dated(prompt, schema):
        return faithful(prompt, schema) | {"fact_date": "1950-01-01"}

    job.top_up(get_team("nautico"), settings(), FakeLLMClient(dated), httpx.Client(), MONDAY)

    assert posted(route)[0]["fact_date"] == ""


@respx.mock
def test_job_keeps_what_it_wrote_when_the_llm_fails(sources) -> None:
    route = page(unused=0, seen=[])
    calls = []

    def flaky(prompt, schema):
        calls.append(prompt)
        if len(calls) > 1:
            raise LLMError("quota")
        return faithful(prompt, schema)

    report = job.top_up(
        get_team("nautico"), settings(), FakeLLMClient(flaky), httpx.Client(), MONDAY
    )

    assert len(posted(route)) == 1 and report.accepted == 1
    assert "quota" in report.problems[0]


@respx.mock
def test_job_without_the_page_writes_nothing(sources) -> None:
    respx.get(f"{API}/count").mock(return_value=httpx.Response(503))
    llm = FakeLLMClient(faithful)

    report = job.top_up(get_team("nautico"), settings(), llm, httpx.Client(), MONDAY)

    assert llm.prompts == []
    assert report.skipped_reason == "portal fora do ar"


def test_acervo_all_runs_every_specials_team(monkeypatch) -> None:
    from typer.testing import CliRunner

    import geral.__main__ as cli

    seen = []

    def fake(team, settings, llm, wiki, today):
        seen.append(team.slug)
        return job.TopUpReport(team=team.slug, accepted=2, rejected=1)

    monkeypatch.setattr(job, "top_up", fake)
    monkeypatch.setattr(cli.pipeline, "get_llm_client", lambda settings: FakeLLMClient(faithful))

    result = CliRunner().invoke(cli.app, ["acervo", "--all"])

    assert result.exit_code == 0, result.output
    assert sorted(seen) == ["abc", "csa", "nautico"]
    assert "nautico: 2 aceitas, 1 recusadas" in result.output


def test_refusal_reads_the_section_title_as_source() -> None:
    from geral.specials.writer import StoryDraft

    p = Passage(kind="jogo", key="k", title="Clube — 2013: rebaixamento", url="u", text=TEXT)
    story = StoryDraft(
        title="O ano difícil",
        body="Em 2013, o Náutico caiu. " + TEXT,
        summary="Queda.",
        kind="jogo",
        source_key="k",
        source_url="u",
        source_title=p.title,
    )

    assert job.refusal(story, p, get_team("nautico")) is None


def test_a_story_that_never_names_the_club_is_refused() -> None:
    from geral.specials.writer import StoryDraft

    other = " ".join(["O atacante brilhou no Bahia em 1978 com gols de cabeça."] * 12)
    p = Passage(kind="idolo", key="k", title="Osni Lopes", url="u", text=other + " Náutico")
    story = StoryDraft(
        title="Osni",
        body=other,
        summary="Artilheiro.",
        kind="idolo",
        source_key="k",
        source_url="u",
        source_title="Osni Lopes",
    )

    assert job.refusal(story, p, get_team("nautico")) == "não fala do clube"


@respx.mock
def test_job_cuts_a_fact_date_to_the_year_when_day_and_month_are_not_in_the_source(sources) -> None:
    route = page(unused=7, seen=[])

    def dated(prompt, schema):
        return faithful(prompt, schema) | {"fact_date": "1947-06-14"}

    job.top_up(get_team("nautico"), settings(), FakeLLMClient(dated), httpx.Client(), MONDAY)

    assert posted(route)[0]["fact_date"] == "1947"


def test_fact_date_keeps_day_and_month_found_in_the_source() -> None:
    text = "Em 14 de junho de 1947 o Náutico venceu. Em 19/08/1934 nasceu o Timbu."

    assert job.checked_date("1947-06-14", text) == "1947-06-14"
    assert job.checked_date("1934-08-19", text) == "1934-08-19"
    assert job.checked_date("1947-06-15", text) == "1947"
    assert job.checked_date("1950", text) == ""


@respx.mock
def test_a_duplicate_story_is_not_counted_as_accepted(sources) -> None:
    respx.get(f"{API}/count").mock(return_value=httpx.Response(200, json={"unused": 7}))
    respx.get(f"{API}/sources").mock(return_value=httpx.Response(200, json=[]))
    respx.post(API).mock(return_value=httpx.Response(409))

    report = job.top_up(
        get_team("nautico"), settings(), FakeLLMClient(faithful), httpx.Client(), MONDAY
    )

    assert report.accepted == 0


@respx.mock
def test_a_wikipedia_error_skips_only_that_team(monkeypatch) -> None:
    page(unused=0, seen=[])

    def down(client, team):
        raise httpx.HTTPStatusError(
            "503", request=httpx.Request("GET", "u"), response=httpx.Response(503)
        )

    monkeypatch.setattr(job.sources, "passages", down)

    report = job.top_up(
        get_team("nautico"), settings(), FakeLLMClient(faithful), httpx.Client(), MONDAY
    )

    assert report.skipped_reason == "Wikipédia fora do ar"


def test_an_impossible_date_is_cut_to_the_year() -> None:
    assert job.checked_date("1934-06-31", "Em 31/06/1934, um registro errado.") == "1934"


@respx.mock
def test_job_saves_birthdays_on_sunday(monkeypatch) -> None:
    found = [passage(1, "idolo")]
    monkeypatch.setattr(job.sources, "passages", lambda client, team: found)
    monkeypatch.setattr(
        job,
        "birthdays",
        lambda client, passages: [{"name": "Bita", "birth_date": "1941-03-06", "source_url": "u"}],
    )
    page(unused=10, seen=[])
    saved = respx.put("https://geral.test/api/teams/nautico/birthdays").mock(
        return_value=httpx.Response(204)
    )
    llm = FakeLLMClient(faithful)

    job.top_up(get_team("nautico"), settings(), llm, httpx.Client(), SUNDAY)

    assert json.loads(saved.calls.last.request.content)[0]["name"] == "Bita"
    assert llm.prompts == []  # the stock is full: birthdays only


def test_a_story_naming_an_excluded_term_is_refused() -> None:
    from geral.specials.writer import StoryDraft

    text = " ".join(["O CSA venceu o CRB em 1980 diante da Mancha Azul."] * 12)
    p = Passage(kind="clube", key="k", title="Torcida", url="u", text=text)
    story = StoryDraft(
        title="A festa",
        body=text,
        summary="Festa.",
        kind="clube",
        source_key="k",
        source_url="u",
        source_title="Torcida",
    )

    assert job.refusal(story, p, get_team("csa")) == "cita termo excluído"
