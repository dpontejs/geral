"""Download the jogo da velha player base into `src/geral/games/velha/base.json`.

Run with `uv run python scripts/import_base.py`, read the report (players per club, Seleção, Copa),
review the diff of the generated file, then commit it. The board clubs are in
`src/geral/games/velha/clubes.toml`.
"""

import httpx

from geral.games.mediawiki import HEADERS
from geral.games.velha.base import BASE, load_clubs
from geral.games.velha.importacao import build_base, dump


def main() -> None:
    with httpx.Client(headers=HEADERS, timeout=120) as client:
        data, report = build_base(client, load_clubs())
    BASE.write_text(dump(data), encoding="utf-8")
    print(f"wrote {BASE}")
    print("\n".join(report))


if __name__ == "__main__":
    main()
