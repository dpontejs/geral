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
