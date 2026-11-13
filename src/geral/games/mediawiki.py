"""Wikidata and Wikipedia calls shared by the importers, slowly (Wikimedia robot policy)."""

import re
import time

import httpx

SPARQL = "https://query.wikidata.org/sparql"
ENWIKI = "https://en.wikipedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
HEADERS = {
    "User-Agent": "geral-games/0.1 (https://github.com/dpontejs/geral)",
    "Accept": "application/sparql-results+json",
    "Accept-Encoding": "gzip",
}
BATCH = 50  # titles or ids per MediaWiki call
INVALID_TITLE = re.compile(r"[|\[\]{}<>#\n]")


def sparql(client: httpx.Client, query: str) -> list[dict]:
    """The bindings of one SPARQL query, retrying when told to wait."""
    for attempt in range(10):  # the query service limits query time per minute: be patient
        response = client.get(SPARQL, params={"query": query})
        if response.status_code != 429:
            break
        wait = int(response.headers.get("Retry-After", 30)) + attempt * 15
        print(f"  wikidata: asked to wait ({wait}s)", flush=True)
        time.sleep(wait)
    time.sleep(3)  # one query at a time, slowly
    return response.raise_for_status().json()["results"]["bindings"]


def api(client: httpx.Client, url: str, params: dict) -> dict:
    """One MediaWiki call, slowly (Wikimedia robot policy), retrying when told to wait."""
    params = {"format": "json", "formatversion": "2", **params}
    for attempt in range(5):
        response = client.get(url, params=params, headers={"Accept": "application/json"})
        if response.status_code != 429:
            break
        print(f"  {url}: asked to wait ({response.headers.get('Retry-After', '?')}s)", flush=True)
        time.sleep(int(response.headers.get("Retry-After", 30)) + attempt * 10)
    time.sleep(0.5)
    return response.raise_for_status().json()


def enwiki_titles(client: httpx.Client, qids: list[str]) -> dict[str, str]:
    """Player id -> English Wikipedia page title (players without one are left out)."""
    titles = {}
    for i in range(0, len(qids), BATCH):
        params = {"action": "wbgetentities", "ids": "|".join(qids[i : i + BATCH])}
        params |= {"props": "sitelinks", "sitefilter": "enwiki"}
        for qid, entity in api(client, WIKIDATA, params)["entities"].items():
            if link := entity.get("sitelinks", {}).get("enwiki"):
                titles[qid] = link["title"]
    return titles


def wikitexts(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    """Page title -> its wikitext, fifty pages per call."""
    texts = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i : i + BATCH]
        params = {"action": "query", "titles": "|".join(chunk), "redirects": 1}
        params |= {"prop": "revisions", "rvprop": "content", "rvslots": "main"}
        renamed, moved, pages = {}, {}, {}
        while True:  # a batch too big for one answer comes back in parts ("continue")
            answer = api(client, ENWIKI, params)
            query = answer["query"]
            renamed |= {n["from"]: n["to"] for n in query.get("normalized", [])}
            moved |= {r["from"]: r["to"] for r in query.get("redirects", [])}
            pages |= {
                page["title"]: page["revisions"][0]["slots"]["main"]["content"]
                for page in query["pages"]
                if page.get("revisions")
            }
            if "continue" not in answer:
                break
            params |= answer["continue"]
        for title in chunk:
            final = moved.get(renamed.get(title, title), renamed.get(title, title))
            texts[title] = pages.get(final, "")
        print(f"  wikipedia: {min(i + BATCH, len(titles))}/{len(titles)} pages", flush=True)
    return texts


def page_qids(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    """Linked page title -> its Wikidata id, following redirects."""
    # A '|' would split the batch; other leftovers of templates are no title either.
    titles = [t for t in titles if t.strip() and not INVALID_TITLE.search(t)]
    found = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i : i + BATCH]
        params = {"action": "query", "titles": "|".join(chunk), "redirects": 1}
        query = api(client, ENWIKI, params | {"prop": "pageprops", "ppprop": "wikibase_item"})
        query = query["query"]
        renamed = {n["from"]: n["to"] for n in query.get("normalized", [])}
        moved = {r["from"]: r["to"] for r in query.get("redirects", [])}
        ids = {p["title"]: p.get("pageprops", {}).get("wikibase_item") for p in query["pages"]}
        for title in chunk:
            final = renamed.get(title, title)
            final = moved.get(final, final)
            if ids.get(final):
                found[title] = ids[final]
    return found


def labels(client: httpx.Client, qids: list[str]) -> dict[str, str]:
    """Wikidata id -> its name in Brazilian Portuguese (else Portuguese, else English, else '')."""
    names = {}
    for i in range(0, len(qids), BATCH):
        params = {"action": "wbgetentities", "ids": "|".join(qids[i : i + BATCH])}
        params |= {"props": "labels", "languages": "pt-br|pt|en"}
        for qid, entity in api(client, WIKIDATA, params)["entities"].items():
            found = entity.get("labels", {})
            names[qid] = next(
                (found[lang]["value"] for lang in ("pt-br", "pt", "en") if lang in found), ""
            )
    return names


def with_statement(client: httpx.Client, prop: str, value: str) -> list[str]:
    """Every Wikidata item with `prop` = `value` (the search index; no SPARQL)."""
    params = {"action": "query", "list": "search", "srsearch": f"haswbstatement:{prop}={value}"}
    params |= {"srnamespace": 0, "srlimit": 500, "srprop": ""}
    found = []
    while True:
        answer = api(client, WIKIDATA, params)
        found += [hit["title"] for hit in answer["query"]["search"]]
        if "continue" not in answer:
            return found
        params |= answer["continue"]


def entities(
    client: httpx.Client, qids: list[str], props: str, languages: str = ""
) -> dict[str, dict]:
    """Wikidata id -> its entity (only `props`, e.g. 'labels|claims'), fifty per call."""
    found = {}
    for i in range(0, len(qids), BATCH):
        params = {"action": "wbgetentities", "ids": "|".join(qids[i : i + BATCH]), "props": props}
        if languages:
            params["languages"] = languages
        found |= api(client, WIKIDATA, params)["entities"]
        print(f"  wikidata: {min(i + BATCH, len(qids))}/{len(qids)} items ({props})", flush=True)
    return found
