"""Resolve footballer names to Wikidata ids, to start `src/geral/games/jogadores.toml`.

One-off helper: prints a TOML entry per name with the first search hit described as a
footballer, plus the description, so a human can check the match before committing.
Usage: uv run python scripts/find_wikidata.py "Romário" "Edmundo=Edmundo Alves de Souza Neto" ...
(an argument "Shown name=search text" searches the text and keeps the shown name).
"""

import sys
import time

import httpx

API = "https://www.wikidata.org/w/api.php"
HEADERS = {
    "User-Agent": "geral-games/0.1 (hobby project)",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",  # Wikimedia answers 403 to the httpx default
}
FOOTBALL = ("football", "futebol", "soccer", "futbolista", "calciatore")


def find(client: httpx.Client, name: str) -> tuple[str, str] | None:
    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": "pt",
        "uselang": "pt",
        "type": "item",
        "limit": 7,
        "format": "json",
    }
    for attempt in range(5):
        response = client.get(API, params=params)
        if response.status_code != 429:
            break
        time.sleep(int(response.headers.get("Retry-After", 10)) + attempt * 5)
    time.sleep(1.5)  # Wikimedia robot policy: one request at a time, slowly
    for hit in response.raise_for_status().json()["search"]:
        description = hit.get("description", "")
        if any(word in description.lower() for word in FOOTBALL):
            return hit["id"], description
    return None


def main(names: list[str]) -> None:
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for arg in names:
            name, _, search = arg.partition("=")
            found = find(client, search or name)
            if found is None:
                print(f"# NOT FOUND: {name}\n")
                continue
            qid, description = found
            print(f'[[jogador]]\nnome = "{name}"\nwikidata = "{qid}"  # {description}\n')


if __name__ == "__main__":
    main(sys.argv[1:])
