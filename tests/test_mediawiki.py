import httpx
import respx

from geral.games import mediawiki


@respx.mock
def test_api_waits_and_retries_on_429(monkeypatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(mediawiki.time, "sleep", waits.append)
    route = respx.get("https://en.wikipedia.org/w/api.php").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={"query": {"pages": []}}),
        ]
    )
    with httpx.Client() as client:
        assert mediawiki.api(client, mediawiki.ENWIKI, {"action": "query"}) == {
            "query": {"pages": []}
        }
    assert route.call_count == 2
    assert waits[0] == 1


@respx.mock
def test_sparql_returns_the_bindings(monkeypatch) -> None:
    monkeypatch.setattr(mediawiki.time, "sleep", lambda s: None)
    respx.get(mediawiki.SPARQL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"results": {"bindings": [{"x": {"value": "1"}}]}}),
        ]
    )
    with httpx.Client() as client:
        assert mediawiki.sparql(client, "SELECT 1") == [{"x": {"value": "1"}}]


def _page(title: str, text: str | None) -> dict:
    page = {"title": title}
    if text is not None:
        page["revisions"] = [{"slots": {"main": {"content": text}}}]
    return page


@respx.mock
def test_wikitexts_follows_continue_when_a_batch_is_too_big(monkeypatch) -> None:
    monkeypatch.setattr(mediawiki.time, "sleep", lambda s: None)
    first = {
        "continue": {"rvcontinue": "123|456", "continue": "||"},
        "query": {"pages": [_page("A", "text a"), _page("B", None)]},
    }
    second = {"query": {"pages": [_page("A", None), _page("B", "text b")]}}
    route = respx.get(mediawiki.ENWIKI).mock(
        side_effect=[httpx.Response(200, json=first), httpx.Response(200, json=second)]
    )
    with httpx.Client() as client:
        assert mediawiki.wikitexts(client, ["A", "B"]) == {"A": "text a", "B": "text b"}
    assert route.calls[1].request.url.params["rvcontinue"] == "123|456"


@respx.mock
def test_labels_prefer_brazilian_portuguese(monkeypatch) -> None:
    monkeypatch.setattr(mediawiki.time, "sleep", lambda s: None)
    labels = {
        "Q1": {"pt-br": {"value": "Seleção"}, "pt": {"value": "Selecção"}},
        "Q2": {"en": {"value": "Only English"}},
        "Q3": {},
    }
    respx.get(mediawiki.WIKIDATA).mock(
        return_value=httpx.Response(
            200, json={"entities": {q: {"labels": v} for q, v in labels.items()}}
        )
    )
    with httpx.Client() as client:
        assert mediawiki.labels(client, ["Q1", "Q2", "Q3"]) == {
            "Q1": "Seleção",
            "Q2": "Only English",
            "Q3": "",
        }


@respx.mock
def test_with_statement_pages_through_the_search(monkeypatch) -> None:
    monkeypatch.setattr(mediawiki.time, "sleep", lambda s: None)
    route = respx.get(mediawiki.WIKIDATA).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "continue": {"sroffset": 2, "continue": "-||"},
                    "query": {"search": [{"title": "Q1"}, {"title": "Q2"}]},
                },
            ),
            httpx.Response(200, json={"query": {"search": [{"title": "Q3"}]}}),
        ]
    )
    with httpx.Client() as client:
        assert mediawiki.with_statement(client, "P54", "Q17479") == ["Q1", "Q2", "Q3"]
    first = route.calls[0].request.url.params
    assert first["srsearch"] == "haswbstatement:P54=Q17479"
    assert route.calls[1].request.url.params["sroffset"] == "2"


@respx.mock
def test_entities_come_in_batches_of_fifty(monkeypatch) -> None:
    monkeypatch.setattr(mediawiki.time, "sleep", lambda s: None)

    def answer(request: httpx.Request) -> httpx.Response:
        ids = request.url.params["ids"].split("|")
        assert len(ids) <= 50
        assert request.url.params["props"] == "sitelinks"
        return httpx.Response(200, json={"entities": {q: {"id": q} for q in ids}})

    route = respx.get(mediawiki.WIKIDATA).mock(side_effect=answer)
    qids = [f"Q{n}" for n in range(1, 121)]
    with httpx.Client() as client:
        found = mediawiki.entities(client, qids, "sitelinks")
    assert sorted(found) == sorted(qids)
    assert route.call_count == 3


@respx.mock
def test_page_qids_skips_what_cannot_be_a_title(monkeypatch) -> None:
    monkeypatch.setattr(mediawiki.time, "sleep", lambda s: None)

    def answer(request: httpx.Request) -> httpx.Response:
        titles = request.url.params["titles"].split("|")
        assert titles == ["Grêmio FBPA"]
        page = {"title": "Grêmio FBPA", "pageprops": {"wikibase_item": "Q221695"}}
        return httpx.Response(200, json={"query": {"pages": [page]}})

    respx.get(mediawiki.ENWIKI).mock(side_effect=answer)
    with httpx.Client() as client:
        found = mediawiki.page_qids(client, ["União|Sociedade Esportiva União", "Grêmio FBPA", " "])
    assert found == {"Grêmio FBPA": "Q221695"}
