"""Rules of a Mano a Mano room: pure, synchronous, with the clock injected.

Two players (or one and the bot) take turns kicking and keeping. Each kick goes through
`barreira` (free kicks only: the keeper arms the wall) → `escolha` (both lock their choice in
secret) → `corrida` (the run-up, until `chute_em`) → `voo` (the keeper's exit window) →
`resultado` (the replay) → the next kick, or `fim`. Every method receives `agora` and returns
the events the hub must deliver; privacy (nobody sees the other's choice before `cobranca`) is
decided here.
"""

import random
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import ValidationError

from geral.games.mano import bot
from geral.games.mano.disputa import Disputa
from geral.games.mano.regras import resolver
from geral.games.mano.tipos import (
    Barreira,
    Chute,
    Defesa,
    Lado,
    Lance,
    Modo,
    Nivel,
    Posicao,
    Trajetoria,
)
from geral.games.prancheta.filtro import tem_palavrao
from geral.games.prancheta.tipos import normalizar

PRAZO_ESCOLHA = timedelta(seconds=10)  # to arm the wall and to lock each choice
CORRIDA = timedelta(seconds=1.5)  # from both locked to `chute_em`
JANELA = timedelta(milliseconds=600)  # the keeper's exit counts from `chute_em` for this long
FOLGA = timedelta(milliseconds=150)  # plus this, for the network
RESULTADO = timedelta(seconds=3)  # the replay before the next kick
AUSENCIA = timedelta(seconds=30)  # with no events connection for this long: loses by W.O.
ESPERA_FIM = timedelta(minutes=10)  # a finished match waits this long for a rematch
INTERVALO_ACAO = timedelta(seconds=0.3)  # one action per player every this long
APELIDO_MIN, APELIDO_MAX = 2, 16
LADOS: tuple[Lado, ...] = ("esquerda", "fica", "direita")
TRAJETORIAS: tuple[Trajetoria, ...] = ("rasteira", "por_cima", "pelo_lado")
POSICOES = ("meia_lua", "entrada_esquerda", "entrada_direita")
APELIDO_BOT: dict[Nivel, str] = {
    "facil": "Bot fácil",
    "medio": "Bot médio",
    "dificil": "Bot difícil",
}
EM_JOGO = ("barreira", "escolha", "corrida", "voo", "resultado")


@dataclass
class Evento:
    tipo: str  # estado | cobranca_inicio | cobranca | fim
    dados: dict  # the contract's JSON, already with "seq"
    para: int | None = None


class ErroSala(Exception):
    def __init__(self, status: int, motivo: str):
        super().__init__(motivo)
        self.status = status
        self.motivo = motivo


@dataclass
class _Jogador:
    id: int
    apelido: str
    token: str | None  # the bot has none
    desde: datetime  # last time the player had no events connection (or joined)
    conexoes: int = 0
    ultima_acao: datetime | None = None
    revanche: bool = False

    @property
    def bot(self) -> bool:
        return self.token is None


