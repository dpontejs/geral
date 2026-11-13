"""Download the careers in `jogadores_pt.toml` from Portuguese Wikipedia into `carreiras_pt.json`.

For the idols of clubs the English Wikipedia barely covers (ABC first): each player plays only in
the edition of `edicao`. Club names are fixed in `src/geral/games/clubes.toml`, as for the main
careers. Review the report and the diff of the generated file, then commit it.

Usage:
  uv run python scripts/import_carreiras_pt.py            # download and write
  uv run python scripts/import_carreiras_pt.py --cache    # rebuild from the last download
  uv run python scripts/import_carreiras_pt.py --categoria "Futebolistas do ABC Futebol Clube" abc
      # print TOML entries for the players of a category, to review before adding to the list
"""

import json
import re
import sys
import tomllib
from pathlib import Path

import httpx
from congelar_calendario import freeze_until_tomorrow  # scripts/, next to this one

from geral.games import ptwiki
from geral.games.onde_jogou import CAREERS, CAREERS_PT, HERE, load_fixes

PLAYERS_PT = HERE / "jogadores_pt.toml"
CACHE = Path.home() / ".cache" / "geral" / "ptwiki-carreiras.json"


def download(players: list[dict]) -> dict:
    with httpx.Client(headers=ptwiki.HEADERS, timeout=60) as client:
        pages = ptwiki.fetch_pages(client, [p["pagina"] for p in players])
        columns = [ptwiki.infobox(page["text"]).get("clubes", "") for page in pages.values()]
        for page, clubes in zip(pages.values(), ptwiki.expand_many(client, columns), strict=True):
            page["clubes"] = clubes
        titles = sorted({t for page in pages.values() for t in ptwiki.shown_names(page["clubes"])})
        clubs = ptwiki.page_ids(client, titles)
        info = ptwiki.club_info(client, sorted(set(clubs.values())))
    return {"pages": pages, "clubs": clubs, "info": info}


def suggest(category: str, edition: str) -> None:
    with httpx.Client(headers=ptwiki.HEADERS, timeout=60) as client:
        titles = ptwiki.category_members(client, category)
        pages = ptwiki.fetch_pages(client, titles)
    for title in titles:
        page = pages.get(title)
        nome = ptwiki.plain(ptwiki.infobox(page["text"]).get("nome", "")) if page else ""
        nome = nome or re.sub(r"\s*\(.*\)$", "", title)
        print(f'[[jogador]]\npagina = "{title}"\nnome = "{nome}"\nedicao = "{edition}"\n')


def main() -> None:
    if "--categoria" in sys.argv:
        at = sys.argv.index("--categoria")
        suggest(sys.argv[at + 1], sys.argv[at + 2])
        return
    players = tomllib.loads(PLAYERS_PT.read_text(encoding="utf-8"))["jogador"]
    if "--cache" in sys.argv:
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
    else:
        raw = download(players)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    main = json.loads(CAREERS.read_text(encoding="utf-8"))["clubes"]
    taken = {qid: club["nome"] for qid, club in main.items()}
    careers, report = ptwiki.build(
        players, raw["pages"], raw["clubs"], raw["info"], load_fixes(), taken
    )
    until = freeze_until_tomorrow()  # the puzzles already played keep their answers
    print(f"froze #1..#{until}", file=sys.stderr)
    CAREERS_PT.write_text(
        json.dumps(careers, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    for line in report:
        print(line)
    print(f"{len(careers['jogadores'])} jogadores em {CAREERS_PT.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
