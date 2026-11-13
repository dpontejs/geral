"""Download the careers of the players in `jogadores.toml` into `carreiras.json`.

The clubs and years come from the English Wikipedia infobox (kept current by its editors); Wikidata
gives the position, the club names and countries, and the whole career of a player whose page has
no infobox. Run with `uv run python scripts/import_carreiras.py`, review the diff of the generated
file, then commit it. Club names are fixed in `src/geral/games/clubes.toml`; after editing it, rerun
with `--cache` to rebuild from the last download (kept outside the repo) without asking again.
"""

import json
import sys
import tomllib
from pathlib import Path

import httpx
from congelar_calendario import freeze_until_tomorrow  # scripts/, next to this one

from geral.games.mediawiki import HEADERS, enwiki_titles, page_qids, sparql, wikitexts
from geral.games.onde_jogou import CAREERS, PLAYERS, convert, load_fixes
from geral.games.wikipedia import career_rows, load_links, parse_career

QUERY = """
SELECT ?player ?club ?clubLabel ?clubShort ?countryLabel ?start ?end ?positionLabel WHERE {
  VALUES ?player { %s }
  ?player p:P54 ?st . ?st ps:P54 ?club .
  OPTIONAL { ?st pq:P580 ?start }
  OPTIONAL { ?st pq:P582 ?end }
  OPTIONAL { ?club wdt:P1813 ?clubShort . FILTER(LANG(?clubShort) IN ("pt", "pt-br", "mul")) }
  OPTIONAL { ?player wdt:P413 ?position }
  OPTIONAL { ?club wdt:P17 ?country }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt-br,pt,en". }
}
"""
CHUNK = 30
CACHE = Path.home() / ".cache" / "geral" / "wikidata-carreiras.json"
WIKI_CACHE = Path.home() / ".cache" / "geral" / "wikipedia-carreiras.json"
CLUBS_QUERY = """
SELECT ?club ?clubLabel ?clubShort ?countryLabel WHERE {
  VALUES ?club { %s }
  OPTIONAL { ?club wdt:P1813 ?clubShort . FILTER(LANG(?clubShort) IN ("pt", "pt-br", "mul")) }
  OPTIONAL { ?club wdt:P17 ?country }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt-br,pt,en". }
}
"""


def fetch(client: httpx.Client, qids: list[str]) -> list[dict]:
    rows = []
    for b in sparql(client, QUERY % " ".join(f"wd:{q}" for q in qids)):

        def value(key: str, b: dict = b) -> str:
            return b.get(key, {}).get("value", "")

        rows.append(
            {
                "player": value("player").rsplit("/", 1)[-1],
                "club": value("club").rsplit("/", 1)[-1],
                "clubLabel": value("clubLabel"),
                "clubShort": value("clubShort"),
                "country": value("countryLabel"),
                "start": value("start"),
                "end": value("end"),
                "national": False,  # dropped by name (NOT_A_CLUB) and by clubes.toml instead
                "position": value("positionLabel"),
            }
        )
    return rows


def club_info(client: httpx.Client, qids: list[str]) -> dict[str, dict[str, str]]:
    info = {}
    for i in range(0, len(qids), CHUNK):
        query = CLUBS_QUERY % " ".join(f"wd:{q}" for q in qids[i : i + CHUNK])
        for b in sparql(client, query):
            club = b["club"]["value"].rsplit("/", 1)[-1]
            about = info.setdefault(club, {"label": "", "short": "", "country": ""})
            about["label"] = about["label"] or b.get("clubLabel", {}).get("value", "")
            about["short"] = about["short"] or b.get("clubShort", {}).get("value", "")
            about["country"] = about["country"] or b.get("countryLabel", {}).get("value", "")
    return info


