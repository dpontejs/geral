import json
from pathlib import Path

import httpx
import pytest
import respx

from geral.games import mediawiki
from geral.games.velha import importacao
from geral.games.velha.base import load

FIXTURES = Path(__file__).parent / "fixtures" / "velha"
CLUBS = {"Q5014111": "Vasco", "Q221695": "Grêmio", "Q80964": "Palmeiras", "Q17479": "Flamengo"}


def _claim(qid: str, start: str = "", end: str = "", rank: str = "normal") -> dict:
    qualifiers = {}
    for prop, year in (("P580", start), ("P582", end)):
        if year:
            time = {"time": f"+{year}-01-01T00:00:00Z"}
            qualifiers[prop] = [{"datavalue": {"value": time}}]
    snak = {"datavalue": {"value": {"id": qid}}}
    return {"mainsnak": snak, "qualifiers": qualifiers, "rank": rank}


MEMBERS = {"Q5014111": ["Q1", "Q3", "Q4"], "Q221695": ["Q2"], "Q17479": ["Q5"], "Q83459": ["Q1"]}
FAMA = {"Q1": 50, "Q2": 20, "Q3": 30, "Q4": 1, "Q5": 40}
ENWIKI = {"Q1": "Edmundo", "Q2": "Uruguaio (footballer)"}
NAMES = {"Q1": "Edmundo", "Q2": "Uruguaio", "Q3": "Barbosa", "Q5": "Oscar", "Q77": "Uruguai"}
FOOTBALLER = [_claim("Q937857")]
CLAIMS = {
    "Q5": {  # a basketball player of Flamengo: not in the base
        "P106": [_claim("Q3665646")],
        "P413": [_claim("Q308879")],
        "P54": [_claim("Q17479", "1980", "1990")],
    },
    "Q1": {
        "P106": FOOTBALLER,
        "P413": [_claim("Q280658")],
        "P27": [_claim("Q155")],
        "P54": [_claim("Q80845")],  # ignored: Edmundo has an infobox
    },
    "Q2": {
        "P106": FOOTBALLER,
        "P413": [_claim("Q193592"), _claim("Q2827965")],  # winger: atacante too
        "P1532": [_claim("Q77")],
        "P27": [_claim("Q77")],
    },
    "Q3": {
        "P106": FOOTBALLER,
        "P413": [_claim("Q201330"), _claim("Q12345")],  # Q12345 has no group: reported
        "P1344": [_claim("Q132515"), _claim("Q20730966")],  # 1950; a qualifier is no Copa
        "P54": [
            _claim("Q5014111", "1950", "1960"),
            _claim("Q83459", "1949"),
            _claim("Q221695", "1940", "1941", rank="deprecated"),
        ],
    },
}


def _wikidata(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    if params.get("list") == "search":
        club = params["srsearch"].removeprefix("haswbstatement:P54=")
        hits = [{"title": q} for q in MEMBERS.get(club, [])]
        return httpx.Response(200, json={"query": {"search": hits}})
    ids = params["ids"].split("|")
    if params["props"] == "sitelinks":
        entities = {
            q: {
                "sitelinks": {f"wiki{n}": {"title": "x"} for n in range(FAMA[q] - 1)}
                | ({"enwiki": {"title": ENWIKI[q]}} if q in ENWIKI else {"xwiki": {"title": "x"}})
            }
            for q in ids
        }
    elif params["props"] == "labels|claims":
        assert "Q4" not in ids  # below the minimum fama: never asked about
        entities = {
            q: {"labels": {"pt-br": {"value": NAMES[q]}}, "claims": CLAIMS.get(q, {})} for q in ids
        }
    else:
        assert params["props"] == "labels"
        entities = {q: {"labels": {"pt-br": {"value": NAMES[q]}}} for q in ids}
    return httpx.Response(200, json={"entities": entities})


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


@pytest.fixture
def network(monkeypatch):
    monkeypatch.setattr(mediawiki.time, "sleep", lambda s: None)
    with respx.mock:
        respx.get(mediawiki.SPARQL).mock(side_effect=AssertionError("no SPARQL: rate limited"))
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
    assert players["Q2"]["posicoes"] == ["meio-campo", "atacante"]
    assert players["Q2"]["selecao"] is False
    assert players["Q2"]["copa"] is True  # through a squads link that is a redirect
    assert players["Q3"]["anos"] == "1950–1960"  # clubs only, as in the infobox
    assert players["Q3"]["clubes"] == ["Q5014111"]
    assert players["Q3"]["selecao"] is True
    assert players["Q3"]["copa"] is True
    assert players["Q3"]["posicoes"] == ["goleiro"]
    assert data["paises"] == {"Q77": "Uruguai"}
    assert any("Q12345" in line for line in report)
    assert any("1 not footballers" in line for line in report)

    path = tmp_path / "base.json"
    path.write_text(importacao.dump(data), encoding="utf-8")
    assert json.loads(path.read_text()) == data
    clubs = tmp_path / "clubes.toml"
    clubs.write_text("".join(f'[{q}]\nnome = "{n}"\n' for q, n in CLUBS.items()))
    base = load(path, clubs)
    assert base.players["Q1"].clubes == frozenset({"Q5014111", "Q80964"})
    assert base.countries == {"Q77": "Uruguai"}
