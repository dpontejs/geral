"""Download the jogo da velha base: who played for the board clubs or the Seleção, and where.

Who enters and the categories come from Wikidata, through its API (the SPARQL service throttles
hard); careers (clubs, loans, years) and the Seleção come from the English Wikipedia infobox when
there is one, as in "Onde jogou?". Copa = the
"{year} FIFA World Cup squads" pages plus Wikidata's P1344 on the editions it covers well.
"""

import json
from collections import Counter

import httpx

from geral.games.mediawiki import entities, labels, page_qids, wikitexts, with_statement
from geral.games.onde_jogou import COUNTRY_NAMES
from geral.games.wikipedia import national_teams, parse_career, squad_players

MIN_FAMA = 4  # Wikipedias a player needs to enter: 5758 of 7835 candidates (2026-11-13)
SELECAO = "Q83459"  # the senior Brazil team
BRAZIL = "Q155"
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


def _values(entity: dict, prop: str) -> list[dict]:
    """The statements of `prop` that are not deprecated, with an item as value."""
    return [
        c
        for c in entity.get("claims", {}).get(prop, [])
        if c.get("rank") != "deprecated" and isinstance(_value(c.get("mainsnak", {})), dict)
    ]


def _value(snak: dict):
    return snak.get("datavalue", {}).get("value")


def _ids(entity: dict, prop: str) -> list[str]:
    return [_value(c["mainsnak"])["id"] for c in _values(entity, prop)]


def _year(claim: dict, prop: str) -> int | None:
    for snak in claim.get("qualifiers", {}).get(prop, []):
        time = (_value(snak) or {}).get("time", "")
        if time[1:5].isdigit() and int(time[1:5]) >= 1850:
            return int(time[1:5])
    return None


def _span(starts: list[int], ends: list[int | None]) -> str:
    """'1985–2002'; '2019–' while a stint is open (None); '' when no year is known."""
    if not starts:
        return ""
    if None in ends:
        return f"{min(starts)}–"
    return f"{min(starts)}–{max(e for e in ends if e is not None)}"


def _label(entity: dict) -> str:
    found = entity.get("labels", {})
    return next((found[lang]["value"] for lang in ("pt-br", "pt", "en") if lang in found), "")


def build_base(
    client: httpx.Client, clubs: dict[str, str], min_fama: int = MIN_FAMA
) -> tuple[dict, list[str]]:
    """The `base.json` dict and the report lines."""
    report: list[str] = []
    candidates = set()
    for club in [*sorted(clubs), SELECAO]:
        candidates |= set(with_statement(client, "P54", club))
    print(f"  wikidata: {len(candidates)} players in the board clubs or the Seleção", flush=True)
    links = entities(client, sorted(candidates), "sitelinks")
    fama = {q: len(e.get("sitelinks", {})) for q, e in links.items() if e.get("sitelinks")}
    ids = sorted(q for q, n in fama.items() if n >= min_fama)
    titles = {
        q: links[q]["sitelinks"]["enwiki"]["title"]
        for q in ids
        if "enwiki" in links[q]["sitelinks"]
    }
    about = entities(client, ids, "labels|claims", "pt-br|pt|en")
    names = {q: _label(about.get(q, {})) for q in ids}
    facts = {
        q: {p: _ids(about.get(q, {}), p) for p in ("P413", "P1532", "P27", "P1344")} for q in ids
    }
    stints = {
        q: [
            (_value(c["mainsnak"])["id"], _year(c, "P580"), _year(c, "P582"))
            for c in _values(about.get(q, {}), "P54")
        ]
        for q in ids
    }
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
    country_names = {q: COUNTRY_NAMES.get(n, n) for q, n in labels(client, countries).items()}

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
    return {"paises": country_names, "jogadores": players}, report


def dump(data: dict) -> str:
    """`base.json` with one player per line (a readable diff when the base changes)."""
    lines = [json.dumps(p, ensure_ascii=False) for p in data["jogadores"]]
    paises = json.dumps(data["paises"], ensure_ascii=False, sort_keys=True)
    return '{"paises": ' + paises + ',\n"jogadores": [\n' + ",\n".join(lines) + "\n]}\n"
