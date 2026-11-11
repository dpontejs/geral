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
from typing import Literal

from pydantic import BaseModel

from geral.games.daily import number_on, pick, shuffled

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

LAUNCH = date(2026, 11, 11)  # puzzle #1: no later than the deploy, or two days share #1
MAX_GUESSES = 6
COACH_HINT_AFTER, WINNER_HINT_AFTER = 3, 4  # misses
# The 12 big clubs (a data file, like the matches): their meetings are "clássicos".
BIG_12 = frozenset(Path(__file__).with_name("grandes.txt").read_text(encoding="utf-8").splitlines())


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


@dataclass(frozen=True)
class Puzzle:
    number: int
    match: Match


def _memorable(m: Match, club: str | None) -> bool:
    goals, margin = m.home_goals + m.away_goals, abs(m.home_goals - m.away_goals)
    if club is None:
        return (m.home in BIG_12 and m.away in BIG_12) or goals >= 4 or margin >= 3
    rival = m.away if m.home == club else m.home
    return club in (m.home, m.away) and (goals >= 3 or rival in BIG_12)


def pool(matches: list[Match], club: str | None) -> list[Match]:
    """Matches of `club` (None: the whole Série A) in the edition's fixed daily order."""
    games = sorted((m for m in matches if _memorable(m, club)), key=lambda m: m.id)
    return shuffled(games, f"quanto-foi:{club or 'geral'}")


def puzzle_number(day: date) -> int:
    return number_on(day, LAUNCH)


def by_number(games: list[Match], number: int) -> Puzzle:
    return Puzzle(number, pick(games, number))


def puzzle(games: list[Match], day: date) -> Puzzle:
    return by_number(games, puzzle_number(day))


class Side(BaseModel):
    status: Literal["certo", "perto", "longe"]
    hint: Literal["mais", "menos", ""]  # the real number is higher / lower


class Reveal(BaseModel):
    home: str
    away: str
    home_goals: int
    away_goals: int
    stadium: str
    day: date
    round: int
    home_scorers: list[str]
    away_scorers: list[str]


class Verdict(BaseModel):
    rows: list[tuple[Side, Side]]
    solved: bool
    over: bool
    hints: list[str]
    reveal: Reveal | None


def _side(guess: int, real: int) -> Side:
    diff = real - guess
    status = "certo" if diff == 0 else "perto" if abs(diff) == 1 else "longe"
    return Side(status=status, hint="mais" if diff > 0 else "menos" if diff < 0 else "")


def judge(match: Match, guesses: list[tuple[int, int]]) -> Verdict:
    real = (match.home_goals, match.away_goals)
    solved = real in guesses
    over = solved or len(guesses) >= MAX_GUESSES
    misses = len(guesses) - (1 if solved else 0)
    hints = []
    if misses >= COACH_HINT_AFTER and match.home_coach and match.away_coach:
        hints.append(f"Técnicos: {match.home_coach} × {match.away_coach}")
    if misses >= WINNER_HINT_AFTER:
        hints.append(
            "Deu empate"
            if real[0] == real[1]
            else f"Venceu: {match.home if real[0] > real[1] else match.away}"
        )
    reveal = None
    if over:
        reveal = Reveal(
            home=match.home,
            away=match.away,
            home_goals=match.home_goals,
            away_goals=match.away_goals,
            stadium=match.stadium,
            day=match.day,
            round=match.round,
            home_scorers=list(match.home_scorers),
            away_scorers=list(match.away_scorers),
        )
    return Verdict(
        rows=[(_side(h, real[0]), _side(a, real[1])) for h, a in guesses],
        solved=solved,
        over=over,
        hints=hints,
        reveal=reveal,
    )
