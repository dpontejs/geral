"""Download the jogo da velha base: who played for the board clubs or the Seleção, and where.

Who enters and the categories come from Wikidata; careers (clubs, loans, years) and the Seleção
come from the English Wikipedia infobox when there is one, as in "Onde jogou?". Copa = the
"{year} FIFA World Cup squads" pages plus Wikidata's P1344 on the editions it covers well.
"""

import json
from collections import Counter

import httpx

from geral.games.mediawiki import enwiki_titles, page_qids, sparql, wikitexts
from geral.games.onde_jogou import COUNTRY_NAMES
from geral.games.wikipedia import national_teams, parse_career, squad_players

MIN_FAMA = 3  # Wikipedias a player needs to enter (keeps the base at 3–6 thousand)
SELECAO = "Q83459"  # the senior Brazil team
BRAZIL = "Q155"
CHUNK = 100  # players per SPARQL query
# P1344 is well filled for these editions (1930–2018); 2022 is thin and 2026 mixes qualifiers.
EDITIONS = {
    "Q48432", "Q1477177", "Q131591", "Q132515", "Q131075", "Q132533", "Q160813", "Q134202",
    "Q132664", "Q166121", "Q46943", "Q46934", "Q46938", "Q132529", "Q101751", "Q101730",
    "Q47735", "Q37285", "Q176883", "Q79859", "Q170645",
}  # fmt: skip
WORLD_CUPS = (
    1930, 1934, 1938, 1950, 1954, 1958, 1962, 1966, 1970, 1974, 1978, 1982, 1986, 1990, 1994,
    1998, 2002, 2006, 2010, 2014, 2018, 2022, 2026,
)  # fmt: skip
POSITION_GROUPS = {
    "Q201330": "goleiro", "Q172964": "goleiro",
    "Q336286": "zagueiro", "Q268258": "zagueiro",
    "Q90173132": "lateral",
    "Q193592": "meio-campo", "Q904289": "meio-campo", "Q8025128": "meio-campo",
    "Q90326494": "meio-campo", "Q18691898": "meio-campo", "Q1201458": "meio-campo",
    "Q280658": "atacante", "Q9731197": "atacante", "Q3446915": "atacante",
    "Q11681748": "atacante",
}  # fmt: skip

MEMBERS = """
SELECT ?player ?playerLabel ?fama WHERE {
  ?player wdt:P54 wd:%s ; wikibase:sitelinks ?fama .
  FILTER(?fama >= %d)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt-br,pt,en". }
}
"""
FACTS = """
SELECT ?player ?prop ?value WHERE {
  VALUES ?player { %s }
  VALUES ?prop { wdt:P413 wdt:P1532 wdt:P27 wdt:P1344 }
  ?player ?prop ?value .
}
"""
CAREERS = """
SELECT ?player ?club ?start ?end WHERE {
  VALUES ?player { %s }
  ?player p:P54 ?st . ?st ps:P54 ?club .
  OPTIONAL { ?st pq:P580 ?start }
  OPTIONAL { ?st pq:P582 ?end }
}
"""
LABELS = """
SELECT ?item ?itemLabel WHERE {
  VALUES ?item { %s }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt-br,pt,en". }
}
"""


def _id(binding: dict, key: str) -> str:
    return binding.get(key, {}).get("value", "").rsplit("/", 1)[-1]


def _year(binding: dict, key: str) -> int | None:
    value = binding.get(key, {}).get("value", "")
    return int(value[:4]) if value[:4].isdigit() and int(value[:4]) >= 1850 else None


def _span(starts: list[int], ends: list[int | None]) -> str:
    """'1985–2002'; '2019–' while a stint is open (None); '' when no year is known."""
    if not starts:
        return ""
    if None in ends:
        return f"{min(starts)}–"
    return f"{min(starts)}–{max(e for e in ends if e is not None)}"


def _chunks(ids: list[str]):
    for i in range(0, len(ids), CHUNK):
        yield " ".join(f"wd:{q}" for q in ids[i : i + CHUNK])


