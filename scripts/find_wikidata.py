"""Resolve footballer names to Wikidata ids, to start `src/geral/games/jogadores.toml`.

One-off helper with a single SPARQL query (Wikimedia rate-limits one search per name): a name
matches a footballer's label or alias in Portuguese or English; with several matches, the one
with the most Wikipedia articles wins. Prints a TOML entry per name, with the description, so a
human can check the match before committing.

Usage: uv run python scripts/find_wikidata.py "Romário" "Edmundo=Edmundo Alves de Souza Neto" ...
(an argument "Shown name=search text" searches the text and keeps the shown name).
"""

import sys

import httpx

SPARQL = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "geral-games/0.1 (hobby project)",
    "Accept": "application/sparql-results+json",
    "Accept-Encoding": "gzip",  # Wikimedia answers 403 to the httpx default
}
QUERY = """
SELECT ?name ?player ?playerDescription ?links WHERE {
  VALUES ?name { %s }
  { ?player rdfs:label ?name } UNION { ?player skos:altLabel ?name }
  ?player wdt:P106 wd:Q937857 ; wikibase:sitelinks ?links .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt-br,pt,en". }
}
"""


def literal(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"@pt "{escaped}"@en'


def main(args: list[str]) -> None:
    wanted = [(name, search or name) for name, _, search in (a.partition("=") for a in args)]
    query = QUERY % " ".join(literal(search) for _, search in wanted)
    with httpx.Client(headers=HEADERS, timeout=120) as client:
        response = client.post(SPARQL, data={"query": query})
    best: dict[str, tuple[int, str, str]] = {}
    for b in response.raise_for_status().json()["results"]["bindings"]:
        name, links = b["name"]["value"], int(b["links"]["value"])
        qid = b["player"]["value"].rsplit("/", 1)[-1]
        description = b.get("playerDescription", {}).get("value", "")
        if links > best.get(name, (-1, "", ""))[0]:
            best[name] = (links, qid, description)
    for name, search in wanted:
        if search not in best:
            print(f"# NOT FOUND: {name} ({search})\n")
            continue
        links, qid, description = best[search]
        print(
            f'[[jogador]]\nnome = "{name}"\nwikidata = "{qid}"  # {description} ({links} wikis)\n'
        )


if __name__ == "__main__":
    main(sys.argv[1:])
