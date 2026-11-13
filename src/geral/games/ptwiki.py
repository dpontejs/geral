"""Club careers from the Portuguese Wikipedia infobox ("Info/Futebolista"), for the team editions.

Many idols of smaller Brazilian clubs have no English infobox (the source of `carreiras.json`),
but do have a Portuguese article. Its infobox lists the years (`ano`) and the clubs (`clubes`) as
two parallel columns split by `<br />`; a club is a link or a `{{Futebol X}}` template that the
API expands into one. Each club page maps to a Wikidata id, so the clubs are the same ones as in
`carreiras.json`. `scripts/import_carreiras_pt.py` writes `carreiras_pt.json` from
`jogadores_pt.toml`; those players only play in their own team's edition.
"""

import re
import time

import httpx

from geral.games.onde_jogou import convert, normalize
from geral.games.wikipedia import Stint, _club, _params, career_rows, years

API = "https://pt.wikipedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
HEADERS = {
    "User-Agent": "geral-games/0.1 (https://github.com/dpontejs/geral)",  # Wikimedia UA policy
    "Accept-Encoding": "gzip",  # Wikimedia answers 403 to the httpx default
}
BATCH = 50  # titles or ids per MediaWiki call
LINE = re.compile(r"<br\s*/?>", re.IGNORECASE)
LINK = re.compile(r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]")
STAFF = re.compile(r"treinador|t[ée]cnico|auxiliar|preparador|dirigente", re.IGNORECASE)
LOAN = re.compile(r"\(?\s*\[\[Empréstimo[^\]]*\]\]\s*\)?")  # "([[Empréstimo (esportes)|emp.]])"


def infobox(wikitext: str) -> dict[str, str]:
    """The parameters of the first `{{Info/...}}` template (player or coach), or none."""
    start = re.search(r"\{\{\s*Info/[^|}]*", wikitext)
    if not start:
        return {}
    depth, i = 0, start.start()
    while i < len(wikitext) - 1:
        pair = wikitext[i : i + 2]
        if pair == "{{":
            depth, i = depth + 1, i + 2
        elif pair == "}}":
            depth, i = depth - 1, i + 2
            if depth == 0:
                return _params(wikitext[start.end() : i - 2])
        else:
            i += 1
    return _params(wikitext[start.end() :])


def _lines(value: str) -> list[str]:
    lines = [LOAN.sub("", line).strip() for line in LINE.split(value)]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def parse_career(anos: str, clubes: str) -> list[Stint] | None:
    """The clubs with their years, line by line (loans included); None when the columns differ."""
    spans, clubs = _lines(anos), _lines(clubes)
    if not clubs or len(spans) != len(clubs):
        return None
    stints = []
    for span_text, club_text in zip(spans, clubs, strict=True):
        club = _club(club_text)
        if club:
            stints.append(Stint(*(years(span_text) or (None, None)), club))
    return stints


def shown_names(clubes: str) -> dict[str, str]:
    """Linked club page -> the name the article shows ("América Futebol Clube (…)" -> "América")."""
    shown: dict[str, str] = {}
    for line in _lines(clubes):
        link = LINK.search(line)
        if link:
            shown.setdefault(link.group(1).strip(), (link.group(2) or link.group(1)).strip())
    return shown


def plain(raw: str) -> str:
    """The text an infobox field shows: no references, links as shown, no bold or italics."""
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", raw, flags=re.DOTALL)
    text = LINK.sub(lambda m: m.group(2) or m.group(1), text)
    return " ".join(text.replace("'", "").split())


def position(raw: str) -> str:
    text = LINE.sub(" e ", plain(raw))
    text = re.sub(r"\bex[- ]", "", text, flags=re.IGNORECASE)  # retired: the career is the point
    text = text.replace("(", " e ").replace(")", " ")  # "Treinador (ex meio-campista)"
    parts = [" ".join(p.split()) for p in re.split(r"(?<!\S)e(?!\S)|[,/;]", text)]
    kept = [p for p in parts if p and not STAFF.search(p)]  # a coach's years
    text = " e ".join([", ".join(kept[:-1]), kept[-1]]) if len(kept) > 1 else "".join(kept)
    return text[:1].upper() + text[1:]