def download_wikipedia(
    client: httpx.Client, qids: list[str], known: set[str], resume: bool
) -> dict:
    """Everything the Wikipedia careers need, as one JSON-friendly dict (cached as is).

    The slow part (pages and links) is kept apart until the end, so `--cache` can resume a run
    that failed later; a plain run always downloads it again (transfers change).
    """
    partial = WIKI_CACHE.with_suffix(".parcial.json")
    if resume and partial.exists():
        texts, clubs = json.loads(partial.read_text(encoding="utf-8")).values()
    else:
        titles = enwiki_titles(client, qids)
        print(f"  wikipedia: {len(titles)} of {len(qids)} players have a page", flush=True)
        pages = wikitexts(client, sorted(set(titles.values())))
        texts = {qid: pages.get(title, "") for qid, title in titles.items()}
        targets = sorted({s.target for text in texts.values() for s in parse_career(text)})
        clubs = page_qids(client, targets)
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text(json.dumps({"texts": texts, "clubs": clubs}), encoding="utf-8")
    # Hand-made links too: their clubs need a name and a country like any other.
    ids = set(clubs.values()) | set(load_links().values())
    info = club_info(client, sorted(ids - known))
    partial.unlink(missing_ok=True)
    return {"texts": texts, "clubs": clubs, "info": info}


def merge(rows: list[dict], wiki: dict) -> tuple[list[dict], dict[str, list[str]], list[str]]:
    """Wikipedia careers where there is an infobox; Wikidata rows for the rest."""
    positions = {r["player"]: r["position"] for r in rows if r.get("position")}
    info = {
        r["club"]: {"label": r["clubLabel"], "short": r["clubShort"], "country": r["country"]}
        for r in rows
    } | wiki["info"]
    merged, unknown, fallback = [], {}, []
    links = load_links()
    by_player: dict[str, list[dict]] = {}
    for r in rows:
        by_player.setdefault(r["player"], []).append(r)
    for qid in {*by_player, *wiki["texts"]}:
        stints = parse_career(wiki["texts"].get(qid, ""))
        career, missing = career_rows(
            qid, stints, wiki["clubs"], info, positions.get(qid, ""), links
        )
        if career:
            merged += career
            if missing:
                unknown[qid] = missing
        else:
            merged += by_player.get(qid, [])
            fallback.append(qid)
    return merged, unknown, fallback


def main() -> None:
    players = tomllib.loads(PLAYERS.read_text(encoding="utf-8"))["jogador"]
    qids = [p["wikidata"] for p in players]
    if "--cache" in sys.argv and CACHE.exists():
        rows = json.loads(CACHE.read_text(encoding="utf-8"))
    else:
        rows = []
        with httpx.Client(headers=HEADERS, timeout=120) as client:
            for i in range(0, len(qids), CHUNK):
                rows += fetch(client, qids[i : i + CHUNK])
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    if "--cache" in sys.argv and WIKI_CACHE.exists():
        wiki = json.loads(WIKI_CACHE.read_text(encoding="utf-8"))
    else:
        with httpx.Client(headers=HEADERS, timeout=120) as client:
            wiki = download_wikipedia(
                client, qids, {r["club"] for r in rows}, resume="--cache" in sys.argv
            )
        WIKI_CACHE.parent.mkdir(parents=True, exist_ok=True)
        WIKI_CACHE.write_text(json.dumps(wiki, ensure_ascii=False), encoding="utf-8")
    rows, unknown, fallback = merge(rows, wiki)
    data = convert(players, rows, load_fixes())
    # Puzzles already played (and tomorrow's) keep their answer with the new data.
    print(f"froze #1..#{freeze_until_tomorrow()} in the games calendar")
    CAREERS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {CAREERS}: {len(data['jogadores'])} players, {len(data['clubes'])} clubs")
    names = {p["wikidata"]: p["nome"] for p in players}
    print(
        f"{len(fallback)} from Wikidata (no Wikipedia infobox): "
        + ", ".join(sorted(names.get(q, q) for q in fallback))
    )
    for qid, clubs in sorted(unknown.items(), key=lambda kv: names.get(kv[0], kv[0])):
        print(f"  {names.get(qid, qid)}: no Wikidata id for {', '.join(clubs)}")


if __name__ == "__main__":
    main()
