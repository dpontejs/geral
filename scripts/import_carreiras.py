"""Download the careers of the players in `jogadores.toml` from Wikidata into `carreiras.json`.

Run with `uv run python scripts/import_carreiras.py`, review the diff of the generated file, then
commit it. Club names are fixed in `src/geral/games/clubes.toml`; after editing it, rerun with
`--cache` to rebuild from the last download (kept outside the repo) without asking Wikidata again.
"""

import json
import sys
import time
import tomllib
from pathlib import Path

import httpx

from geral.games.onde_jogou import CAREERS, PLAYERS, convert, load_fixes

SPARQL = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "geral-games/0.1 (hobby project)",
    "Accept": "application/sparql-results+json",
    "Accept-Encoding": "gzip",
}
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


def fetch(client: httpx.Client, qids: list[str]) -> list[dict]:
    query = QUERY % " ".join(f"wd:{q}" for q in qids)
    for attempt in range(5):
        response = client.get(SPARQL, params={"query": query})
        if response.status_code != 429:
            break
        time.sleep(int(response.headers.get("Retry-After", 30)) + attempt * 10)
    time.sleep(2)  # Wikimedia robot policy: one query at a time, slowly
    rows = []
    for b in response.raise_for_status().json()["results"]["bindings"]:

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
    data = convert(players, rows, load_fixes())
    CAREERS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {CAREERS}: {len(data['jogadores'])} players, {len(data['clubes'])} clubs")


if __name__ == "__main__":
    main()