def build_base(
    client: httpx.Client, clubs: dict[str, str], min_fama: int = MIN_FAMA
) -> tuple[dict, list[str]]:
    """The `base.json` dict and the report lines."""
    report: list[str] = []
    names, fama = {}, {}
    for club in [*sorted(clubs), SELECAO]:
        for b in sparql(client, MEMBERS % (club, min_fama)):
            if int(b["fama"]["value"]) >= min_fama:
                names[_id(b, "player")] = b.get("playerLabel", {}).get("value", "")
                fama[_id(b, "player")] = int(b["fama"]["value"])
    ids = sorted(names)
    print(f"  wikidata: {len(ids)} players with fama >= {min_fama}", flush=True)

    facts: dict[str, dict[str, list[str]]] = {q: {} for q in ids}
    stints: dict[str, list[tuple[str, int | None, int | None]]] = {q: [] for q in ids}
    for values in _chunks(ids):
        for b in sparql(client, FACTS % values):
            facts[_id(b, "player")].setdefault(_id(b, "prop"), []).append(_id(b, "value"))
        for b in sparql(client, CAREERS % values):
            stints[_id(b, "player")].append((_id(b, "club"), _year(b, "start"), _year(b, "end")))

    titles = enwiki_titles(client, ids)
    pages = wikitexts(client, sorted(set(titles.values())))
    texts = {q: pages.get(t, "") for q, t in titles.items()}
    careers = {q: parse_career(text) for q, text in texts.items()}
    teams = {q: national_teams(text) for q, text in texts.items()}

    squads: dict[int, list[str]] = {}
    for year in WORLD_CUPS:  # one page per call: each is large
        title = f"{year} FIFA World Cup squads"
        squads[year] = squad_players(wikitexts(client, [title])[title])
    targets = {s.target for c in careers.values() for s in c}
    targets |= {t for ts in teams.values() for t in ts}
    targets |= {t for ts in squads.values() for t in ts}
    page_ids = page_qids(client, sorted(targets))
    in_squads = {page_ids[t] for ts in squads.values() for t in ts if t in page_ids}

    players, ungrouped, from_wikidata, dropped = [], Counter(), 0, 0
    for q in ids:
        if careers.get(q):
            club_ids = {page_ids.get(s.target) for s in careers[q] if s.start is not None}
            known = [s for s in careers[q] if s.start is not None]
            anos = _span([s.start for s in known], [s.end for s in known])
            selecao = any(page_ids.get(t) == SELECAO for t in teams[q])
        else:
            from_wikidata += 1
            club_ids = {club for club, _, _ in stints[q]}
            rows = [(s, e) for club, s, e in stints[q] if club in clubs and club != SELECAO]
            years = [y for row in rows for y in row if y is not None]
            anos = f"{min(years)}–{max(years)}" if years else ""
            selecao = SELECAO in club_ids
        board_clubs = sorted(club_ids & set(clubs))
        if not board_clubs and not selecao:
            dropped += 1  # in Wikidata's P54 only (a youth stint, say): no category of its own
            continue
        f = facts[q]
        posicoes = []
        for pos in f.get("P413", []):
            if pos not in POSITION_GROUPS:
                ungrouped[pos] += 1
            elif POSITION_GROUPS[pos] not in posicoes:
                posicoes.append(POSITION_GROUPS[pos])
        paises = f.get("P1532") or (f["P27"] if len(f.get("P27", [])) == 1 else [])
        paises = sorted({p for p in paises if p != BRAZIL})
        copa = q in in_squads or bool(EDITIONS & set(f.get("P1344", [])))
        players.append(
            {
                "id": q,
                "nome": names[q],
                "anos": anos,
                "posicoes": posicoes,
                "paises": paises,
                "fama": fama[q],
                "clubes": board_clubs,
                "selecao": selecao,
                "copa": copa,
            }
        )

    countries = sorted({p for player in players for p in player["paises"]})
    labels = {}
    for values in _chunks(countries):
        for b in sparql(client, LABELS % values):
            label = b.get("itemLabel", {}).get("value", "")
            labels[_id(b, "item")] = COUNTRY_NAMES.get(label, label)

    by_club = Counter(c for p in players for c in p["clubes"])
    report.append(f"{len(players)} players (fama >= {min_fama}); {dropped} left out (no category)")
    report.append(f"{from_wikidata} careers from Wikidata (no Wikipedia infobox)")
    report.append(f"Seleção: {sum(p['selecao'] for p in players)}")
    wikidata_copa = sum(bool(EDITIONS & set(facts[p["id"]].get("P1344", []))) for p in players)
    report.append(
        f"Copa: {sum(p['copa'] for p in players)} "
        f"({sum(p['id'] in in_squads for p in players)} from the squads pages, "
        f"{wikidata_copa} from Wikidata)"
    )
    report.append("squads pages: " + ", ".join(f"{y}: {len(s)}" for y, s in squads.items()))
    report += [f"  {clubs[c]}: {by_club[c]}" for c in sorted(clubs, key=lambda c: by_club[c])]
    report += [f"position without group: {pos} ({n})" for pos, n in ungrouped.most_common()]
    return {"paises": labels, "jogadores": players}, report


def dump(data: dict) -> str:
    """`base.json` with one player per line (a readable diff when the base changes)."""
    lines = [json.dumps(p, ensure_ascii=False) for p in data["jogadores"]]
    paises = json.dumps(data["paises"], ensure_ascii=False, sort_keys=True)
    return '{"paises": ' + paises + ',\n"jogadores": [\n' + ",\n".join(lines) + "\n]}\n"