def build(
    players: list[dict],
    pages: dict[str, dict],
    clubs: dict[str, str],
    info: dict[str, dict[str, str]],
    fixes: dict[str, dict],
    taken: dict[str, str] | None = None,
) -> tuple[dict, list[str]]:
    """The careers file (`onde_jogou` shape, each player tagged with its edition) and a report.

    `pages`: title -> {"qid", "text", "clubes" (the expanded clubs column)}; `clubs`: club page
    -> Wikidata id; `info`: club id -> {"label", "country"}; `taken`: club id -> name of the
    clubs already in `carreiras.json` (a new club whose short name is taken is named in full).
    """
    report: list[str] = []
    rows: list[dict] = []
    kept: list[dict] = []
    shown: dict[str, str] = {}
    editions: dict[str, list[str]] = {}  # a page listed for several teams plays in all of them
    unique = []
    for player in players:
        if player["pagina"] not in editions:
            unique.append(player)
        listed = editions.setdefault(player["pagina"], [])
        listed.extend([player["edicao"]] if player["edicao"] not in listed else [])
    for player in unique:
        title = player["pagina"]
        page = pages.get(title)
        if page is None:
            report.append(f"{title}: página não encontrada")
            continue
        params = infobox(page["text"])
        if "clubes" not in params:
            report.append(f"{title}: sem quadro de carreira")
            continue
        stints = parse_career(params.get("ano", ""), page["clubes"])
        if stints is None:
            report.append(f"{title}: anos e clubes não batem")
            continue
        for page_title, name in shown_names(page["clubes"]).items():
            if page_title in clubs:
                shown.setdefault(clubs[page_title], name)
        about = {qid: {**data, "short": shown.get(qid, "")} for qid, data in info.items()}
        found, unknown = career_rows(
            page["qid"], stints, clubs, about, position(params.get("posição", ""))
        )
        report.extend(f"{title}: clube sem Wikidata: {club}" for club in unknown)
        rows.extend(found)
        kept.append({"wikidata": page["qid"], "nome": player["nome"], "pagina": title})

    careers = convert(kept, rows, fixes)
    players_at: dict[str, int] = {}
    for jogador in careers["jogadores"]:
        for qid in {s["clube"] for s in jogador["clubes"]}:
            players_at[qid] = players_at.get(qid, 0) + 1
    _name_clashes_in_full(careers["clubes"], info, fixes, taken or {}, players_at)
    pages_of = {p["wikidata"]: p["pagina"] for p in kept}
    for jogador in careers["jogadores"]:
        jogador["edicoes"] = editions[pages_of[jogador["wikidata"]]]
    return careers, report


def _send(client: httpx.Client, method: str, url: str, pause: float, **kwargs) -> dict:
    """One request, waiting and retrying while Wikimedia answers 429 (Too Many Requests)."""
    for attempt in range(5):
        response = client.request(method, url, **kwargs)
        if response.status_code != 429:
            break
        time.sleep(int(response.headers.get("Retry-After", 30)) + attempt * 10)
    time.sleep(pause)  # Wikimedia robot policy: one request at a time, slowly
    return response.raise_for_status().json()


def _get(client: httpx.Client, url: str, params: dict, pause: float) -> dict:
    return _send(client, "GET", url, pause, params={**params, "format": "json", "formatversion": 2})


def _final(query: dict, title: str) -> str:
    """The title the API answered for an asked one (normalized, then redirected)."""
    for step in ("normalized", "redirects"):
        title = {m["from"]: m["to"] for m in query.get(step, [])}.get(title, title)
    return title


def category_members(client: httpx.Client, category: str, pause: float = 1) -> list[str]:
    """The article titles of a category ("Futebolistas do ABC Futebol Clube"), every page."""
    titles: list[str] = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Categoria:{category}",
        "cmnamespace": 0,
        "cmlimit": 500,
    }
    while True:
        answer = _get(client, API, params, pause)
        titles.extend(m["title"] for m in answer["query"]["categorymembers"])
        if "continue" not in answer:
            return titles
        params = {**params, **answer["continue"]}


def fetch_pages(client: httpx.Client, titles: list[str], pause: float = 1) -> dict[str, dict]:
    """Asked title -> {"qid", "text"} (missing pages left out)."""
    pages: dict[str, dict] = {}
    for i in range(0, len(titles), BATCH):
        asked = titles[i : i + BATCH]
        query = _get(
            client,
            API,
            {
                "action": "query",
                "prop": "revisions|pageprops",
                "rvprop": "content",
                "rvslots": "main",
                "ppprop": "wikibase_item",
                "redirects": 1,
                "titles": "|".join(asked),
            },
            pause,
        )["query"]
        by_title = {p["title"]: p for p in query["pages"] if "revisions" in p}
        for title in asked:
            page = by_title.get(_final(query, title))
            if page and page.get("pageprops", {}).get("wikibase_item"):
                pages[title] = {
                    "qid": page["pageprops"]["wikibase_item"],
                    "text": page["revisions"][0]["slots"]["main"]["content"],
                }
    return pages


def expand(client: httpx.Client, wikitext: str, pause: float = 1) -> str:
    """Wikitext with its templates expanded ({{Futebol ABC}} -> [[ABC Futebol Clube|ABC]])."""
    if "{{" not in wikitext:
        return wikitext
    answer = _send(
        client,
        "POST",
        API,
        pause,
        data={
            "action": "expandtemplates",
            "prop": "wikitext",
            "text": wikitext,
            "format": "json",
            "formatversion": 2,
        },
    )
    return answer["expandtemplates"]["wikitext"]


