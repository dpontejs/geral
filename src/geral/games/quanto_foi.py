"""'Quanto foi?': guess the score of a historic Série A match, one puzzle per day and edition.

Matches come from the free Brasileirão dataset (github.com/adaoduque/Brasileirao_Dataset,
2003-2024), converted once by `scripts/import_brasileirao.py` into the CSV next to this module.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DATA = Path(__file__).with_name("brasileirao.csv")
FIELDS = (
    "id,date,round,home,away,home_goals,away_goals,stadium,"
    "home_coach,away_coach,home_scorers,away_scorers"
).split(",")

# The dataset drops accents; the game shows names the way the fans write them.
DISPLAY = {
    "America-MG": "América-MG",
    "America-RN": "América-RN",
    "Atletico-GO": "Atlético-GO",
    "Atletico-MG": "Atlético-MG",
    "Avai": "Avaí",
    "Botafogo-RJ": "Botafogo",
    "Ceara": "Ceará",
    "Criciuma": "Criciúma",
    "Cuiaba": "Cuiabá",
    "Goias": "Goiás",
    "Gremio": "Grêmio",
    "Gremio Prudente": "Grêmio Prudente",
    "Nautico": "Náutico",
    "Parana": "Paraná",
    "Santo Andre": "Santo André",
    "Sao Caetano": "São Caetano",
    "Sao Paulo": "São Paulo",
    "Vitoria": "Vitória",
}
SCORER_SEP = ";"


@dataclass(frozen=True)
class Match:
    id: int
    day: date
    round: int
    home: str
    away: str
    home_goals: int
    away_goals: int
    stadium: str
    home_coach: str
    away_coach: str
    home_scorers: tuple[str, ...]
    away_scorers: tuple[str, ...]


def _minute(value: str) -> tuple[int, int]:
    """'90+1' sorts after '90' and before '91'."""
    base, _, extra = value.partition("+")
    digits = re.sub(r"\D", "", base)
    return int(digits or 0), int(extra or 0)


def convert(full_csv: str, goals_csv: str) -> str:
    """Join the dataset's matches and goals into one compact CSV with display names."""
    goals: dict[tuple[str, str], list[tuple[tuple[int, int], str]]] = {}
    for g in csv.DictReader(io.StringIO(goals_csv)):
        name = g["atleta"].strip()
        if g["tipo_de_gol"].strip() == "Gol Contra":
            name += " (contra)"  # the dataset credits an own goal to the club that benefited
        goals.setdefault((g["partida_id"], g["clube"]), []).append((_minute(g["minuto"]), name))

    def scorers(match_id: str, club: str) -> str:
        return SCORER_SEP.join(name for _, name in sorted(goals.get((match_id, club), [])))

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(FIELDS)
    for m in csv.DictReader(io.StringIO(full_csv)):
        writer.writerow(
            [
                m["ID"],
                datetime.strptime(m["data"], "%d/%m/%Y").date().isoformat(),
                m["rodata"],
                DISPLAY.get(m["mandante"], m["mandante"]),
                DISPLAY.get(m["visitante"], m["visitante"]),
                m["mandante_Placar"],
                m["visitante_Placar"],
                m["arena"].strip(),
                m["tecnico_mandante"].strip(),
                m["tecnico_visitante"].strip(),
                scorers(m["ID"], m["mandante"]),
                scorers(m["ID"], m["visitante"]),
            ]
        )
    return out.getvalue()


def _names(value: str) -> tuple[str, ...]:
    return tuple(value.split(SCORER_SEP)) if value else ()


def load_matches(path: Path = DATA) -> list[Match]:
    with path.open(encoding="utf-8", newline="") as f:
        return [
            Match(
                id=int(r["id"]),
                day=date.fromisoformat(r["date"]),
                round=int(r["round"]),
                home=r["home"],
                away=r["away"],
                home_goals=int(r["home_goals"]),
                away_goals=int(r["away_goals"]),
                stadium=r["stadium"],
                home_coach=r["home_coach"],
                away_coach=r["away_coach"],
                home_scorers=_names(r["home_scorers"]),
                away_scorers=_names(r["away_scorers"]),
            )
            for r in csv.DictReader(f)
        ]
