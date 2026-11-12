"""Freeze the daily answers of the careers games up to tomorrow (Brasília), with the current data.

`import_carreiras.py` runs this before writing new careers, so a data update never changes a
puzzle already played (or today's, mid-day). Run it by hand with `--carreiras <file>` to freeze
with another careers file, e.g. the one before an update.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from geral.games import calendario, onde_jogou
from geral.teams import load_teams

BRASILIA = ZoneInfo("America/Sao_Paulo")


def freeze_until_tomorrow(careers: Path = onde_jogou.CAREERS) -> int:
    tomorrow = datetime.now(BRASILIA).date() + timedelta(days=1)
    until = onde_jogou.puzzle_number(tomorrow)
    teams = {slug: team.name for slug, team in load_teams().items() if team.listed}
    calendario.freeze_games(calendario.CALENDAR, onde_jogou.load(careers), teams, until)
    return until


if __name__ == "__main__":
    path = Path(sys.argv[sys.argv.index("--carreiras") + 1]) if "--carreiras" in sys.argv else None
    until = freeze_until_tomorrow(path or onde_jogou.CAREERS)
    print(f"froze #1..#{until} in {calendario.CALENDAR}")
