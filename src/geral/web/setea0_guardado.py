"""7a0 do clube: every finished campaign kept for its share link.

The link never replays the campaign (the data changes with every review of a club's list): it reads
the copy kept here, compressed JSON in the site's SQLite, like `carreira_guardada`. The code is a
hash of the whole input, so the same campaign finished twice is one row.
"""

import base64
import hashlib
import json
import sqlite3
import zlib
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS setea0_guardado (
    codigo TEXT PRIMARY KEY,
    campanha BLOB NOT NULL,
    criada_em TEXT NOT NULL
)
"""


def codigo(
    edicao: str,
    semente: str,
    modo: str,
    esquema: str,
    escolhas: list[Any],
    cobrancas: list[Any],
    versao: str,
) -> str:
    """10 base64url characters of the sha256 of the sorted JSON of the campaign's input."""
    entrada = {
        "edicao": edicao,
        "semente": semente,
        "modo": modo,
        "esquema": esquema,
        "escolhas": escolhas,
        "cobrancas": cobrancas,
        "versao": versao,
    }
    texto = json.dumps(entrada, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(hashlib.sha256(texto.encode()).digest()).decode()[:10]


class GuardadoStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(SCHEMA)

    def guardar(self, codigo: str, campanha_json: str, agora: datetime) -> None:
        """Keep a finished campaign for its share link; the first copy stays."""
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO setea0_guardado VALUES (?, ?, ?)",
                (codigo, zlib.compress(campanha_json.encode(), 9), agora.isoformat()),
            )

    def guardada(self, codigo: str) -> str | None:
        """The campaign kept for this code, as JSON; None when it was not kept."""
        with closing(sqlite3.connect(self.path)) as db:
            linha = db.execute(
                "SELECT campanha FROM setea0_guardado WHERE codigo = ?", (codigo,)
            ).fetchone()
        return zlib.decompress(linha[0]).decode() if linha else None
