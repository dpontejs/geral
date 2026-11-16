"""Jogo da velha duels by link: one row per duel in its own table of the site's SQLite.

Only the moves are kept; the board state always comes from replaying them (`judge_duel`). The
server owns the clock: `prazo` ends the current turn, and a deadline that passed becomes a timeout
move on the next read or write, as many times as turns went by. The creator's side is drawn (X
always starts); the clock starts when the second player joins. A rematch swaps the sides.
"""

import hashlib
import json
import secrets
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
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
    x_token TEXT,
    o_token TEXT,
    jogadas TEXT NOT NULL DEFAULT '[]',
    prazo TEXT,
    criada_em TEXT NOT NULL,
    revanche TEXT,
    proposta TEXT
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
    x_token: str | None
    o_token: str | None
    jogadas: list[dict]
    prazo: datetime | None
    criada_em: datetime
    revanche: str | None = None  # the rematch's id, once someone asked for it
    proposta: dict | None = None  # {"tipo": "encerrar" | "sortear", "lado": who asked}

    @property
    def complete(self) -> bool:
        """Both players are in (the board shows and the clock runs)."""
        return self.x_token is not None and self.o_token is not None

    def side_of(self, token: str | None) -> str | None:
        return {self.x_token: "X", self.o_token: "O"}.get(token) if token else None


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

    def create(self, board_code: str, now: datetime, side: str) -> tuple[str, str, str]:
        """A new duel: (id, the creator's token, the creator's side). Old duels are deleted here."""
        duel_id, token = secrets.token_urlsafe(6), secrets.token_urlsafe(16)
        with closing(self._connect()) as db:
            db.execute(
                "DELETE FROM velha_partidas WHERE criada_em < ?", ((now - LIFETIME).isoformat(),)
            )
            self._insert(db, duel_id, board_code, side, token, now)
            db.execute("COMMIT")
        return duel_id, token, side

    def join(self, duel_id: str, now: datetime) -> tuple[str, str] | None:
        """(token, side) of the second player, once; None when both are in. The clock starts."""
        with closing(self._connect()) as db:
            row = self._load(db, duel_id, now)
            if row.complete:
                db.execute("ROLLBACK")
                return None
            token, side = secrets.token_urlsafe(16), "O" if row.o_token is None else "X"
            self._claim(db, duel_id, side, token, now)
            db.execute("COMMIT")
        return token, side

    def rematch(
        self, duel_id: str, token: str, now: datetime, judge: Judge, board_code: str
    ) -> tuple[str, str, str]:
        """(id, token, side) of this player in the rematch of a finished duel, sides swapped.

        The first player to ask creates it (on `board_code`); the second one joins it, which
        starts the clock. Asking again gives the same answer (the token is derived, not stored).
        """
        with closing(self._connect()) as db:
            row = self._expire(db, self._load(db, duel_id, now), now, judge)
            side = row.side_of(token)
            if side is None:
                db.execute("COMMIT")
                raise NotYourTurn("not a player of this duel")
            if not judge(row.tabuleiro, row.jogadas).over:
                db.execute("COMMIT")
                raise DuelConflict("the duel is not over")
            new_side = "O" if side == "X" else "X"
            if row.revanche is None:
                new_id = secrets.token_urlsafe(6)
                new_token = _rematch_token(token, new_id)
                self._insert(db, new_id, board_code, new_side, new_token, now)
                db.execute("UPDATE velha_partidas SET revanche = ? WHERE id = ?", (new_id, row.id))
            else:
                new_id, new_token = row.revanche, _rematch_token(token, row.revanche)
                rematch = self._load(db, new_id, now)
                if rematch.side_of(new_token) is None:
                    self._claim(db, new_id, new_side, new_token, now)
            db.execute("COMMIT")
        return new_id, new_token, new_side

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
            side = row.side_of(token)
            if side is None:
                db.execute("COMMIT")
                raise NotYourTurn("not a player of this duel")
            if state.over or not row.complete:
                db.execute("COMMIT")
                raise DuelConflict("the duel is over" if state.over else "waiting for a player")
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
            row.proposta = None  # a move goes on with the game
            self._save(db, row)
            db.execute("COMMIT")
        return row

    def propose(self, duel_id: str, token: str, tipo: str, now: datetime, judge: Judge) -> Row:
        """A player asks to end the duel or to draw a new board; the other one answers."""
        with closing(self._connect()) as db:
            row = self._expire(db, self._load(db, duel_id, now), now, judge)
            side = row.side_of(token)
            if side is None:
                db.execute("COMMIT")
                raise NotYourTurn("not a player of this duel")
            if tipo not in ("encerrar", "sortear"):
                db.execute("COMMIT")
                raise ValueError(f"unknown proposal {tipo!r}")
            if judge(row.tabuleiro, row.jogadas).over or not row.complete:
                db.execute("COMMIT")
                raise DuelConflict("no proposal outside a running duel")
            row.proposta = {"tipo": tipo, "lado": side}
            self._save(db, row)
            db.execute("COMMIT")
        return row

    def answer(
        self, duel_id: str, token: str, aceita: bool, now: datetime, judge: Judge, board_code: str
    ) -> Row:
        """The other player accepts or refuses the proposal; the one who asked may withdraw it.

        Ending adds an agreed end (the most cells win); a new draw puts `board_code` in place,
        clears the moves and gives X a fresh turn (the sides stay).
        """
        with closing(self._connect()) as db:
            row = self._expire(db, self._load(db, duel_id, now), now, judge)
            side = row.side_of(token)
            if side is None:
                db.execute("COMMIT")
                raise NotYourTurn("not a player of this duel")
            if row.proposta is None or judge(row.tabuleiro, row.jogadas).over:
                db.execute("COMMIT")
                raise DuelConflict("nothing to answer")
            if aceita and side == row.proposta["lado"]:
                db.execute("COMMIT")
                raise DuelConflict("the other player answers a proposal")
            if aceita and row.proposta["tipo"] == "encerrar":
                row.jogadas, row.prazo = [*row.jogadas, {"encerrar": True}], None
            elif aceita:
                row.tabuleiro, row.jogadas, row.prazo = board_code, [], now + TURN
            row.proposta = None
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
            "SELECT id, tabuleiro, x_token, o_token, jogadas, prazo, criada_em, revanche, proposta"
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
            revanche=found[7],
            proposta=json.loads(found[8]) if found[8] else None,
        )

    def _insert(
        self, db: sqlite3.Connection, duel_id: str, code: str, side: str, token: str, now: datetime
    ) -> None:
        column = "x_token" if side == "X" else "o_token"
        db.execute(
            f"INSERT INTO velha_partidas (id, tabuleiro, {column}, criada_em) VALUES (?, ?, ?, ?)",
            (duel_id, code, token, now.isoformat()),
        )

    def _claim(
        self, db: sqlite3.Connection, duel_id: str, side: str, token: str, now: datetime
    ) -> None:
        """The second player takes `side`: the duel is complete and X's clock starts."""
        column = "x_token" if side == "X" else "o_token"
        db.execute(
            f"UPDATE velha_partidas SET {column} = ?, prazo = ? WHERE id = ?",
            (token, (now + TURN).isoformat(), duel_id),
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
            "UPDATE velha_partidas SET tabuleiro = ?, jogadas = ?, prazo = ?, proposta = ?"
            " WHERE id = ?",
            (
                row.tabuleiro,
                json.dumps(row.jogadas),
                row.prazo.isoformat() if row.prazo else None,
                json.dumps(row.proposta) if row.proposta else None,
                row.id,
            ),
        )


def _rematch_token(token: str, rematch_id: str) -> str:
    """The player's token in the rematch: derived from their secret token, so it is never stored
    twice and asking again gives the same one."""
    return hashlib.sha256(f"{token}:{rematch_id}".encode()).hexdigest()[:22]


async def duel_events(
    load: Callable[[], Awaitable[dict]],
    sleep: Callable[[float], Awaitable[None]],
    every: float = 0.5,
    ticks: int = 600,
) -> AsyncIterator[str]:
    """Server-sent events: the duel's state on connect and whenever it changes, until it ends
    and a rematch is asked (or the stream times out).

    The stream closes after `ticks` checks (about 5 minutes); the browser reconnects by itself.
    """
    last = None
    for _ in range(ticks):
        view = await load()
        key = (
            view["jogou"],
            view["completo"],
            view["prazo"],
            view.get("revanche"),
            json.dumps(view.get("proposta")),
            view.get("codigo"),
        )
        if key != last:
            last = key
            yield f"data: {json.dumps(view, ensure_ascii=False)}\n\n"
        if view["over"] and view.get("revanche"):
            return  # after the end it stays open until a rematch shows up
        await sleep(every)
