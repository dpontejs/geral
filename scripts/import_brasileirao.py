"""Download the free Brasileirão dataset and write the compact CSV used by 'Quanto foi?'.

Source: https://github.com/adaoduque/Brasileirao_Dataset (Série A 2003-2024; goals from 2014).
Run with `uv run python scripts/import_brasileirao.py` and commit the generated file.
"""

import httpx

from geral.games.quanto_foi import DATA, convert

BASE = "https://raw.githubusercontent.com/adaoduque/Brasileirao_Dataset/master/"


def main() -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        full, goals = (
            client.get(BASE + name).raise_for_status().text
            for name in ("campeonato-brasileiro-full.csv", "campeonato-brasileiro-gols.csv")
        )
    DATA.write_text(convert(full, goals), encoding="utf-8")
    print(f"wrote {DATA}")


if __name__ == "__main__":
    main()
