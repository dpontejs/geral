"""Rules of a Prancheta room: pure, synchronous, with the clock injected.

Every method receives `agora` and returns the events the hub must deliver. Privacy (who sees
the word, the choices, a near miss) is decided here; the hub only routes `para`/`exceto`.
"""

import random
import secrets
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from geral.games.prancheta.filtro import tem_palavrao
from geral.games.prancheta.tipos import Banco, Palavra, normalizar

MAX_JOGADORES = 10
MAX_PEDIDOS = 10  # requests waiting for the host's answer
TEMPO_ESCOLHA = timedelta(seconds=15)
TEMPO_DESENHO = timedelta(seconds=80)
TEMPO_INTERVALO = timedelta(seconds=6)
AUSENCIA = timedelta(seconds=30)
BASE = {"facil": 5, "media": 7, "dificil": 10}
PISO = 2
ASSISTENCIA = 2
PEDACO_MAX = 64
PONTOS_MAX = 20_000
CHUTE_MAX = 40
CHUTE_INTERVALO = timedelta(seconds=0.5)
PEDACOS_POR_SEGUNDO = 40
APELIDO_MIN, APELIDO_MAX = 2, 16
CORES = range(13)  # 0 is the eraser, 1–12 the chalks
ESPESSURAS = (1, 2, 3)
COORDENADAS = range(1001)
DIFICULDADES = ("facil", "media", "dificil")
MARCOS_DICA = (0.5, 0.75)  # shares of the drawing time that unlock a hint each


@dataclass
class Evento:
    # estado | traco | desfazer | limpar | chute | acerto | trave | dica | pulou | recusado | fim
    tipo: str
    dados: dict  # the contract's JSON, already with "seq"
    para: int | None = None
    exceto: int | None = None


class ErroSala(Exception):
    def __init__(self, status: int, motivo: str):
        super().__init__(motivo)
        self.status = status
        self.motivo = motivo


@dataclass
class _Jogador:
    id: int
    apelido: str
    token: str
    desde: datetime  # last time the player had no events connection (or joined)
    pontos: int = 0
    gols: int = 0
    assist: int = 0
    conexoes: int = 0
    presente: bool = True
    acertou: bool = False
    ultimo_chute: datetime | None = None
    pedacos: deque = field(default_factory=deque)


@dataclass
class _Pedido:
    """Someone who opened the link and asked to join: waits for the host's answer."""

    id: int  # the player id they get if accepted
    apelido: str
    token: str
    desde: datetime  # last time the request had no events connection (or was made)
    conexoes: int = 0


