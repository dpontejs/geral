"""Wikidata and Wikipedia calls shared by the importers, slowly (Wikimedia robot policy)."""

import time

import httpx

SPARQL = "https://query.wikidata.org/sparql"
ENWIKI = "https://en.wikipedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
HEADERS = {
    "User-Agent": "geral-games/0.1 (hobby project)",
    "Accept": "application/sparql-results+json",
    "Accept-Encoding": "gzip",
}
BATCH = 50  # titles or ids per MediaWiki call


def sparql(client: httpx.Client, query: str) -> list[dict]:
    """The bindings of one SPARQL query, retrying when told to wait."""
    for attempt in range(5):
        response = client.get(SPARQL, params={"query": query})
        if response.status_code != 429:
            break
        time.sleep(int(response.headers.get("Retry-After", 30)) + attempt * 10)
    time.sleep(2)  # one query at a time, slowly
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
        query = api(client, ENWIKI, params)["query"]
        renamed = {n["from"]: n["to"] for n in query.get("normalized", [])}
        moved = {r["from"]: r["to"] for r in query.get("redirects", [])}
        pages = {
            page["title"]: page["revisions"][0]["slots"]["main"]["content"]
            for page in query["pages"]
            if page.get("revisions")
        }
        for title in chunk:
            final = moved.get(renamed.get(title, title), renamed.get(title, title))
            texts[title] = pages.get(final, "")
        print(f"  wikipedia: {min(i + BATCH, len(titles))}/{len(titles)} pages", flush=True)
    return texts


def page_qids(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    """Linked page title -> its Wikidata id, following redirects."""
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
