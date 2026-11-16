"""Jogo da velha duels by link: one row per duel in its own table of the site's SQLite.

Only the moves are kept; the board state always comes from replaying them (`judge_duel`). The
server owns the clock: `prazo` ends the current turn, and a deadline that passed becomes a timeout
move on the next read or write, as many times as turns went by. X's clock starts when O joins.
"""

import json
import secrets
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from geral.games.velha.duelo import SECONDS, DuelState

LIFETIME = timedelta(hours=24)
TURN = timedelta(seconds=SECONDS)
SCHEMA = """
CREATE TABLE IF NOT EXISTS velha_partidas (
    id TEXT PRIMARY KEY,
    tabuleiro TEXT NOT NULL,
    x_token TEXT NOT NULL,
    o_token TEXT,
    jogadas TEXT NOT NULL DEFAULT '[]',
    prazo TEXT,
    criada_em TEXT NOT NULL
);
"""

type Judge = Callable[[str, list[dict]], DuelState]  # (board code, moves) -> state


class DuelNotFound(LookupError):
    """No such duel, or one older than a day (404)."""


class NotYourTurn(PermissionError):
    """A token of nobody, or of the side not on turn (403)."""


class DuelConflict(ValueError):
    """The duel cannot take this move now: over, waiting for O, or a taken cell (409)."""


@dataclass
class Row:
    id: str
    tabuleiro: str
    x_token: str
    o_token: str | None
    jogadas: list[dict]
    prazo: datetime | None
    criada_em: datetime


class DuelStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # One writer at a time: a read may also write (expired turns), so it locks too.
        db = sqlite3.connect(self.path, isolation_level=None)
        db.execute("BEGIN IMMEDIATE")
        return db

    def create(self, board_code: str, now: datetime) -> tuple[str, str]:
        """A new duel; the creator plays X. Duels older than a day are deleted here."""
        duel_id, x_token = secrets.token_urlsafe(6), secrets.token_urlsafe(16)
        with closing(self._connect()) as db:
            db.execute(
                "DELETE FROM velha_partidas WHERE criada_em < ?", ((now - LIFETIME).isoformat(),)
            )
            db.execute(
                "INSERT INTO velha_partidas (id, tabuleiro, x_token, criada_em)"
                " VALUES (?, ?, ?, ?)",
                (duel_id, board_code, x_token, now.isoformat()),
            )
            db.execute("COMMIT")
        return duel_id, x_token

    def join(self, duel_id: str, now: datetime) -> str | None:
        """O's token, once; None when someone already joined. X's clock starts now."""
        o_token = secrets.token_urlsafe(16)
        with closing(self._connect()) as db:
            row = self._load(db, duel_id, now)
            if row.o_token is not None:
                db.execute("ROLLBACK")
                return None
            db.execute(
                "UPDATE velha_partidas SET o_token = ?, prazo = ? WHERE id = ?",
                (o_token, (now + TURN).isoformat(), duel_id),
            )
            db.execute("COMMIT")
        return o_token

    def get(self, duel_id: str, now: datetime, judge: Judge) -> Row:
        with closing(self._connect()) as db:
            row = self._expire(db, self._load(db, duel_id, now), now, judge)
            db.execute("COMMIT")
        return row

    def play(
        self, duel_id: str, token: str, vez_n: int, move: dict, now: datetime, judge: Judge
    ) -> Row:
        """Play `move` for the side holding `token`, if it saw all the moves (`vez_n`).

        A `vez_n` behind the moves (a retry, a stale tab) changes nothing and returns the duel.
        """
        with closing(self._connect()) as db:
            row = self._expire(db, self._load(db, duel_id, now), now, judge)
            if vez_n != len(row.jogadas):
                db.execute("COMMIT")
                return row
            state = judge(row.tabuleiro, row.jogadas)
            side = {row.x_token: "X", row.o_token: "O"}.get(token) if token else None
            if side is None:
                db.execute("COMMIT")
                raise NotYourTurn("not a player of this duel")
            if state.over or row.o_token is None:
                db.execute("COMMIT")
                raise DuelConflict("the duel is over" if state.over else "waiting for O")
            if side != state.vez:
                db.execute("COMMIT")
                raise NotYourTurn(f"it is {state.vez}'s turn")
            if move.get("casa") in state.casas:
                db.execute("COMMIT")
                raise DuelConflict(f"cell {move['casa']} is taken")
            jogadas = [*row.jogadas, move]
            try:
                after = judge(row.tabuleiro, jogadas)  # GuessError: unknown player, bad cell
            except ValueError:
                db.execute("COMMIT")
                raise
            row.jogadas, row.prazo = jogadas, None if after.over else now + TURN
            self._save(db, row)
            db.execute("COMMIT")
        return row

    def purge(self, now: datetime) -> None:
        with closing(self._connect()) as db:
            db.execute(
                "DELETE FROM velha_partidas WHERE criada_em < ?", ((now - LIFETIME).isoformat(),)
            )
            db.execute("COMMIT")

    def _load(self, db: sqlite3.Connection, duel_id: str, now: datetime) -> Row:
        found = db.execute(
            "SELECT id, tabuleiro, x_token, o_token, jogadas, prazo, criada_em"
            " FROM velha_partidas WHERE id = ?",
            (duel_id,),
        ).fetchone()
        if found is None or datetime.fromisoformat(found[6]) < now - LIFETIME:
            db.execute("ROLLBACK")
            raise DuelNotFound(duel_id)
        return Row(
            id=found[0],
            tabuleiro=found[1],
            x_token=found[2],
            o_token=found[3],
            jogadas=json.loads(found[4]),
            prazo=datetime.fromisoformat(found[5]) if found[5] else None,
            criada_em=datetime.fromisoformat(found[6]),
        )

    def _expire(self, db: sqlite3.Connection, row: Row, now: datetime, judge: Judge) -> Row:
        """Every turn whose deadline passed becomes a timeout move (saved)."""
        changed = False
        while row.prazo is not None and now >= row.prazo:
            row.jogadas.append({"estouro": True})
            over = judge(row.tabuleiro, row.jogadas).over
            row.prazo = None if over else row.prazo + TURN
            changed = True
        if changed:
            self._save(db, row)
        return row

    def _save(self, db: sqlite3.Connection, row: Row) -> None:
        db.execute(
            "UPDATE velha_partidas SET jogadas = ?, prazo = ? WHERE id = ?",
            (json.dumps(row.jogadas), row.prazo.isoformat() if row.prazo else None, row.id),
        )