class Sala:
    def __init__(
        self, id: str, modo: Modo, bot: Nivel | None, agora: datetime, rng: random.Random
    ) -> None:
        if modo not in ("penaltis", "faltas"):
            raise ErroSala(422, "unknown mode")
        if bot not in (None, "facil", "medio", "dificil"):
            raise ErroSala(422, "unknown bot level")
        self.id = id
        self.modo: Modo = modo
        self.nivel: Nivel | None = bot
        self.criada_em = agora
        self.partida_desde = agora  # when the current match began (the súmula's `criada_em`)
        self.encerrada = False  # closed for good: the hub drops it
        self._rng_sala = rng  # seeds one `Random` per match (the bot's habit lives in it)
        self._rng = random.Random(rng.getrandbits(64))
        self._seq = 0
        self._jogadores: list[_Jogador] = []
        self._tokens: dict[str, int] = {}
        self._fase = "espera"
        self._prazo: datetime | None = None
        self._partida = 1
        self._disputa = Disputa()
        self._lances: list[Lance] = []
        self._posicao: Posicao | None = None
        self._barreira: Barreira | None = None
        self._chute: Chute | None = None
        self._defesa: Defesa | None = None  # the bot's carries its exit; a human's is decided later
        self._chute_em: datetime | None = None
        self._saida: bool | None = None  # the human keeper's first press: None = not yet

    # --- entrada e identidade ---

    def entrar(self, apelido: str, agora: datetime) -> tuple[int, str, list[Evento]]:
        """Player 0 creates the room, player 1 joins (with a bot, the bot is player 1)."""
        if self.encerrada:
            raise ErroSala(409, "room is over")
        if len(self._jogadores) >= 2:
            raise ErroSala(409, "room is full")
        apelido = self._validar_apelido(apelido)
        jogador = _Jogador(len(self._jogadores), apelido, secrets.token_urlsafe(16), desde=agora)
        self._jogadores.append(jogador)
        assert jogador.token is not None
        self._tokens[jogador.token] = jogador.id
        if self.nivel is not None:
            self._jogadores.append(_Jogador(1, APELIDO_BOT[self.nivel], None, desde=agora))
        if len(self._jogadores) == 2:
            return jogador.id, jogador.token, self._iniciar_cobranca(agora)
        return jogador.id, jogador.token, self._estados(agora)

    def _validar_apelido(self, apelido: str) -> str:
        apelido = apelido.strip()
        if not APELIDO_MIN <= len(apelido) <= APELIDO_MAX:
            raise ErroSala(422, "nickname must have 2 to 16 characters")
        if tem_palavrao(apelido):
            raise ErroSala(422, "nickname not allowed")
        if normalizar(apelido) in {normalizar(j.apelido) for j in self._jogadores}:
            raise ErroSala(422, "nickname already in the room")
        return apelido

    def jogador(self, token: str) -> int:
        if token not in self._tokens:
            raise ErroSala(403, "invalid token")
        return self._tokens[token]

    def esta(self, jogador: int) -> bool:
        """Still in the room: has not left."""
        return any(j.token in self._tokens for j in self._jogadores if j.id == jogador)

    # --- ações ---

    def agir(self, jogador: int, acao: dict, agora: datetime) -> list[Evento]:
        if not self.esta(jogador):
            raise ErroSala(403, "player is not in the room")
        if self.encerrada:
            raise ErroSala(409, "room is over")
        tratar = {
            "barreira": self._armar,
            "chute": self._chutar,
            "defesa": self._defender,
            "saida": self._sair_do_gol,
            "revanche": self._revanche,
            "sair": self._sair,
        }.get(acao.get("tipo"))
        if tratar is None:
            raise ErroSala(422, "unknown action")
        j = self._jogadores[jogador]
        if j.ultima_acao is not None and agora - j.ultima_acao < INTERVALO_ACAO:
            raise ErroSala(429, "too many actions")
        dados = {k: v for k, v in acao.items() if k != "tipo"}
        eventos = tratar(jogador, dados, agora)
        j.ultima_acao = agora  # only an accepted action uses the slot
        return eventos

    def _exigir(self, jogador: int, fase: str, papel: str) -> None:
        if self._fase != fase:
            raise ErroSala(409, f"not the time for this ({self._fase})")
        if self._papel(jogador) != papel:
            raise ErroSala(409, f"only the {papel} does this")

    def _armar(self, jogador: int, dados: dict, agora: datetime) -> list[Evento]:
        self._exigir(jogador, "barreira", "goleiro")
        try:
            barreira = Barreira(n=dados.get("n"), x=dados.get("x"))
        except ValidationError as erro:
            raise ErroSala(422, "invalid wall") from erro
        return self._ir_a_escolha(barreira, agora)

    def _chutar(self, jogador: int, dados: dict, agora: datetime) -> list[Evento]:
        self._exigir(jogador, "escolha", "batedor")
        if self._chute is not None:
            raise ErroSala(409, "already locked")
        campos = {"alvo": dados.get("alvo"), "barra": dados.get("barra")}
        if self.modo == "faltas":  # a penalty drops the trajectory and the curve
            if dados.get("trajetoria") is None:
                raise ErroSala(422, "a free kick needs a trajetoria")
            campos |= {"trajetoria": dados["trajetoria"], "curva": dados.get("curva", 0)}
        try:
            self._chute = Chute(**campos)
        except ValidationError as erro:
            raise ErroSala(422, "invalid kick") from erro
        return self._depois_de_travar(agora)

    def _defender(self, jogador: int, dados: dict, agora: datetime) -> list[Evento]:
        self._exigir(jogador, "escolha", "goleiro")
        if self._defesa is not None:
            raise ErroSala(409, "already locked")
        if dados.get("lado") not in LADOS:
            raise ErroSala(422, "invalid side")
        self._defesa = Defesa(lado=dados["lado"], saida=False)
        return self._depois_de_travar(agora)

    def _sair_do_gol(self, jogador: int, dados: dict, agora: datetime) -> list[Evento]:
        """The keeper's exit: the first press after both locked decides, in or out of the window.

        A press that arrives after the kick was resolved (a slow network) changes nothing.
        """
        if self._fase == "resultado" and self._papel(jogador) == "goleiro":
            return []
        if self._fase not in ("corrida", "voo"):
            raise ErroSala(409, f"not the time for this ({self._fase})")
        if self._papel(jogador) != "goleiro":
            raise ErroSala(409, "only the goleiro does this")
        if self._saida is None:
            assert self._chute_em is not None
            self._saida = self._chute_em <= agora <= self._chute_em + JANELA + FOLGA
        return []

    def _revanche(self, jogador: int, dados: dict, agora: datetime) -> list[Evento]:
        if self._fase != "fim":
            raise ErroSala(409, "the match is not over")
        if not self.esta(1 - jogador) and not self._jogadores[1 - jogador].bot:
            raise ErroSala(409, "the other player left")
        self._jogadores[jogador].revanche = True
        if not all(j.revanche or j.bot for j in self._jogadores):
            return self._estados(agora)
        self._partida += 1
        self.partida_desde = agora
        self._rng = random.Random(self._rng_sala.getrandbits(64))
        self._disputa = Disputa()
        self._lances = []
        for j in self._jogadores:
            j.revanche = False
        return self._iniciar_cobranca(agora)

    def _sair(self, jogador: int, dados: dict, agora: datetime) -> list[Evento]:
        """Leaves for good: losing by W.O. mid-match; at the end or alone, the room closes."""
        j = self._jogadores[jogador]
        assert j.token is not None
        del self._tokens[j.token]
        if self._fase in EM_JOGO:
            return self._wo(jogador, agora)
        self.encerrada = True
        self._prazo = None
        return self._estados(agora)

    # --- conexão e relógio ---

    def conectou(self, jogador: int, agora: datetime) -> list[Evento]:
        if 0 <= jogador < len(self._jogadores):
            self._jogadores[jogador].conexoes += 1
        return []

    def desconectou(self, jogador: int, agora: datetime) -> list[Evento]:
        if 0 <= jogador < len(self._jogadores):
            j = self._jogadores[jogador]
            j.conexoes = max(j.conexoes - 1, 0)
            if j.conexoes == 0:
                j.desde = agora
        return []

    def avancar(self, agora: datetime) -> list[Evento]:
        eventos: list[Evento] = []
        if self.encerrada:
            return eventos
        if self._fase in EM_JOGO:
            ausentes = [
                j
                for j in self._jogadores
                if not j.bot and j.conexoes == 0 and agora - j.desde >= AUSENCIA
            ]
            if ausentes:  # both gone: whoever left first loses
                return self._wo(min(ausentes, key=lambda j: j.desde).id, agora)
        while not self.encerrada and self._prazo is not None and agora >= self._prazo:
            if self._fase == "barreira":
                barreira = Barreira(n=self._rng.randint(2, 5), x=self._rng.randint(0, 1000))
                eventos += self._ir_a_escolha(barreira, agora)
            elif self._fase == "escolha":
                if self._chute is None:
                    self._chute = self._chute_ao_acaso()
                if self._defesa is None:
                    self._defesa = Defesa(lado=self._rng.choice(LADOS), saida=False)
                eventos += self._depois_de_travar(agora)
            elif self._fase == "corrida":
                assert self._chute_em is not None
                self._fase = "voo"
                self._prazo = self._chute_em + JANELA + FOLGA
            elif self._fase == "voo":
                eventos += self._resolver(agora)
            elif self._fase == "resultado":
                if self._disputa.acabou():
                    eventos += self._fim(agora)
                else:
                    eventos += self._iniciar_cobranca(agora)
            elif self._fase == "fim":  # nobody asked for a rematch: the room closes
                self.encerrada = True
                self._prazo = None
        return eventos

    def encerrar(self, agora: datetime) -> list[Evento]:
        """The hub's cleanup, for good: a match in progress keeps its súmula as it stands."""
        if self.encerrada:
            return []
        eventos = self._fim(agora) if self._fase in EM_JOGO else []
        self.encerrada = True
        self._prazo = None
        return eventos

    # --- fases ---

    def _iniciar_cobranca(self, agora: datetime) -> list[Evento]:
        self._chute = None
        self._defesa = None
        self._barreira = None
        self._posicao = None
        self._chute_em = None
        self._saida = None
        if self.modo == "penaltis":
            return self._ir_a_escolha(None, agora)
        self._posicao = Posicao(nome=self._rng.choice(POSICOES), desvio=self._rng.randint(-80, 80))
        goleiro = self._jogadores[1 - self._disputa.batedor()]
        if goleiro.bot:
            assert self.nivel is not None
            return self._ir_a_escolha(bot.armar(self.nivel, self._rng), agora)
        self._fase = "barreira"
        self._prazo = agora + PRAZO_ESCOLHA
        return self._estados(agora)

    def _ir_a_escolha(self, barreira: Barreira | None, agora: datetime) -> list[Evento]:
        self._barreira = barreira
        self._fase = "escolha"
        self._prazo = agora + PRAZO_ESCOLHA
        batedor = self._disputa.batedor()
        if self.nivel is not None:  # the bot (player 1) locks at once
            # what it reads: the human's kicks when it keeps, the human's dives when it kicks,
            # that is, the past kicks where the human held the role it faces now
            historico = [lance for quem, lance in self._lances_por_batedor() if quem == batedor]
            if batedor == 1:
                self._chute = bot.chutar(
                    self.nivel,
                    historico,
                    self._rng,
                    barreira=self._barreira,
                    posicao=self._posicao,
                )
            else:
                self._defesa = bot.defender(self.nivel, historico, self._rng)
        return self._estados(agora)

    def _lances_por_batedor(self) -> list[tuple[int, Lance]]:
        return [
            (quem, lance)
            for (quem, _), lance in zip(self._disputa.cobrancas, self._lances, strict=True)
        ]

    def _depois_de_travar(self, agora: datetime) -> list[Evento]:
        if self._chute is None or self._defesa is None:
            return self._estados(agora)
        self._fase = "corrida"
        self._chute_em = agora + CORRIDA
        self._prazo = self._chute_em
        return [
            *self._estados(agora),
            self._evento(
                "cobranca_inicio",
                # the server's clock now, so the client can move `chute_em` to its own
                {"chute_em": self._chute_em.isoformat(), "agora": agora.isoformat()},
            ),
        ]

    def _chute_ao_acaso(self) -> Chute:
        alvo = (self._rng.randint(0, 1000), self._rng.randint(0, 1000))
        barra = self._rng.randint(0, 1000)
        if self.modo == "penaltis":
            return Chute(alvo=alvo, barra=barra)
        return Chute(
            alvo=alvo,
            barra=barra,
            trajetoria=self._rng.choice(TRAJETORIAS),
            curva=self._rng.uniform(-1, 1),
        )

    def _resolver(self, agora: datetime) -> list[Evento]:
        assert self._chute is not None and self._defesa is not None
        defesa = self._defesa
        if not self._jogadores[1 - self._disputa.batedor()].bot:
            defesa = Defesa(lado=defesa.lado, saida=bool(self._saida))
        lance = resolver(
            self._chute, defesa, self._rng, barreira=self._barreira, posicao=self._posicao
        )
        self._disputa.registrar(lance.resultado == "gol")
        self._lances.append(lance)
        self._fase = "resultado"
        self._prazo = agora + RESULTADO
        return [
            self._evento(
                "cobranca", {"lance": lance.model_dump(mode="json"), "placar": self._placar()}
            ),
            *self._estados(agora),
        ]

    def _wo(self, perdedor: int, agora: datetime) -> list[Evento]:
        if not self._disputa.acabou():
            self._disputa.wo(perdedor)
        return self._fim(agora)

    def _fim(self, agora: datetime) -> list[Evento]:
        self._fase = "fim"
        self._prazo = agora + ESPERA_FIM
        return [*self._estados(agora), self._evento("fim", {"sumula": self._sumula()})]

    # --- leitura ---

    def _papel(self, jogador: int) -> str | None:
        if len(self._jogadores) < 2 or self._fase in ("espera", "fim"):
            return None
        if self._fase == "resultado":  # the replay: the roles of the kick just taken
            batedor = self._disputa.cobrancas[-1][0]
        else:
            batedor = self._disputa.batedor()
        return "batedor" if jogador == batedor else "goleiro"

    def _placar(self) -> list[int]:
        return list(self._disputa.placar())

    def _sumula(self) -> dict:
        return {
            "id": f"{self.id}-{self._partida}",
            "sala": self.id,
            "partida": self._partida,
            "modo": self.modo,
            "jogadores": [{"apelido": j.apelido, "bot": j.bot} for j in self._jogadores],
            "placar": self._placar(),
            "vencedor": self._disputa.vencedor(),
            "wo": self._disputa.perdedor_wo is not None,
            "cobrancas": [
                {"batedor": quem, "resultado": lance.resultado, "onde": list(lance.onde)}
                for quem, lance in self._lances_por_batedor()
            ],
        }

    def sumula(self) -> dict | None:
        """The current match's súmula once it is over; else None."""
        return self._sumula() if self._fase == "fim" else None

    def foto(self, jogador: int, agora: datetime) -> dict:
        papel = self._papel(jogador)
        outro = 1 - jogador
        travou = {"voce": False, "outro": False}
        escolha = None
        if self._fase in ("barreira", "escolha", "corrida", "voo"):
            meu, dele = (
                (self._chute, self._defesa) if papel == "batedor" else (self._defesa, self._chute)
            )
            travou = {"voce": meu is not None, "outro": dele is not None}
            if isinstance(meu, Chute):
                escolha = meu.model_dump(mode="json")
            elif isinstance(meu, Defesa):
                escolha = {"lado": meu.lado}
        serie: list[list[bool]] = [[], []]
        for quem, gol in self._disputa.cobrancas:
            serie[quem].append(gol)
        return {
            "seq": self._seq,
            "voce": jogador,
            "fase": self._fase,
            "modo": self.modo,
            "partida": self._partida,
            "papel": papel,
            "prazo": self._prazo.isoformat() if self._prazo else None,
            "agora": agora.isoformat(),
            "chute_em": self._chute_em.isoformat() if self._chute_em else None,
            "placar": self._placar(),
            "serie": serie,
            "posicao": self._posicao.model_dump() if self._posicao else None,
            "barreira": self._barreira.model_dump() if self._barreira else None,
            "travou": travou,
            "escolha": escolha,
            "ultimo": (
                self._lances[-1].model_dump(mode="json")
                if self._fase in ("resultado", "fim") and self._lances
                else None
            ),
            "revanche": {
                "voce": self._jogadores[jogador].revanche,
                "outro": len(self._jogadores) > 1
                and (self._jogadores[outro].revanche or self._jogadores[outro].bot),
            },
            "sumula": f"{self.id}-{self._partida}" if self._fase == "fim" else None,
            "jogadores": [
                {
                    "apelido": j.apelido,
                    "bot": j.bot,
                    "presente": j.bot or j.conexoes > 0,
                    "saiu": not j.bot and j.token not in self._tokens,
                }
                for j in self._jogadores
            ],
        }

    def _estados(self, agora: datetime) -> list[Evento]:
        """One `estado` per player still in the room (each sees their own view), one seq."""
        self._seq += 1
        return [
            Evento("estado", self.foto(j.id, agora), para=j.id)
            for j in self._jogadores
            if not j.bot and j.token in self._tokens
        ]

    def _evento(self, tipo: str, dados: dict) -> Evento:
        self._seq += 1
        return Evento(tipo, {**dados, "seq": self._seq})