EXPAND_BATCH = 25  # texts per expandtemplates call
SEPARATOR = "\n⁂⁂⁂\n"  # between the texts of one call; no template writes it


def expand_many(client: httpx.Client, texts: list[str], pause: float = 1) -> list[str]:
    """`expand` for many texts, several per call (one call each would hit the rate limit)."""
    expanded = list(texts)
    todo = [i for i, text in enumerate(texts) if "{{" in text]
    for start in range(0, len(todo), EXPAND_BATCH):
        group = todo[start : start + EXPAND_BATCH]
        parts = expand(client, SEPARATOR.join(texts[i] for i in group), pause).split(SEPARATOR)
        if len(parts) != len(group):  # a template swallowed a separator: one by one
            parts = [expand(client, texts[i], pause) for i in group]
        for i, part in zip(group, parts, strict=True):
            expanded[i] = part
    return expanded


def page_ids(client: httpx.Client, titles: list[str], pause: float = 1) -> dict[str, str]:
    """Club page title (or a redirect to it) -> Wikidata id; no id or a disambiguation: left out."""
    ids: dict[str, str] = {}
    for i in range(0, len(titles), BATCH):
        asked = titles[i : i + BATCH]
        query = _get(
            client,
            API,
            {
                "action": "query",
                "prop": "pageprops",
                "ppprop": "wikibase_item|disambiguation",
                "redirects": 1,
                "titles": "|".join(asked),
            },
            pause,
        )["query"]
        found = {
            p["title"]: p["pageprops"]["wikibase_item"]
            for p in query["pages"]
            if p.get("pageprops", {}).get("wikibase_item")
            and "disambiguation" not in p["pageprops"]  # which club? the article doesn't say
        }
        for title in asked:
            if (target := _final(query, title)) in found:
                ids[title] = found[target]
    return ids


def _entities(client: httpx.Client, qids: list[str], pause: float) -> dict[str, dict]:
    entities: dict[str, dict] = {}
    for i in range(0, len(qids), BATCH):
        entities.update(
            _get(
                client,
                WIKIDATA,
                {
                    "action": "wbgetentities",
                    "props": "labels|claims",
                    "languages": "pt-br|pt|en",
                    "ids": "|".join(qids[i : i + BATCH]),
                },
                pause,
            )["entities"]
        )
    return entities


def _label(entity: dict) -> str:
    labels = entity.get("labels", {})
    for lang in ("pt-br", "pt", "en"):
        if lang in labels:
            return labels[lang]["value"]
    return ""


def club_info(client: httpx.Client, qids: list[str], pause: float = 1) -> dict[str, dict]:
    """Club id -> {"label" (in Portuguese), "country"} from Wikidata."""
    clubs = _entities(client, qids, pause)
    countries = {}
    for qid, entity in clubs.items():
        claims = entity.get("claims", {}).get("P17", [])
        value = claims[0]["mainsnak"].get("datavalue", {}).get("value", {}) if claims else {}
        if value.get("id"):
            countries[qid] = value["id"]
    names = _entities(client, sorted(set(countries.values())), pause) if countries else {}
    return {
        qid: {
            "label": _label(entity),
            "country": _label(names.get(countries.get(qid, ""), {})),
        }
        for qid, entity in clubs.items()
    }


def _name_clashes_in_full(
    clubes: dict[str, dict],
    info: dict[str, dict],
    fixes: dict[str, dict],
    taken: dict[str, str],
    players_at: dict[str, int],
) -> None:
    """Two clubs shown as "Peñarol" can't both be typed. A club of the main file (or named in
    clubes.toml) keeps its name; otherwise the club with the most players does (ties: lowest
    id). The others take the full label, and the country too when the label is also shared."""

    def fixed(qid: str) -> bool:
        return qid in taken or "nome" in fixes.get(qid, {})

    def keeper(group: set[str]) -> set[str]:
        held = {q for q in group if fixed(q)}
        if held:
            return held
        return {min(group, key=lambda q: (-players_at.get(q, 0), int(q[1:])))}

    names = {**{q: c["nome"] for q, c in clubes.items() if q not in taken}, **taken}
    for step in ("label", "country"):
        groups: dict[str, set[str]] = {}
        for qid, name in names.items():
            groups.setdefault(normalize(name), set()).add(qid)
        for group in (g for g in groups.values() if len(g) > 1):
            for qid in (
                group - keeper(group) if step == "label" else group - {*filter(fixed, group)}
            ):
                about = info.get(qid, {})
                if qid not in clubes or fixed(qid):
                    continue
                if step == "label" and about.get("label"):
                    names[qid] = about["label"]
                elif step == "country" and about.get("country"):
                    names[qid] = f"{names[qid]} ({about['country']})"
    for qid, club in clubes.items():
        if not fixed(qid) and names[qid] != club["nome"]:
            aliases = (set(club["apelidos"]) | {club["nome"]}) - {names[qid]}
            club.update(nome=names[qid], apelidos=sorted(aliases))
