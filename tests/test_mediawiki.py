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