def _eh_int(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


class Sala:
    def __init__(
        self, id: str, rodadas: int, banco: Banco, rng: random.Random, agora: datetime
    ) -> None:
        self.id = id
        self.rodadas = rodadas
        self.criada_em = agora
        self.encerrada = False
        self._banco = banco
        self._rng = rng
        self._seq = 0
        self._jogadores: dict[int, _Jogador] = {}  # active players, in joining order
        self._tokens: dict[str, int] = {}
        self._pedidos: dict[int, _Pedido] = {}  # waiting for the host, in arrival order
        self._tokens_pedido: dict[str, int] = {}
        self._proximo_id = 1
        self._anfitriao: int | None = None
        self._fase = "espera"
        self._rodada = 0
        self._fila: list[int] = []
        self._prazo: datetime | None = None
        self._usadas: set[str] = set()
        self._desenhista: int | None = None
        self._opcoes: list[Palavra] | None = None
        self._palavra: Palavra | None = None
        self._tracos: dict[int, dict] = {}
        self._total_pontos = 0
        self._dica: list[str | None] | None = None
        self._dicas_dadas = 0
        self._acertaram: list[int] = []
        self._todos: dict[int, _Jogador] = {}  # everyone who ever joined, for the súmula
        self._expulsos: set[int] = set()
        self._votos: dict[int, set[int]] = {}  # target -> who voted against them
        self._lances: list[dict] = []
        self._lance_registrado = True

    # --- entrada e identidade ---

    def entrar(self, apelido: str, agora: datetime) -> tuple[int, str, list[Evento]]:
        """Joins at once: only the room's creator (everyone else asks with `pedir`)."""
        if self.encerrada:
            raise ErroSala(409, "room is over")
        if len(self._jogadores) >= MAX_JOGADORES:
            raise ErroSala(409, "room is full")
        apelido = self._validar_apelido(apelido)
        jogador = self._admitir(self._proximo_id, apelido, secrets.token_urlsafe(16), agora)
        self._proximo_id += 1
        return jogador.id, jogador.token, self._estados(agora)

    def pedir(self, apelido: str, agora: datetime) -> tuple[int, str, list[Evento]]:
        """Asks the host to join; the request's id is the player id it gets if accepted.

        A request takes no seat until accepted. Its token opens the events stream (to learn the
        answer) but acts on nothing.
        """
        if self.encerrada:
            raise ErroSala(409, "room is over")
        if len(self._pedidos) >= MAX_PEDIDOS:
            raise ErroSala(409, "too many requests")
        apelido = self._validar_apelido(apelido)
        pedido = _Pedido(self._proximo_id, apelido, secrets.token_urlsafe(16), desde=agora)
        self._proximo_id += 1
        self._pedidos[pedido.id] = pedido
        self._tokens_pedido[pedido.token] = pedido.id
        return pedido.id, pedido.token, self._estados(agora)

    def _validar_apelido(self, apelido: str) -> str:
        apelido = apelido.strip()
        if not APELIDO_MIN <= len(apelido) <= APELIDO_MAX:
            raise ErroSala(422, "nickname must have 2 to 16 characters")
        if tem_palavrao(apelido):
            raise ErroSala(422, "nickname not allowed")
        em_uso = [*self._jogadores.values(), *self._pedidos.values()]
        if normalizar(apelido) in {normalizar(j.apelido) for j in em_uso}:
            raise ErroSala(422, "nickname already in the room")
        return apelido

    def _admitir(
        self, id_: int, apelido: str, token: str, desde: datetime, conexoes: int = 0
    ) -> _Jogador:
        jogador = _Jogador(id_, apelido, token, desde=desde, conexoes=conexoes)
        self._jogadores[jogador.id] = jogador
        self._todos[jogador.id] = jogador
        self._tokens[jogador.token] = jogador.id
        if self._anfitriao is None:
            self._anfitriao = jogador.id
        if self._fase not in ("espera", "fim"):
            self._fila.append(jogador.id)
        return jogador

    def esta(self, jogador: int) -> bool:
        """Still has a place here: a player (not left, not sent off) or a request waiting."""
        return jogador in self._jogadores or jogador in self._pedidos

    def jogador(self, token: str) -> int:
        """The player who acts with this token; a request still waiting cannot act (409)."""
        if token in self._tokens:
            return self._tokens[token]
        if token in self._tokens_pedido:
            raise ErroSala(409, "waiting for the host")
        raise ErroSala(403, "invalid token")

    def identificar(self, token: str) -> int:
        """Whoever may listen to the events with this token: a player or a request waiting."""
        quem = self._tokens.get(token) or self._tokens_pedido.get(token)
        if quem is None:
            raise ErroSala(403, "invalid token")
        return quem

    # --- ações ---

    def agir(self, jogador: int, acao: dict, agora: datetime) -> list[Evento]:
        if jogador not in self._jogadores:
            raise ErroSala(403, "player is not in the room")
        if self.encerrada:
            raise ErroSala(409, "room is over")
        tratar = {
            "comecar": self._comecar,
            "escolher": self._escolher,
            "traco": self._traco,
            "desfazer": self._desfazer,
            "limpar": self._limpar,
            "chute": self._chute,
            "cartao": self._cartao,
            "tirar": self._tirar,
            "sair": self._sair,
            "aceitar": self._aceitar,
            "recusar": self._recusar,
            "dica": self._dar_dica,
            "pular": self._pular,
        }.get(acao.get("tipo"))
        if tratar is None:
            raise ErroSala(422, "unknown action")
        return tratar(self._jogadores[jogador], acao, agora)

    def _comecar(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        if jogador.id != self._anfitriao:
            raise ErroSala(409, "only the host starts")
        if self._fase != "espera":
            raise ErroSala(409, "already started")
        if len(self._presentes()) < 2:
            raise ErroSala(409, "need two players")
        return self._proximo_lance(agora)

    def _escolher(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        self._exigir_desenhista(jogador, "escolha")
        indice = acao.get("indice")
        if not _eh_int(indice) or not 0 <= indice <= 2:
            raise ErroSala(422, "index must be 0 to 2")
        assert self._opcoes is not None
        return self._comecar_desenho(self._opcoes[indice], agora)

    def _traco(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        self._exigir_desenhista(jogador, "desenho")
        id_, cor, esp, pts, fim = (acao.get(k) for k in ("id", "cor", "esp", "pts", "fim"))
        valido = (
            _eh_int(id_)
            and _eh_int(cor)
            and cor in CORES
            and _eh_int(esp)
            and esp in ESPESSURAS
            and isinstance(fim, bool)
            and isinstance(pts, list)
            and len(pts) <= PEDACO_MAX
            and all(
                isinstance(p, list)
                and len(p) == 2
                and all(_eh_int(c) and c in COORDENADAS for c in p)
                for p in pts
            )
        )
        if not valido:
            raise ErroSala(422, "invalid stroke")
        if self._total_pontos + len(pts) > PONTOS_MAX:
            raise ErroSala(422, "drawing is too long")
        while jogador.pedacos and agora - jogador.pedacos[0] >= timedelta(seconds=1):
            jogador.pedacos.popleft()
        if len(jogador.pedacos) >= PEDACOS_POR_SEGUNDO:
            raise ErroSala(429, "too many stroke pieces")
        jogador.pedacos.append(agora)
        self._total_pontos += len(pts)
        atual = self._tracos.get(id_)
        if atual is None:
            self._tracos[id_] = {"id": id_, "cor": cor, "esp": esp, "pts": list(pts), "fim": fim}
        else:
            atual["pts"].extend(pts)
            atual["fim"] = fim
        dados = {"id": id_, "cor": cor, "esp": esp, "pts": pts, "fim": fim}
        return [self._evento("traco", dados, exceto=jogador.id)]

    def _desfazer(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        self._exigir_desenhista(jogador, "desenho")
        if not self._tracos:
            return []
        id_, traco = self._tracos.popitem()
        self._total_pontos -= len(traco["pts"])
        return [self._evento("desfazer", {"id": id_}, exceto=jogador.id)]

    def _limpar(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        self._exigir_desenhista(jogador, "desenho")
        self._tracos.clear()
        self._total_pontos = 0
        return [self._evento("limpar", {}, exceto=jogador.id)]

    def _chute(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        if self._fase != "desenho" or jogador.id == self._desenhista or jogador.acertou:
            raise ErroSala(409, "cannot guess now")
        cru = acao.get("texto")
        if not isinstance(cru, str) or not cru.strip() or len(cru.strip()) > CHUTE_MAX:
            raise ErroSala(422, "guess must have 1 to 40 characters")
        if jogador.ultimo_chute and agora - jogador.ultimo_chute < CHUTE_INTERVALO:
            raise ErroSala(429, "guessing too fast")
        jogador.ultimo_chute = agora
        assert self._palavra is not None
        veredito = self._banco.julgar(cru, self._palavra)
        texto = cru.strip()
        if veredito == "certo":
            return self._acerto(jogador, agora)
        if veredito == "trave":
            return [self._evento("trave", {"texto": texto}, para=jogador.id)]
        dados = {"jogador": jogador.id, "texto": texto}
        normal = normalizar(texto)
        entrega = tem_palavrao(texto) or any(
            normalizar(alvo) in normal for alvo in (self._palavra.texto, *self._palavra.aceita)
        )
        return [self._evento("chute", dados, para=jogador.id if entrega else None)]

    def _acerto(self, jogador: _Jogador, agora: datetime) -> list[Evento]:
        assert self._palavra is not None
        self._acertaram.append(jogador.id)
        pontos = max(BASE[self._palavra.dificuldade] - (len(self._acertaram) - 1), PISO)
        jogador.acertou = True
        jogador.pontos += pontos
        jogador.gols += 1
        desenhista = self._jogadores.get(self._desenhista or 0)
        if desenhista is not None:
            desenhista.pontos += ASSISTENCIA
            desenhista.assist += 1
        eventos = [self._evento("acerto", {"jogador": jogador.id, "pontos": pontos})]
        if self._todos_acertaram():
            eventos += self._ir_ao_intervalo(agora)
        return eventos

    def _todos_acertaram(self) -> bool:
        quem_chuta = [j for j in self._presentes() if j != self._desenhista]
        return all(self._jogadores[j].acertou for j in quem_chuta)

    def _cartao(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        alvo = self._alvo(jogador, acao)
        self._votos.setdefault(alvo, set()).add(jogador.id)
        return self._checar_votos(agora) or self._estados(agora)  # everyone sees the count

    def _tirar(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        if jogador.id != self._anfitriao:
            raise ErroSala(409, "only the host sends someone off")
        alvo = self._alvo(jogador, acao)
        return self._remover(self._jogadores[alvo], agora, expulso=True)

    def _sair(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        return self._remover(jogador, agora, expulso=False)

    def _pedido(self, jogador: _Jogador, acao: dict) -> _Pedido:
        if jogador.id != self._anfitriao:
            raise ErroSala(409, "only the host answers requests")
        pedido = acao.get("pedido")
        if not _eh_int(pedido) or pedido not in self._pedidos:
            raise ErroSala(422, "invalid request")
        return self._pedidos[pedido]

    def _aceitar(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        pedido = self._pedido(jogador, acao)
        if len(self._jogadores) >= MAX_JOGADORES:
            raise ErroSala(409, "room is full")
        self._tirar_pedido(pedido)
        self._admitir(pedido.id, pedido.apelido, pedido.token, pedido.desde, pedido.conexoes)
        return self._depois_de_mudar(agora)

    def _recusar(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        pedido = self._pedido(jogador, acao)
        self._tirar_pedido(pedido)
        return [self._evento("recusado", {}, para=pedido.id), *self._estados(agora)]

    def _tirar_pedido(self, pedido: _Pedido) -> None:
        del self._pedidos[pedido.id]
        del self._tokens_pedido[pedido.token]

    def _dar_dica(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        """Whoever draws lights one random unlit letter, once per threshold already passed."""
        self._exigir_desenhista(jogador, "desenho")
        liberadas = sum(1 for marco in self._marcos_dica() if marco <= agora)
        if self._dicas_dadas >= liberadas:
            raise ErroSala(409, "no hint to give now")
        assert self._palavra is not None and self._dica is not None
        apagadas = [i for i, c in enumerate(self._dica) if c is None]
        i = self._rng.choice(apagadas)
        self._dica[i] = self._palavra.texto[i]
        self._dicas_dadas += 1
        self._seq += 1
        return [
            self._evento("dica", {"dica": list(self._dica)}, exceto=jogador.id),
            Evento("estado", self.foto(jogador.id, agora), para=jogador.id),
        ]

    def _marcos_dica(self) -> list[datetime]:
        """When each hint unlocks; never more hints than 1/3 of the letters."""
        if self._fase != "desenho" or self._palavra is None or self._prazo is None:
            return []
        letras = sum(1 for c in self._palavra.texto if c.isalpha())
        inicio = self._prazo - TEMPO_DESENHO
        return [inicio + TEMPO_DESENHO * m for m in MARCOS_DICA][: letras // 3]

    def _pular(self, jogador: _Jogador, acao: dict, agora: datetime) -> list[Evento]:
        """Whoever draws gives up the turn: the word is shown and the points stay."""
        if self._fase not in ("escolha", "desenho") or jogador.id != self._desenhista:
            raise ErroSala(409, "not your turn")
        return [self._evento("pulou", {"jogador": jogador.id}), *self._ir_ao_intervalo(agora)]

    def _alvo(self, jogador: _Jogador, acao: dict) -> int:
        alvo = acao.get("alvo")
        if not _eh_int(alvo) or alvo not in self._jogadores or alvo == jogador.id:
            raise ErroSala(422, "invalid target")
        return alvo

    def _remover(self, jogador: _Jogador, agora: datetime, expulso: bool) -> list[Evento]:
        """Takes a player out (left or sent off); their token stops working and their votes fall."""
        del self._jogadores[jogador.id]
        del self._tokens[jogador.token]
        if expulso:
            self._expulsos.add(jogador.id)
        self._votos.pop(jogador.id, None)
        for votantes in self._votos.values():
            votantes.discard(jogador.id)
        if jogador.id in self._fila:
            self._fila.remove(jogador.id)
        return self._depois_de_mudar(agora, tambem=(jogador.id,))

    def _checar_votos(self, agora: datetime) -> list[Evento]:
        """A strict majority of the present players (target not counted) sends the target off."""
        if self.encerrada:
            return []
        presentes = set(self._presentes())
        for alvo, votantes in self._votos.items():
            outros = presentes - {alvo}
            if 2 * len(votantes & outros) > len(outros):
                return self._remover(self._jogadores[alvo], agora, expulso=True)
        return []

    def _depois_de_mudar(self, agora: datetime, tambem: tuple[int, ...] = ()) -> list[Evento]:
        """Reacts to a change in who is in the room or present, and tells everyone."""
        presentes = self._presentes()
        if self._anfitriao not in presentes:
            candidatos = presentes or list(self._jogadores)
            self._anfitriao = candidatos[0] if candidatos else None
        if self._fase in ("escolha", "desenho", "intervalo") and len(presentes) < 2:
            return self._encerrar(agora, tambem)
        em_lance = self._fase in ("escolha", "desenho")
        if (em_lance and self._desenhista not in presentes) or (
            self._fase == "desenho" and self._todos_acertaram()
        ):
            eventos = self._ir_ao_intervalo(agora, tambem)
        else:
            eventos = self._estados(agora, tambem)
        return eventos + self._checar_votos(agora)

    def _exigir_desenhista(self, jogador: _Jogador, fase: str) -> None:
        if self._fase != fase or jogador.id != self._desenhista:
            raise ErroSala(409, "not your turn")

    # --- conexão e relógio ---

    def conectou(self, jogador: int, agora: datetime) -> list[Evento]:
        pedido = self._pedidos.get(jogador)
        if pedido is not None:
            pedido.conexoes += 1
            return []
        j = self._jogadores.get(jogador)
        if j is None:
            return []
        j.conexoes += 1
        if j.presente or self.encerrada:
            return []
        j.presente = True
        return self._depois_de_mudar(agora)

    def desconectou(self, jogador: int, agora: datetime) -> list[Evento]:
        j = self._jogadores.get(jogador) or self._pedidos.get(jogador)
        if j is None:
            return []
        j.conexoes = max(j.conexoes - 1, 0)
        if j.conexoes == 0:
            j.desde = agora
        return []

    def avancar(self, agora: datetime) -> list[Evento]:
        eventos: list[Evento] = []
        if self.encerrada:
            return eventos
        ausentes = [
            j
            for j in self._jogadores.values()
            if j.presente and j.conexoes == 0 and agora - j.desde >= AUSENCIA
        ]
        for j in ausentes:
            j.presente = False
        if ausentes:
            eventos += self._depois_de_mudar(agora)
        caidos = [
            p for p in self._pedidos.values() if p.conexoes == 0 and agora - p.desde >= AUSENCIA
        ]
        for pedido in caidos:  # gave up waiting: the request falls with its token
            self._tirar_pedido(pedido)
        if caidos and not self.encerrada:
            eventos += self._estados(agora)
        while not self.encerrada and self._prazo is not None and agora >= self._prazo:
            if self._fase == "escolha":
                assert self._opcoes is not None
                eventos += self._comecar_desenho(self._rng.choice(self._opcoes), agora)
            elif self._fase == "desenho":
                eventos += self._ir_ao_intervalo(agora)
            elif self._fase == "intervalo":
                eventos += self._proximo_lance(agora)
        return eventos

    # --- fases ---

    def _proximo_lance(self, agora: datetime) -> list[Evento]:
        while True:
            while self._fila:
                candidato = self._fila.pop(0)
                if candidato in self._presentes():
                    return self._iniciar_lance(candidato, agora)
            if self._rodada >= self.rodadas:
                return self._encerrar(agora)
            self._rodada += 1
            self._fila = list(self._presentes())

    def _iniciar_lance(self, desenhista: int, agora: datetime) -> list[Evento]:
        self._fase = "escolha"
        self._desenhista = desenhista
        self._opcoes = self._banco.opcoes(self._rng, self._usadas)
        self._usadas.update(p.texto for p in self._opcoes)
        self._palavra = None
        self._dica = None
        self._dicas_dadas = 0
        self._acertaram = []
        self._lance_registrado = False
        self._tracos = {}
        self._total_pontos = 0
        self._prazo = agora + TEMPO_ESCOLHA
        for j in self._jogadores.values():
            j.acertou = False
        return self._estados(agora)

    def _comecar_desenho(self, palavra: Palavra, agora: datetime) -> list[Evento]:
        self._fase = "desenho"
        self._palavra = palavra
        self._dica = [None if c.isalpha() else c for c in palavra.texto]
        self._opcoes = None
        self._prazo = agora + TEMPO_DESENHO
        return self._estados(agora)

    def _ir_ao_intervalo(self, agora: datetime, tambem: tuple[int, ...] = ()) -> list[Evento]:
        self._registrar_lance()
        self._fase = "intervalo"
        self._opcoes = None
        self._prazo = agora + TEMPO_INTERVALO
        return self._estados(agora, tambem)

    def encerrar(self, agora: datetime) -> list[Evento]:
        """The hub's cleanup: a game in progress goes to `fim`; a room still waiting just closes."""
        if self._fase == "espera":
            self.encerrada = True
            return []
        return self._encerrar(agora)

    def _encerrar(self, agora: datetime, tambem: tuple[int, ...] = ()) -> list[Evento]:
        if self.encerrada:
            return []
        self._registrar_lance()
        self._fase = "fim"
        self._prazo = None
        self._opcoes = None
        self.encerrada = True
        return [
            *self._estados(agora, tambem),
            self._evento("fim", {"sumula": self.sumula()}),
        ]

    def _registrar_lance(self) -> None:
        if self._lance_registrado or self._palavra is None:
            return
        self._lance_registrado = True
        self._lances.append(
            {
                "desenhista": self._todos[self._desenhista or 0].apelido,
                "palavra": self._palavra.texto,
                "acertaram": [self._todos[j].apelido for j in self._acertaram],
            }
        )

    def sumula(self) -> dict:
        """Players by points (then joining order) and the plays in order; nobody sent off."""
        jogadores = sorted(
            (j for j in self._todos.values() if j.id not in self._expulsos),
            key=lambda j: -j.pontos,
        )
        return {
            "id": self.id,
            "jogadores": [
                {"apelido": j.apelido, "pontos": j.pontos, "gols": j.gols, "assist": j.assist}
                for j in jogadores
            ],
            "lances": [dict(lance, acertaram=list(lance["acertaram"])) for lance in self._lances],
        }

    # --- leitura ---

    def _presentes(self) -> list[int]:
        return [j.id for j in self._jogadores.values() if j.presente]

    def foto(self, jogador: int, agora: datetime) -> dict:
        pedido = self._pedidos.get(jogador)
        if pedido is not None:  # waiting: nothing of the room but who decides
            anfitriao = self._jogadores.get(self._anfitriao or 0)
            return {
                "seq": self._seq,
                "voce": jogador,
                "fase": "pedido",
                "agora": agora.isoformat(),
                "apelido": pedido.apelido,
                "anfitriao": anfitriao.apelido if anfitriao else None,
            }
        desenha = jogador == self._desenhista
        presentes = set(self._presentes())
        ve_palavra = self._fase in ("intervalo", "fim") or (desenha and self._fase == "desenho")
        return {
            "seq": self._seq,
            "voce": jogador,
            "fase": self._fase,
            "rodada": self._rodada,
            "rodadas": self.rodadas,
            "prazo": self._prazo.isoformat() if self._prazo else None,
            "agora": agora.isoformat(),
            "desenhista": self._desenhista,
            "jogadores": [
                {
                    "id": j.id,
                    "apelido": j.apelido,
                    "pontos": j.pontos,
                    "gols": j.gols,
                    "assist": j.assist,
                    "presente": j.presente,
                    "anfitriao": j.id == self._anfitriao,
                    "acertou": j.acertou,
                    # red cards that count against them, and how many send them off
                    "cartoes": len(self._votos.get(j.id, set()) & (presentes - {j.id})),
                    "cartoes_para_sair": len(presentes - {j.id}) // 2 + 1,
                }
                for j in self._jogadores.values()
            ],
            "dica": list(self._dica) if self._dica is not None else None,
            # only whoever draws: hints given and when each one unlocks
            "dicas": (
                {
                    "dadas": self._dicas_dadas,
                    "marcos": [m.isoformat() for m in self._marcos_dica()],
                }
                if desenha and self._fase == "desenho"
                else None
            ),
            # only the host: who asked to join
            "pedidos": (
                [{"id": p.id, "apelido": p.apelido} for p in self._pedidos.values()]
                if jogador == self._anfitriao
                else None
            ),
            "opcoes": (
                [{"texto": p.texto, "dificuldade": p.dificuldade} for p in self._opcoes]
                if desenha and self._fase == "escolha" and self._opcoes
                else None
            ),
            "palavra": self._palavra.texto if ve_palavra and self._palavra else None,
            "tracos": [{**t, "pts": [list(p) for p in t["pts"]]} for t in self._tracos.values()],
        }

    def _estados(self, agora: datetime, tambem: tuple[int, ...] = ()) -> list[Evento]:
        """One `estado` per player and request waiting (each sees their own view), one seq.

        `tambem` adds who just left or was sent off: their view no longer lists them.
        """
        self._seq += 1
        quem = (*self._jogadores, *self._pedidos, *tambem)
        return [Evento("estado", self.foto(j, agora), para=j) for j in quem]

    def _evento(self, tipo: str, dados: dict, **destino) -> Evento:
        self._seq += 1
        return Evento(tipo, {**dados, "seq": self._seq}, **destino)
