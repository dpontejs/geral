"""Club careers from the English Wikipedia infobox ("Infobox football biography").

Wikidata lags on current transfers (a player shown at a club he left years ago); the Wikipedia
infobox is kept up to date by many editors. Each club is a link whose page maps to a Wikidata id,
so the careers keep the same club ids, names and aliases (clubes.toml) as before.
"""

import html
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

LINKS = Path(__file__).with_name("wikipedia_links.toml")
YEARS = re.compile(r"(\d{4})\s*(?:([–—-])\s*(\d{4}|\d{2}(?!\d))?)?")
DASH = re.compile(r"\{\{\s*(?:s?ndash|snd|spaced ndash)\s*\}\}", re.IGNORECASE)
SELECAO_PAGE = "Brazil national football team"  # the senior team; U-20 and Olympic have own pages
SQUAD_PLAYER = re.compile(r"\{\{\s*nat fs (?:g )?player\b[^\n]*?\|\s*name\s*=\s*\[\[([^\]|#]+)")
ILL = re.compile(r"\{\{\s*(?:ill|interlanguage link)\s*\|\s*([^|{}]+)", re.IGNORECASE)
WRAPPER = re.compile(r"\{\{[^{}|]*\|([^{}]*)\}\}")  # {{nowrap|...}} keeps what it wraps


@dataclass(frozen=True)
class Stint:
    start: int | None  # None: the years could not be read (reported, not dropped)
    end: int | None  # None: still there
    target: str  # the linked page title, or the plain club name when unlinked


def years(text: str) -> tuple[int, int | None] | None:
    """'2007–2012' -> (2007, 2012); '2011' -> (2011, 2011); '2022–' -> (2022, None)."""
    text = html.unescape(text)  # "1978&ndash;1990"
    text = DASH.sub("–", text)  # "1978{{ndash}}1990"
    text = re.sub(r"\{\{\s*0\s*\}\}", "", text)  # {{0}}: a padding digit, not a year
    text = WRAPPER.sub(r"\1", text)  # {{nowrap|1978–1990}}
    match = YEARS.search(text)
    if not match:
        return None
    start, dash, end = match.groups()
    if end and len(end) == 2:  # "1998–99", "1999–00": the end in the start's century, or the next
        century = int(start[:2]) + (1 if end < start[2:] else 0)
        end = f"{century}{end}"
    if end:
        return int(start), int(end)
    return (int(start), None) if dash else (int(start), int(start))


def _infobox(wikitext: str) -> str:
    start = re.search(r"\{\{\s*Infobox[ _]football[ _]biography", wikitext, re.IGNORECASE)
    if not start:
        return ""
    depth, i = 0, start.start()
    while i < len(wikitext) - 1:
        pair = wikitext[i : i + 2]
        if pair == "{{":
            depth, i = depth + 1, i + 2
        elif pair == "}}":
            depth, i = depth - 1, i + 2
            if depth == 0:
                return wikitext[start.end() : i - 2]
        else:
            i += 1
    return wikitext[start.end() :]


def _params(body: str) -> dict[str, str]:
    """Split the template on the '|' that are not inside [[links]] or {{templates}}."""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    body = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", body, flags=re.DOTALL)
    parts, depth, current, i = [], 0, [], 0
    while i < len(body):
        pair = body[i : i + 2]
        if pair in ("[[", "{{"):
            depth, i = depth + 1, i + 2
            current.append(pair)
            continue
        if pair in ("]]", "}}"):
            depth, i = max(0, depth - 1), i + 2
            current.append(pair)
            continue
        if body[i] == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(body[i])
        i += 1
    parts.append("".join(current))
    params = {}
    for part in parts:
        key, sep, value = part.partition("=")
        if sep:
            params[key.strip()] = value.strip()
    return params


def _club(text: str) -> str:
    link = re.search(r"\[\[([^\]|#]+)", text)
    if link:
        return link.group(1).strip()
    interlanguage = ILL.search(text)  # {{ill|Antarctica Futebol Clube|pt|lt=Antarctica FC}}
    if interlanguage:
        return interlanguage.group(1).strip()
    text = re.sub(r"<[^>]+>", "", text)  # <span title="…">Operário de Muriaé</span>
    plain = WRAPPER.sub(r"\1", text)  # {{nowrap|Deportivo Pereira}}
    plain = re.sub(r"\{\{[^}]*\}\}|'''?|\(loan\)|→", "", plain)
    return " ".join(plain.split())


def parse_career(wikitext: str) -> list[Stint]:
    """The senior clubs (loans included; youth and national teams left out), in order."""
    params = _params(_infobox(wikitext))
    stints = []
    numbers = sorted(int(k[5:]) for k in params if re.fullmatch(r"clubs\d+", k))
    for n in numbers:
        club = _club(params[f"clubs{n}"])
        span = years(params.get(f"years{n}", ""))
        if club:  # a year with no club happens in real infoboxes: nothing to keep
            stints.append(Stint(*(span or (None, None)), club))
    return stints


def national_teams(wikitext: str) -> list[str]:
    """The national teams of the infobox (youth and Olympic included), as linked page titles."""
    params = _params(_infobox(wikitext))
    numbers = sorted(int(k[12:]) for k in params if re.fullmatch(r"nationalteam\d+", k))
    return [team for n in numbers if (team := _club(params[f"nationalteam{n}"]))]


def squad_players(wikitext: str) -> list[str]:
    """The linked players of a "FIFA World Cup squads" page (`{{nat fs g player|name=[[…]]}}`)."""
    return SQUAD_PLAYER.findall(wikitext)


def career_rows(
    player: str,
    stints: list[Stint],
    clubs: dict[str, str],
    info: dict[str, dict[str, str]],
    position: str,
    links: dict[str, str] | None = None,
) -> tuple[list[dict], list[str]]:
    """Rows in the shape `onde_jogou.convert` reads, and the clubs with no Wikidata id.

    `links` (from `wikipedia_links.toml`) gives the id of a linked page or plain name that has none.
    """
    rows, unknown = [], []
    for stint in stints:
        if stint.start is None:
            unknown.append(f"{stint.target} (anos ilegíveis)")
            continue
        club = (links or {}).get(stint.target) or clubs.get(stint.target)
        if club is None:
            unknown.append(stint.target)
            continue
        about = info.get(club, {})
        rows.append(
            {
                "player": player,
                "club": club,
                "clubLabel": about.get("label") or stint.target,
                "clubShort": about.get("short", ""),
                "country": about.get("country", ""),
                "start": str(stint.start),
                "end": "" if stint.end is None else str(stint.end),
                "national": False,
                "position": position,
            }
        )
    return rows, unknown


def load_links(path: Path = LINKS) -> dict[str, str]:
    """Hand-made club ids for infobox clubs whose page has no Wikidata id (or no page)."""
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
