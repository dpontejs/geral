import json
from pathlib import Path

import httpx
import pytest
import respx

from geral.games import mediawiki
from geral.games.velha import importacao
from geral.games.velha.base import load

FIXTURES = Path(__file__).parent / "fixtures" / "velha"
CLUBS = {"Q5014111": "Vasco", "Q221695": "Grêmio", "Q80964": "Palmeiras"}
WD = "http://www.wikidata.org/entity/"


def _b(**values: str) -> dict:
    return {
        k: {"value": WD + v if v.startswith("Q") or v.startswith("P") else v}
        for k, v in values.items()
    }


def _sparql(request: httpx.Request) -> httpx.Response:
    query = request.url.params["query"]
    assert "wikibase:label" not in query  # the label service is slow: names come from the API
    if "wikibase:sitelinks" in query:  # members of one club or of the Seleção
        rows = []
        if "wd:Q5014111" in query:
            rows = [
                _b(player="Q1", fama="50"),
                _b(player="Q3", fama="30"),
                _b(player="Q4", fama="1"),
            ]
        elif "wd:Q221695" in query:
            rows = [_b(player="Q2", fama="20")]
        elif "wd:Q83459" in query:
            rows = [_b(player="Q1", fama="50")]
        return httpx.Response(200, json={"results": {"bindings": rows}})
    if "P1344" in query:  # facts
        assert "wd:Q4" not in query  # below MIN_FAMA: never asked about
        rows = [
            _b(player="Q1", prop="P413", value="Q280658"),
            _b(player="Q1", prop="P27", value="Q155"),
            _b(player="Q2", prop="P413", value="Q193592"),
            _b(player="Q2", prop="P1532", value="Q77"),
            _b(player="Q2", prop="P27", value="Q77"),
            _b(player="Q3", prop="P413", value="Q201330"),
            _b(player="Q3", prop="P413", value="Q12345"),  # no group: reported
            _b(player="Q3", prop="P1344", value="Q132515"),  # 1950
            _b(player="Q3", prop="P1344", value="Q20730966"),  # a qualifier, not a Copa
        ]
        return httpx.Response(200, json={"results": {"bindings": rows}})
    if "p:P54" in query:  # Wikidata careers (used without an infobox)
        rows = [
            _b(
                player="Q3",
                club="Q5014111",
                start="1950-01-01T00:00:00Z",
                end="1960-01-01T00:00:00Z",
            ),
            _b(player="Q3", club="Q83459", start="1949-01-01T00:00:00Z"),
            _b(player="Q1", club="Q80845"),  # ignored: Edmundo has an infobox
        ]
        return httpx.Response(200, json={"results": {"bindings": rows}})
    raise AssertionError(query)


PAGES = {
    "Edmundo": (FIXTURES / "edmundo.wiki").read_text(),
    "Uruguaio (footballer)": (FIXTURES / "uruguaio.wiki").read_text(),
    "2018 FIFA World Cup squads": (FIXTURES / "2018_squads.wiki").read_text(),
}
PAGE_IDS = {
    "CR Vasco da Gama": "Q5014111",
    "SE Palmeiras": "Q80964",
    "Grêmio FBPA": "Q221695",
    "Club Nacional de Football": "Q6",
    "Brazil national football team": "Q83459",
    "Brazil national under-20 football team": "Q7",
    "Uruguay national football team": "Q8",
    "Fernando Muslera": "Q9",
    "Uruguaio (footballer)": "Q2",
}
REDIRECTS = {"Luis Uruguayo": "Uruguaio (footballer)"}


def _enwiki(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    titles = params["titles"].split("|")
    redirects = [{"from": t, "to": REDIRECTS[t]} for t in titles if t in REDIRECTS]
    finals = [REDIRECTS.get(t, t) for t in titles]
    if params["prop"] == "revisions":
        pages = [
            {"title": t, "revisions": [{"slots": {"main": {"content": PAGES[t]}}}]}
            if t in PAGES
            else {"title": t, "missing": True}
            for t in finals
        ]
    else:
        pages = [
            {"title": t, "pageprops": {"wikibase_item": PAGE_IDS[t]}}
            if t in PAGE_IDS
            else {"title": t, "missing": True}
            for t in finals
        ]
    return httpx.Response(200, json={"query": {"pages": pages, "redirects": redirects}})


LABELS = {"Q1": "Edmundo", "Q2": "Uruguaio", "Q3": "Barbosa", "Q77": "Uruguai"}


def _wikidata(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    ids = params["ids"].split("|")
    if params["props"] == "labels":
        assert params["languages"] == "pt-br|pt|en"
        entities = {q: {"labels": {"pt-br": {"value": LABELS[q]}}} for q in ids}
        return httpx.Response(200, json={"entities": entities})
    titles = {"Q1": "Edmundo", "Q2": "Uruguaio (footballer)"}
    entities = {
        q: {"sitelinks": {"enwiki": {"title": titles[q]}}} if q in titles else {} for q in ids
    }
    return httpx.Response(200, json={"entities": entities})


@pytest.fixture
def network(monkeypatch):
    monkeypatch.setattr(mediawiki.time, "sleep", lambda s: None)
    with respx.mock:
        respx.get(mediawiki.SPARQL).mock(side_effect=_sparql)
        respx.get(mediawiki.ENWIKI).mock(side_effect=_enwiki)
        respx.get(mediawiki.WIKIDATA).mock(side_effect=_wikidata)
        yield


def test_import_base_builds_from_recorded_wikidata_and_wikipedia(network, tmp_path) -> None:
    with httpx.Client() as client:
        data, report = importacao.build_base(client, CLUBS, min_fama=2)
    players = {p["id"]: p for p in data["jogadores"]}
    assert sorted(players) == ["Q1", "Q2", "Q3"]  # Q4 is below the minimum fama
    assert players["Q1"] == {
        "id": "Q1",
        "nome": "Edmundo",
        "anos": "1985–2002",
        "posicoes": ["atacante"],
        "paises": [],
        "fama": 50,
        "clubes": ["Q5014111", "Q80964"],  # the loan counts, the youth club does not
        "selecao": True,
        "copa": False,
    }
    assert players["Q2"]["anos"] == "2015–"  # the whole career, Nacional included
    assert players["Q2"]["clubes"] == ["Q221695"]
    assert players["Q2"]["paises"] == ["Q77"]
    assert players["Q2"]["selecao"] is False
    assert players["Q2"]["copa"] is True  # through a squads link that is a redirect
    assert players["Q3"]["anos"] == "1950–1960"  # clubs only, as in the infobox
    assert players["Q3"]["clubes"] == ["Q5014111"]
    assert players["Q3"]["selecao"] is True
    assert players["Q3"]["copa"] is True
    assert players["Q3"]["posicoes"] == ["goleiro"]
    assert data["paises"] == {"Q77": "Uruguai"}
    assert any("Q12345" in line for line in report)

    path = tmp_path / "base.json"
    path.write_text(importacao.dump(data), encoding="utf-8")
    assert json.loads(path.read_text()) == data
    clubs = tmp_path / "clubes.toml"
    clubs.write_text("".join(f'[{q}]\nnome = "{n}"\n' for q, n in CLUBS.items()))
    base = load(path, clubs)
    assert base.players["Q1"].clubes == frozenset({"Q5014111", "Q80964"})
    assert base.countries == {"Q77": "Uruguai"}
