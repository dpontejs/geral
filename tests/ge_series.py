"""The four séries as ge served them on 2026-11-21, for respx (docs/features/central.md)."""

import json
import re
from pathlib import Path

import httpx
import respx

from geral.general import SERIES
from geral.stats.ge_tables import GE_TABLES_API, PHASES, TUUID

FIXTURES = Path(__file__).parent / "fixtures" / "ge_tables"
KEYS = {"Série A": "seriea", "Série B": "serieb", "Série C": "seriec", "Série D": "seried26"}
# Early Série D phases are left out of the repo (300 KB): an empty knockout stands in.
EMPTY_KNOCKOUT = {"fase": {"tipo": {"tipo_id": "2"}}, "secao": []}


def mock_series(router: respx.MockRouter, only: tuple[str, ...] | None = None) -> None:
    for name, key in KEYS.items():
        if only and name not in only:
            continue
        page = (FIXTURES / f"page_{key}.html").read_text(encoding="utf-8")
        router.get(SERIES[name]).mock(return_value=httpx.Response(200, text=page))
        base = f"{GE_TABLES_API}/{TUUID.search(page).group(1)}/fase"
        for phase in json.loads(PHASES.search(page).group(1)):
            slug = phase["slug"]
            file = FIXTURES / f"{key}_{slug}.json"
            data = json.loads(file.read_text(encoding="utf-8")) if file.exists() else EMPTY_KNOCKOUT
            router.get(f"{base}/{slug}/classificacao/").mock(
                return_value=httpx.Response(200, json=data)
            )
            for rounds in FIXTURES.glob(f"{key}_{slug}_r*.json"):
                n = rounds.stem.rsplit("_r", 1)[1]
                router.get(f"{base}/{slug}/rodada/{n}/jogos/").mock(
                    return_value=httpx.Response(200, text=rounds.read_text(encoding="utf-8"))
                )
            router.get(url__regex=rf"^{re.escape(base)}/{slug}/rodada/\d+/jogos/$").mock(
                return_value=httpx.Response(200, json=[])
            )
